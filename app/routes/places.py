from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
import json

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.core.config import settings
from app.core.firebase import firestore_db
from app.core.security import require_user

router = APIRouter(prefix="/places", tags=["places"])

GOOGLE_PLACE_DETAILS_FIELD_MASK = ",".join(
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


def server_timestamp():
    from google.cloud import firestore as google_firestore

    return google_firestore.SERVER_TIMESTAMP


def get_google_error_message(body: Any, fallback_status_code: int) -> str:
    if isinstance(body, dict):
        error = body.get("error")

        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"]

    return f"Google Places request failed with status {fallback_status_code}"


def normalize_photo_attributions(photo: dict[str, Any]) -> list[str]:
    author_attributions = photo.get("authorAttributions")

    if not isinstance(author_attributions, list):
        return []

    labels: list[str] = []

    for attribution in author_attributions:
        if not isinstance(attribution, dict):
            continue

        display_name = attribution.get("displayName")

        if isinstance(display_name, str) and display_name.strip():
            labels.append(display_name.strip())

    return labels


def fetch_google_place_photo_uri(photo_name: str | None):
    if not photo_name or not settings.google_places_api_key:
        return None

    encoded_photo_name = quote(photo_name, safe="/")
    query = urlencode(
        {
            "key": settings.google_places_api_key,
            "maxWidthPx": 900,
            "maxHeightPx": 420,
            "skipHttpRedirect": "true",
        }
    )
    request = Request(
        f"https://places.googleapis.com/v1/{encoded_photo_name}/media?{query}",
        headers={"Accept": "application/json"},
        method="GET",
    )

    try:
        with urlopen(request, timeout=8) as response:
            response_body = response.read().decode("utf-8")
            data = json.loads(response_body) if response_body else {}
            return data.get("photoUri") if isinstance(data.get("photoUri"), str) else None
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None


def normalize_google_place_details(google_place_id: str, data: dict[str, Any]):
    current_opening_hours = data.get("currentOpeningHours")
    display_name = data.get("displayName")
    photos = data.get("photos")
    primary_photo = photos[0] if isinstance(photos, list) and photos else None
    primary_photo_name = (
        primary_photo.get("name") if isinstance(primary_photo, dict) else None
    )

    return {
        "id": data.get("id") or google_place_id,
        "name": display_name.get("text") if isinstance(display_name, dict) else None,
        "formattedAddress": data.get("formattedAddress"),
        "phoneNumber": data.get("nationalPhoneNumber") or data.get("internationalPhoneNumber"),
        "websiteUri": data.get("websiteUri"),
        "googleMapsUri": data.get("googleMapsUri"),
        "rating": data.get("rating"),
        "userRatingCount": data.get("userRatingCount"),
        "businessStatus": data.get("businessStatus"),
        "openNow": (
            current_opening_hours.get("openNow")
            if isinstance(current_opening_hours, dict)
            else None
        ),
        "nextOpenTime": (
            current_opening_hours.get("nextOpenTime")
            if isinstance(current_opening_hours, dict)
            else None
        ),
        "nextCloseTime": (
            current_opening_hours.get("nextCloseTime")
            if isinstance(current_opening_hours, dict)
            else None
        ),
        "weekdayDescriptions": (
            current_opening_hours.get("weekdayDescriptions")
            if isinstance(current_opening_hours, dict)
            else None
        ),
        "photoUri": fetch_google_place_photo_uri(primary_photo_name),
        "photoAttributions": (
            normalize_photo_attributions(primary_photo)
            if isinstance(primary_photo, dict)
            else []
        ),
    }


def fetch_google_place_details(google_place_id: str):
    if not settings.google_places_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Places API key is not configured on the backend.",
        )

    encoded_google_place_id = quote(google_place_id, safe="")
    request = Request(
        f"https://places.googleapis.com/v1/places/{encoded_google_place_id}",
        headers={
            "Accept": "application/json",
            "X-Goog-Api-Key": settings.google_places_api_key,
            "X-Goog-FieldMask": GOOGLE_PLACE_DETAILS_FIELD_MASK,
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=8) as response:
            response_body = response.read().decode("utf-8")
            data = json.loads(response_body) if response_body else {}
            return normalize_google_place_details(google_place_id, data)
    except HTTPError as error:
        response_body = error.read().decode("utf-8")

        try:
            data = json.loads(response_body) if response_body else {}
        except json.JSONDecodeError:
            data = {}

        raise HTTPException(
            status_code=error.code,
            detail=get_google_error_message(data, error.code),
        ) from error
    except URLError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach Google Places.",
        ) from error
    except TimeoutError as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Google Places request timed out.",
        ) from error
    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Google Places returned an invalid response.",
        ) from error


@router.get("")
def list_places():
    docs = firestore_db.collection("places").stream()

    places: list[dict[str, Any]] = []

    for doc in docs:
        data = doc.to_dict() or {}
        data["id"] = doc.id
        places.append(data)

    return {"places": places}


@router.get("/google-details/{google_place_id}")
def get_google_place_details(google_place_id: str, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return fetch_google_place_details(google_place_id)


@router.get("/{place_id}")
def get_place(place_id: str):
    doc = firestore_db.collection("places").document(place_id).get()

    if not doc.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Place not found")

    data = doc.to_dict() or {}
    data["id"] = doc.id

    return data


@router.post("")
def create_or_update_place(place: dict[str, Any], user=Depends(require_user)):
    place_id = place.get("id")

    if place_id:
        doc_ref = firestore_db.collection("places").document(str(place_id))
    else:
        doc_ref = firestore_db.collection("places").document()

    data = {**place}
    data.pop("id", None)
    data["updatedAt"] = server_timestamp()
    data["updatedBy"] = user["uid"]

    if not doc_ref.get().exists:
        data["createdAt"] = server_timestamp()
        data["createdBy"] = user["uid"]

    doc_ref.set(data, merge=True)

    saved_doc = doc_ref.get()
    saved_data = saved_doc.to_dict() or {}
    saved_data["id"] = saved_doc.id

    return saved_data


@router.patch("/{place_id}")
def update_place(place_id: str, updates: dict[str, Any], user=Depends(require_user)):
    doc_ref = firestore_db.collection("places").document(place_id)
    doc = doc_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Place not found")

    updates = {**updates, "updatedBy": user["uid"], "updatedAt": server_timestamp()}
    doc_ref.update(updates)

    updated_doc = doc_ref.get()
    data = updated_doc.to_dict() or {}
    data["id"] = updated_doc.id

    return data


@router.delete("/{place_id}")
def delete_place(place_id: str, user=Depends(require_user)):
    doc_ref = firestore_db.collection("places").document(place_id)
    doc = doc_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Place not found")

    doc_ref.delete()

    return {"deleted": True, "id": place_id}
