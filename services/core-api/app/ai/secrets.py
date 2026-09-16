from __future__ import annotations

from typing import Protocol

import keyring

DEFAULT_AI_API_KEY_REF = "ai-provider:default:api-key"
DEFAULT_KEYRING_SERVICE = "XiaoyueJobSearch"


class CredentialStoreUnavailableError(RuntimeError):
    pass


class SecretStore(Protocol):
    def set_secret(self, ref: str, value: str) -> None: ...

    def get_secret(self, ref: str) -> str | None: ...

    def delete_secret(self, ref: str) -> None: ...


class KeyringSecretStore:
    def __init__(self, *, keyring_module=keyring, service_name: str = DEFAULT_KEYRING_SERVICE):
        self._keyring = keyring_module
        self._service_name = service_name

    def _raise_unavailable(self, exc: Exception) -> None:
        raise CredentialStoreUnavailableError("Operating system credential store is unavailable") from exc

    def set_secret(self, ref: str, value: str) -> None:
        try:
            self._keyring.set_password(self._service_name, ref, value)
        except self._keyring.errors.KeyringError as exc:
            self._raise_unavailable(exc)

    def get_secret(self, ref: str) -> str | None:
        try:
            return self._keyring.get_password(self._service_name, ref)
        except self._keyring.errors.KeyringError as exc:
            self._raise_unavailable(exc)

    def delete_secret(self, ref: str) -> None:
        try:
            if self._keyring.get_password(self._service_name, ref) is None:
                return
            self._keyring.delete_password(self._service_name, ref)
        except self._keyring.errors.KeyringError as exc:
            self._raise_unavailable(exc)


def get_secret_store() -> SecretStore:
    return KeyringSecretStore()
