"""Validate workflow contracts with the JSON Schema keywords used in this project."""

from functools import cache
import json
import math
from pathlib import Path
import re


SCHEMAS = Path(__file__).with_name("schemas")
TYPES = {
    "object": lambda value: isinstance(value, dict),
    "array": lambda value: isinstance(value, list),
    "string": lambda value: isinstance(value, str),
    "boolean": lambda value: type(value) is bool,
    "integer": lambda value: type(value) is int,
    "number": lambda value: type(value) is int or (type(value) is float and math.isfinite(value)),
    "null": lambda value: value is None,
}
SUPPORTED = {
    "$schema", "$id", "title", "description", "default", "examples", "type", "required",
    "properties", "additionalProperties", "items", "enum", "const", "minItems", "maxItems",
    "minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum", "pattern", "uniqueItems", "anyOf",
}


class SchemaViolation(ValueError):
    """The artifact violates its checked-in JSON contract."""


@cache
def _load(name: str) -> dict:
    if not re.fullmatch(r"[a-z_]+", name):
        raise ValueError(f"Invalid workflow schema name: {name!r}")
    return json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))


def _equal(left, right) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    return left == right


def _matches(schema: dict, value, path: str) -> bool:
    try:
        _check(schema, value, path)
    except SchemaViolation:
        return False
    return True


def _check(schema: dict, value, path: str) -> None:
    def require(condition: bool, detail: str):
        if not condition:
            raise SchemaViolation(f"{path}: {detail}")

    unknown = schema.keys() - SUPPORTED
    require(not unknown, f"Unsupported schema keywords: {sorted(unknown)}")
    types = schema.get("type")
    if types:
        types = [types] if isinstance(types, str) else types
        require(any(TYPES[name](value) for name in types), f"Expected {' or '.join(types)}")
    if "enum" in schema:
        require(any(_equal(value, choice) for choice in schema["enum"]), "Value is outside enum")
    if "const" in schema:
        require(_equal(value, schema["const"]), f"Expected {schema['const']!r}")
    if "anyOf" in schema:
        require(any(_matches(option, value, path) for option in schema["anyOf"]), "No matching schema alternative")
    if isinstance(value, dict):
        missing = set(schema.get("required", [])) - value.keys()
        require(not missing, f"Missing required fields: {sorted(missing)}")
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for key, entry in value.items():
            rule = properties.get(key, additional)
            require(rule is not False, f"Unexpected property {key!r}")
            if isinstance(rule, dict):
                _check(rule, entry, f"{path}.{key}")
    if isinstance(value, list):
        require(schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", len(value)), "Array length out of bounds")
        if schema.get("uniqueItems"):
            require(all(not any(_equal(item, earlier) for earlier in value[:index])
                        for index, item in enumerate(value)), "Array items are not unique")
        if "items" in schema:
            for index, item in enumerate(value):
                _check(schema["items"], item, f"{path}[{index}]")
    if isinstance(value, str):
        require(schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", len(value)), "String length out of bounds")
        if "pattern" in schema:
            require(re.search(schema["pattern"], value) is not None, "String does not match pattern")
    if TYPES["number"](value):
        require(schema.get("minimum", value) <= value <= schema.get("maximum", value), "Number out of bounds")
        if "exclusiveMinimum" in schema:
            require(value > schema["exclusiveMinimum"], "Number must exceed minimum")


def validate_schema(name: str, value) -> None:
    _check(_load(name), value, name)
