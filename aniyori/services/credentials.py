"""Fail-closed storage for credentials in the desktop Secret Service."""

from __future__ import annotations

import shutil
import subprocess


class CredentialStoreError(RuntimeError):
    """Raised when a credential cannot be safely stored or retrieved."""


class CredentialStoreUnavailable(CredentialStoreError):
    """Raised when the Secret Service command-line client is unavailable."""


class SecretServiceCredentialStore:
    """Use libsecret's secret-tool without writing credentials to config files.

    If secret-tool or the desktop Secret Service is unavailable, operations fail
    safely. This class deliberately has no plaintext or homemade-crypto fallback.
    """

    def __init__(self, *, binary: str | None = None, timeout: float = 5):
        self.binary = binary or shutil.which("secret-tool")
        if not self.binary:
            raise CredentialStoreUnavailable(
                "The desktop Secret Service is unavailable; install libsecret-tools "
                "and unlock a compatible keyring to store credentials."
            )
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("Credential-store timeout must be greater than zero.")
        self.timeout = timeout

    @staticmethod
    def _validate_attribute(value: str, label: str) -> str:
        if not isinstance(value, str) or not value.strip() or any(
            ord(character) < 32 for character in value
        ):
            raise ValueError(f"{label} must be non-empty text without control characters.")
        return value

    def _run(self, arguments: list[str], *, secret: str | None = None):
        try:
            result = subprocess.run(
                [self.binary, *arguments],
                input=None if secret is None else secret + "\n",
                text=True,
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CredentialStoreUnavailable(
                "Could not access the desktop Secret Service."
            ) from error
        return result

    def store(self, service: str, account: str, secret: str) -> None:
        """Store a password or token in the unlocked desktop keyring."""
        service = self._validate_attribute(service, "Service")
        account = self._validate_attribute(account, "Account")
        if not isinstance(secret, str) or not secret or any(
            character in secret for character in ("\x00", "\r", "\n")
        ):
            raise ValueError("Credential must be non-empty text without line breaks.")
        result = self._run(
            [
                "store",
                "--label=Aniyori application credential",
                "service",
                service,
                "account",
                account,
            ],
            secret=secret,
        )
        if result.returncode != 0:
            raise CredentialStoreUnavailable(
                "The desktop keyring could not store this credential."
            )

    def lookup(self, service: str, account: str) -> str | None:
        """Return a stored secret, or None when no matching item exists."""
        service = self._validate_attribute(service, "Service")
        account = self._validate_attribute(account, "Account")
        result = self._run([
            "lookup",
            "service",
            service,
            "account",
            account,
        ])
        if result.returncode != 0:
            if not result.stdout and result.returncode == 1:
                return None
            raise CredentialStoreUnavailable(
                "The desktop keyring could not retrieve this credential."
            )
        value = result.stdout[:-1] if result.stdout.endswith("\n") else result.stdout
        return value or None

    def remove(self, service: str, account: str) -> bool:
        """Remove one credential; return False when no matching item exists."""
        service = self._validate_attribute(service, "Service")
        account = self._validate_attribute(account, "Account")
        result = self._run([
            "clear",
            "service",
            service,
            "account",
            account,
        ])
        if result.returncode == 0:
            return True
        if result.returncode == 1 and not result.stdout:
            return False
        raise CredentialStoreUnavailable(
            "The desktop keyring could not remove this credential."
        )
