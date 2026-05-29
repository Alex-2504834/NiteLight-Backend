import os


class Settings:
    def __init__(self):
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.port = int(os.getenv("PORT", "8000"))
        self.host = os.getenv("HOST", "0.0.0.0")
        self.firebase_service_account_json = os.getenv(
            "FIREBASE_SERVICE_ACCOUNT_JSON",
            "",
        )
        self.allowed_origins = os.getenv("ALLOWED_ORIGINS", "*")

    @property
    def allowed_origins_list(self) -> list[str]:
        if not self.allowed_origins:
            return ["*"]

        return [
            origin.strip()
            for origin in self.allowed_origins.split(",")
            if origin.strip()
        ]


settings = Settings()
