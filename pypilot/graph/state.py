"""运行状态定义。"""
from typing import Annotated, Any

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]

    user_input: str

    step: int
    raw_text: str
    action: str | None
    action_input: Any

    last_step: tuple | None
    last_action: str | None
    last_obs: str | None

    repeat_count: int
    force_verify_count: int
    empty_count: int
    finalize_count: int
    parse_fail_count: int

    need_verify: bool
    pending_path: str | None

    decision: str
    observation: str
    forced_action: str | None
    forced_input: Any

    stop_reason: str
    summary: str
    final: str


def new_turn(user_input: str) -> dict:
    """构造一次任务调用的初始状态。"""
    return {
        "messages": [HumanMessage(user_input)],
        "user_input": user_input,
        "step": 0,
        "raw_text": "",
        "action": None,
        "action_input": None,
        "last_step": None,
        "last_action": None,
        "last_obs": None,
        "repeat_count": 0,
        "force_verify_count": 0,
        "empty_count": 0,
        "finalize_count": 0,
        "parse_fail_count": 0,
        "need_verify": False,
        "pending_path": None,
        "decision": "",
        "observation": "",
        "forced_action": None,
        "forced_input": None,
        "stop_reason": "",
        "summary": "",
        "final": "",
    }
