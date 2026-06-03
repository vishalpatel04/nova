# Configuration

## Environment variables

Copy `.env.example` to `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `NOVA_ENV` | `development` | Environment name |
| `NOVA_LOG_LEVEL` | `INFO` | Log level |
| `NOVA_API_HOST` | `0.0.0.0` | API bind host |
| `NOVA_API_PORT` | `8000` | API bind port |
| `DATABASE_URL` | `postgresql+asyncpg://...` | Async PostgreSQL URL |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL |
| `NOVA_CONFIG_DIR` | `config` | Path to YAML configs |
| `NOVA_API_TOKEN` | — | Dev bearer token |
| `NOVA_DEFAULT_USER_ID` | `arth` | Seed user ID |

### Worker-specific

| Variable | Description |
|----------|-------------|
| `DEVICE_ID` | Unique device slug (required on worker nodes) |
| `DEVICE_NAME` | Human-readable name |
| `DEVICE_TYPE` | One of the types in `config/devices.yaml` |
| `CONTROL_PLANE_URL` | API base URL |
| `WORKER_HEARTBEAT_INTERVAL_SECONDS` | Heartbeat interval |
| `WORKER_HEALTH_PORT` | Worker health endpoint port |

## YAML configuration

| File | Purpose |
|------|---------|
| `config/agents.yaml` | Commander and specialist definitions |
| `config/models.yaml` | Model tier → provider/model mapping |
| `config/voices.yaml` | Voice profile metadata and modes |
| `config/devices.yaml` | Device type templates and pairing policy |
| `config/policies.yaml` | Approval, audit, rate limits, security |

## Secrets policy

- API keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) are **environment only**
- `config/models.yaml` references env var names, never values
- Database stores no plaintext secrets
- `policies.yaml` enforces `never_store_plaintext_secrets: true`

## Loading

Settings are loaded via Pydantic `BaseSettings` in `nova_core/schemas/settings.py`:

```python
from nova_core.schemas.settings import get_settings

settings = get_settings()
agents = settings.load_yaml("agents.yaml")
```

Agent registry is parsed by `nova_core/agents/registry.py` and seeded into the database on API startup.

## Voice modes (macOS)

Defined in `config/voices.yaml`:

| Mode | Description |
|------|-------------|
| `prime_only` | Only NOVA speaks |
| `war_room` | Multiple commanders speak |
| `silent_operations` | Text only |
| `briefing` | NOVA structured briefings |
