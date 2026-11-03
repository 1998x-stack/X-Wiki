"""Strict JSON-compatible domain wire round trips, using only the stdlib.

JSON Schema is the external client contract; this codec independently refuses
unknown keys, wrong primitive types, invalid enums and malformed nested data.
"""

import types
from dataclasses import MISSING, asdict, fields, is_dataclass
from enum import Enum
from typing import TypeVar, Union, get_args, get_origin, get_type_hints

from .errors import ContractError

T = TypeVar("T")


def to_payload(entity: object) -> dict[str, object]:
    if not is_dataclass(entity) or isinstance(entity, type):
        raise ContractError("expected a dataclass instance")

    def encode(value: object) -> object:
        if isinstance(value, Enum):
            return value.value
        if is_dataclass(value) and not isinstance(value, type):
            return {key: encode(item) for key, item in asdict(value).items()}
        if isinstance(value, (list, tuple)):
            return [encode(item) for item in value]
        if isinstance(value, dict):
            return {key: encode(item) for key, item in value.items()}
        return value

    return {key: encode(value) for key, value in asdict(entity).items()}


def _decode(value: object, annotation: object) -> object:
    origin = get_origin(annotation)
    if origin in (types.UnionType, Union):
        for option in get_args(annotation):
            try:
                return _decode(value, option)
            except ContractError:
                continue
        raise ContractError("value does not match any allowed union type")

    if annotation is type(None):
        if value is None:
            return None
        raise ContractError("null required")

    if origin is tuple:
        subtype, ellipsis = get_args(annotation)
        if ellipsis is not Ellipsis or not isinstance(value, list):
            raise ContractError("tuple fields must be JSON arrays")
        return tuple(_decode(item, subtype) for item in value)

    if isinstance(annotation, type) and issubclass(annotation, Enum):
        if not isinstance(value, str):
            raise ContractError("enum values must be strings")
        try:
            return annotation(value)
        except ValueError as error:
            raise ContractError(f"invalid {annotation.__name__}: {value!r}") from error

    if isinstance(annotation, type) and is_dataclass(annotation):
        return from_payload(annotation, value)

    if annotation in (str, int, bool):
        if type(value) is not annotation:
            raise ContractError(f"expected {annotation.__name__}")
        return value

    raise ContractError(f"unsupported contract type: {annotation!r}")


def from_payload(model: type[T], payload: object) -> T:
    if not isinstance(model, type) or not is_dataclass(model):
        raise ContractError("model must be a dataclass type")
    if not isinstance(payload, dict) or any(type(key) is not str for key in payload):
        raise ContractError("payload must be a JSON object")
    declared = {field.name: field for field in fields(model)}
    unknown = set(payload) - set(declared)
    if unknown:
        raise ContractError(f"unknown fields in {model.__name__}: {sorted(unknown)}")
    annotations = get_type_hints(model)
    kwargs: dict[str, object] = {}
    for name, field in declared.items():
        if name in payload:
            try:
                kwargs[name] = _decode(payload[name], annotations[name])
            except ContractError as error:
                raise ContractError(f"{model.__name__}.{name}: {error}") from error
        elif field.default is MISSING and field.default_factory is MISSING:
            raise ContractError(f"{model.__name__}.{name} is required")
    return model(**kwargs)
