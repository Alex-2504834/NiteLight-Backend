from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routes import admin, authProfiles, health, me, payments, places


app = FastAPI(title="NiteLight API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowedOriginsList,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(admin.router)
app.include_router(me.router)
app.include_router(authProfiles.router)
app.include_router(places.router)
app.include_router(payments.router)
