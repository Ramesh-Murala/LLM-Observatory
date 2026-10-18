import json

import pytest

from observatory.datasets import parse_dataset
from observatory.engine import run_experiment
from observatory.evaluators import evaluate


def example(**changes):
    case = {"id": "nested-01", "category": "json-schema", "prompt": "Return an order.",
            "baseline": '{"items":[{"quantity":2}]}',
            "candidate": '{"items":[{"quantity":"two"}]}', "checks": [{
                "type": "json_schema", "schema": {
                    "type": "object", "required": ["items"], "additionalProperties": False,
                    "properties": {"items": {"type": "array", "minItems": 1, "items": {
                        "type": "object", "required": ["quantity"],
                        "properties": {"quantity": {"type": "integer", "minimum": 1}},
                        "additionalProperties": False,
                    }}},
                },
            }]}
    case.update(changes)
    return case


def raw(case):
    return (json.dumps(case) + "\n").encode()


def test_nested_schema_is_enforced_before_release():
    run = run_experiment(dataset_raw=raw(example()), dataset_name="orders")
    assert run["dataset"] == "orders"
    assert run["summaries"]["baseline"]["pass_rate"] == 1
    assert run["summaries"]["candidate"]["pass_rate"] == 0
    assert not run["gate"]["passed"]
    assert "type failed at /items/0/quantity" in run["traces"][1]["checks"][0]["reason"]


@pytest.mark.parametrize("changes", [
    {"id": ""}, {"checks": []}, {"prompt": ""}, {"baseline": 42},
    {"checks": [{"type": "max_words", "value": True}]},
    {"checks": [{"type": "unknown"}]},
    {"checks": [{"type": "json", "fields": {"x": "invented"}}]},
    {"checks": [{"type": "json_schema", "schema": {"type": "invented"}}]},
    {"checks": [{"type": "json_schema", "schema": {"$ref": "https://example.invalid"}}]},
])
def test_invalid_contracts_rejected(changes):
    with pytest.raises(ValueError, match="line 1"):
        parse_dataset(raw(example(**changes)))


def test_versions_are_content_addressed_and_bounded():
    data = raw(example())
    assert parse_dataset(data)[1] == parse_dataset(data)[1]
    assert parse_dataset(data)[1] != parse_dataset(data + b"\n")[1]
    for invalid in (b"", b"\xff", data * 201, b"x" * 512_001):
        with pytest.raises(ValueError):
            parse_dataset(invalid)


@pytest.mark.parametrize("output", [
    '{"items":[{"quantity":true}]}', '{"items":[]}',
    '{"items":[{"quantity":0}]}', '{"items":[{"quantity":2}],"extra":1}',
    '{"items":[{"quantity":2}],"items":[]}', '{"items":NaN}', '{"items":1e999}',
])
def test_schema_output_boundaries(output):
    assert not evaluate(example(), output)[0].passed


def test_document_local_schema_reference():
    case = example(checks=[{"type": "json_schema", "schema": {
        "$defs": {"count": {"type": "integer", "minimum": 1}},
        "type": "object", "required": ["count"],
        "properties": {"count": {"$ref": "#/$defs/count"}},
    }}])
    cases, _ = parse_dataset(raw(case))
    assert evaluate(cases[0], '{"count":3}')[0].passed
    assert not evaluate(cases[0], '{"count":"3"}')[0].passed
