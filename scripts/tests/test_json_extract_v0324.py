"""LLM 响应 JSON 提取层回归（v0.3.24）

事故背景
--------
2026-10-08 跑 live 冒烟（`test_live_smoke.py --live`），LLM 明显返回了**合法
JSON** —— `finish_reason=stop`、大括号闭合、16K 字符、content 首尾截取
`json.loads` 直接成功 —— 却被旧解析层判成 "LLM returned non-JSON"，
**静默降级到 mock 分镜**。

表现是 10 页全部没有 `keywords`、没有 `[GENDER:xx]`，一直拖到审阅阶段才炸出
30 个 error。temperature=0.7，所以是偶发的 —— 也就是说"看起来跑通了"。

旧解析层的两个真实缺陷：
  1. **手写大括号计数不认字符串字面量** —— visual 里出现一个不平衡的
     { 或 }（英文缩写 / 引文 / 代码片段），depth 永远回不到 0，整段失败
  2. 尾部有多余文字（模型爱在 JSON 后面补"以上"）同样连带失败

新实现用 stdlib 的 `JSONDecoder.raw_decode`（json 自己的扫描器，正确处理
字符串与转义，解析完第一个完整 JSON 值即停），并按可靠度分层尝试、
把尝试记录带进报错信息。

跑法：python scripts/tests/test_json_extract_v0324.py
"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT))

from scripts.core.planner import _extract_json, _raw_decode_first_object, LLMNotConfigured  # noqa: E402

fails = []


def check(label, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}{('  ' + detail) if detail else ''}")
    if not cond:
        fails.append(label)


GOOD = {
    "title": "北海雪十九年",
    "characters": [{"name": "苏武", "role": "主角", "era": "西汉", "gender": "male"}],
    "pages": [{"page": 1, "visual": "CONCEPT: 守 -> 一根光竹 // 苏武 握节",
               "caption": "出塞", "body": "正文", "keywords": ["苏武", "匈奴"]}],
}
GJ = json.dumps(GOOD, ensure_ascii=False, indent=2)

print("=== 1. 干净 JSON（最常见）===")
d, tried = _extract_json(GJ)
check("能解析", d == GOOD, f"tried={tried}")

print("\n=== 2. markdown 围栏 ===")
for fence in ("```json\n%s\n```" % GJ, "```JSON\n%s\n```" % GJ, "```\n%s\n```" % GJ):
    d, _ = _extract_json(fence)
    check(f"围栏 {fence.splitlines()[0][:12]} 能解析", d == GOOD)

print("\n=== 3. thinking 模式前缀 ===")
d, tried = _extract_json(f"<think>\n让我先想想分镜……\n</think>\n\n{GJ}")
check("<think> 前缀能剥离", d == GOOD, f"tried={tried}")

print("\n=== 4. 尾部有多余文字（旧实现在这里会挂）===")
for tail in ("以上。", "\n\n希望对你有帮助！", "Note: 10 pages."):
    d, _ = _extract_json(GJ + "\n" + tail)
    check(f"尾部 {tail[:10]!r} 仍能解析", d == GOOD)

print("\n=== 5. 字符串里含不平衡大括号（旧实现必挂）===")
TRICKY = dict(GOOD)
TRICKY["pages"] = [dict(GOOD["pages"][0], visual="SUBJECT: {unbalanced} 图 // 苏武")]
d, _ = _extract_json(json.dumps(TRICKY, ensure_ascii=False, indent=2))
check("visual 里单独一个 { 能解析", d is not None and d["pages"][0]["visual"] == "SUBJECT: {unbalanced} 图 // 苏武")

TRICKY2 = dict(GOOD)
TRICKY2["pages"] = [dict(GOOD["pages"][0], body="他说「好」}然后走了", dialogue="a{b}c")]
d, _ = _extract_json(json.dumps(TRICKY2, ensure_ascii=False, indent=2))
check("正文/引文里的 } 和 { 混排能解析", d is not None and d["pages"][0]["body"] == "他说「好」}然后走了")

print("\n=== 6. 中文与转义字符 ===")
ESC = dict(GOOD)
ESC["summary"] = '带转义："引号" 与 \\ 反斜杠 与\n换行'
d, _ = _extract_json(json.dumps(ESC, ensure_ascii=False, indent=2))
check("转义/换行往返无损", d is not None and d["summary"] == ESC["summary"])

print("\n=== 7. 真的不是 JSON 时必须明确失败（不能静默）===")
d, tried = _extract_json("抱歉，我无法完成这个请求。")
check("纯文本返回 None", d is None)
check("尝试记录非空（进报错信息）", len(tried) > 0, f"tried={tried}")
d, _ = _extract_json("")
check("空串返回 None", d is None)
d, _ = _extract_json("<think>只有思考没有输出</think>")
check("只有 think 标签返回 None", d is None)

print("\n=== 8. raw_decode 行为 ===")
check("无 '{' 返回 None", _raw_decode_first_object("没有大括号") is None)
check("截断 JSON 返回 None", _raw_decode_first_object('{"a": 1, "b": [1, 2') is None)
check("尾部多余内容仍能解", _raw_decode_first_object('{"a": 1}\n说明文字') == {"a": 1})
check("数组不是 dict → None", _raw_decode_first_object("[1,2,3]") is None)

print("\n=== 9. 关键契约：解析出的 gender 必须是裸字符串 ===")
d, _ = _extract_json(GJ)
g = d["characters"][0]["gender"]
check("gender 是 str", isinstance(g, str) and g in ("male", "female"), f"实际={g!r}")

print("\n=== 10. 异常类型区分（决定是否降级 mock）===")
check("LLMNotConfigured 是 RuntimeError 子类（兼容旧 except）",
      issubclass(LLMNotConfigured, RuntimeError))
check("普通 RuntimeError 不是 LLMNotConfigured（不降级）",
      not issubclass(RuntimeError, LLMNotConfigured))

print()
if fails:
    print(f"FAILED: {len(fails)} 项 -> {fails}")
    raise SystemExit(1)
print("ALL GREEN")
