from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from google.cloud.firestore_v1 import transactional

from app.core.firebase import firestore_db
from app.core.security import require_user

router = APIRouter(prefix="/auth", tags=["auth"])

USERNAME_EMAIL_DOMAIN = "users.nitelight.local"


def normalise_username(username: str) -> str:
    return username.strip().lower()


def normalise_email(email: str | None) -> str | None:
    value = (email or "").strip().lower()
    return value if value else None


def normalise_phone(phone_number: str | None) -> str | None:
    value = (phone_number or "").replace(" ", "").replace("(", "").replace(")", "").replace("-", "").strip()
    return value if value else None


def username_to_auth_email(username: str) -> str:
    return f"{normalise_username(username)}@{USERNAME_EMAIL_DOMAIN}"


def username_ref(username: str):
    return firestore_db.collection("usernames").document(username)


def email_ref(email: str):
    return firestore_db.collection("emails").document(email)


def phone_ref(phone_number: str):
    return firestore_db.collection("phones").document(phone_number)


def user_ref(uid: str):
    return firestore_db.collection("users").document(uid)


def server_timestamp():
    from google.cloud import firestore as google_firestore

    return google_firestore.SERVER_TIMESTAMP


@router.post("/resolve-login")
def resolve_login(payload: dict[str, Any]):
    identifier = str(payload.get("identifier", "")).strip()

    if not identifier:
        raise HTTPException(status_code=400, detail="Missing login identifier")

    lower_identifier = identifier.lower()

    if "@" in identifier and "." in identifier:
        doc = email_ref(lower_identifier).get()
        data = doc.to_dict() or {}
        return {"authEmail": data.get("authEmail") or lower_identifier}

    phone_candidate = normalise_phone(identifier)
    if phone_candidate and phone_candidate.replace("+", "").isdigit() and len(phone_candidate) >= 7:
        doc = phone_ref(phone_candidate).get()
        data = doc.to_dict() or {}

        if not doc.exists or not data.get("authEmail"):
            raise HTTPException(status_code=404, detail="No account was found for that phone number")

        return {"authEmail": data["authEmail"]}

    username = normalise_username(identifier)
    doc = username_ref(username).get()
    data = doc.to_dict() or {}

    if doc.exists and data.get("authEmail"):
        return {"authEmail": data["authEmail"]}

    return {"authEmail": username_to_auth_email(username)}


@router.post("/password-profile")
def sync_password_profile(payload: dict[str, Any], user=Depends(require_user)):
    uid = user["uid"]
    username = normalise_username(str(payload.get("username", "")))
    display_name = str(payload.get("displayName", "")).strip()
    email = normalise_email(payload.get("email"))
    phone_number = normalise_phone(payload.get("phoneNumber"))
    auth_email = str(payload.get("authEmail", "")).strip().lower()
    auth_provider = str(payload.get("authProvider", "email-password"))

    if not uid:
        raise HTTPException(status_code=401, detail="Invalid user")

    if not username or len(username) < 3:
        raise HTTPException(status_code=400, detail="Invalid username")

    if not display_name or len(display_name) < 2:
        raise HTTPException(status_code=400, detail="Invalid display name")

    if not auth_email:
        raise HTTPException(status_code=400, detail="Missing auth email")

    transaction = firestore_db.transaction()

    @transactional
    def reserve_and_write(transaction):
        username_doc = username_ref(username).get(transaction=transaction)
        username_data = username_doc.to_dict() or {}

        if username_doc.exists and username_data.get("uid") != uid:
            raise HTTPException(status_code=409, detail="That username is already taken")

        if email:
            email_doc = email_ref(email).get(transaction=transaction)
            email_data = email_doc.to_dict() or {}

            if email_doc.exists and email_data.get("uid") != uid:
                raise HTTPException(status_code=409, detail="That email address is already in use")

        if phone_number:
            phone_doc = phone_ref(phone_number).get(transaction=transaction)
            phone_data = phone_doc.to_dict() or {}

            if phone_doc.exists and phone_data.get("uid") != uid:
                raise HTTPException(status_code=409, detail="That phone number is already in use")

        now = server_timestamp()

        transaction.set(username_ref(username), {"uid": uid, "authEmail": auth_email, "updatedAt": now}, merge=True)

        if email:
            transaction.set(email_ref(email), {"uid": uid, "authEmail": auth_email, "updatedAt": now}, merge=True)

        if phone_number:
            transaction.set(phone_ref(phone_number), {"uid": uid, "authEmail": auth_email, "updatedAt": now}, merge=True)

        transaction.set(
            user_ref(uid),
            {
                "username": username,
                "displayName": display_name,
                "email": email,
                "phoneNumber": phone_number,
                "authEmail": auth_email,
                "emailVerified": bool(user.get("email_verified")),
                "phoneVerified": bool(user.get("phone_number")),
                "authProvider": auth_provider,
                "mfaEnabled": False,
                "isGuest": False,
                "updatedAt": now,
                "createdAt": now,
            },
            merge=True,
        )

    reserve_and_write(transaction)

    return {"ok": True, "uid": uid}


@router.post("/google-profile")
def sync_google_profile(user=Depends(require_user)):
    uid = user["uid"]
    email = normalise_email(user.get("email"))
    now = server_timestamp()

    user_ref(uid).set(
        {
            "displayName": user.get("name"),
            "email": email,
            "phoneNumber": user.get("phone_number"),
            "emailVerified": bool(user.get("email_verified")),
            "phoneVerified": bool(user.get("phone_number")),
            "authProvider": "google",
            "mfaEnabled": False,
            "isGuest": False,
            "updatedAt": now,
            "createdAt": now,
        },
        merge=True,
    )

    if email:
        email_ref(email).set({"uid": uid, "authEmail": email, "updatedAt": now}, merge=True)

    return {"ok": True, "uid": uid}


@router.post("/guest-profile")
def sync_guest_profile(user=Depends(require_user)):
    uid = user["uid"]
    now = server_timestamp()

    user_ref(uid).set(
        {
            "isGuest": True,
            "authProvider": "anonymous",
            "mfaEnabled": False,
            "updatedAt": now,
            "createdAt": now,
        },
        merge=True,
    )

    return {"ok": True, "uid": uid}
