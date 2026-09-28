# -*- coding: utf-8 -*-
"""v0.3.2 修复回归测试（不烧 API 额度，全部走 mock / 本地）。

跑法(任意目录): python scripts/tests/test_regression_v032.py

注: 必须显式声明 utf-8 —— 本文件含中文源码字面量，Windows 上 Python
默认按 GBK 解析源码会抛 SyntaxError。
"""
import json
import re
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
print("=== F. 分镜要素抽取 + 内嵌进 layout_preview (v0.3.6) ===")
# 教训：逐词替换 LLM 自由英文必然产出 "雪y" / "跪ing" 这类拼接垃圾，
# 比英文原文更难读。正确策略是"抽取而非翻译"——要么干净中文，要么完整英文。
# v0.3.6 起这些要素直接内嵌进 layout_preview.html（Checkpoint 1 唯一产物）。
from scripts.core.story_script import _seg, page_elements  # noqa: E402
from scripts.core.article import render_layout_preview  # noqa: E402
from scripts.core.planner import Storyboard, StoryPage  # noqa: E402

# 能译出的 → 中文
ck("人名道具动作 -> 中文",
   _seg("SUBJECT: Su Wu holding staff, kneeling in snow;", "subject")
   == "苏武 手捧 旌节 跪地 雪")
ck("长词吃掉短词",
   "旌节 旌节" not in _seg("SUBJECT: Su Wu presenting the bare bamboo staff;", "subject"))
ck("动作段 -> 中文", "跪地" in _seg("ACTION: Su Wu kneels deeply, bowing;", "action"))
# 译不出的 → 保留完整英文，不产出半吊子
out = _seg("SUBJECT: a hermit philosopher in tattered robes, elongated;", "subject")
ck("译不出时保留英文原文", "hermit" in out and "跪" not in out)
for bad in ("雪y", "跪ing", "芦苇荡s"):
    ck(f"无拼接残骸 {bad!r}", bad not in _seg("SUBJECT: Su Wu kneeling in snow by reeds;", "subject"))

ck("page_elements 同时支持 dict 与 dataclass",
   len(page_elements({"visual": "SUBJECT: Su Wu;"})) == 1
   and len(page_elements(StoryPage(page=1, visual="SUBJECT: Su Wu;"))) == 1)

# v0.3.7：用户反馈「有英文看不懂 + 内容显示不全」。
# 解法是让 planner 在每段写 `// 中文速记`，抽取时优先用它。
_v = ("Character bible: [GENDER:male] SUBJECT: Su Wu, a Han-Chinese diplomat "
      "// 苏武 汉使; SECONDARY: two attendants // 双侍从; "
      "ACTION: Su Wu kneeling in snow // 跪雪地; "
      "CAMERA: Extreme wide shot, high angle, 24mm, deep focus // 大远景 俯拍; "
      "MOOD: somber, desaturated blue-white // 肃穆 低饱和")
ck("速记优先于英文", _seg(_v, "subject") == "苏武 汉使")
ck("速记-景别", _seg(_v, "camera") == "大远景 俯拍")
ck("速记-情绪", _seg(_v, "mood") == "肃穆 低饱和")
ck("Character bible 前缀不吞掉 SUBJECT", "苏武" in _seg(_v, "subject"))
ck("同标签多次出现取最后一个",
   _seg("SUBJECT: Su Wu a // 甲; ACTION: x // 乙; SUBJECT 2: Li Ling b", "subject") == "李陵")

# 无速记时靠术语词典兜底（老数据路径）
ck("无速记-术语词典翻景别",
   _seg("CAMERA: wide shot, low angle", "camera") == "远景 仰拍")
ck("无速记-术语词典翻情绪",
   _seg("MOOD: somber, desaturated palette", "mood").startswith("肃穆 低饱和"))

# v0.3.7: LLM 常改用 Foreground/Midground/Background 自然段写法，
# 抽取器必须同时认这两种格式，否则「主体/景别」会空、「背景」显示英文。
_vb = ("Character bible: Su Wu, 45yo envoy. [GENDER:male] Expression: grim_resolve. "
       "Wide establishing shot, low angle, 24mm lens, deep focus. "
       "Foreground: heavy iron chains casting long shadows. "
       "Midground: Su Wu sitting in a dark cell, staff visible. "
       "Background: vast grey sky, distant snow-capped mountains. "
       "Lighting: hard overhead sunlight. Mood: solemn, desaturated blue-grey.")
ck("B写法-背景", _seg(_vb, "background") != "")
ck("B写法-情绪", _seg(_vb, "mood") != "")
ck("B写法-景别(混在角色段)", "远景" in _seg(_vb, "camera") or "全景深" in _seg(_vb, "camera"))
ck("B写法-动作(取 Midground)", "苏武" in _seg(_vb, "action"))
_els = page_elements({"visual": _vb})
ck("B写法 page_elements 六要素不全空", len(_els) >= 4, "(%d 项)" % len(_els))
ck("B写法 page_elements 全部无省略号",
   all("…" not in v for _, v in _els))

# v0.3.7：不得出现「…」截断残缺
_hard = "BACKGROUND: vast snowy horizon, distant city walls with flying eaves"
ck("长内容不出现省略号截断", "…" not in _seg(_hard, "background"))

# layout_preview 内嵌
_sb = Storyboard(topic="T", style_id="chinese_lianhuanhua_classic", pages=[
    StoryPage(page=1, visual="SUBJECT: Su Wu; // 苏武", body="正文。" * 20,
              caption="题", highlight="起", keywords=["苏武", "北海"]),
    StoryPage(page=2, visual="ACTION: Li Ling weeps; // 李陵", body="正文。" * 20,
              caption="题2", highlight="承", keywords=["李陵"]),
])
_html = render_layout_preview(_sb, template="c")
ck("layout_preview 含分镜意图块", _html.count("本图分镜意图") == 2)
ck("layout_preview 含要素标签", _html.count(">主体<") + _html.count(">动作<") == 2)
ck("layout_preview 含关键词", _html.count("关键词：") == 2)
ck("layout_preview CSS 已注入", ".kcf-note{" in _html)
ck("layout_preview 占位图用 data URI", "data:image/svg" in _html)
ck("HTML 未被 _esc 转义成可见文本", "&lt;div" not in _html)

print()
print("=== G. 排版结构化 + 引号不被劈开 (v0.3.8) ===")
# 用户反馈「不要出现大段大段文字，读者没耐心」+ 发现引号被切出裸露的 ”
from scripts.core.article import (  # noqa: E402
    _first_sentence, _split_paragraphs, _split_sentences,
)

_body = ("匈奴单于试图用高墙囚禁苏武。起初是软禁，试图消磨意志。"
         "苏武被安置在冰窖中。这是外交史上的罕见案例。")
_segs = _split_paragraphs(_body)
ck("正文被切成多段", len(_segs) >= 3, "(%d 段)" % len(_segs))
ck("无超长段落", all(len(s) <= 60 for s in _segs),
   "最长 %d 字" % max(len(s) for s in _segs))
ck("无碎片段落", all(len(s) >= 12 for s in _segs),
   "最短 %d 字" % min(len(s) for s in _segs))
ck("切分后无内容丢失", "".join(_segs).replace(" ", "") == _body.replace(" ", ""))

# 引号：切分点必须在引号闭合之后
_q = '苏武以“宁死不负汉节”自明心志。匈奴单于赞其“勇士”。'
ck("引号不被劈开", all(s.count("“") == s.count("”")
                    for s in _split_paragraphs(_q)))
ck("_split_sentences 也不劈引号",
   all(s.count("“") == s.count("”") for s in _split_sentences(_q)))
ck("_first_sentence 保留句号",
   _first_sentence("第一句。第二句。") == "第一句。")
ck("_first_sentence 引号内句号不被提前截断",
   _first_sentence('他说“好”。然后走了。') == '他说“好”。')

# 真实渲染：整页不该再出现 >60 字的裸文本块（导语/金句除外）
_html_c = render_layout_preview(_sb, template="c")
_txt = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", _html_c, flags=re.S)
_txt = re.sub(r"<[^>]+>", "|", _txt)
_long = [b.strip() for b in _txt.split("|") if len(b.strip()) > 90]
ck("渲染后无 90 字以上裸文本块", not _long, str(_long[:1]))

# v0.3.8.1：正文不缩进。首行缩进是"印刷体连续正文"的规矩，
# 现在一句一段、靠段间距标明边界，缩进只会让左边参差。
ck("正文不含首行缩进", "text-indent" not in _html_c)
ck("e 模板正文也不含缩进",
   "text-indent" not in render_layout_preview(_sb, template="e"))

# v0.3.8.1：「定格瞬间」曾用 _extract_quote(body) 从正文抽句子当引文，
# 导致和正文段落完全重复。无 dialogue 时宁可不渲染这张卡。
_html_dup = render_layout_preview(_sb, template="c")
# HTML 里「定 格 瞬 间」字间有 span/空格，直接找关键片段
ck("无 dialogue 时不渲染定格瞬间卡",
   "瞬" not in _html_dup and "定 格" not in _html_dup,
   "(实际出现 %d 次)" % _html_dup.count("瞬"))
_sb_dlg = Storyboard(topic="T", style_id="chinese_lianhuanhua_classic", pages=[
    StoryPage(page=1, visual="SUBJECT: Su Wu; // 苏武", body="正文第一句。正文第二句。",
              caption="题", highlight="起", keywords=["苏武"], dialogue="宁死不屈。"),
])
_h = render_layout_preview(_sb_dlg, template="c")
ck("有 dialogue 时渲染定格瞬间卡", "瞬" in _h and "定" in _h)
ck("定格瞬间内容取自 dialogue", "宁不死" in _h or "宁死不屈" in _h)

# v0.3.8: planner prompt 侧的约定也锁住，避免以后改 prompt 时回退
from scripts.core.planner import PLANNER_SYSTEM_PROMPT as _PS  # noqa: E402

ck("prompt 要求 body 写成短句", "3-5 个短句" in _PS)
ck("prompt 说明 dialogue 不得复制 body",
   "不能" in _PS and "dialogue" in _PS and "重复" in _PS)

# v0.3.9: `// 中文速记` 绝不能进图像 prompt。
# 实测苏武牧羊：带速记跑图 10 张全部跑偏成彩绘风/庭院景，
# 雪原/地窖/草原全被画成中式庭院 —— 中文速记冲淡了风格锁定。
from scripts.core.prompts import build_image_prompt  # noqa: E402

_v_with_note = ("SUBJECT: Su Wu, a Han-Chinese envoy, wearing dark robe; // 苏武 汉使 出塞 雪原 "
                "ACTION: Su Wu walking, leading a large flock of sheep; // 苏武 牧羊 羊群 远景 "
                "BACKGROUND: vast grey sky, distant snow-capped mountains; // 雪 群山 地平线 "
                "MOOD: solemn, desaturated blue-white palette; // 肃穆 低饱和 "
                "LIGHTING: hard overhead sunlight")
_p_clean = build_image_prompt("chinese_lianhuanhua_classic", _v_with_note, gender="auto")
_i = _p_clean.find("Scene:")
_j = _p_clean.find("Composition")
_scene = _p_clean[_i:_j] if _j > _i else _p_clean
ck("图像 prompt 已剥离中文速记", "苏武 汉使 出塞 雪原" not in _p_clean)
ck("图像 prompt 保留英文描述", "flock of sheep" in _p_clean)
ck("图像 prompt 保留七要素标签", all(
    t.lower() in _p_clean.lower()
    for t in ("SUBJECT", "ACTION", "BACKGROUND", "MOOD")))
ck("剥离后仍有风格锁定", _p_clean.count("classical Chinese painted illustration") >= 1)

print()
print("=" * 46)
print("FAILED:", FAIL if FAIL else "NONE — 全部通过")
sys.exit(1 if FAIL else 0)
