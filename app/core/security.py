from typing import Any

from fastapi import Depends, HTTPException, status as httpStatus
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.constants import usersCollectionName
from app.core.firebase import firebaseAuth, firestoreDb


bearerScheme = HTTPBearer(auto_error=False)


def requireUser(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearerScheme),
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(
            status_code=httpStatus.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
        )

    try:
        decodedToken = firebaseAuth.verify_id_token(credentials.credentials)
    except Exception as error:
        raise HTTPException(
            status_code=httpStatus.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization token",
        ) from error

    return {
        "uid": decodedToken.get("uid"),
        "email": decodedToken.get("email"),
        "emailVerified": decodedToken.get("email_verified"),
        "phoneNumber": decodedToken.get("phone_number"),
        "name": decodedToken.get("name"),
        "authTime": decodedToken.get("auth_time"),
        "firebase": decodedToken.get("firebase", {}),
    }


def requireAdmin(user: dict[str, Any] = Depends(requireUser)) -> dict[str, Any]:
    uid = user.get("uid")
    if not uid:
        raise HTTPException(
            status_code=httpStatus.HTTP_401_UNAUTHORIZED,
            detail="Invalid user",
        )

    profileSnapshot = firestoreDb.collection(usersCollectionName).document(uid).get()
    if not profileSnapshot.exists:
        raise HTTPException(
            status_code=httpStatus.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    profileData = profileSnapshot.to_dict() or {}
    if profileData.get("isAdmin") is not True:
        raise HTTPException(
            status_code=httpStatus.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return {**user, "profile": profileData}
