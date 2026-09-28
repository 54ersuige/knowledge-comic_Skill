# -*- coding: utf-8 -*-
"""v0.3.2 修复回归测试（不烧 API 额度，全部走 mock / 本地）。

跑法(任意目录): python scripts/tests/test_regression_v032.py

注: 必须显式声明 utf-8 —— 本文件含中文源码字面量，Windows 上 Python
默认按 GBK 解析源码会抛 SyntaxError。
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

# 自解析 skill 根目录（原写法指向文件所在目录，移动后会失效）
SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT))

from scripts.core import prompts as P
from scripts.core.planner import mock_storyboard
import scripts.run as R

FAIL = []


def ck(name, cond, extra=""):
    print(("  PASS " if cond else "  FAIL "), name, extra)
    if not cond:
        FAIL.append(name)


print("=== A. 风格/模板分类器 (P0) ===")
cases = [
    ("张巡守睢阳", "chinese_lianhuanhua_classic", "c"),
    ("王昭君出塞", "chinese_lianhuanhua_classic", "c"),
    ("看石崇与王恺争豪", "chinese_lianhuanhua_classic", "c"),
    ("岳飞抗金", "chinese_lianhuanhua_classic", "c"),
    ("郭子仪单骑退回纥", "chinese_lianhuanhua_classic", "c"),
    ("赤壁之战", "chinese_lianhuanhua_classic", "c"),
    ("李白", "chinese_lianhuanhua_classic", "c"),
    ("论语", "chinese_lianhuanhua_classic", "c"),
    # v0.3.3 名单外用例：人名表里没有"苏武"，也没有朝代词。
    # 这类"史事动作 + 无名人"题材是名单式分类器的结构性短板，
    # 必须由 _looks_like_cn_history() 兜底层覆盖，否则会退回 new_yorker。
    ("苏武牧羊", "chinese_lianhuanhua_classic", "c"),
    ("苏武北海牧羊", "chinese_lianhuanhua_classic", "c"),
    ("范仲淹被贬", "chinese_lianhuanhua_classic", "c"),
    ("卧薪尝胆", "chinese_lianhuanhua_classic", "c"),
    ("塞北戍边", "chinese_lianhuanhua_classic", "c"),
    ("负荆请罪", "chinese_lianhuanhua_classic", "c"),
    ("峰终定律", "new_yorker", "e"),
    ("Transformer 注意力机制", "new_yorker", "e"),
    ("心理学与认知", "new_yorker", "e"),
    ("量子力学", "new_yorker", "e"),
    ("商业模式画布", "us_mid_century", "e"),
    ("品牌设计", "us_mid_century", "e"),
    ("华为与腾讯的竞争", "new_yorker", "e"),
    ("iPhone 与安卓对比", "new_yorker", "e"),
    ("旅行随笔", "new_yorker", "a"),
    ("情感疗愈", "new_yorker", "a"),
    # 兜底层不得误伤：命中现代商战排除词的题眼应回到商业/通用，而不是历史
    # （"产品迭代与用户增长" 命中 _MODERN_BLOCKLIST 的 用户/产品 + 商业强信号 增长）
    ("产品迭代与用户增长", "us_mid_century", "e"),
    # 含拉丁字母 → 不走中文史事兜底
    ("产品迭代与用户增长 v2", "us_mid_century", "e"),
]
bad = []
for t, es, et in cases:
    got_s = P.recommend_style(t)[0]
    got_t = P.recommend_template(t)[0]
    if got_s != es or got_t != et:
        bad.append((t, got_s, got_t))
ck(f"{len(cases)} 组分类全部正确", not bad, str(bad))

print()
print("=== B. mock storyboard ===")
for n in [4, 6, 8, 12]:
    sb = mock_storyboard("测试", ["a", "b", "c"], "chinese_lianhuanhua_classic", num_pages=n)
    nums = [p.page for p in sb.pages]
    ck(f"num_pages={n} 严格生效", len(sb.pages) == n and nums == list(range(1, n + 1)),
       f"(实得 {len(sb.pages)})")
sb = mock_storyboard("测试", ["a"], "chinese_lianhuanhua_classic", num_pages=8)
ck("历史风格降级无现代科学家", "scientist" not in sb.pages[0].visual)

print()
print("=== C. prompt 构造 ===")
for sid in P.STYLES:
    d = P.build_image_prompt(sid, "测试场景 [GENDER:male]", gender="auto")
    ck(f"{sid} 长度<=10000", len(d) <= 10000, f"({len(d)})")

d = P.build_image_prompt("chinese_lianhuanhua_classic", "Wide shot (35mm, low angle, deep focus) 场景")
ck("cinematic 词已剥离",
   "35mm" not in d and "low angle" not in d.lower() and "deep focus" not in d.lower())

d2 = P.build_image_prompt("chinese_lianhuanhua_classic", "男性主角 [GENDER:male]", gender="auto")
d3 = P.build_image_prompt("chinese_lianhuanhua_classic", "女性主角 [GENDER:female]", gender="auto")
ck("性别分支生效", d2 != d3)

from scripts.core.image_gen import _inject_character_lock  # noqa: E402

locked = _inject_character_lock("张巡率军退敌",
                                characters=[{"name": "张巡", "visual_signature": "40yo Tang general, square jaw"}])
ck("角色锁动态派生", "CHARACTER LOCK" in locked and "square jaw" in locked)
legacy = _inject_character_lock("郭子仪单骑退回纥")
ck("legacy 兜底仍生效", "CHARACTER LOCK" in legacy)
none = _inject_character_lock("无名路人走过")
ck("无角色不注入", none == "无名路人走过")

print()
print("=== D. 端到端 render / preflight（不烧额度）===")
tmp = Path(tempfile.mkdtemp())
sb2, job, wd = R.step_plan(
    "张巡守睢阳", ["安史之乱", "孤城苦守", "以少胜多"],
    style_id="chinese_lianhuanhua_classic", template_id="c",
    num_pages=6, use_llm=False, data_dir=tmp,
)
ck("step_plan 产出", len(sb2.pages) == 6, f"(pages={len(sb2.pages)})")
raw = json.loads((wd / "storyboard.json").read_text(encoding="utf-8"))
ck("recommended_template 落盘", raw.get("recommended_template") == "c")

(wd / "pages").mkdir(exist_ok=True)
for i in range(1, 7):
    (wd / "pages" / f"{i:02d}-page.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 2000)

hp = R.step_render_article(job, "c", data_dir=tmp)
ck("render 产出 HTML", hp.exists() and hp.stat().st_size > 1000, f"({hp.stat().st_size} bytes)")
ck("朱砂高亮生效", "#9b2332" in hp.read_text(encoding="utf-8"))

pf = R.step_preflight(job, "c", data_dir=tmp)
failed_names = [c["name"] for c in pf["checks"] if not c["ok"]]
ck("preflight 对正常图放行", pf["ok"], str(failed_names) if not pf["ok"] else "")

(wd / "pages" / "03-page.png").write_bytes(b"")
pf2 = R.step_preflight(job, "c", data_dir=tmp)
ck("preflight 拦截 0 字节图",
   (not pf2["ok"]) and any(c["name"] == "image_empty" for c in pf2["checks"]))

shutil.rmtree(tmp, ignore_errors=True)

print()
print("=== E. 正文长度代码层兜底 (v0.3.4) ===")
# planner prompt 早就承诺「超过 150 字自动砍到 150」，但代码里一直没实现。
# 实测真实 LLM 正文达标率 5/10~9/10 波动，说明光靠 prompt 约束不住，
# 用户"文字不能过多"的硬偏好必须由代码层守住。
from scripts.core.planner import _clamp_body  # noqa: E402

ck("不超限原样返回", _clamp_body("短正文。") == "短正文。")
ck("150 字整原样保留", len(_clamp_body("字" * 150)) == 150)
ck("151 字截到 150", len(_clamp_body("字" * 151)) == 150)
ck("300 字截到 150", len(_clamp_body("字" * 300)) == 150)
ck("句号边界收刀", _clamp_body("甲" * 145 + "。" + "乙" * 100).endswith("。"))
ck("空串安全", _clamp_body("") == "")

print()
print("=== F. 分镜脚本：画面速记不出中英残骸 (v0.3.5) ===")
# 教训：逐词替换 LLM 自由英文必然产出 "雪y" / "跪ing" 这类拼接垃圾，
# 比英文原文更难读。正确策略是"抽取而非翻译"——要么干净中文，要么完整英文。
from scripts.core.story_script import _seg, render_script  # noqa: E402

# 能译出的 → 中文
ck("人名道具动作 -> 中文",
   _seg("SUBJECT: Su Wu holding staff, kneeling in snow;", "subject") == "苏武 手捧 旌节 跪地")
ck("长词吃掉短词(竹杖旌节 不重复 旌节)",
   "旌节 旌节" not in _seg("SUBJECT: Su Wu presenting the bare bamboo staff;", "subject"))
ck("动作段 -> 中文", "跪地" in _seg("ACTION: Su Wu kneels deeply, bowing;", "action"))
# 译不出的 → 保留完整英文，不产出半吊子
out = _seg("SUBJECT: a hermit philosopher in tattered robes, elongated;", "subject")
ck("译不出时保留英文原文", "hermit" in out and "跪" not in out)
# 不得出现中英拼接残骸
for bad in ("雪y", "跪ing", "芦苇荡s", "汉使 ,"):
    ck(f"无拼接残骸 {bad!r}", bad not in _seg("SUBJECT: Su Wu kneeling in snow by reeds, 汉使 ,", "subject"))

md = render_script({
    "topic": "T", "title": "测试", "style_id": "chinese_lianhuanhua_classic",
    "recommended_template": "c",
    "pages": [{
        "page": 1, "highlight": "起", "caption": "题",
        "body": "正文内容在这里。" * 12, "keywords": ["甲", "乙"],
        "visual": "SUBJECT: Su Wu holding staff; ACTION: Su Wu kneels; BACKGROUND: snow",
    }],
})
ck("脚本含三行结构", all(k in md for k in ("文字：", "高亮：", "画面：")))

print()
print("=" * 46)
print("FAILED:", FAIL if FAIL else "NONE — 全部通过")
sys.exit(1 if FAIL else 0)
