"""Config loading tests."""

from nova_core.agents.registry import get_commander, load_agent_registry
from nova_core.schemas.settings import Settings


def test_settings_loads() -> None:
    settings = Settings(nova_config_dir="config", _env_file=None)
    assert settings.nova_env in ("development", "test")
    assert settings.nova_api_port == 8000


def test_load_agents_yaml() -> None:
    settings = Settings(nova_config_dir="config")
    agents = load_agent_registry(settings)
    assert len(agents) >= 7
    commanders = [a for a in agents if a.parent_commander is None]
    assert len(commanders) == 7


def test_nova_commander_exists() -> None:
    settings = Settings(nova_config_dir="config")
    agents = load_agent_registry(settings)
    nova = get_commander(agents, "nova")
    assert nova is not None
    assert nova.display_name == "NOVA"
    assert nova.role == "chief_of_staff"


def test_all_config_files_load() -> None:
    settings = Settings(nova_config_dir="config")
    for filename in ["agents.yaml", "models.yaml", "voices.yaml", "devices.yaml", "policies.yaml"]:
        data = settings.load_yaml(filename)
        assert isinstance(data, dict)
        assert len(data) > 0


def test_commander_has_required_fields() -> None:
    settings = Settings(nova_config_dir="config")
    data = settings.load_yaml("agents.yaml")
    for commander in data["commanders"]:
        assert "id" in commander
        assert "display_name" in commander
        assert "role" in commander
        assert "colour_token" in commander
        assert "icon_token" in commander
        assert "voice_profile_id" in commander
        assert "model_tier" in commander
        assert "allowed_tool_categories" in commander
