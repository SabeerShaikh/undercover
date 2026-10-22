"""Tests that tools are module-level and hide ToolRuntime from the model."""

from agent.tools import CLAIM_TOOLS, QUEUE_TOOLS, get_claim, work_one, write_todos


def test_runtime_is_hidden_from_the_model():
    for tool in (*CLAIM_TOOLS, *QUEUE_TOOLS):
        assert "runtime" not in tool.args


def test_claim_tools_need_no_claim_id_argument():
    assert list(get_claim.args) == []


def test_work_claim_takes_only_claim_id():
    assert list(work_one.args) == ["claim_id"]


def test_write_todos_schema_has_items_not_runtime():
    assert "todos" in write_todos.args
    assert "runtime" not in write_todos.args
