"""Token and auth unit tests."""

from nova_core.auth.fingerprint import fingerprint_request
from nova_core.auth.tokens import generate_pairing_code, generate_token


def test_pairing_code_format() -> None:
    code = generate_pairing_code()
    assert len(code) == 6
    assert code.isupper()


def test_fingerprint_differs_for_different_bodies() -> None:
    fp1 = fingerprint_request({"title": "A"})
    fp2 = fingerprint_request({"title": "B"})
    assert fp1 != fp2


def test_fingerprint_stable() -> None:
    body = {"mission_type": "system_status", "title": "Test"}
    assert fingerprint_request(body) == fingerprint_request(body)


def test_worker_token_format() -> None:
    token = generate_token("worker")
    assert token.startswith("nova_wrk_")
