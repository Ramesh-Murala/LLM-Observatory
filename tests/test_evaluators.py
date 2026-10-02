import pytest

from observatory.evaluators import evaluate


@pytest.mark.parametrize(
    "output,expected",
    [
        ('{"count":3}', True),
        ('{"count":"3"}', False),
        ('{"count":true}', False),
        ('```json\n{"count":3}\n```', False),
        ("[]", False),
        ('{"other":3}', False),
    ],
)
def test_json_contract(output, expected):
    case = {"checks": [{"type": "json", "fields": {"count": "int"}}]}
    assert evaluate(case, output)[0].passed is expected


def test_empty_rules_are_rejected():
    with pytest.raises(ValueError):
        evaluate({"checks": []}, "anything")


def test_word_limit_boundary():
    case = {"checks": [{"type": "max_words", "value": 2}]}
    assert evaluate(case, "two words")[0].passed
    assert not evaluate(case, "three whole words")[0].passed


def test_reference_and_exclusion_are_case_insensitive():
    assert evaluate({"checks": [{"type": "exact", "value": "Tokyo"}]}, " tokyo ")[0].passed
    assert not evaluate({"checks": [{"type": "excludes", "value": "secret"}]}, "SECRET")[0].passed
