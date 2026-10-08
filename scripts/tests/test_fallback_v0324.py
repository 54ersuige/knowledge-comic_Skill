"""LLM 失败降级契约测试（v0.3.24）

事故背景
--------
2026-10-08 live 冒烟：LLM 返回了**合法 JSON**（`finish_reason=stop`、括号闭合、
16K 字符），旧解析层却判成 "non-JSON"，`plan_storyboard` 捕获 `RuntimeError`
后**无条件降级到 mock**。mock 分镜没有 `keywords`、没有 `[GENDER:xx]` →
朱砂红高亮与性别锚点整条链路静默废掉，10 页全空却"跑完了"，一路拖到审阅
阶段才炸出 30 个 error。

这里锁死降级契约，**不调 LLM**（用桩函数替掉 `_call_llm_storyboard`）：

| 场景 | 期望 |
|---|---|
| `use_llm=False` | 直接 mock，不尝试调用 |
| 没配 key（`LLMNotConfigured`） | **合法离线模式**，降级 + 明确告知 |
| 配了 key 但调用/解析失败 + `allow_mock_fallback=False`（默认） | **抛错**，不降级 |
| 同上 + `allow_mock_fallback=True` | 降级（CI / 离线批量场景） |

跑法：python scripts/tests/test_fallback_v0324.py
"""
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT))

from scripts.core import planner  # noqa: E402
from scripts.core.planner import LLMNotConfigured, plan_storyboard  # noqa: E402

fails = []


def check(label, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}{('  ' + detail) if detail else ''}")
    if not cond:
        fails.append(label)


class _Stub:
    """替掉 _call_llm_storyboard，记录是否被调用过。"""

    def __init__(self, exc=None):
        self.exc = exc
        self.called = 0

    def __enter__(self):
        self._orig = planner._call_llm_storyboard

        def _f(*a, **kw):
            self.called += 1
            if self.exc:
                raise self.exc
            return planner.mock_storyboard(a[0], a[1], a[2], kw.get("num_pages"))

        planner._call_llm_storyboard = _f
        return self

    def __exit__(self, *exc):
        planner._call_llm_storyboard = self._orig
        return False


TOPIC, BULLETS = "张巡守睢阳", ["孤城挡叛军", "百姓送粮", "援军不至"]

print("=== 1. use_llm=False → 直接 mock，不调 LLM ===")
with _Stub(RuntimeError("should not be called")) as s:
    sb = plan_storyboard(TOPIC, BULLETS, "chinese_lianhuanhua_classic", use_llm=False)
check("不抛错", sb is not None)
check("LLM 未被调用", s.called == 0, f"called={s.called}")
check("有页", len(sb.pages) > 0, f"pages={len(sb.pages)}")

print("\n=== 2. 没配 key → 合法降级（LLMNotConfigured）===")
with _Stub(LLMNotConfigured("LLM_API_KEY not configured")) as s:
    sb = plan_storyboard(TOPIC, BULLETS, "chinese_lianhuanhua_classic", use_llm=True)
check("降级成功（不抛错）", sb is not None and len(sb.pages) > 0)
check("确实尝试过 LLM", s.called == 1)

print("\n=== 3. 真故障 + 默认参数 → 必须抛错，不静默降级 ===")
boom = RuntimeError("LLM returned non-JSON. tried=[...]:fail")
with _Stub(boom):
    try:
        plan_storyboard(TOPIC, BULLETS, "chinese_lianhuanhua_classic", use_llm=True)
        check("抛出异常", False, "!!! 竟然静默降级了")
    except RuntimeError as e:
        check("抛出异常", True)
        check("异常信息透传原始原因", "non-JSON" in str(e))

print("\n=== 4. 真故障 + allow_mock_fallback=True → 允许降级 ===")
with _Stub(boom):
    sb = plan_storyboard(TOPIC, BULLETS, "chinese_lianhuanhua_classic",
                         use_llm=True, allow_mock_fallback=True)
check("降级成功", sb is not None and len(sb.pages) > 0)

print("\n=== 5. 契约常量 ===")
import inspect
sig = inspect.signature(plan_storyboard)
check("allow_mock_fallback 有这个参数", "allow_mock_fallback" in sig.parameters)
check("默认 False（不静默降级）",
      sig.parameters["allow_mock_fallback"].default is False,
      f"default={sig.parameters['allow_mock_fallback'].default!r}")

from scripts.run import step_plan  # noqa: E402
ssig = inspect.signature(step_plan)
check("step_plan 也透传了 allow_mock_fallback", "allow_mock_fallback" in ssig.parameters)
check("step_plan 默认也是 False", ssig.parameters["allow_mock_fallback"].default is False)

print()
if fails:
    print(f"FAILED: {len(fails)} 项 -> {fails}")
    raise SystemExit(1)
print("ALL GREEN")
