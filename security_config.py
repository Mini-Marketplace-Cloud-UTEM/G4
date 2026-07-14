import json
import os
from functools import lru_cache
from typing import Any, Optional
from urllib.parse import urlparse

from cryptography.fernet import Fernet


LOCAL_ENVIRONMENTS = {"local", "development", "test"}


def _environment() -> str:
    return os.getenv("ENVIRONMENT", "production").lower()


def is_local_environment() -> bool:
    return _environment() in LOCAL_ENVIRONMENTS


def get_required_secret(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Falta configurar el secreto obligatorio {name}.")
    return value.strip()


def get_https_service_url(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()
    parsed = urlparse(value)
    if parsed.scheme != "https":
        raise RuntimeError(f"{name} debe usar HTTPS.")
    return value.rstrip("/")


def get_required_database_url() -> str:
    value = get_required_secret("DATABASE_URL").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise RuntimeError("DATABASE_URL debe ser una URL PostgreSQL valida.")
    return value


def get_required_rabbitmq_url() -> str:
    value = get_required_secret("RABBITMQ_URL").strip()
    parsed = urlparse(value)
    if parsed.scheme != "amqps":
        raise RuntimeError("RABBITMQ_URL debe usar AMQPS para transporte cifrado.")
    return value


def should_allow_insecure_request(host: Optional[str]) -> bool:
    if not is_local_environment():
        return False
    if not host:
        return False
    hostname = host.split(":", 1)[0]
    return hostname in {"127.0.0.1", "localhost", "::1"}


def is_request_over_tls(scheme: str, forwarded_proto: Optional[str]) -> bool:
    return scheme == "https" or (forwarded_proto or "").split(",", 1)[0].strip() == "https"


def redact_identifier(value: Any, visible: int = 6) -> str:
    if value is None:
        return "none"
    text = str(value)
    if len(text) <= visible * 2:
        return "***"
    return f"{text[:visible]}...{text[-visible:]}"


def sanitize_external_error(value: str, limit: int = 300) -> str:
    sanitized = value.replace("\n", " ").replace("\r", " ")
    for marker in ("Bearer ", "authorization", "Authorization"):
        sanitized = sanitized.replace(marker, "[redacted]")
    return sanitized[:limit]


@lru_cache(maxsize=1)
def _field_cipher() -> Fernet:
    key = get_required_secret("FIELD_ENCRYPTION_KEY")
    return Fernet(key.encode("utf-8"))


def encrypt_field(value: Optional[str]) -> Optional[str]:
    if value in (None, ""):
        return value
    return _field_cipher().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_field(value: Optional[str]) -> Optional[str]:
    if value in (None, ""):
        return value
    return _field_cipher().decrypt(value.encode("utf-8")).decode("utf-8")


def encrypt_json_field(value: dict[str, Any]) -> str:
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return encrypt_field(serialized) or ""
