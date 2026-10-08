"""节点实现。"""
from langchain_core.messages import AIMessage, HumanMessage

from pypilot.config import MAX_ITERATIONS
from pypilot.graph.state import AgentState
from pypilot.guards.policy import (
    FINAL,
    HARNESS_VERIFY,
    OBSERVE,
    PARSE_ERROR,
    STOP,
    TOOL,
    GuardView,
    evaluate_guards,
)
from pypilot.memory.checkpointer import build_summary, needs_summary
from pypilot.memory.context import build_context
from pypilot.prompts import nudges
from pypilot.protocol.react import parse_react
from pypilot.tools.builtin import call_tool


class Ui:
    """终端输出出口，verbose 可在运行时切换。"""

    def __init__(self, verbose: bool = True):
        self.verbose = bool(verbose)

    def step(self, n: int, text: str) -> None:
        if not self.verbose:
            return
        print(f"\n--- step {n} ---")
        print(text)

    def observation(self, obs: str, *, full: bool = False) -> None:
        if not self.verbose:
            return
        if full or len(obs) < nudges.OBS_TRUNCATE_LIMIT:
            shown = obs
        else:
            shown = obs[: nudges.OBS_TRUNCATE_LIMIT] + nudges.OBS_TRUNCATE_MARK
        print(f"Observation: {shown}")

    def harness(self, path: str) -> None:
        if not self.verbose:
            return
        print(nudges.HARNESS_VERBOSE.format(path=path))


def make_model_node(llm, ui: Ui):
    """调用模型并解析输出。"""

    def model_node(state: AgentState) -> dict:
        step = state.get("step", 0) + 1
        ctx = build_context(state.get("messages", []), summary=state.get("summary") or "")
        try:
            resp = llm.invoke(ctx)
        except Exception as e:
            return {"step": step, "raw_text": "", "final": nudges.llm_error_final(e)}

        text = resp.content if isinstance(resp.content, str) else str(resp.content)
        ui.step(step, text)
        action, action_input = parse_react(text)
        return {
            "step": step,
            "raw_text": text,
            "action": action,
            "action_input": action_input,
            "messages": [AIMessage(text)],
        }

    return model_node


def make_guard_node(ui: Ui):
    """执行步骤裁决，写回状态。"""

    def guard_node(state: AgentState) -> dict:
        view = GuardView(
            action=state.get("action"),
            action_input=state.get("action_input"),
            last_step=state.get("last_step"),
            last_action=state.get("last_action"),
            last_obs=state.get("last_obs"),
            need_verify=state.get("need_verify", False),
            pending_path=state.get("pending_path"),
            repeat_count=state.get("repeat_count", 0),
            force_verify_count=state.get("force_verify_count", 0),
            empty_count=state.get("empty_count", 0),
            finalize_count=state.get("finalize_count", 0),
            parse_fail_count=state.get("parse_fail_count", 0),
        )
        out = evaluate_guards(view)

        updates = {
            "decision": out.decision,
            "stop_reason": out.stop_reason,
            "observation": out.observation,
            "repeat_count": state.get("repeat_count", 0) + out.repeat_count,
            "force_verify_count": state.get("force_verify_count", 0) + out.force_verify_count,
            "empty_count": state.get("empty_count", 0) + out.empty_count,
            "finalize_count": state.get("finalize_count", 0) + out.finalize_count,
            "parse_fail_count": state.get("parse_fail_count", 0) + out.parse_fail_count,
        }

        if out.decision in (FINAL, STOP):
            updates["final"] = out.final
        elif out.decision == OBSERVE:
            ui.observation(out.observation)
            updates["messages"] = [HumanMessage(f"Observation: {out.observation}")]
        elif out.decision == HARNESS_VERIFY:
            updates["forced_action"] = out.action
            updates["forced_input"] = out.action_input
        return updates

    return guard_node


def make_act_node(ui: Ui):
    """按裁决执行工具或回喂提示。"""

    def act_node(state: AgentState) -> dict:
        decision = state.get("decision")

        if decision == HARNESS_VERIFY:
            forced = state.get("forced_input") or {}
            path = forced.get("path")
            ui.harness(path)
            obs = call_tool(state.get("forced_action") or "run_python", forced)
            ui.observation(obs, full=True)
            suffix = nudges.harness_obs_suffix(path)
            return {
                "messages": [HumanMessage(f"Observation: {obs}{suffix}")],
                "last_action": "run_python",
                "last_obs": obs,
                "need_verify": False,
                "force_verify_count": 0,
                "finalize_count": 0,
            }

        action = state.get("action")
        action_input = state.get("action_input")

        if decision == PARSE_ERROR:
            obs = state.get("observation") or nudges.parse_failed_obs(str(action_input))
            ui.observation(obs)
            return {"messages": [HumanMessage(f"Observation: {obs}")]}

        obs = call_tool(action, action_input)
        ui.observation(obs)

        updates = {
            "messages": [HumanMessage(f"Observation: {obs}")],
            "last_step": (action, repr(action_input)),
            "repeat_count": 0,
            "last_action": action,
            "last_obs": obs,
            "finalize_count": 0,
        }

        if action == "write_file":
            updates["need_verify"] = True
            updates["force_verify_count"] = 0
            updates["pending_path"] = (
                action_input.get("path") if isinstance(action_input, dict) else None
            )
        elif action == "run_python":
            updates["need_verify"] = False
            updates["force_verify_count"] = 0
        return updates

    return act_node


def loopback_node(state: AgentState) -> dict:
    return {}


def make_max_iter_node():
    def max_iter_node(state: AgentState) -> dict:
        return {"final": nudges.max_iter_final(MAX_ITERATIONS)}

    return max_iter_node


SUMMARIZE_KEEP_LAST = 4


def make_summarize_node(llm, ui: Ui):
    """压缩较早的历史消息。"""

    def summarize_node(state: AgentState) -> dict:
        messages = state.get("messages", [])
        if not needs_summary(messages):
            return {}
        humans = [m for m in messages if isinstance(m, HumanMessage)]
        if len(humans) <= SUMMARIZE_KEEP_LAST:
            return {}
        old = humans[:-SUMMARIZE_KEEP_LAST]
        try:
            summary = build_summary(llm, old)
        except Exception as e:
            if ui.verbose:
                print(f"[摘要失败，已跳过] {type(e).__name__}: {e}")
            return {}
        return {"summary": summary}

    return summarize_node
