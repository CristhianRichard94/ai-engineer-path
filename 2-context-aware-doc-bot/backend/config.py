from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"

    # OpenAI
    openai_api_key: str

    # Qdrant
    qdrant_uri: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "github_repos"
    qdrant_vector_size: int = 1536

    # Celery (filesystem broker — see worker/app.py for the "ponytail" note
    # on this stopgap's limitations)
    celery_broker_dir: str = "/tmp/doc_bot_celery/broker"
    commit_cache_dir: str = "/tmp/doc_bot_celery/commit_cache"

    # GitHub
    github_api_url: str = "https://api.github.com"


settings = Settings()
