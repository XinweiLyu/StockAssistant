"""Strict tool-result JSON on actual runner and external-tool paths."""

import json
import math
from types import SimpleNamespace

import pytest

from src.agent.llm_adapter import LLMToolAdapter, ToolCall
from src.agent.tools.execution import (
    execute_runner_tool_call,
    redact_external_tool_result,
    serialize_tool_result,
)
from src.agent.tools.registry import ToolDefinition, ToolRegistry


def _reject_constant(token):
    raise ValueError(f"Nonstandard JSON constant: {token}")


def test_runner_tool_result_reaches_adapter_as_strict_json_without_mutating_data():
    raw = {"price": float("nan"), "history": [1.5, float("inf")], "label": "NaN"}
    registry = ToolRegistry()
    registry.register(ToolDefinition(
        name="sample_quote", description="Fixture quote", parameters=[], handler=lambda: raw,
    ))
    _, result, ok, _, _, _ = execute_runner_tool_call(
        tool_call=ToolCall(id="quote_1", name="sample_quote", arguments={}), tool_registry=registry,
    )
    adapter = LLMToolAdapter.__new__(LLMToolAdapter)
    wire = adapter._convert_messages([{
        "role": "tool", "tool_call_id": "quote_1", "content": result,
    }])
    assert ok is True
    assert json.loads(wire[0]["content"], parse_constant=_reject_constant) == {
        "price": None, "history": [1.5, None], "label": "NaN",
    }
    assert math.isnan(raw["price"])
    assert math.isinf(raw["history"][1])


def test_object_tool_result_normalizes_nested_nonfinite_values():
    result = SimpleNamespace(price=float("-inf"), history=[float("nan")], _internal="hidden")
    assert json.loads(serialize_tool_result(result), parse_constant=_reject_constant) == {
        "price": None, "history": [None],
    }


@pytest.mark.parametrize("value", [
    {"price": float("nan"), "api_key": "demo-credential"},
    '{"price": NaN, "api_key": "demo-credential"}',
])
def test_external_result_keeps_redaction_and_strict_json(value):
    result = json.loads(redact_external_tool_result(value), parse_constant=_reject_constant)
    assert result == {"price": None, "api_key": "[REDACTED]"}


@pytest.mark.parametrize("text", ["NaN Infinity", '{"label": "NaN"}'])
def test_literal_string_result_is_unchanged(text):
    assert serialize_tool_result(text) == text
