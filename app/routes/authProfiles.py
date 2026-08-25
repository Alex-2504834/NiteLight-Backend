import re
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status as httpStatus
from google.cloud import firestore as googleFirestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.constants import (
    accountDeletionMaxAuthAgeSeconds,
    minimumDisplayNameLength,
    singleUserLookupLimit,
    userLookupLimit,
    usersCollectionName,
)
from app.core.firebase import firebaseAuth, firestoreDb
from app.core.security import requireUser


router = APIRouter(prefix="/auth", tags=["auth"])
usernameEmailDomain = "users.nitelight.local"
usernamePattern = re.compile(r"^[a-z0-9_.-]{3,32}$")
emailPattern = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
phonePattern = re.compile(r"^\+[0-9]{7,15}$")
emailPasswordProvider = "email-password"
phonePasswordProvider = "phone-password"
googleProvider = "google"
authProviders = {emailPasswordProvider, phonePasswordProvider}


def normaliseUsername(username: str) -> str:
    return username.strip().lower()


def normaliseEmail(email: str | None) -> str | None:
    normalisedEmail = (email or "").strip().lower()
    return normalisedEmail or None


def normalisePhone(phoneNumber: str | None) -> str | None:
    normalisedPhone = re.sub(r"[\s()\-]", "", phoneNumber or "").strip()
    return normalisedPhone or None


def getUsernameAuthEmail(username: str) -> str:
    return f"{username}@{usernameEmailDomain}"


def getUserRef(uid: str):
    return firestoreDb.collection(usersCollectionName).document(uid)


def getServerTimestamp():
    return googleFirestore.SERVER_TIMESTAMP


def findUsersBy(
    fieldName: str,
    fieldValue: str,
    resultLimit: int = userLookupLimit,
) -> list[dict[str, Any]]:
    userSnapshots = (
        firestoreDb.collection(usersCollectionName)
        .where(filter=FieldFilter(fieldName, "==", fieldValue))
        .limit(resultLimit)
        .stream()
    )
    users: list[dict[str, Any]] = []

    for userSnapshot in userSnapshots:
        userData = userSnapshot.to_dict() or {}
        userData["uid"] = userSnapshot.id
        users.append(userData)

    return users


def ensureFieldAvailable(
    fieldName: str,
    fieldValue: str | None,
    uid: str,
    unavailableMessage: str,
):
    if fieldValue is None:
        return

    if any(
        matchingUser["uid"] != uid
        for matchingUser in findUsersBy(fieldName, fieldValue)
    ):
        raise HTTPException(
            status_code=httpStatus.HTTP_409_CONFLICT,
            detail=unavailableMessage,
        )


def requireProfile(uid: str) -> dict[str, Any]:
    profileSnapshot = getUserRef(uid).get()
    if not profileSnapshot.exists:
        raise HTTPException(
            status_code=httpStatus.HTTP_404_NOT_FOUND,
            detail="Account profile not found",
        )

    return {"uid": uid, **(profileSnapshot.to_dict() or {})}


def getPasswordAuthEmail(profile: dict[str, Any]) -> str:
    authProvider = profile.get("authProvider")

    if authProvider == emailPasswordProvider:
        email = profile.get("email")
        if isinstance(email, str) and email:
            return email
        raise HTTPException(
            status_code=httpStatus.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account profile is missing email",
        )

    if authProvider == phonePasswordProvider:
        username = profile.get("username")
        if isinstance(username, str) and username:
            return getUsernameAuthEmail(username)
        raise HTTPException(
            status_code=httpStatus.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account profile is missing username",
        )

    raise HTTPException(
        status_code=httpStatus.HTTP_400_BAD_REQUEST,
        detail="Use the account's original sign-in method",
    )


@router.post("/resolve-login")
def resolveLogin(payload: dict[str, Any]):
    identifier = str(payload.get("identifier", "")).strip()
    if not identifier:
        raise HTTPException(
            status_code=httpStatus.HTTP_400_BAD_REQUEST,
            detail="Missing login identifier",
        )

    if "@" in identifier:
        return {"authEmail": identifier.lower()}

    phoneNumber = normalisePhone(identifier)
    if phoneNumber and phonePattern.fullmatch(phoneNumber):
        matchingUsers = findUsersBy(
            "phoneNumber",
            phoneNumber,
            resultLimit=singleUserLookupLimit,
        )
        if not matchingUsers:
            raise HTTPException(
                status_code=httpStatus.HTTP_404_NOT_FOUND,
                detail="No account was found for that phone number",
            )
        return {"authEmail": getPasswordAuthEmail(matchingUsers[0])}

    username = normaliseUsername(identifier)
    matchingUsers = findUsersBy(
        "username",
        username,
        resultLimit=singleUserLookupLimit,
    )
    if not matchingUsers:
        raise HTTPException(
            status_code=httpStatus.HTTP_404_NOT_FOUND,
            detail="No account was found for that username",
        )

    return {"authEmail": getPasswordAuthEmail(matchingUsers[0])}


@router.get("/profile")
def getProfile(user=Depends(requireUser)):
    uid = user.get("uid")
    if not uid:
        raise HTTPException(
            status_code=httpStatus.HTTP_401_UNAUTHORIZED,
            detail="Invalid user",
        )

    profile = requireProfile(uid)
    profile["emailVerified"] = bool(user.get("emailVerified"))
    profile["phoneVerified"] = bool(user.get("phoneNumber"))
    return profile


@router.delete("/account")
def deleteAccount(user=Depends(requireUser)):
    uid = user.get("uid")
    authTime = user.get("authTime")

    if not uid:
        raise HTTPException(
            status_code=httpStatus.HTTP_401_UNAUTHORIZED,
            detail="Invalid user",
        )

    authAgeSeconds = (
        time.time() - authTime if isinstance(authTime, (int, float)) else None
    )
    if authAgeSeconds is None or authAgeSeconds > accountDeletionMaxAuthAgeSeconds:
        raise HTTPException(
            status_code=httpStatus.HTTP_401_UNAUTHORIZED,
            detail="For security, sign out and sign back in before deleting your account.",
        )

    firebaseAuth.delete_user(uid)
    getUserRef(uid).delete()
    return {"deleted": True, "uid": uid}


@router.post("/password-profile")
def syncPasswordProfile(payload: dict[str, Any], user=Depends(requireUser)):
    uid = user.get("uid")
    username = normaliseUsername(str(payload.get("username", "")))
    displayName = str(payload.get("displayName", "")).strip()
    email = normaliseEmail(payload.get("email"))
    phoneNumber = normalisePhone(payload.get("phoneNumber"))
    authProvider = str(payload.get("authProvider", "")).strip()
    tokenEmail = normaliseEmail(user.get("email"))

    if not uid:
        raise HTTPException(
            status_code=httpStatus.HTTP_401_UNAUTHORIZED,
            detail="Invalid user",
        )
    if not usernamePattern.fullmatch(username):
        raise HTTPException(
            status_code=httpStatus.HTTP_400_BAD_REQUEST,
            detail="Invalid username",
        )
    if len(displayName) < minimumDisplayNameLength:
        raise HTTPException(
            status_code=httpStatus.HTTP_400_BAD_REQUEST,
            detail="Invalid display name",
        )
    if authProvider not in authProviders:
        raise HTTPException(
            status_code=httpStatus.HTTP_400_BAD_REQUEST,
            detail="Invalid auth provider",
        )
    if email is not None and not emailPattern.fullmatch(email):
        raise HTTPException(
            status_code=httpStatus.HTTP_400_BAD_REQUEST,
            detail="Invalid email address",
        )
    if phoneNumber is not None and not phonePattern.fullmatch(phoneNumber):
        raise HTTPException(
            status_code=httpStatus.HTTP_400_BAD_REQUEST,
            detail="Invalid phone number",
        )

    if authProvider == emailPasswordProvider:
        if email is None or tokenEmail != email:
            raise HTTPException(
                status_code=httpStatus.HTTP_400_BAD_REQUEST,
                detail="Email does not match Firebase account",
            )
    else:
        expectedEmail = getUsernameAuthEmail(username)
        if phoneNumber is None or tokenEmail != expectedEmail:
            raise HTTPException(
                status_code=httpStatus.HTTP_400_BAD_REQUEST,
                detail="Account details do not match Firebase account",
            )

    ensureFieldAvailable("username", username, uid, "That username is already taken")
    ensureFieldAvailable("email", email, uid, "That email address is already in use")
    ensureFieldAvailable(
        "phoneNumber",
        phoneNumber,
        uid,
        "That phone number is already in use",
    )

    userRef = getUserRef(uid)
    existingProfile = userRef.get()
    serverTimestamp = getServerTimestamp()
    profileData = {
        "username": username,
        "displayName": displayName,
        "email": email,
        "phoneNumber": phoneNumber,
        "authProvider": authProvider,
        "updatedAt": serverTimestamp,
    }

    if not existingProfile.exists:
        profileData["createdAt"] = serverTimestamp

    userRef.set(profileData, merge=True)
    return {"ok": True, "uid": uid}


@router.post("/google-profile")
def syncGoogleProfile(user=Depends(requireUser)):
    uid = user.get("uid")
    email = normaliseEmail(user.get("email"))

    if not uid:
        raise HTTPException(
            status_code=httpStatus.HTTP_401_UNAUTHORIZED,
            detail="Invalid user",
        )
    if email is None:
        raise HTTPException(
            status_code=httpStatus.HTTP_400_BAD_REQUEST,
            detail="Google account has no email address",
        )

    userRef = getUserRef(uid)
    existingProfile = userRef.get()
    serverTimestamp = getServerTimestamp()
    profileData = {
        "displayName": user.get("name"),
        "email": email,
        "phoneNumber": normalisePhone(user.get("phoneNumber")),
        "authProvider": googleProvider,
        "updatedAt": serverTimestamp,
    }

    if not existingProfile.exists:
        profileData["createdAt"] = serverTimestamp

    userRef.set(profileData, merge=True)
    return {"ok": True, "uid": uid}
