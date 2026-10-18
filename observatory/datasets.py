"""Validate bounded, versioned evaluation datasets before any provider calls."""

import hashlib
import json
import math
from typing import Any, Literal

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

MAX_DATASET_BYTES = 512_000


def strict_json(text: str) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("Non-finite JSON number")

    def floating(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("Non-finite JSON number")
        return result

    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant, parse_float=floating)


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["exact", "contains", "excludes", "max_words", "json", "json_schema"]
    value: Any = None
    fields: dict[str, str] | None = None
    contract: dict | None = Field(default=None, alias="schema")

    @model_validator(mode="after")
    def valid_contract(self):
        if self.type in {"exact", "contains", "excludes"}:
            if not isinstance(self.value, str) or not self.value.strip():
                raise ValueError("Phrase checks require a nonempty string")
        elif self.type == "max_words":
            if type(self.value) is not int or self.value < 0:
                raise ValueError("Word limits must be nonnegative integers")
        elif self.type == "json":
            allowed = {"str", "int", "float", "bool", "list", "dict", "NoneType"}
            if not self.fields or any(value not in allowed for value in self.fields.values()):
                raise ValueError("JSON field types are invalid")
        elif self.type == "json_schema":
            if not self.contract:
                raise ValueError("A JSON Schema contract is required")
            Draft202012Validator.check_schema(self.contract)
            self._check_local_refs(self.contract)
        return self

    @staticmethod
    def _check_local_refs(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"$ref", "$dynamicRef"} and not child.startswith("#"):
                    raise ValueError("Only document-local schema references are supported")
                Rule._check_local_refs(child)
        elif isinstance(value, list):
            for child in value:
                Rule._check_local_refs(child)


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")
    category: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=20_000)
    baseline: str = Field(max_length=20_000)
    candidate: str = Field(max_length=20_000)
    checks: list[Rule] = Field(min_length=1, max_length=20)


def parse_dataset(raw: bytes) -> tuple[list[dict], str]:
    if len(raw) > MAX_DATASET_BYTES:
        raise ValueError("Dataset exceeds 512,000 bytes")
    try:
        lines = [line for line in raw.decode("utf-8").splitlines() if line.strip()]
    except UnicodeDecodeError as exc:
        raise ValueError("Dataset must use UTF-8") from exc
    if not 1 <= len(lines) <= 200:
        raise ValueError("Dataset must contain between 1 and 200 cases")
    cases = []
    for index, line in enumerate(lines, 1):
        try:
            case = Case.model_validate(strict_json(line))
            cases.append(case.model_dump(by_alias=True, exclude_none=True))
        except (ValueError, ValidationError, SchemaError, TypeError, RecursionError) as exc:
            # Invalid data can contain private text. Report location, not its value.
            raise ValueError(f"Invalid dataset contract at line {index}") from exc
    ids = [case["id"] for case in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("Dataset must have unique case IDs")
    return cases, hashlib.sha256(raw).hexdigest()
