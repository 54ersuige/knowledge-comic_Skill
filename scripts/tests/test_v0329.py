"""v0.3.29 回归测试：new_yorker 风格方向重写 + LLM 解析失败自动重试

两件事都是用户实测反馈驱动的（2026-10-08）。

Bug 1 · new_yorker 画风方向错了
    用户反馈：「我觉得右边的效果还是不好，我要的是 Adrian Tomine 为纽约客创作的
    插画风格」。而原定义写的是
        "editorial cartoon … like a cartoon by Tom Bachtell or Liam Walsh.
         Risograph print style on cream paper …"
    —— Bachtell 是**夸张漫画家**，出的图是"大头漫画"；而 Tomine 的风格恰恰相反。
    Tomine 本人自述（Slate「Working」访谈）：
        "更细致、更讲究构图、永远全彩… 偏柔和的粉彩调平涂色… **完全不写实绘画感**"
    多源一致特征：均匀细墨线（ligne claire）/ 平涂无纹理 / 低对比柔和调色 /
    **写实比例不做夸张脸** / 情绪靠姿态 / 正视角 + 大留白 / Edward Hopper 式城市孤独。

Bug 2 · LLM 偶发返回无法解析的内容 → 整轮失败
    temperature=0.7，实测 6 次运行里 1 次解析失败并抛错（抛错本身是对的，
    v0.3.25 刻意拆掉了静默降级）。但一次偶发就整轮失败、要人手动重跑，
    代价不成比例 —— v0.3.29 加**一次自动重试**，只针对解析失败，不重试 API 异常。

跑法：python scripts/tests/test_v0329.py
"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT))

from scripts.core import planner  # noqa: E402
from scripts.core.prompts import STYLES  # noqa: E402

fails = []


def check(label, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}{('  ' + detail) if detail else ''}")
    if not cond:
        fails.append(label)


# ===== Bug 1：new_yorker 必须是 Tomine 方向 =====
print("=== new_yorker 风格定义（应指向 Adrian Tomine）===")

ny = STYLES["new_yorker"]
en = ny.prompt_en
zh = ny.prompt_zh

check("prompt_en 明确点名 Adrian Tomine", "Adrian Tomine" in en)
check("不再引用夸张漫画家 Tom Bachtell", "Bachtell" not in en)
check("不再引用 Liam Walsh", "Liam Walsh" not in en)
check("不再是 Risograph（那是另一套美学）",
      "Risograph" not in en and "riso" not in en.lower())
check("明令不要夸张漫画脸", "NOT caricature" in en and "NOT big-head" in en)
check("保留 uniform even-weight 墨线（ligne claire）",
      "ligne claire" in en and "EVEN weight" in en)
check("低饱和柔和调色（Tomine 自述的 pastel 平涂）",
      "pastel" in en and "Muted low-contrast" in en)
check("平涂无纹理（他原话：完全不写实绘画感）",
      "no halftone" in en and "no paper grain" in en and "no painterly" in en)
check("写实头身比", "realistic head-to-body proportions" in en)
check("正视角 + 大留白构图",
      "near-orthographic" in en and "negative space" in en)
check("风格名不再自称「讽刺」", "讽刺" not in ny.name_zh)
check("prompt_zh 同步点名 Tomine", "Tomine" in zh)
check("风格名/英文名已对齐插画语义",
      "illustration" in ny.name_en.lower() and "cartoon" not in ny.name_en.lower())


# ===== Bug 2：解析失败自动重试 =====
print("=== LLM 解析失败自动重试 ===")


class _Cfg:
    """不依赖本机 .env 的假配置（key 不能以 sk-placeholder 开头，否则走离线模式）。"""
    llm_api_key = "sk-test-not-a-placeholder"
    llm_base_url = "http://127.0.0.1:1/v1"
    llm_model = "stub-model"


def _valid_json() -> str:
    return json.dumps({
        "title": "t", "subtitle": "s", "summary": "m",
        "pages": [{
            "page": 1, "visual": "SUBJECT: x [GENDER:male]", "caption": "c",
            "dialogue": "d", "narration": "", "body": "正文",
            "keywords": ["k"], "punchline": "p", "key_visual": "kv", "highlight": "h",
        }],
    }, ensure_ascii=False)


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)
        self.finish_reason = "stop"


class _Resp:
    def __init__(self, content):
        self.choices = [_Choice(content)]


def _run(sequence):
    """在打桩环境下跑 plan_storyboard，返回 (结果, 调用次数, 异常)。

    `planner.OpenAI` 在原代码里是**当类调用**的（`OpenAI(api_key=...)`），
    所以这里也必须换成一个**类**；调用次数用闭包 holder 记录
    （实例是在 _call_llm_storyboard 内部创建的，外面拿不到引用）。
    """
    seq = list(sequence)
    holder = {"calls": 0}

    class _Completions:
        def create(self, **_kw):
            i = min(holder["calls"], len(seq) - 1)
            holder["calls"] += 1
            item = seq[i]
            if isinstance(item, Exception):
                raise item
            return _Resp(item)

    class _Chat:
        completions = _Completions()

    class _FakeOpenAI:
        def __init__(self, *_a, **_kw):
            self.chat = _Chat()

    orig_openai, orig_cfg = planner.OpenAI, planner.get_config
    planner.OpenAI = _FakeOpenAI
    planner.get_config = lambda: _Cfg()
    try:
        try:
            sb = planner.plan_storyboard("t", ["a", "b"], "new_yorker", use_llm=True)
            return sb, holder["calls"], None
        except Exception as e:  # noqa: BLE001
            return None, holder["calls"], e
    finally:
        planner.OpenAI, planner.get_config = orig_openai, orig_cfg


# 1) 首次坏、第二次好 -> 应成功，且正好调了 2 次
sb, calls, err = _run(["这不是 JSON >>>", _valid_json()])
check("首次解析失败后自动重试并成功", sb is not None and err is None,
      f"err={type(err).__name__ if err else None}")
check("重试恰好多调一次（共 2 次）", calls == 2, f"实际 {calls} 次")

# 2) 两次都坏 -> 应抛错，且恰好调 2 次（不会无限重试）
sb, calls, err = _run(["坏内容 A", "坏内容 B"])
check("两次都失败则抛错", sb is None and isinstance(err, RuntimeError))
check("失败时也只用 2 次尝试（不无限重试）", calls == 2, f"实际 {calls} 次")
check("报错信息点明尝试次数",
      err is not None and "2 attempts" in str(err), str(err)[:60] if err else "")

# 3) API 异常 -> 不重试（那是网络/额度问题，重试无意义）
sb, calls, err = _run([RuntimeError("boom"), _valid_json()])
check("API 异常不触发重试（只调 1 次）", calls == 1, f"实际 {calls} 次")
check("API 异常直接抛出", err is not None and "LLM API call failed" in str(err))

# 4) 首次就好 -> 只调 1 次
sb, calls, err = _run([_valid_json()])
check("顺利时不做多余调用", calls == 1 and err is None, f"实际 {calls} 次")


print("=" * 60)
if fails:
    print(f"FAILED {len(fails)}:")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print("ALL PASS (v0.3.29 风格方向 + 解析重试)")
sys.exit(0)
