"""Resolve storage credential refs (Key Vault / encrypted file) for workers."""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)


def _fernet_key_from_password(password: Optional[str] = None) -> bytes:
    from cryptography.fernet import Fernet  # noqa: F401 — ensure installed
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    if password is None:
        password = os.environ.get("METHYL_STORAGE_CREDENTIAL_PASSWORD", "")
        if not password:
            salt = str(Path.home()).encode()
        else:
            salt = password.encode()
    else:
        salt = password.encode()
    salt_bytes = salt[:16].ljust(16, b"0")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt_bytes,
        iterations=100000,
    )
    key = kdf.derive(b"methyl_storage_secret")
    return base64.urlsafe_b64encode(key)


def read_encrypted_secret_file(path: Path, *, password: Optional[str] = None) -> str:
    from cryptography.fernet import Fernet

    data = path.read_bytes()
    # Support JSON wrapper {"value": "..."} encrypted as whole file of ciphertext
    f = Fernet(_fernet_key_from_password(password))
    plain = f.decrypt(data).decode("utf-8")
    # Allow JSON object with nested fields for multi-field secrets
    try:
        parsed = json.loads(plain)
        if isinstance(parsed, dict) and "value" in parsed and len(parsed) == 1:
            return str(parsed["value"])
        if isinstance(parsed, dict):
            return plain  # multi-field JSON string for caller to parse
        return plain
    except json.JSONDecodeError:
        return plain


def write_encrypted_secret_file(
    path: Path,
    value: str,
    *,
    password: Optional[str] = None,
) -> None:
    from cryptography.fernet import Fernet

    path.parent.mkdir(parents=True, exist_ok=True)
    f = Fernet(_fernet_key_from_password(password))
    path.write_bytes(f.encrypt(value.encode("utf-8")))
    os.chmod(path, 0o600)


def read_key_vault_secret(vault_url: str, secret_name: str) -> str:
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient

    client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())
    secret = client.get_secret(secret_name)
    if secret.value is None:
        raise RuntimeError(f"Key Vault secret {secret_name!r} at {vault_url} has no value")
    return secret.value


def resolve_secret_payload(credentials: Mapping[str, Any]) -> Mapping[str, Any]:
    """
    Expand vault / encrypted_file credential refs into concrete auth fields.

    Returns a new mapping suitable for building boto3 / Azure clients.
    Passes through explicit_keys / account_key / connection_string / ambient modes.
    """
    auth = str(credentials.get("authMode") or "")
    if auth == "azure_key_vault":
        vault_url = credentials.get("vaultUrl") or credentials.get("azure_key_vault_url")
        secret_name = credentials.get("secretName") or credentials.get("azure_secret_name")
        if not vault_url or not secret_name:
            raise RuntimeError(
                "azure_key_vault credentials require vaultUrl and secretName"
            )
        raw = read_key_vault_secret(str(vault_url), str(secret_name))
        return _payload_from_vault_or_file_value(raw, credentials)
    if auth == "encrypted_file":
        path = credentials.get("path") or credentials.get("encrypted_file_path")
        if not path:
            raise RuntimeError("encrypted_file credentials require path")
        raw = read_encrypted_secret_file(Path(str(path)).expanduser())
        return _payload_from_vault_or_file_value(raw, credentials)
    return credentials


def _payload_from_vault_or_file_value(
    raw: str, credentials: Mapping[str, Any]
) -> dict[str, Any]:
    """
    Interpret secret value as JSON auth payload or a single secret string.

    JSON examples:
      {"authMode":"explicit_keys","accessKeyId":"...","secretAccessKey":"..."}
      {"authMode":"account_key","accountKey":"..."}
      {"authMode":"connection_string","connectionString":"..."}
    """
    target = credentials.get("materializeAs") or credentials.get("secretKind")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict) and parsed.get("authMode"):
        return dict(parsed)
    # Single string secret — materialize into requested shape
    if target == "account_key" or credentials.get("providerHint") == "azure_blob":
        return {"authMode": "account_key", "accountKey": raw}
    if target == "connection_string":
        return {"authMode": "connection_string", "connectionString": raw}
    # Default: S3 access key pair encoded as "accessKeyId:secretAccessKey"
    if ":" in raw and target in (None, "explicit_keys", "s3"):
        access, _, secret = raw.partition(":")
        if access and secret:
            return {
                "authMode": "explicit_keys",
                "accessKeyId": access,
                "secretAccessKey": secret,
            }
    if target == "explicit_keys":
        raise RuntimeError(
            "Key Vault/encrypted secret for explicit_keys must be JSON or "
            "accessKeyId:secretAccessKey"
        )
    # Fall back: treat as connection string if looks like one
    if "AccountKey=" in raw or "AccountName=" in raw:
        return {"authMode": "connection_string", "connectionString": raw}
    raise RuntimeError(
        "Unable to interpret vault/encrypted secret; store JSON with authMode "
        "or accessKeyId:secretAccessKey / account key / connection string"
    )
