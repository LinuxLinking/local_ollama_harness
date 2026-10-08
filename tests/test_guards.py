"""步骤裁决的确定性单测。

用 FakeLLM 按预设剧本回放，不依赖真实模型。覆盖：
  防循环：连续完全相同 (Action, Input) → 回喂干预，达到阈值强停。
  验证前置：write_file 后没 run_python 就 Final Answer → 拦截逼验证。
  验证后收尾：run_python 退出码 0 后又调工具 → 拦截逼收尾。
  验证强制：write_file 后连续做非 run_python 动作 → harness 代跑并回喂真实结果。
  空输出：空回复不当作 Final Answer → 回喂逼收尾。

跑法（项目根目录）：
    .venv/Scripts/python.exe tests/test_guards.py
"""
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pypilot.agent import Agent  # noqa: E402

SANDBOX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sandbox")
F = os.path.join(SANDBOX, "f.py")


class _Resp:
    def __init__(self, content):
        self.content = content


class FakeLLM:
    """按给定剧本依次返回固定输出。"""
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        return _Resp(self.script.pop(0))


def _cleanup():
    if os.path.exists(F):
        os.remove(F)


def _run(name, script, expect_substr):
    _cleanup()
    agent = Agent(verbose=True, llm=FakeLLM(script))
    result = agent.run("测试任务")
    ok = expect_substr in result
    print(f"\n[{name}] {'PASS' if ok else 'FAIL'}")
    if not ok:
        print(f"  期望包含: {expect_substr!r}")
        print(f"  实际 final: {result!r}")
    _cleanup()
    return ok


# write_file → 跳过验证直接 Final Answer → 应被拦截逼回 run_python
VERIFY_FIRST_CASE = [
    'Thought: 写文件\nAction: write_file\nAction Input: {"path": "f.py", "content": "print(1)"}',
    'Thought: 修好了\nFinal Answer: 已创建 f.py 并运行，退出码 0，正常。',
    'Thought: 跑验证\nAction: run_python\nAction Input: {"path": "f.py"}',
    'Thought: 验证通过\nFinal Answer: 已创建并验证 f.py，退出码 0，输出 1。',
]

# write_file → run_python 退出码0 → 又 read_file（不收尾）→ 应被拦截逼收尾
FINALIZE_CASE = [
    'Thought: 写文件\nAction: write_file\nAction Input: {"path": "f.py", "content": "print(1)"}',
    'Thought: 跑验证\nAction: run_python\nAction Input: {"path": "f.py"}',
    'Thought: 再看一眼\nAction: read_file\nAction Input: {"path": "f.py"}',
    'Thought: 验证通过\nFinal Answer: 已创建并验证 f.py，退出码 0。',
]

# 连续 read_file 同样输入 5 次 → 重复计数到 4 → 强停
REPEAT_STOP_CASE = [
    'Thought: 看\nAction: read_file\nAction Input: {"path": "f.py"}',
    'Thought: 再看\nAction: read_file\nAction Input: {"path": "f.py"}',
    'Thought: 再看\nAction: read_file\nAction Input: {"path": "f.py"}',
    'Thought: 再看\nAction: read_file\nAction Input: {"path": "f.py"}',
    'Thought: 再看\nAction: read_file\nAction Input: {"path": "f.py"}',
    # 第 6 条不应被用到（强停在第 5 步之后）；留一条防越界
    'Thought: 兜底\nFinal Answer: 不该到这里',
]

# 第 1 次重复给泛泛警告，第 2 次起换成可直接照抄的具体模板
REPEAT_NUDGE_CASE = [
    'Thought: 看\nAction: read_file\nAction Input: {"path": "f.py"}',
    'Thought: 再看\nAction: read_file\nAction Input: {"path": "f.py"}',   # repeat=1 泛泛警告
    'Thought: 又看\nAction: read_file\nAction Input: {"path": "f.py"}',   # repeat=2 具体模板
    'Thought: 修好它\nAction: write_file\nAction Input: {"path": "f.py", "content": "print(1)"}',
    'Thought: 跑验证\nAction: run_python\nAction Input: {"path": "f.py"}',
    'Thought: 验证通过\nFinal Answer: 已修复并验证 f.py。',
]


# write_file → 不 run_python，而是 read_file → 又 write_file →
# 连续 2 次非 run_python 动作被拦，harness 代跑 run_python → 回喂真实结果 → 收尾
FORCE_VERIFY_CASE = [
    'Thought: 写文件\nAction: write_file\nAction Input: {"path": "f.py", "content": "print(1)"}',
    'Thought: 再看看\nAction: read_file\nAction Input: {"path": "f.py"}',
    'Thought: 又写一遍\nAction: write_file\nAction Input: {"path": "f.py", "content": "print(1)"}',
    'Thought: 验证通过\nFinal Answer: 已创建并验证 f.py，退出码 0，输出 1。',
]


def _run_force_verify():
    """除 final 外，额外断言 harness 确实代跑了 run_python。"""
    _cleanup()
    agent = Agent(verbose=True, llm=FakeLLM(FORCE_VERIFY_CASE))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = agent.run("测试验证强制")
    out = buf.getvalue()
    took_over = "harness 代为验证" in out
    ok = took_over and "已创建并验证 f.py" in result
    print(f"\n[验证强制] {'PASS' if ok else 'FAIL'}")
    if not ok:
        print(f"  harness 代跑: {'是' if took_over else '否'}")
        print(f"  实际 final: {result!r}")
    _cleanup()
    return ok


def _run_repeat_nudge():
    """断言：第 1 次重复是泛泛警告，第 2 次换成可直接照抄的具体模板。"""
    _cleanup()
    with open(F, "w", encoding="utf-8") as fh:
        fh.write("print(0)\n")
    agent = Agent(verbose=True, llm=FakeLLM(REPEAT_NUDGE_CASE))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = agent.run("测试防循环二次升级")
    out = buf.getvalue()
    generic_first = "请推进到下一步" in out      # 第 1 次：泛泛警告
    concrete = "第二次了" in out and "照抄下面三行" in out  # 第 2 次：可照抄模板
    ok = generic_first and concrete and "已修复并验证 f.py" in result
    print(f"\n[防循环模板升级] {'PASS' if ok else 'FAIL'}")
    if not ok:
        print(f"  第1次泛泛警告={'有' if generic_first else '无'}  "
              f"第2次具体模板={'有' if concrete else '无'}  final={result!r}")
    _cleanup()
    return ok


# 模型一整轮吐空字符串 → 不能当 Final Answer → 回喂逼它收尾
EMPTY_OUTPUT_CASE = [
    'Thought: 写文件\nAction: write_file\nAction Input: {"path": "f.py", "content": "print(1)"}',
    'Thought: 跑验证\nAction: run_python\nAction Input: {"path": "f.py"}',
    '',
    'Thought: 总结\nFinal Answer: 已创建并验证 f.py，退出码 0，输出 1。',
]


def _run_empty_output():
    """断言：空输出不被当成 Final Answer，回喂后拿到真正的回答。"""
    _cleanup()
    agent = Agent(verbose=True, llm=FakeLLM(EMPTY_OUTPUT_CASE))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = agent.run("测试空输出兜底")
    out = buf.getvalue()
    nudged = "输出是空的" in out
    ok = nudged and "已创建并验证 f.py" in result
    print(f"\n[空输出兜底] {'PASS' if ok else 'FAIL'}")
    if not ok:
        print(f"  回喂={'有' if nudged else '无'}  实际 final={result!r}")
    _cleanup()
    return ok


def main():
    results = []
    results.append(("验证前置兜底", _run("验证前置", VERIFY_FIRST_CASE, "已创建并验证 f.py")))
    results.append(("验证后收尾兜底", _run("验证后收尾", FINALIZE_CASE, "已创建并验证 f.py")))
    results.append(("验证强制兜底", _run_force_verify()))
    results.append(("防循环二次升级", _run_repeat_nudge()))
    results.append(("空输出兜底", _run_empty_output()))

    # read_file 已存在文件，测防循环强停
    _cleanup()
    with open(F, "w", encoding="utf-8") as fh:
        fh.write("print(1)\n")
    agent = Agent(verbose=True, llm=FakeLLM(REPEAT_STOP_CASE))
    result = agent.run("测试防循环")
    ok = "反复重复同一操作" in result
    results.append(("防循环强停", ok))
    print(f"\n[防循环强停] {'PASS' if ok else 'FAIL'}  final={result!r}")
    _cleanup()

    print("\n========== 汇总 ==========")
    all_ok = True
    for name, ok in results:
        print(f"  {'✓' if ok else '✗'} {name}")
        all_ok = all_ok and ok
    print("全部通过" if all_ok else "有失败")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
