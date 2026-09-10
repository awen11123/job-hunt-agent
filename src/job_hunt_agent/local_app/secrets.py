from __future__ import annotations

import re
from typing import Protocol


_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class KeyringBackend(Protocol):
    def set_password(self, service: str, username: str, password: str) -> None: ...

    def get_password(self, service: str, username: str) -> str | None: ...

    def delete_password(self, service: str, username: str) -> None: ...


class SecretStore:
    def __init__(
        self,
        *,
        backend: KeyringBackend | None = None,
        service_name: str = "JobHuntAgent",
    ) -> None:
        if backend is None:
            import keyring

            backend = keyring
        self._backend = backend
        self._service_name = service_name

    def set(self, reference: str, value: str) -> None:
        normalized_reference = self._validate_reference(reference)
        if not value.strip():
            raise ValueError("Credential value must not be blank")
        self._backend.set_password(self._service_name, normalized_reference, value)

    def get(self, reference: str) -> str | None:
        normalized_reference = self._validate_reference(reference)
        return self._backend.get_password(self._service_name, normalized_reference)

    def delete(self, reference: str) -> None:
        normalized_reference = self._validate_reference(reference)
        if self._backend.get_password(self._service_name, normalized_reference) is not None:
            self._backend.delete_password(self._service_name, normalized_reference)

    @staticmethod
    def _validate_reference(reference: str) -> str:
        normalized = reference.strip()
        if not _REFERENCE_PATTERN.fullmatch(normalized):
            raise ValueError("Credential reference contains unsupported characters")
        return normalized

