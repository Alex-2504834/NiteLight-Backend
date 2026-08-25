import secrets
from typing import Any

from fastapi import Depends, Header, HTTPException, status as httpStatus
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.constants import adminActorName, adminApiKeyHeaderName
from app.core.firebase import firebaseAuth


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


def requireAdmin(
    adminApiKey: str | None = Header(default=None, alias=adminApiKeyHeaderName),
) -> dict[str, str]:
    configuredAdminApiKey = settings.adminApiKey

    if not configuredAdminApiKey:
        raise HTTPException(
            status_code=httpStatus.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API key is not configured",
        )

    if not adminApiKey or not secrets.compare_digest(adminApiKey, configuredAdminApiKey):
        raise HTTPException(
            status_code=httpStatus.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin API key",
        )

    return {"uid": adminActorName}
