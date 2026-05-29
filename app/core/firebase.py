import json
from typing import Any

import firebase_admin
from firebase_admin import auth, credentials, firestore

from app.core.config import settings


if not settings.firebase_service_account_json:
    raise RuntimeError("Missing FIREBASE_SERVICE_ACCOUNT_JSON environment variable")

if not firebase_admin._apps:
    service_account = json.loads(settings.firebase_service_account_json)
    cred = credentials.Certificate(service_account)
    firebase_admin.initialize_app(cred)

firebase_auth = auth

firestore_db: Any = firestore.client()