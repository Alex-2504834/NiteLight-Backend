import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException, Response, status as httpStatus
from google.cloud import firestore as googleFirestore

from app.core.config import settings
from app.core.constants import (googlePhotoMaxHeightPx, googlePhotoMaxWidthPx, googlePlacesBaseUrl, googlePlacesRequestTimeoutSeconds, placesCollectionName)
from app.core.firebase import firestoreDb
from app.core.placeValidation import PlaceValidationError, validatePlace
from app.core.security import requireAdmin


router = APIRouter(prefix="/places", tags=["places"])
googlePlaceDetailsFieldMask = ",".join(
    [
        "id",
        "displayName",
        "formattedAddress",
        "nationalPhoneNumber",
        "internationalPhoneNumber",
        "websiteUri",
        "googleMapsUri",
        "rating",
        "userRatingCount",
        "businessStatus",
        "currentOpeningHours",
        "photos",
    ]
)
editablePlaceFields = {
    "name",
    "type",
    "description",
    "needsReferral",
    "supplies",
    "placeId",
    "address",
    "coord",
    "openingHours",
}
auditPlaceFields = {"createdAt", "createdBy", "updatedAt", "updatedBy"}
jsonAcceptHeader = {"Accept": "application/json"}
noStoreCacheValue = "no-store"


def getServerTimestamp():
    return googleFirestore.SERVER_TIMESTAMP


def getGoogleErrorMessage(responseBody: Any, fallbackStatusCode: int) -> str:
    if isinstance(responseBody, dict):
        errorData = responseBody.get("error")

        if isinstance(errorData, dict) and isinstance(errorData.get("message"), str):
            return errorData["message"]

    return f"Google Places request failed with status {fallbackStatusCode}"


def normalizePhotoAttributions(photo: dict[str, Any]) -> list[str]:
    authorAttributions = photo.get("authorAttributions")

    if not isinstance(authorAttributions, list):
        return []

    attributionLabels: list[str] = []

    for attribution in authorAttributions:
        if not isinstance(attribution, dict):
            continue

        displayName = attribution.get("displayName")

        if isinstance(displayName, str) and displayName.strip():
            attributionLabels.append(displayName.strip())

    return attributionLabels


def fetchGooglePlacePhotoUri(photoName: str | None):
    if not photoName or not settings.googlePlacesApiKey:
        return None

    encodedPhotoName = quote(photoName, safe="/")
    queryString = urlencode(
        {
            "key": settings.googlePlacesApiKey,
            "maxWidthPx": googlePhotoMaxWidthPx,
            "maxHeightPx": googlePhotoMaxHeightPx,
            "skipHttpRedirect": "true",
        }
    )
    request = Request(
        f"{googlePlacesBaseUrl}/{encodedPhotoName}/media?{queryString}",
        headers=jsonAcceptHeader,
        method="GET",
    )

    try:
        with urlopen(request, timeout=googlePlacesRequestTimeoutSeconds) as response:
            responseBody = response.read().decode("utf-8")
            responseData = json.loads(responseBody) if responseBody else {}
            photoUri = responseData.get("photoUri")
            return photoUri if isinstance(photoUri, str) else None
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None


def normalizeGooglePlaceDetails(
    googlePlaceId: str,
    responseData: dict[str, Any],
):
    currentOpeningHours = responseData.get("currentOpeningHours")
    displayName = responseData.get("displayName")
    photos = responseData.get("photos")
    primaryPhoto = photos[0] if isinstance(photos, list) and photos else None
    primaryPhotoName = (
        primaryPhoto.get("name") if isinstance(primaryPhoto, dict) else None
    )

    return {
        "id": responseData.get("id") or googlePlaceId,
        "name": displayName.get("text") if isinstance(displayName, dict) else None,
        "formattedAddress": responseData.get("formattedAddress"),
        "phoneNumber": responseData.get("nationalPhoneNumber")
        or responseData.get("internationalPhoneNumber"),
        "websiteUri": responseData.get("websiteUri"),
        "googleMapsUri": responseData.get("googleMapsUri"),
        "rating": responseData.get("rating"),
        "userRatingCount": responseData.get("userRatingCount"),
        "businessStatus": responseData.get("businessStatus"),
        "openNow": (
            currentOpeningHours.get("openNow")
            if isinstance(currentOpeningHours, dict)
            else None
        ),
        "nextOpenTime": (
            currentOpeningHours.get("nextOpenTime")
            if isinstance(currentOpeningHours, dict)
            else None
        ),
        "nextCloseTime": (
            currentOpeningHours.get("nextCloseTime")
            if isinstance(currentOpeningHours, dict)
            else None
        ),
        "weekdayDescriptions": (
            currentOpeningHours.get("weekdayDescriptions")
            if isinstance(currentOpeningHours, dict)
            else None
        ),
        "photoUri": fetchGooglePlacePhotoUri(primaryPhotoName),
        "photoAttributions": (
            normalizePhotoAttributions(primaryPhoto)
            if isinstance(primaryPhoto, dict)
            else []
        ),
    }


def fetchGooglePlaceDetails(googlePlaceId: str):
    if not settings.googlePlacesApiKey:
        raise HTTPException(
            status_code=httpStatus.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Places API key is not configured on the backend.",
        )

    encodedGooglePlaceId = quote(googlePlaceId, safe="")
    request = Request(
        f"{googlePlacesBaseUrl}/places/{encodedGooglePlaceId}",
        headers={
            "Accept": "application/json",
            "X-Goog-Api-Key": settings.googlePlacesApiKey,
            "X-Goog-FieldMask": googlePlaceDetailsFieldMask,
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=googlePlacesRequestTimeoutSeconds) as response:
            responseBody = response.read().decode("utf-8")
            responseData = json.loads(responseBody) if responseBody else {}
            return normalizeGooglePlaceDetails(googlePlaceId, responseData)
    except HTTPError as error:
        responseBody = error.read().decode("utf-8")

        try:
            responseData = json.loads(responseBody) if responseBody else {}
        except json.JSONDecodeError:
            responseData = {}

        raise HTTPException(
            status_code=error.code,
            detail=getGoogleErrorMessage(responseData, error.code),
        ) from error
    except URLError as error:
        raise HTTPException(
            status_code=httpStatus.HTTP_502_BAD_GATEWAY,
            detail="Could not reach Google Places.",
        ) from error
    except TimeoutError as error:
        raise HTTPException(
            status_code=httpStatus.HTTP_504_GATEWAY_TIMEOUT,
            detail="Google Places request timed out.",
        ) from error
    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=httpStatus.HTTP_502_BAD_GATEWAY,
            detail="Google Places returned an invalid response.",
        ) from error


def buildPlaceDocument(placeData: dict[str, Any], documentId: str) -> dict[str, Any]:
    unknownFields = set(placeData) - editablePlaceFields - auditPlaceFields
    if unknownFields:
        raise PlaceValidationError(f"Place {documentId} has unknown fields: {', '.join(sorted(unknownFields))}")

    editableData = {fieldName: fieldValue for fieldName, fieldValue in placeData.items() if fieldName in editablePlaceFields}
    validatedPlace = validatePlace(editableData, allowId=False)
    return {"id": documentId, **validatedPlace}


@router.get("")
def listPlaces():
    placeSnapshots = firestoreDb.collection(placesCollectionName).stream()
    places: list[dict[str, Any]] = []

    for placeSnapshot in placeSnapshots:
        placeData = buildPlaceDocument(placeSnapshot.to_dict() or {}, placeSnapshot.id)
        places.append(placeData)

    return {"places": places}


@router.get("/google-details/{googlePlaceId}")
def getGooglePlaceDetails(googlePlaceId: str, response: Response):
    response.headers["Cache-Control"] = noStoreCacheValue
    return fetchGooglePlaceDetails(googlePlaceId)


@router.get("/{placeId}")
def getPlace(placeId: str):
    placeSnapshot = firestoreDb.collection(placesCollectionName).document(placeId).get()

    if not placeSnapshot.exists:
        raise HTTPException(
            status_code=httpStatus.HTTP_404_NOT_FOUND,
            detail="Place not found",
        )

    return buildPlaceDocument(placeSnapshot.to_dict() or {}, placeSnapshot.id)


@router.post("")
def createOrUpdatePlace(place: dict[str, Any], user=Depends(requireAdmin)):
    try:
        placePayload = validatePlace(place)
    except PlaceValidationError as error:
        raise HTTPException(
            status_code=httpStatus.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

    placeId = placePayload.pop("id", None)
    placesCollection = firestoreDb.collection(placesCollectionName)
    placeRef = placesCollection.document(placeId) if placeId else placesCollection.document()
    existingSnapshot = placeRef.get()
    serverTimestamp = getServerTimestamp()
    placeData = {
        **placePayload,
        "updatedAt": serverTimestamp,
        "updatedBy": user["uid"],
    }

    if existingSnapshot.exists:
        existingData = existingSnapshot.to_dict() or {}
        if "createdAt" in existingData:
            placeData["createdAt"] = existingData["createdAt"]
        if "createdBy" in existingData:
            placeData["createdBy"] = existingData["createdBy"]
    else:
        placeData["createdAt"] = serverTimestamp
        placeData["createdBy"] = user["uid"]

    placeRef.set(placeData)
    savedSnapshot = placeRef.get()
    return buildPlaceDocument(savedSnapshot.to_dict() or {}, savedSnapshot.id)


@router.patch("/{placeId}")
def updatePlace(
    placeId: str,
    updates: dict[str, Any],
    user=Depends(requireAdmin),
):
    if "id" in updates:
        raise HTTPException(
            status_code=httpStatus.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="id cannot be changed",
        )

    placeRef = firestoreDb.collection(placesCollectionName).document(placeId)
    existingSnapshot = placeRef.get()

    if not existingSnapshot.exists:
        raise HTTPException(
            status_code=httpStatus.HTTP_404_NOT_FOUND,
            detail="Place not found",
        )

    currentPlace = buildPlaceDocument(
        existingSnapshot.to_dict() or {},
        placeId,
    )
    currentPlace.pop("id")

    try:
        placePayload = validatePlace({**currentPlace, **updates}, allowId=False)
    except PlaceValidationError as error:
        raise HTTPException(
            status_code=httpStatus.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

    existingData = existingSnapshot.to_dict() or {}
    placePayload["updatedBy"] = user["uid"]
    placePayload["updatedAt"] = getServerTimestamp()

    if "createdAt" in existingData:
        placePayload["createdAt"] = existingData["createdAt"]
    if "createdBy" in existingData:
        placePayload["createdBy"] = existingData["createdBy"]

    placeRef.set(placePayload)
    updatedSnapshot = placeRef.get()
    return buildPlaceDocument(updatedSnapshot.to_dict() or {}, updatedSnapshot.id)


@router.delete("/{placeId}")
def deletePlace(placeId: str, user=Depends(requireAdmin)):
    placeRef = firestoreDb.collection(placesCollectionName).document(placeId)
    placeSnapshot = placeRef.get()

    if not placeSnapshot.exists:
        raise HTTPException(
            status_code=httpStatus.HTTP_404_NOT_FOUND,
            detail="Place not found",
        )

    placeRef.delete()

    return {"deleted": True, "id": placeId}
