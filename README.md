# NiteLight Backend

FastAPI backend for NiteLight. Private Firebase Admin credentials live here, not in the React Native app.

## Portainer env vars

Set these in your Portainer stack:

```env
ENVIRONMENT=production
PORT=8000
HOST=0.0.0.0
FIREBASE_SERVICE_ACCOUNT_JSON={...one-line service account json...}
ALLOWED_ORIGINS=*
STRIPE_SECRET_KEY=sk_test_...
STRIPE_CURRENCY=gbp
STRIPE_TEST_AMOUNT=100
```

## Endpoints

Public:

- `GET /health`
- `GET /places`
- `GET /places/{place_id}`
- `POST /auth/resolve-login`

Requires Firebase ID token in `Authorization: Bearer <token>`:

- `GET /me`
- `POST /auth/password-profile`
- `POST /auth/google-profile`
- `POST /auth/guest-profile`
- `POST /places`
- `PATCH /places/{place_id}`
- `DELETE /places/{place_id}`
- `POST /payments/test-payment-sheet`

## Security note

A static API key in a mobile app is extractable, so this backend uses Firebase ID tokens instead. Add Firebase App Check later for stronger app authenticity checks.
