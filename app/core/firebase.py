import json
from typing import Any

import firebase_admin as firebaseAdmin
from firebase_admin import auth, credentials, firestore

from app.core.config import settings


if not settings.firebaseServiceAccountJson:
    raise RuntimeError("Missing FIREBASE_SERVICE_ACCOUNT_JSON environment variable")

try:
    firebaseAdmin.get_app()
except ValueError:
    serviceAccount = json.loads(settings.firebaseServiceAccountJson)
    credential = credentials.Certificate(serviceAccount)
    firebaseAdmin.initialize_app(credential)

firebaseAuth = auth
firestoreDb: Any = firestore.client()
