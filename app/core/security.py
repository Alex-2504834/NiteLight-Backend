from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.firebase import firebase_auth


bearer_scheme = HTTPBearer(auto_error=False)


def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
        )

    try:
        decoded_token = firebase_auth.verify_id_token(credentials.credentials)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization token",
        )

    return {
        "uid": decoded_token.get("uid"),
        "email": decoded_token.get("email"),
        "email_verified": decoded_token.get("email_verified"),
        "phone_number": decoded_token.get("phone_number"),
        "name": decoded_token.get("name"),
        "firebase": decoded_token.get("firebase", {}),
    }
