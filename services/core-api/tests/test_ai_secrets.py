from types import SimpleNamespace

import pytest

from app.ai.secrets import (
    DEFAULT_AI_API_KEY_REF,
    CredentialStoreUnavailableError,
    KeyringSecretStore,
)


class FakeKeyringError(Exception):
    pass


class FakeKeyring:
    errors = SimpleNamespace(KeyringError=FakeKeyringError)

    def __init__(self):
        self.values: dict[tuple[str, str], str] = {}
        self.fail = False

    def set_password(self, service: str, ref: str, value: str) -> None:
        if self.fail:
            raise FakeKeyringError("credential backend unavailable")
        self.values[(service, ref)] = value

    def get_password(self, service: str, ref: str) -> str | None:
        if self.fail:
            raise FakeKeyringError("credential backend unavailable")
        return self.values.get((service, ref))

    def delete_password(self, service: str, ref: str) -> None:
        if self.fail:
            raise FakeKeyringError("credential backend unavailable")
        self.values.pop((service, ref), None)


def test_keyring_secret_store_uses_fixed_service_and_deterministic_ref():
    backend = FakeKeyring()
    store = KeyringSecretStore(keyring_module=backend)

    assert DEFAULT_AI_API_KEY_REF == "ai-provider:default:api-key"
    store.set_secret(DEFAULT_AI_API_KEY_REF, "sk-test-value")

    assert backend.values[("XiaoyueJobSearch", DEFAULT_AI_API_KEY_REF)] == "sk-test-value"
    assert store.get_secret(DEFAULT_AI_API_KEY_REF) == "sk-test-value"

    store.delete_secret(DEFAULT_AI_API_KEY_REF)
    assert store.get_secret(DEFAULT_AI_API_KEY_REF) is None


def test_keyring_failure_never_falls_back_to_plaintext_storage():
    backend = FakeKeyring()
    backend.fail = True
    store = KeyringSecretStore(keyring_module=backend)

    with pytest.raises(CredentialStoreUnavailableError):
        store.set_secret(DEFAULT_AI_API_KEY_REF, "sk-should-not-leak")

    with pytest.raises(CredentialStoreUnavailableError):
        store.get_secret(DEFAULT_AI_API_KEY_REF)

    with pytest.raises(CredentialStoreUnavailableError):
        store.delete_secret(DEFAULT_AI_API_KEY_REF)
