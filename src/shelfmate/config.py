from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    db_password: str
    log_level: str = "INFO"
    log_dir: str = "logs"
    email_address: str | None = None
    email_app_password: str | None = None
    alert_errors_by_email: bool = False


settings = Settings()
