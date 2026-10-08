"""ReAct 文本协议解析。"""
import ast
import json
import re


def _salvage_action_input(raw: str):
    """json.loads 失败后的容错解析，成功返回 dict，失败返回 None。"""
    stripped = raw.strip()

    # 从开头解析第一个完整 JSON 对象，忽略尾部多余文字
    try:
        obj, _ = json.JSONDecoder().raw_decode(stripped)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, ValueError):
        pass

    # 兼容三引号 / 单引号等 Python 字面量写法
    try:
        obj = ast.literal_eval(stripped)
        if isinstance(obj, dict):
            return obj
    except (ValueError, SyntaxError):
        pass

    return None


def parse_react(text: str):
    """解析模型输出。

    返回 (action, action_input)：
      - action 为 None  -> Final Answer，action_input 是最终回答文本
      - action 为 str   -> 工具名，action_input 是 dict 或 ("__PARSE_FAILED__", raw)
    """
    text = text.strip()
    # 模型可能自行补写 Observation，截断到第一个 Observation 之前
    if "Observation:" in text:
        text = text.split("Observation:")[0].strip()

    if re.search(r"Final Answer:", text, re.IGNORECASE):
        final = re.split(r"Final Answer:", text, flags=re.IGNORECASE)[-1].strip()
        return None, final

    m_action = re.search(r"Action:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
    m_input = re.search(
        r"Action Input:\s*(.+?)(?:\n\s*(?:Thought|Action|Observation|Final)|\Z)",
        text,
        re.IGNORECASE | re.DOTALL,
    )

    if not m_action:
        return None, text

    action = m_action.group(1).strip()
    raw_input = m_input.group(1).strip() if m_input else ""

    try:
        action_input = json.loads(raw_input)
    except (json.JSONDecodeError, ValueError):
        action_input = _salvage_action_input(raw_input)
        if action_input is None:
            return action, ("__PARSE_FAILED__", raw_input)

    if not isinstance(action_input, dict):
        action_input = {"path": action_input} if action_input else {}

    return action, action_input
