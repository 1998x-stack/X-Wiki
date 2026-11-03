"""Dependency-free, strict validation helpers for immutable domain objects."""

import re
from datetime import datetime

from .errors import ContractError

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def identifier(value: str, name: str) -> None:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ContractError(f"{name} must be a nonempty stable identifier (max 128 ASCII chars)")


def optional_identifier(value: str | None, name: str) -> None:
    if value is not None:
        identifier(value, name)


def digest(value: str, name: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ContractError(f"{name} must be a lowercase SHA-256 hex digest")


def required_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{name} must be nonempty text")


def optional_text(value: str | None, name: str) -> None:
    if value is not None:
        required_text(value, name)


def timestamp(value: str, name: str) -> None:
    if not isinstance(value, str):
        raise ContractError(f"{name} must be an offset-aware ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError(f"{name} must be an offset-aware ISO 8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{name} must contain an explicit timezone offset")


def refs(value: tuple[str, ...], name: str) -> None:
    if not isinstance(value, tuple):
        raise ContractError(f"{name} must be an immutable tuple of IDs")
    for item in value:
        identifier(item, name)
    if len(value) != len(set(value)):
        raise ContractError(f"{name} contains duplicate IDs")


def optional_duration(value: int | None, name: str) -> None:
    if value is not None and (type(value) is not int or value < 0):
        raise ContractError(f"{name} must be a nonnegative integer")


def enum_value(value: object, enum_type: type, name: str) -> None:
    if not isinstance(value, enum_type):
        raise ContractError(f"{name} must be a {enum_type.__name__} value")
