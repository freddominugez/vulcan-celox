"""API key in the macOS Keychain (or the Linux keyring). The value comes in via stdin, never via the command
line, and is never written to a file, log or API response."""

from __future__ import annotations

import re
from typing import Optional

from vulcan_celox.core.runner import Runner

SERVICE = "com.byvulcan.celox.anthropic"
OLD_SERVICE = "com.byvulcan." + "terminal.anthropic"  # name used up to 1.1: the key is copied on first read
ACCOUNT = "api-key"
SECURITY = "/usr/bin/security"
# format of Anthropic keys; restricting the characters also prevents injection into the `security -i` command
KEY_PATTERN = re.compile(r"^sk-ant-[A-Za-z0-9_\-]{20,300}$")


class SecretError(Exception):
    pass


def valid_key(value: str) -> bool:
    return bool(KEY_PATTERN.match(value or ""))


def mask(value: Optional[str]) -> str:
    if not value:
        return ""
    return f"sk-ant-…{value[-4:]}"


class KeychainStore:
    def __init__(self, runner=None, service: str = SERVICE, account: str = ACCOUNT, security: str = SECURITY):
        self.runner = runner or Runner()
        self.service = service
        self.account = account
        self.security = security
        self.migrating = False

    def get(self) -> Optional[str]:
        result = self.runner.run([self.security, "find-generic-password", "-s", self.service, "-a", self.account, "-w"],
                                 timeout=15)
        value = (result.stdout or "").strip()
        if result.ok and valid_key(value):
            return value
        return self._from_old_service()

    def _from_old_service(self) -> Optional[str]:
        if self.migrating:
            return None
        result = self.runner.run([self.security, "find-generic-password", "-s", OLD_SERVICE, "-a", self.account, "-w"], timeout=15)
        value = (result.stdout or "").strip()
        if not result.ok or not valid_key(value):
            return None
        self.migrating = True
        try:
            self.set(value)
        except SecretError:
            pass  # did not copy: the old one stays valid, and the next read tries again
        finally:
            self.migrating = False
        return value

    def set(self, value: str) -> None:
        if not valid_key(value):
            raise SecretError("formato de chave inválido")
        command = (f'add-generic-password -U -s {self.service} -a {self.account} '
                   f'-l "Vulcan Celox: chave da Anthropic" -w {value}\n')
        result = self.runner.run([self.security, "-i"], input=command, timeout=15)
        if not result.ok or self.get() != value:
            raise SecretError("não foi possível gravar a chave no Keychain")

    def delete(self) -> None:
        self.runner.run([self.security, "delete-generic-password", "-s", self.service, "-a", self.account], timeout=15)


class SecretToolStore:
    """Linux: the system keyring (Secret Service) via `secret-tool`, with the value on stdin."""

    def __init__(self, runner=None, service: str = SERVICE, account: str = ACCOUNT, tool: Optional[str] = None):
        import shutil
        self.runner = runner or Runner()
        self.service = service
        self.account = account
        self.tool = tool or shutil.which("secret-tool")
        self.migrating = False

    def _attrs(self):
        return ["service", self.service, "account", self.account]

    def get(self) -> Optional[str]:
        if not self.tool:
            return None
        result = self.runner.run([self.tool, "lookup", *self._attrs()], timeout=15)
        value = (result.stdout or "").strip()
        if result.ok and valid_key(value):
            return value
        if self.migrating:
            return None
        result = self.runner.run([self.tool, "lookup", "service", OLD_SERVICE, "account", self.account], timeout=15)
        value = (result.stdout or "").strip()
        if not result.ok or not valid_key(value):
            return None
        self.migrating = True
        try:
            self.set(value)
        except SecretError:
            pass
        finally:
            self.migrating = False
        return value

    def set(self, value: str) -> None:
        if not valid_key(value):
            raise SecretError("formato de chave inválido")
        if not self.tool:
            raise SecretError("instale o secret-tool (pacote libsecret-tools) para guardar a chave no chaveiro do sistema")
        result = self.runner.run([self.tool, "store", "--label=Vulcan Celox: chave da Anthropic", *self._attrs()],
                                 input=value, timeout=15)
        if not result.ok or self.get() != value:
            raise SecretError("não foi possível gravar a chave no chaveiro do sistema")

    def delete(self) -> None:
        if self.tool:
            self.runner.run([self.tool, "clear", *self._attrs()], timeout=15)


class WindowsCredentialStore:
    """Windows Credential Manager: the key is protected by the user's account."""

    def __init__(self, service: str = SERVICE, account: str = ACCOUNT):
        self.target, self.account = service, account

    def get(self) -> Optional[str]:
        from vulcan_celox.core.win32 import credential_read
        value = credential_read(self.target)
        return value if value and valid_key(value) else None

    def set(self, value: str) -> None:
        from vulcan_celox.core.win32 import credential_write
        if not valid_key(value):
            raise SecretError("formato de chave inválido")
        if not credential_write(self.target, self.account, value) or self.get() != value:
            raise SecretError("não foi possível gravar a chave no chaveiro do sistema")

    def delete(self) -> None:
        from vulcan_celox.core.win32 import credential_delete
        credential_delete(self.target)


def default_keystore(runner=None, system: Optional[str] = None):
    from vulcan_celox.core.oscompat import is_macos, is_windows
    if is_windows(system):
        return WindowsCredentialStore()
    return KeychainStore(runner=runner) if is_macos(system) else SecretToolStore(runner=runner)


class MemoryKeyStore:
    """For tests and for running outside macOS: keeps it in memory only."""

    def __init__(self) -> None:
        self.value: Optional[str] = None

    def get(self) -> Optional[str]:
        return self.value

    def set(self, value: str) -> None:
        if not valid_key(value):
            raise SecretError("formato de chave inválido")
        self.value = value

    def delete(self) -> None:
        self.value = None
