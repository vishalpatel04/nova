"""Worker Keychain token lookup tests."""

from nova_core.schemas.settings import WorkerSettings


def test_worker_settings_prefers_keychain_token(monkeypatch) -> None:
    monkeypatch.setattr(
        "nova_core.auth.keychain.read_generic_password",
        lambda service, account: "nova_wrk_keychain",
    )
    settings = WorkerSettings(
        DEVICE_ID="m3-worker",
        WORKER_TOKEN="nova_wrk_plaintext",
        WORKER_TOKEN_KEYCHAIN_SERVICE="com.nova.worker",
    )

    assert settings.resolved_worker_token == "nova_wrk_keychain"


def test_worker_settings_falls_back_to_env_token(monkeypatch) -> None:
    monkeypatch.setattr(
        "nova_core.auth.keychain.read_generic_password",
        lambda service, account: None,
    )
    settings = WorkerSettings(DEVICE_ID="m3-worker", WORKER_TOKEN="nova_wrk_plaintext")

    assert settings.resolved_worker_token == "nova_wrk_plaintext"
