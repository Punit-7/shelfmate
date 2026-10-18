from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    db_password: SecretStr
    log_level: str = "INFO"
    log_dir: str = "logs"
    email_address: str | None = None
    email_app_password: SecretStr | None = None
    alert_errors_by_email: bool = False
    # Where the other services live. Inside Docker, change localhost to the service name.
    api_url: str = "http://localhost:8000"
    searxng_url: str = "http://localhost:8080"
    ollama_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b"


settings = Settings()
