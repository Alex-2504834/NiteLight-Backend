from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.firebase import firebase_auth

bearer_scheme = HTTPBearer(auto_error=False)


async def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
        )

    try:
        decoded_token = firebase_auth.verify_id_token(credentials.credentials)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization token",
        ) from exc

    return {
        "uid": decoded_token.get("uid"),
        "email": decoded_token.get("email"),
        "phone_number": decoded_token.get("phone_number"),
        "name": decoded_token.get("name"),
        "claims": decoded_token,
    }


async def require_admin(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:

    uid = user.get("uid")
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user")

    user_record = firebase_auth.get_user(uid)
    custom_claims = user_record.custom_claims or {}

    if not custom_claims.get("admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    return user
