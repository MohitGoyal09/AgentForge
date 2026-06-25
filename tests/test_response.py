from __future__ import annotations

from agentforge_harness.client.response import parse_tool_call_arguments


def test_empty_string_returns_empty_dict():
    assert parse_tool_call_arguments("") == {}


def test_valid_json_object_is_parsed():
    assert parse_tool_call_arguments('{"path": "README.md"}') == {"path": "README.md"}


def test_invalid_json_is_wrapped_with_correct_key():
    result = parse_tool_call_arguments("{not valid json")
    assert result == {"raw_arguments": "{not valid json"}
    # Regression: key was previously misspelled "raw_arguements".
    assert "raw_arguements" not in result


def test_non_dict_json_is_wrapped_in_dict():
    # Regression: json.loads could return a non-dict, breaking callers that
    # expect a params dict.
    assert parse_tool_call_arguments("123") == {"raw_arguments": 123}
    assert parse_tool_call_arguments('["a", "b"]') == {"raw_arguments": ["a", "b"]}
    assert parse_tool_call_arguments('"hello"') == {"raw_arguments": "hello"}
    assert parse_tool_call_arguments("null") == {"raw_arguments": None}
