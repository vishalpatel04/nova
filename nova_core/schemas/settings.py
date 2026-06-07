"""Typed application settings loaded from environment and config files."""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    nova_env: str = Field(default="development", alias="NOVA_ENV")
    nova_log_level: str = Field(default="INFO", alias="NOVA_LOG_LEVEL")
    nova_api_host: str = Field(default="0.0.0.0", alias="NOVA_API_HOST")
    nova_api_port: int = Field(default=8000, alias="NOVA_API_PORT")
    database_url: str = Field(
        default="postgresql+asyncpg://nova:nova@localhost:5433/nova",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    nova_config_dir: str = Field(default="config", alias="NOVA_CONFIG_DIR")
    nova_api_token: str = Field(default="dev-token-change-me", alias="NOVA_API_TOKEN")
    nova_default_user_id: str = Field(default="arth", alias="NOVA_DEFAULT_USER_ID")
    nova_token_pepper: str = Field(
        default="dev-pepper-change-in-production", alias="NOVA_TOKEN_PEPPER"
    )
    nova_bootstrap_admin_enabled: bool = Field(default=False, alias="NOVA_BOOTSTRAP_ADMIN_ENABLED")
    nova_bootstrap_admin_token: str = Field(
        default="nova_bts_dev_bootstrap", alias="NOVA_BOOTSTRAP_ADMIN_TOKEN"
    )
    require_device_token: bool = Field(default=True, alias="NOVA_REQUIRE_DEVICE_TOKEN")
    nova_paid_providers_enabled: bool = Field(default=False, alias="NOVA_PAID_PROVIDERS_ENABLED")
    nova_provider_timeout_seconds: float = Field(default=8.0, alias="NOVA_PROVIDER_TIMEOUT_SECONDS")
    nova_ollama_base_url: str = Field(
        default="http://localhost:11434", alias="NOVA_OLLAMA_BASE_URL"
    )
    nova_openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    nova_anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    nova_deepseek_base_url: str = Field(
        default="http://localhost:11434", alias="NOVA_DEEPSEEK_BASE_URL"
    )
    nova_qwen_base_url: str = Field(default="http://localhost:11434", alias="NOVA_QWEN_BASE_URL")
    nova_ollama_model: str = Field(default="", alias="NOVA_OLLAMA_MODEL")
    nova_qwen_model: str = Field(default="", alias="NOVA_QWEN_MODEL")
    nova_deepseek_model: str = Field(default="", alias="NOVA_DEEPSEEK_MODEL")
    nova_n8n_base_url: str = Field(default="", alias="NOVA_N8N_BASE_URL")
    nova_openclaw_base_url: str = Field(default="", alias="NOVA_OPENCLAW_BASE_URL")
    nova_shortcuts_enabled: bool = Field(default=False, alias="NOVA_SHORTCUTS_ENABLED")
    nova_external_providers_enabled: bool = Field(
        default=False, alias="NOVA_EXTERNAL_PROVIDERS_ENABLED"
    )
    nova_codex_cli_enabled: bool = Field(default=False, alias="NOVA_CODEX_CLI_ENABLED")
    nova_anthropic_enabled: bool = Field(default=False, alias="NOVA_ANTHROPIC_ENABLED")
    nova_openai_enabled: bool = Field(default=False, alias="NOVA_OPENAI_ENABLED")
    nova_memory_embedding_model: str = Field(
        default="nomic-embed-text", alias="NOVA_MEMORY_EMBEDDING_MODEL"
    )
    nova_memory_embedding_dimensions: int = Field(
        default=256, alias="NOVA_MEMORY_EMBEDDING_DIMENSIONS"
    )
    nova_memory_index_batch_size: int = Field(default=50, alias="NOVA_MEMORY_INDEX_BATCH_SIZE")

    @property
    def config_path(self) -> Path:
        return Path(self.nova_config_dir)

    def load_yaml(self, filename: str) -> dict[str, object]:
        path = self.config_path / filename
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        with path.open() as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Expected dict in {path}, got {type(data)}")
        return data


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    device_id: str = Field(default="", alias="DEVICE_ID")
    device_name: str = Field(default="", alias="DEVICE_NAME")
    device_type: str = Field(default="macos_worker", alias="DEVICE_TYPE")
    control_plane_url: str = Field(default="http://localhost:8000", alias="CONTROL_PLANE_URL")
    worker_heartbeat_interval_seconds: int = Field(
        default=30, alias="WORKER_HEARTBEAT_INTERVAL_SECONDS"
    )
    worker_health_port: int = Field(default=9100, alias="WORKER_HEALTH_PORT")
    worker_token: str = Field(default="", alias="WORKER_TOKEN")
    worker_token_keychain_service: str = Field(
        default="com.nova.worker", alias="WORKER_TOKEN_KEYCHAIN_SERVICE"
    )
    worker_token_keychain_account: str = Field(default="", alias="WORKER_TOKEN_KEYCHAIN_ACCOUNT")
    worker_ws_enabled: bool = Field(default=True, alias="WORKER_WS_ENABLED")

    @property
    def resolved_worker_token(self) -> str:
        from nova_core.auth.keychain import read_generic_password

        account = self.worker_token_keychain_account or self.device_id or "nova-worker"
        token = read_generic_password(self.worker_token_keychain_service, account)
        return token or self.worker_token


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_worker_settings() -> WorkerSettings:
    return WorkerSettings()
