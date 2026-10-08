"""生图前硬关卡（v0.3.15 新增）。

**为什么需要**：2026-09-28~29 苏武牧羊项目跑了 4 天，挖出的 bug 绝大多数
是**静默失败** —— 不报错、行为与预期不符，跑完才发现。这道关卡的作用是
**把静默失败变成阻塞**，第一次就拦住，不烧图、不烧额度。

拦截清单（都是本项目真实踩过的坑）：
  1. keywords 为空        → 朱砂高亮整条链路失效
  2. 正文含 hedging 表述  → LLM 不确定时的自我暴露（"（或…）""（实际为…）"）
  3. 角色未标 [GENDER]    → 男性被画成女性（p9 常惠事故）
  4. 正文超长/过短        → 违反 100-150 字铁律
  5. 画面无零文字声明     → 模型爱给织物"补"纹样字符
  6. dialogue 非原著引文  → 文言必须出自典籍，不得自造
  7. punchline 缺失/超长  → 「定格瞬间」是记忆点，不能空也不能成段
  8. 疑似编造人物         → 出现角色表之外的人名（如"阿提拉"）
  9. 图文不符（高风险页） → caption 说了但画面没画

用法：
    from scripts.core.preflight import run_preflight
    result = run_preflight(storyboard)
    if result.blocked:
        print(result.report())
        raise SystemExit(1)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# v0.3.24：内容阈值统一走 thresholds.py（唯一真源）。
# 本模块与 review_page / visual_qa / story_script 共用同一份数字，
# 避免"改一处漏一处"（已发生 4 次：keywords 解析层 / CONCEPT 黑名单 /
# prompt 拼装双路径 / 本次 body+keywords 阈值漂移）。
from scripts.core.thresholds import (
    BODY_HARD_HI,
    BODY_TARGET_HI,
    BODY_TARGET_LO,
    BODY_WARN_LO,
    KEYWORDS_IDEAL as KW_IDEAL,
    KEYWORDS_MAX as KW_MAX,
    KEYWORDS_MIN as KW_MIN,
    PUNCH_MAX,
    QUOTE_MAX,
)

# v0.3.18：时代穿帮词表（从 prompts.py 拿，同一份避免两处漂移）
try:
    from scripts.core.prompts import ANACHRONIC_MARKERS
except Exception:  # pragma: no cover - 独立运行时的兜底
    ANACHRONIC_MARKERS = [
        "金质发冠", "龙袍", "龙纹", "补子", "乌纱", "官帽",
        "朝服", "蟒袍", "雕龙", "织金", "点绣", "补服", "顶戴", "翎羽",
        "朝珠", "紫砂", "扶手椅", "沙发", "玻璃窗", "油灯", "蜡烛",
        "机械钟", "折扇", "繁复", "华丽",
    ]

# 正史/权威典籍常见人名 —— 出现**不在**这个集合里、且也不在 storyboard
# 自定义角色里的中文人名，标为"疑似编造"（宁可误报也不漏报，误报可人工确认）
KNOWN_HISTORICAL_NAMES = {
    # 先秦
    "孔子", "老子", "庄子", "孟子", "荀子", "墨子", "韩非", "商鞅", "屈原",
    "孙膑", "廉颇", "蔺相如", "荆轲", "西施", "王昭君", "杨贵妃", "貂蝉",
    "管仲", "鲍叔牙", "晏婴", "专诸", "要离", "勾践", "夫差", "文种", "范蠡",
    "伍子胥", "申包胥", "西施", "范蠡", "文种",
    # 秦汉
    "秦始皇", "刘邦", "项羽", "韩信", "张良", "萧何", "霍去病", "卫青", "李广",
    "司马迁", "班超", "王莽", "董仲舒", "苏武", "李陵", "常惠", "卫律",
    "呼韩邪单于", "王昭君", "昭君", "单于", "冒顿单于", "赵充国",
    # 三国两晋南北朝
    "诸葛亮", "刘备", "关羽", "张飞", "赵云", "曹操", "周瑜", "陆逊", "司马懿",
    "陶渊明", "祖逖", "谢安", "王羲之", "陈寿", "诸葛亮", "司马昭",
    # 隋唐
    "隋炀帝", "李渊", "李世民", "武则天", "唐玄宗", "李白", "杜甫", "白居易",
    "王维", "李靖", "魏征", "郭子仪", "张巡", "许远", "颜真卿", "安禄山",
    "史思明", "郭子仪", "李光弼", "房玄龄", "杜如晦", "魏征", "长孙无忌",
    # 宋元明清
    "岳飞", "文天祥", "辛弃疾", "陆游", "苏轼", "王安石", "寇准", "包拯",
    "曾国藩", "左宗棠", "林则徐", "郑成功", "戚继光", "袁崇焕", "李自成",
    "崇祯", "朱元璋", "朱棣", "康熙", "雍正", "乾隆", "秦桧", "韩世忠",
    "虞允文", "毕再遇", "王坚", "余玠",
    # 近现代
    "孙中山", "鲁迅", "蔡元培", "林则徐",
}

# 常见官职/地名 —— 出现在"人名位置"时不算编造
COMMON_TERMS = {
    "单于", "大月氏", "匈奴", "汉朝", "汉武帝", "汉昭帝", "汉宣帝", "光武帝",
    "匈奴单于", "汉朝皇帝", "皇帝", "太后", "丞相", "将军", "大夫", "尚书",
    "北海", "长安", "洛阳", "边塞", "雁门", "阴山", "贝加尔湖",
}

# hedging 表述 —— LLM 不确定时的自我暴露，绝不能进正文
HEDGING_PATTERNS = [
    re.compile(r"[（(]\s*(?:或|实际为|大约|可能是|据传|相传)\s*[^）)]{0,24}[）)]"),
    re.compile(r"(?:或已死|或空墓|或已改嫁|或空无)"),
    re.compile(r"(?:我不确定|记不清|存疑)"),
]

MODERN_TONE_WORDS = [
    "极限测试", "活体武器", "政治表演", "生存 vs 尊严", "情绪价值",
    "打卡", "种草", "内卷", "破防", "赛道", "降维打击",
]


@dataclass
class Finding:
    page: int | None          # None = 全文级
    level: str                # "block" 阻塞 / "warn" 建议
    code: str
    msg: str
    hint: str = ""


@dataclass
class PreflightResult:
    findings: list[Finding] = field(default_factory=list)

    @property
    def blocks(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "block"]

    @property
    def warns(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "warn"]

    @property
    def blocked(self) -> bool:
        return bool(self.blocks)

    def to_dict(self) -> dict:
        """v0.3.22：落盘 JSON 报告用。

        Returns:
            {"blocked": bool, "findings": [{"page","level","code","msg","hint"}], "ts": float}
        """
        import time
        return {
            "kind": "preflight",
            "blocked": self.blocked,
            "findings": [
                {"page": f.page, "level": f.level, "code": f.code,
                 "msg": f.msg, "hint": f.hint}
                for f in self.findings
            ],
            "ts": time.time(),
        }

    @property
    def ok(self) -> bool:
        return not self.findings

    def report(self) -> str:
        if self.ok:
            return "✅ 生图前体检全部通过"
        lines = []
        if self.blocks:
            lines.append(f"[阻塞] {len(self.blocks)} 个 —— 必须修完才能跑图")
            for f in self.blocks:
                where = f"p{f.page:02d}" if f.page else "全文"
                lines.append(f"   [{f.code}] {where}：{f.msg}")
                if f.hint:
                    lines.append(f"        → {f.hint}")
        if self.warns:
            lines.append(f"[建议] {len(self.warns)} 个")
            for f in self.warns:
                where = f"p{f.page:02d}" if f.page else "全文"
                lines.append(f"   [{f.code}] {where}：{f.msg}")
        return "\n".join(lines)


# --- 单项检查 ---------------------------------------------------------------

def _f_kw(p: dict) -> list[Finding]:
    kws = p.get("keywords") or []
    out = []
    if not kws:
        out.append(Finding(p["page"], "block", "KW_EMPTY",
                           "keywords 为空 —— 朱砂红高亮整条链路会失效",
                           f"planner prompt 铁律 5 要求 {KW_MIN}-{KW_IDEAL} 个；不满足就会渲染不出高亮"))
    elif len(kws) > KW_MAX:
        out.append(Finding(p["page"], "warn", "KW_TOO_MANY",
                           f"keywords {len(kws)} 个偏多，正文里会碎成一片",
                           f"上限 {KW_MAX} 个；v0.3.12 实测：3 个最干净，只选专有名词"))
    elif len(kws) < KW_MIN:
        # v0.3.24 补：review_page 一直查这条、preflight 一直漏，
        # 结果「1 个关键词」的页面能过阻塞关卡。属于阈值漂移的受害面。
        out.append(Finding(p["page"], "warn", "KW_TOO_FEW",
                           f"keywords 仅 {len(kws)} 个，高亮撑不起阅读引导",
                           f"补到 {KW_IDEAL} 个左右，优先专有名词（人名/地名/朝代/官职）"))
    return out


def _f_body_len(p: dict, target_lo: int = BODY_TARGET_LO, target_hi: int = BODY_TARGET_HI,
                hard_hi: int = BODY_HARD_HI, warn_lo: int = BODY_WARN_LO) -> list[Finding]:
    """正文长度。阈值全部来自 thresholds.py（唯一真源）。

    v0.3.15 修正：初版把 100-150 当**硬边界**，结果 p01 93 字 / p02 95 字 /
    p08 154 字全被判不合格。用户的 100-150 是**目标带**（"文字不能过多"），
    真正的风险是文字压过画面，所以边界大幅放宽：
      - 超过 170 字 = 阻塞（文字确实会压过图）
      - 151-170 字 = 建议（微调即可）
      - 低于 90 字 = 建议（内容偏薄）
      - 90-170 字 = 放行
    原则：关卡拦"方向错"，不拦"没到理想值"。

    v0.3.24：原先这 4 个数字是本函数的默认参数字面量，review_page 那边另有一份
    自己的（且更严），已漂移 —— 见 thresholds.py 模块 docstring 的对照表。
    """
    b = (p.get("body") or "").strip()
    n = len(b)
    out = []
    if n == 0:
        out.append(Finding(p["page"], "block", "BODY_EMPTY", "正文为空"))
    elif n > hard_hi:
        out.append(Finding(p["page"], "block", "BODY_LONG",
                           f"正文 {n} 字 > {hard_hi} 字（文字太重会压过画面）",
                           f"目标 {target_lo}-{target_hi} 字/页；"
                           f"只补画面没说的事，不复述画面"))
    elif n > target_hi:
        out.append(Finding(p["page"], "warn", "BODY_LONG_SOFT",
                           f"正文 {n} 字略超目标上限 {target_hi} 字"))
    elif n < warn_lo:
        out.append(Finding(p["page"], "warn", "BODY_SHORT",
                           f"正文 {n} 字偏薄（目标 {target_lo}-{target_hi} 字）"))
    return out


def _f_hedging(p: dict) -> list[Finding]:
    body = p.get("body") or ""
    out = []
    for pat in HEDGING_PATTERNS:
        m = pat.search(body)
        if m:
            out.append(Finding(p["page"], "block", "HEDGING",
                               f"正文含自我不确定表述 {m.group(0)!r}",
                               "LLM 不确定时的自我暴露。要么查证后写对，要么不写"))
            break
    return out


def _f_modern_tone(p: dict) -> list[Finding]:
    text = (p.get("body") or "") + (p.get("punchline") or "") + (p.get("caption") or "")
    out = []
    hits = [w for w in MODERN_TONE_WORDS if w in text]
    if hits:
        out.append(Finding(p["page"], "warn", "MODERN_TONE",
                           f"含现代口水词 {hits}，与史传分寸不符"))
    return out


def _f_gender(p: dict, style_id: str, allowed: set[str]) -> list[Finding]:
    """连环画风格：每个出场角色都要有 gender 锚点。

    **p9 常惠事故的真实失效模式**（v0.3.14 复盘）：
    visual 里出现具名角色「常惠」，既没写 `[GENDER:]`，也不在 storyboard 的
    `characters[]` 里 → 既拿不到角色锚点、也不走 i2i 参考图 → 模型随机性别化，
    男性被画成女性。

    visual 有两种合法写法，对应两种判据：
      A) **段首前缀式**（p9 修复后现用）—— 每个角色一段，每段以 `[GENDER:xx]` 开头：
         ```
         [GENDER:male] Rider: Han man age 35, ...
         [GENDER:male] Standing figure: Han man age 50, ...
         ```
         判据：**每个角色段都必须带 [GENDER] 前缀**，漏一段即阻塞。
      B) **角色 bible 式**（p01/p04 用的）—— 整页一个主角 bible，段内自带标记：
         ```
         Character bible: Su Wu, ... [GENDER:male] ...
         Midground: Su Wu and a second envoy standing on a snowy ridge.
         ```
         判据：**整页有一个标记即可**，配角由 characters[] 锚点 + i2i 兜底。

    v0.3.15 初版 bug：用"两个大写词 = 两个角色"数角色，把 `Lake Baikal (Bei Hai)`、
    `Zhang Zhong` 当地名/修饰词，导致几乎每页 GENDER_PARTIAL 误报。
    原则：**宁可漏报也不误报** —— 漏报 = 人工扫一眼；误报 = 关卡永远报警、
    用户开始无视它。
    """
    if style_id != "chinese_lianhuanhua_classic":
        return []
    v = p.get("visual") or ""
    if not v:
        return []

    # A) 段首前缀式：多角色并列出镜 → 逐段校验
    # v0.3.17：排除七要素标签。`SUBJECT:` / `ACTION:` / `CAMERA:` 和
    # `Rider:` / `Standing figure:` 语法上都是"大写词 + 冒号"，
    # 正则无法区分，只能靠黑名单。实测不加排除会 10/10 页误报。
    actor_lines = [ln.strip() for ln in v.splitlines()
                   if _ACTOR_LINE_RE.match(ln.strip())
                   and not _is_seven_element_label(ln.strip())]
    if len(actor_lines) >= 2:
        missing = [ln for ln in actor_lines
                   if not re.match(r"\[GENDER:\w+\]", ln, re.I)]
        if missing:
            head = re.sub(r"\s+", " ", missing[0])[:48]
            return [Finding(p["page"], "block", "GENDER_PARTIAL",
                            f"本页 {len(actor_lines)} 个角色段，"
                            f"{len(missing)} 段没标 [GENDER]（首个：{head}...）",
                            "前缀式写法要求每个角色段各自带 [GENDER:xx]；"
                            "漏标的那个会被模型随机性别化（p9 常惠事故）")]
        return []

    # B) 角色 bible 式 / 单人页 / 七要素写法
    if not re.search(r"\[GENDER:\w+\]", v, re.I):
        # v0.3.17：必须走**中英双通道**判断"角色是否已登记"。
        # 实测打脸 —— planner 的 visual 用拼音（Gou Jian / Fu Cai / Helu），
        # characters[] 登记的是中文（勾践 / 夫差 / 阖闾），
        # 只按中文匹配会让 `n in allowed` 恒为 False，
        # 9/10 页漏标 GENDER 却一个都不报。
        if _roles_registered(v, p, allowed):
            return []      # 角色登记在 characters[] → 角色锚点兜底
        return [Finding(p["page"], "warn", "GENDER_NONE",
                        "visual 里没有 [GENDER:xx] 标记，且主角未登记进 characters[]",
                        "连环画风格靠它定男女；缺失时主角性别随机。"
                        "二选一：加 [GENDER:male]，或写进 storyboard.characters[]")]
    return []


# planner 稳定输出的英文人名模式：`Name, 35yo` / `Li Ling (40yo, ...)`
_EN_NAME_RE = re.compile(
    r"\b([A-Z][a-z]{1,12}(?:\s+[A-Z][a-z]{1,12})?)\s*[,(\uff08]\s*\d{1,3}\s*yo",
    re.I)


# 角色段行首：`[GENDER:xx] Rider:` 或 `Standing figure:` / `Foreground man:`
_ACTOR_LINE_RE = re.compile(
    r"^\[GENDER:\w+\]|^[A-Z][A-Za-z]*(?:\s+[a-z]+){0,2}\s*:")

# 七要素标签（v0.2.3 画面表达系统）—— 它们是**画面要素**不是角色
#
# v0.3.18 修正：`concept` 必须在内。CONCEPT: 段是本轮新增的画面意图段，
# 语法上同样是"大写词 + 冒号"，v0.3.17 建的这份黑名单没收录它，
# 于是 `_ACTOR_LINE_RE` 把 CONCEPT: 当成角色段 → 只要同页再有第二个
# 大写冒号行（HEADWEAR:/NEGATIVE: 等），GENDER_PARTIAL 必然误报阻塞，
# 整页跑不了图。黑名单漏一项 = 关卡永远报警，用户会开始无视它。
_SEVEN_ELEMENT_LABELS = {
    "subject", "action", "camera", "placement", "depth layers", "depth",
    "lighting", "mood", "expression", "key visual", "foreground",
    "midground", "background", "composition", "color palette", "palette",
    "medium", "shot", "lens", "note", "style", "framing", "angle",
    # v0.3.18 新增
    "concept", "headwear", "negative", "avoid", "palette note", "wardrobe",
}


def _is_seven_element_label(line: str) -> bool:
    """这行是七要素标签吗？（v0.3.17：排除它们，否则 GENDER_PARTIAL 10/10 误报）"""
    m = re.match(r"^\[GENDER:\w+\]\s*", line)
    if m:
        line = line[m.end():]
    m = re.match(r"^([A-Za-z][A-Za-z ]{0,20}?)\s*[:：]", line)
    if not m:
        return False
    return m.group(1).strip().lower() in _SEVEN_ELEMENT_LABELS


def _roles_registered(visual: str, p: dict, allowed: set[str]) -> bool:
    """本页主角是否有 gender 锚点来源？

    **v0.3.17 两次修正的教训**：

    1. 最初只按中文名匹配 `"勾践" in "Gou Jian, 35yo..."` → 恒 False，
       9/10 页漏报。planner 的 visual 用拼音、characters 用中文，两边没有
       共享标识，靠名字匹配跨不了语言。
    2. 试图像正则那样从英文名反推 → 拼音表要硬编码，而角色是 LLM 动态
       生成的，维护不了。**方向本身错了。**

    **正确的问题不是"名字对上了吗"，而是"有没有 gender 锚点来源"**。
    名字匹配只是来源之一，而且是最脆弱的那个。真正的来源有三个：
      a) 本页内联 `[GENDER:xx]`
      b) characters[] 非空 —— build_image_prompt 会用角色锚点拼装，
         单主角页的 gender 由 characters[0] 的 visual_signature 决定
      c) 本页只有一个人物（单人页无歧义，模型不会猜错）

    所以判据改成：b 或 c 任一成立即视为已覆盖。这不依赖跨语言名字匹配，
    因此对拼音/英文/中文三种写法一视同仁。

    **注意 (b) 的依据是管线事实**：characters[] 非空时，
    build_image_prompt 会把该角色锚点前置到**每一页**（v0.3.0 gender 分支），
    所以即使本页主体写作 `Anon`，也仍然有性别锚点，不会随机化。
    """
    # (b) characters[] 非空 → 角色锚点每页都拼进 prompt（管线事实）
    if (p.get("characters") or []) or allowed:
        return True

    # (c) characters[] 为空时，退回"本页具名角色恰好 1 个"→ 无性别歧义。
    # 不能写成 `len(...) == 0`：那会把 `Anon, 30yo` / `Han man` 这类
    # **匿名**描述也放行，而它们没有任何 gender 锚点来源，
    # 模型会随机性别化 —— 正是 p9 常惠事故的形态。
    return len(_named_roles(visual, p)) == 1

def _is_seven_element_label(line: str) -> bool:
    """这行是七要素标签吗？"""
    m = re.match(r"^\[GENDER:\w+\]\s*", line)
    if m:
        line = line[m.end():]
    m = re.match(r"^([A-Za-z][A-Za-z ]{0,20}?)\s*[:：]", line)
    if not m:
        return False
    return m.group(1).strip().lower() in _SEVEN_ELEMENT_LABELS



def _named_roles(visual: str, p: dict) -> list[str]:
    """本页 visual 里出现的**中文具名角色**。

    只认三种来源：
      1. 中文「// 中文速记」注释里的 2 字词（planner 一定会标人名）
      2. 正史人名表里出现的名字
      3. characters[] 里登记的名字
    英文一律不算（地名 Lake Baikal、修饰 Zhang Zhong 都会误报）。
    """
    names: list[str] = []

    # 1) ~~中文速记~~ —— **刻意不做人名识别**。
    # 中文速记是画面元素速记（`勾践 苦胆 雪原 绝望`），人和物混在一起。
    # 靠词表排除"这不是人名"永远补不全（`_GENERIC_VISUAL_WORDS` 里没有
    # "苦胆"，换个题材就又炸）—— 与"百家姓白名单"是同类的错误。
    #
    # 1b) 带**年龄或身份修饰**的具名主语：`勾践，35岁` / `勾践身背长剑` /
    #     `夫差正在帐中` —— planner 描述主体时必然带这类修饰。
    for _m in re.finditer(
            r"([\u4e00-\u9fa5]{2,4})[，,]?\s*"
            r"(?:\d{1,3}\s*(?:岁|yo)|身[背负手执持]|正[在即]|已经|正在)",
            visual):
        names.append(_m.group(1))

    # 2) 正史人名
    for n in KNOWN_HISTORICAL_NAMES:
        if n in visual and n not in COMMON_TERMS:
            names.append(n)

    # 3) characters[]
    for c in (p.get("characters") or []):
        nm = c.get("name") if isinstance(c, dict) else c
        if nm and nm in visual:
            names.append(nm)

    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out






_TITLE_RE = re.compile(r"单于|将军|太尉|校尉|刺史|太守|丞相|国相|大夫|元帅|"
                       r"太子|公主|御史|尚书令")

# 官职/称谓本身 —— 出现时不是人名
_TITLE_WORDS = {
    "御史", "太守", "都尉", "丞相", "国相", "尚书", "尚书令", "大夫", "少府",
    "将军", "大将军", "副将", "骑将", "车骑", "轻车", "游骑", "司马", "司徒",
    "司空", "司隶", "中郎", "郎中", "门郎", "主簿", "掾史", "令史", "廷尉",
    "光禄", "卫尉", "宗正", "太仆", "大鸿胪", "典客", "鸿胪", "鸿胪卿",
    "单于", "左贤王", "右贤王", "左谷蠡王", "右谷蠡王", "王", "君", "公",
    "侯", "帝", "太后", "皇后", "太子", "公主", "大王", "天王", "元帅",
}

# 功能字/方位字 —— 候选以它结尾说明只抓到半截短语（"汉朝大"、"太守与"）
_FUNC_CHARS = set("与和及率自大朝军兵的在了是为从向对把被让其此这那便都还也很更"
                  "且但因所又再已曾将欲能可不无并则即乃于其之间内外前后上下中"
                  "左右大小新旧一二三四五六七八九十百千万数众等称谓")

def _f_fabricated(p: dict, allowed: set[str]) -> list[Finding]:
    """疑似编造人物。

    **v0.3.15 两次修正**：
    1. 初版把"意识到""试图用"这种动词短语当人名（只匹配"姓+名"结构太宽）。
    2. 二版改用百家姓白名单，结果漏掉"阿提拉单于" —— 阿 不在前 100 姓里，
       测试直接打脸。**白名单本身就是错的做法**：判断是否编造，靠的是
       "它带身份头衔却不见于正史"，不是"它姓什么"。

    现判据：具名头衔（单于/将军/太子/公主/太尉/刺史/太守…）前挂 2-3 个汉字，
    且该词不在正史人名表、常见词表、characters[] 里 → 疑似编造。
    这正是苏武项目出现过的虚构人物「阿提拉单于」的形态。
    """
    text = (p.get("body") or "") + " " + (p.get("dialogue") or "")
    known = allowed | COMMON_TERMS | KNOWN_HISTORICAL_NAMES

    out, seen = [], set()
    for m in re.finditer(r"([\u4e00-\u9fa5]{2,3})(?=(?:单于|将军|太尉|校尉|刺史|"
                         r"太守|丞相|国相|大夫|元帅|太子|公主|御史|尚书令))", text):
        c = m.group(1)
        title = text[m.end():m.end() + 6]
        title = _TITLE_RE.match(title)
        title = title.group(0) if title else ""

        # 守卫 1：人名表存的是全称（「呼韩邪单于」），正则只抓到前缀
        if title and (c + title) in known:
            continue
        # 守卫 2：候选本身是官职/称谓，不是人名（御史 / 太守 / 匈奴）
        if c in _TITLE_WORDS or c in COMMON_TERMS or c in known:
            continue
        # 守卫 3：候选以功能字/方位字结尾 —— 说明抓到的是半截短语
        #         （"汉朝大" + 将军、"太守与" + 丞相）
        bare = c.lstrip("大副左右上中骁奋飞")
        if not bare or bare[-1] in _FUNC_CHARS or c[-1] in _FUNC_CHARS:
            continue
        if c in seen:
            continue
        seen.add(c)
        out.append(Finding(p["page"], "warn", "NAME_UNKNOWN",
                           f"疑似编造人物「{c}」（带身份头衔但不在正史人名表）",
                           "若确有此人请补进 storyboard.characters[]；"
                           "否则多半是 LLM 编的。苏武项目出现过虚构的「阿提拉」"))
    return out


def _f_ragged_needs_plain(p: dict) -> list[Finding]:
    """破损衣物必须配反制词，否则模型会在袍子上"补"伪汉字。

    **实图证据**（kc_1790586703 p04，visual_qa 95% 置信 + 肉眼复核）：
    visual 写 `robe tattered`，袍子上被画满伪汉字。p01 无破损描述，干净。

    模型看到"破烂的袍子"会主动往上面补纹样/字符。破损本身是叙事需要
    （十九年风霜），所以这里不禁止破损，而是**要求配反制词**。
    """
    v = (p.get("visual") or "").lower()
    ragged = [w for w in RAGGED_WORDS if w in v]
    if not ragged:
        return []
    if any(w in v for w in PLAIN_GUARD_WORDS):
        return []
    # **只报 warn，不阻塞** —— 实图复核证明这是风险因子而非充分条件：
    # p04（tattered）确有伪汉字，p08（ragged）却干净。同样诱因结果不同，
    # 判据不成立。阻塞会让关卡变成"狼来了"，用户开始无视它。
    # 真阳性交给 visual_qa —— 只有它能真的看见图上的字。
    return [Finding(p["page"], "warn", "RAGGED_NO_PLAIN",
                    f"衣物写破损（{ragged}）但没有反制词 → 模型会画伪汉字",
                    "实测 p04 确有伪汉字、p08 没有 —— 是风险不是定论。"
                    "建议补 PLAIN unadorned / solid-colour / no-pattern；"
                    "跑完图用 visual_qa 重点看这页衣物")]


# 破损/做旧描述 —— 模型会往这类织物上补纹样字符
RAGGED_WORDS = ["tattered", "worn", "ragged", "torn", "frayed", "patched",
                "weather-beaten", "torn cloth", "shabby"]

# 反制词 —— 明示"素面无纹"，把模型按住
PLAIN_GUARD_WORDS = ["plain", "unadorned", "no pattern", "no-pattern",
                     "solid-colour", "solid color", "unpatterned",
                     "patternless", "without pattern", "no motif",
                     "no motifs", "plain weave", "simple weave", "no symbols",
                     "no characters"]

def _f_no_text_decl(p: dict) -> list[Finding]:
    """零文字风险检查（v0.3.15 反转判据）。

    **初版判据是错的**：它要求 visual 里必须出现 "NO TEXT" 才放行，但零文字
    约束实际由 `prompts.py:ZERO_TEXT_BOOST` **无条件注入**最终 prompt —— 写没写
    都一样。结果苏武牧羊 10/10 页全部误报，p09 只是唯一写了
    `STRICT NO TEXT` 的那页。

    **真风险是反方向的**：visual 里出现 `calligraphy` / `inscribed` / `banner`
    / `signboard` 这类词时，模型会**主动画出字符**，把 ZERO_TEXT_BOOST 压过去。
    planner 铁律 4 明确禁这些词，关卡就是来兜底的。
    """
    v = (p.get("visual") or "").lower()
    out = []
    hits = [w for w in TEXT_INVITING_WORDS if _positive_mention(v, w)]
    if hits:
        out.append(Finding(p["page"], "block", "TEXT_INVITING",
                           f"画面描述含会诱导模型画字的词 {hits}",
                           "planner 铁律 4：服饰/地图/兵器描述不得出现 "
                           "decorative patterns / calligraphy / inscribed / "
                           "banner / signboard 这类词 —— 模型会当真画字符。"
                           "改写成 PLAIN unadorned / abstract terrain"))
    return out




# 弱信号：这些词单独出现时可能只是形容神态/气质，不是器物穿帮。
# 需要多个弱信号同现，或与强信号器物词同现，才判定为穿帮。
_WEAK_ANACHRONISM = {"繁复", "华丽"}

_NEGATION_CUES = ("no", "not", "without", "free of", "zero", "absence of",
                 "devoid of", "never", "avoid", "none of", "rather than",
                 "instead of", "not any")

# 可穿越的连接符 —— 否定线索和被检词之间隔着这些字符时，
# 否定作用域仍然成立。男性锚点写的是 "(NOT 步摇 — too feminine)"，
# 否定词与被检词之间隔着左括号，裸 in 匹配不到。
_NEG_CONNECTORS = set(" \t\n()[]{},;:-—–/\\\"'")

# 否定线索到被检词之间最多允许隔多少字符（防止否定作用域无限延伸，
# 把几百字符前的 NOT 误配给后面的词）
_NEG_MAX_GAP = 40


def _negated_before(text_lower: str, i: int) -> bool:
    """位置 i 之前是否处于否定作用域内。"""
    window = text_lower[max(0, i - _NEG_MAX_GAP):i]
    # 从右往左扫，遇连接符继续，遇非连接符的实词终止
    for cue in _NEGATION_CUES:
        pos = window.rfind(cue)
        if pos < 0:
            continue
        between = window[pos + len(cue):]
        if all(ch in _NEG_CONNECTORS for ch in between):
            return True
    return False


def _positive_mention(text: str, word: str) -> bool:
    """word 在 text 里是否以**肯定**语气出现。

    p09 的 `no calligraphy, no symbols` 是零文字声明的一部分 —— 正确写法。
    只做子串匹配会把这种否定用法误判成"诱导画字"（v0.3.15 初版就踩了）。

    v0.3.20 修两个真实缺陷：
      1. cue 表原为小写，原文写大写 `NOT` / `NO` 时匹配不上
      2. 否定线索与被检词之间可以隔着标点/括号（男性锚点："(NOT 步摇 ...)"），
         裸 `in` 匹配不到 —— 现在按「否定词 + 只隔连接符」判定
    """
    low = text.lower()
    w = word.lower()
    start = 0
    while True:
        i = low.find(w, start)
        if i < 0:
            return False
        if not _negated_before(low, i):
            return True
        start = i + len(w)

# 会诱导模型在图上画字的词 —— planner 铁律 4 明令禁止
TEXT_INVITING_WORDS = [
    "calligraphy", "inscribed", "inscription", "signboard", "banner",
    "scroll with", "banner text", "written", "characters on",
    "decorative pattern", "embroidered with", "engraved",
]



def _f_char_gender(storyboard, p: dict) -> list[Finding]:
    """characters[].gender 缺失 → 阻塞（全文级报一次）。

    **事故依据**（kc_1790664590）：夫差没写 gender，角色参考图被画成女性
    （桃花腮/柳叶眉/步摇簪花），再经 i2i 传进每一页。
    角色参考图是整条链路的**性别源头**，源头错了全批都错。

    v0.3.22 行为变更：以前 KNOWN_GENDER 兜底表里的角色（勾践/夫差/西施/张巡等
    约 90 个正史人物）会自动通过，让 planner 偷懒不填 gender。**这违背了
    v0.3.20 "gender 必填" 的设计** —— planner 必须自己填，库是 backup 不是
    绕过借口。**现在统一阻塞**：任何 characters[].gender 缺失或非 enum 值，
    不管在不在 KNOWN_GENDER 表，全部报 block。修复方法只有一个：补字段。

    KNOWN_GENDER 表的作用降级为**安全网**：管线层（image_gen / resolve_gender）
    仍然查表兜底，绝不让角色参考图失传；但 preflight 必须强制 planner 显式
    表达，保留"史实铁律"的可审计性（来源=planner，不来源=LLM 自动猜）。
    """
    if p["page"] != 1:
        return []
    chars = p.get("characters") or []
    if not chars:
        return []
    missing = []
    for c in chars:
        nm = c.get("name") if isinstance(c, dict) else c
        g = (c.get("gender") if isinstance(c, dict) else "") or ""
        g = g.strip().lower()
        if g not in ("male", "female", "mixed"):
            missing.append(nm)
    if missing:
        return [Finding(
            None, "block", "CHAR_GENDER_MISSING",
            f"角色缺 gender 字段：{missing}",
            "v0.3.22 起 KNOWN_GENDER 表不再为缺失兜底 —— planner 必须显式"
            " 写 'male'/'female'，与 KNOWN_GENDER 是否收录无关。补 "
            "characters[].gender = 'male'/'female' 即过")]
    return []

def _f_era_anachronism(storyboard, p: dict) -> list[Finding]:
    """角色 visual_signature 含后世器物 → 阻塞（**全文级报一次**）。

    **实测事故**（kc_1790664590）：夫差签名写「华丽的红白相间宽袖丝绸袍服、
    佩戴玉璧和繁复的金质发冠」—— 春秋吴王没有这些。模型忠实照画，
    结果每一页画到夫差都成了明清帝王（肥胖、金冠、锦袍）。

    ⚠️ 归因澄清（v0.3.23）：真正穿帮的是**金质发冠 + 繁复的华丽丝绸**。
    玉璧本身是春秋战国正统礼器，**不算穿帮**，已从 ANACHRONIC_MARKERS 移除 ——
    否则任何佩玉璧的先秦角色都会被误阻塞。

    这与 RAGGED_NO_PLAIN 不同：那个是风险因子（p04 中招 p08 没中招），
    这个是**确凿的史实错误**，且在 i2i 模式下会污染所有含该角色的页面。

    **报一次而不是每页一次**：角色签名是 storyboard 级的问题，
    逐页报会得到 10 条一模一样的阻塞（v0.3.15 的 GENDER 检查犯过同样的错）。
    这里 page=None + msg 里列出受影响页号。
    """
    if p["page"] != 1:
        return []                      # 只在第 1 页跑一次，汇总到全文级

    chars = p.get("characters") or []
    if not chars:
        return []
    # 哪些页提到了这个角色
    pages_by_char: dict[str, list[int]] = {}
    for c in chars:
        nm = c.get("name") if isinstance(c, dict) else c
        if not nm:
            continue
        hits_pages = [pg["page"] for pg in _ALL_PAGES
                      if nm in (pg.get("visual") or "")
                      or nm in (pg.get("caption") or "")]
        if hits_pages:
            pages_by_char[nm] = hits_pages

    out = []
    for c in chars:
        nm = c.get("name") if isinstance(c, dict) else c
        sig = (c.get("visual_signature", "") if isinstance(c, dict) else "") or ""
        # v0.3.18：用 _positive_mention 过滤否定语境 ——
        # 苏武签名里的「无繁复纹样」是最合规的写法，不能被「繁复」命中。
        hits = [w for w in ANACHRONIC_MARKERS if _positive_mention(sig, w)]
        # 「繁复/华丽」是弱信号：单独出现时可能只是形容神态，
        # 只有与**器物**同现（"华丽的丝绸袍" vs "神情华丽"）才算穿帮。
        weak = [w for w in hits if w in _WEAK_ANACHRONISM]
        strong = [w for w in hits if w not in _WEAK_ANACHRONISM]
        if not strong and len(weak) < 2:
            continue
        hits = strong + weak[:1]
        affected = pages_by_char.get(nm, [])
        where = f"影响 {len(affected)} 页" if affected else "暂未出现在画面"
        out.append(Finding(
            None, "block", "ERA_ANACHRONISM",
            f"角色「{nm}」的视觉签名含后世器物 {hits}（{where}）",
            "先秦人物不该有金质发冠/龙纹/繁复织锦 —— 模型会忠实照画。"
            "实测 kc_1790664590：夫差被画成明清帝王，每页都错。"
            "改成素麻/葛布/深色圆领袍 + 发束高髻缠布带这类本时代形制"
            "（注：玉璧是春秋战国正统礼器，不在穿帮词表内）"))
    return out


def _f_no_text_missing(p: dict) -> list[Finding]:
    """visual 没写零文字声明 → **建议**（代码层已兜底，这里只提示）。

    为什么不是阻塞：`prompts.py:PATTERN_SUPPRESS` + `ZERO_TEXT_BOOST`
    已经无条件注入，漏写 visual 不会掉出保护。但这仍是 planner 忽略铁律的
    信号 —— 而忽略铁律往往连带其他问题（如本批 10/10 页也没有画风词），
    所以报出来给 Mavis 看，但**不阻塞**。
    """
    v = (p.get("visual") or "").upper()
    if "NO TEXT" not in v and "NO WRITING" not in v:
        return [Finding(p["page"], "warn", "NO_TEXT_MISSING",
                        "visual 未写零文字声明（代码层已兜底，但 planner 可能忽略了整条铁律）",
                        "实测 kc_1790664590：10/10 页都没写，其中 6 页袍上出了伪字。"
                        "建议 visual 末尾加 STRICT NO TEXT —— no characters, "
                        "no calligraphy, no symbols, plain fabric only")]
    return []

def _f_punchline(p: dict) -> list[Finding]:
    out = []
    pl = (p.get("punchline") or "").strip()
    if not pl:
        out.append(Finding(p["page"], "warn", "PUNCH_EMPTY",
                           "缺 punchline —— 「定格瞬间」是本章节的记忆点"))
    elif len(pl) > PUNCH_MAX:
        # v0.3.24：原先写死 30，但同一条的文案却告诉用户「10-22 字」——
        # 代码和自己的提示自相矛盾。按 prompt 铁律 7.2 的 22 收口。
        out.append(Finding(p["page"], "warn", "PUNCH_LONG",
                           f"punchline {len(pl)} 字偏长，记忆点要短（{PUNCH_MAX} 字内）"))
    return out


def _f_dialogue(p: dict) -> list[Finding]:
    d = (p.get("dialogue") or "").strip()
    if not d:
        return [Finding(p["page"], "warn", "QUOTE_EMPTY",
                        "缺文言引文 —— 图下蒙版会空着")]
    if len(d) > QUOTE_MAX:
        # v0.3.24：原先放行到 90 字，与 prompt 铁律 7.1 的 50 字上限脱节。
        out = [Finding(p["page"], "warn", "QUOTE_LONG",
                       f"文言引文 {len(d)} 字偏长，蒙版放不下（{QUOTE_MAX} 字内）")]
        return out
    return []


# --- 主入口 -----------------------------------------------------------------

# v0.3.18：_f_era_anachronism 需要跨页汇总（哪些页提到某角色），
# 用模块级缓存挂一次 —— 纯读取，不跨调用复用。
_ALL_PAGES: list[dict] = []


def run_preflight(storyboard, alignment: dict | None = None) -> PreflightResult:
    """跑完整体检。

    Args:
        storyboard: Storyboard 对象或 dict
        alignment: check_storyboard() 的结果（可选，用于图文不符检查）
    """
    res = PreflightResult()

    # --- 归一化：Storyboard 对象 / dict 两条路合成同一份 page dict ---
    if hasattr(storyboard, "pages") and not isinstance(storyboard, dict):
        sb = storyboard
        style_id = getattr(sb, "style_id", "")
        raw_pages = sb.pages
        raw_chars = getattr(sb, "characters", None) or []
    else:
        sb = storyboard
        style_id = sb.get("style_id", "")
        raw_pages = sb.get("pages", [])
        raw_chars = sb.get("characters") or []

    def _name(c):
        return c.get("name") if isinstance(c, dict) else c

    characters = [c for c in raw_chars if _name(c)]
    allowed = {_name(c) for c in characters}

    pages = []
    for pg in raw_pages:
        if isinstance(pg, dict):
            d = dict(pg)
        else:
            d = {
                "page": pg.page, "visual": pg.visual or "",
                "body": pg.body or "", "caption": pg.caption or "",
                "keywords": list(pg.keywords or []),
                "dialogue": pg.dialogue or "",
                "punchline": getattr(pg, "punchline", "") or "",
            }
        d.setdefault("keywords", [])
        d.setdefault("dialogue", "")
        d.setdefault("punchline", "")
        d["characters"] = characters      # _named_roles 靠它识别已登记角色
        pages.append(d)

    global _ALL_PAGES
    _ALL_PAGES = pages

    for p in pages:
        res.findings.extend(_f_kw(p))
        res.findings.extend(_f_body_len(p))
        res.findings.extend(_f_hedging(p))
        res.findings.extend(_f_modern_tone(p))
        res.findings.extend(_f_gender(p, style_id, allowed))
        res.findings.extend(_f_fabricated(p, allowed))
        res.findings.extend(_f_no_text_decl(p))
        res.findings.extend(_f_ragged_needs_plain(p))
        res.findings.extend(_f_char_gender(storyboard, p))
        res.findings.extend(_f_era_anachronism(storyboard, p))
        res.findings.extend(_f_no_text_missing(p))
        res.findings.extend(_f_punchline(p))
        res.findings.extend(_f_dialogue(p))


    # 图文不符（高风险页直接阻塞）
    if alignment:
        for r in alignment.get("results", []):
            if r.get("severity") == "high":
                res.findings.append(Finding(
                    r["page"], "block", "ALIGN_HIGH",
                    f"caption 里的动作/人物画面没画："
                    f"{r.get('caption_missing_actions') or r.get('caption_missing_entities')}",
                    "跑图几乎必然对不上，先改 visual"))

    return res
