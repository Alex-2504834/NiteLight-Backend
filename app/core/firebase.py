import json
from typing import Any

import firebase_admin as firebaseAdmin
from firebase_admin import auth, credentials, firestore

from app.core.config import settings


def loadServiceAccount() -> tuple[dict[str, Any], str]:
    if not settings.firebaseServiceAccountJson:
        raise RuntimeError("Missing FIREBASE_SERVICE_ACCOUNT_JSON environment variable")

    try:
        serviceAccount = json.loads(settings.firebaseServiceAccountJson)
    except json.JSONDecodeError as error:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON") from error

    if not isinstance(serviceAccount, dict):
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON must contain a JSON object")

    projectId = str(serviceAccount.get("project_id", "")).strip()
    if not projectId:
        raise RuntimeError("Firebase service account is missing project_id")

    return serviceAccount, projectId


serviceAccount, firebaseProjectId = loadServiceAccount()

try:
    firebaseApp = firebaseAdmin.get_app()
except ValueError:
    firebaseCredential = credentials.Certificate(serviceAccount)
    firebaseApp = firebaseAdmin.initialize_app(
        firebaseCredential,
        {"projectId": firebaseProjectId},
    )

firebaseAuth = auth
firestoreDb: Any = firestore.client(app=firebaseApp)
