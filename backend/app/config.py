from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://attend:attend_dev_password@localhost:5432/attend"
    jwt_secret: str = "replace-this-with-a-long-random-secret-before-deployment"
    jwt_expire_minutes: int = 480
    cookie_secure: bool = False
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    media_dir: str = "./media"
    max_upload_mb: int = 8
    company_timezone: str = "Asia/Kolkata"
    financial_year_start_month: int = 4
    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

settings = Settings()
