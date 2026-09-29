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

    @property
    def ok(self) -> bool:
        return not self.findings

    def report(self) -> str:
        if self.ok:
            return "✅ 生图前体检全部通过"
        lines = []
        if self.blocks:
            lines.append(f"🔴 阻塞项 {len(self.blocks)} 个 —— 必须修完才能跑图")
            for f in self.blocks:
                where = f"p{f.page:02d}" if f.page else "全文"
                lines.append(f"   [{f.code}] {where}：{f.msg}")
                if f.hint:
                    lines.append(f"        → {f.hint}")
        if self.warns:
            lines.append(f"🟡 建议项 {len(self.warns)} 个")
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
                           "planner prompt 铁律 5 要求 3-5 个；不满足就会渲染不出高亮"))
    elif len(kws) > 6:
        out.append(Finding(p["page"], "warn", "KW_TOO_MANY",
                           f"keywords {len(kws)} 个偏多，正文里会碎成一片",
                           "v0.3.12 实测：3 个最干净，只选专有名词"))
    return out


def _f_body_len(p: dict, target_lo=100, target_hi=150,
                hard_hi=170, warn_lo=90) -> list[Finding]:
    """正文长度。

    v0.3.15 修正：初版把 100-150 当**硬边界**，结果 p01 93 字 / p02 95 字 /
    p08 154 字全被判不合格。用户的 100-150 是**目标带**（"文字不能过多"），
    真正的风险是文字压过画面，所以边界大幅放宽：
      - 超过 170 字 = 阻塞（文字确实会压过图）
      - 151-170 字 = 建议（微调即可）
      - 低于 90 字 = 建议（内容偏薄）
      - 90-170 字 = 放行
    原则：关卡拦"方向错"，不拦"没到理想值"。
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
    actor_lines = [ln.strip() for ln in v.splitlines()
                   if _ACTOR_LINE_RE.match(ln.strip())]
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

    # B) 角色 bible 式 / 单人页
    if not re.search(r"\[GENDER:\w+\]", v, re.I):
        named = [n for n in _named_roles(v, p) if n in allowed]
        if named:
            return []      # 角色登记在 characters[] → 角色锚点兜底
        return [Finding(p["page"], "warn", "GENDER_NONE",
                        "visual 里没有 [GENDER:xx] 标记，且角色未登记进 characters[]",
                        "连环画风格靠它定男女；缺失时主角性别随机。"
                        "二选一：加 [GENDER:male]，或写进 storyboard.characters[]")]
    return []


# 角色段行首：`[GENDER:xx] Rider:` 或 `Standing figure:` / `Foreground man:`
_ACTOR_LINE_RE = re.compile(
    r"^\[GENDER:\w+\]|^[A-Z][A-Za-z]*(?:\s+[a-z]+){0,2}\s*:")



def _named_roles(visual: str, p: dict) -> list[str]:
    """本页 visual 里出现的**中文具名角色**。

    只认三种来源：
      1. 中文「// 中文速记」注释里的 2 字词（planner 一定会标人名）
      2. 正史人名表里出现的名字
      3. characters[] 里登记的名字
    英文一律不算（地名 Lake Baikal、修饰 Zhang Zhong 都会误报）。
    """
    names: list[str] = []

    # 1) 中文速记（人看的注释，planner 每页都写人名）
    for m in re.finditer(r"//\s*([^\n]+)", visual):
        for tok in re.split(r"[\s·、,，/]+", m.group(1)):
            tok = tok.strip()
            if 2 <= len(tok) <= 4 and re.fullmatch(r"[一-龥]+", tok):
                if tok in COMMON_TERMS or tok in _GENERIC_VISUAL_WORDS:
                    continue
                names.append(tok)

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


# 视觉描述里的泛化物词 —— 不是人名
_GENERIC_VISUAL_WORDS = {
    "枯草", "荒原", "挖掘", "绝望", "坚毅", "雪原", "对比", "矛盾", "帐内",
    "火光", "劝降", "哭声", "沉默", "眼神", "白发", "少年", "将军", "士兵",
}




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



_NEGATION_CUES = ("no ", "not ", "without", "free of", "zero ", "absence of",
                 " devoid of", "never ", "avoid ", "none of", "rather than",
                 "instead of", "not any", "no-")


def _positive_mention(text: str, word: str) -> bool:
    """word 在 text 里是否以**肯定**语气出现。

    p09 的 `no calligraphy, no symbols` 是零文字声明的一部分 —— 正确写法。
    只做子串匹配会把这种否定用法误判成"诱导画字"（v0.3.15 初版就踩了）。
    判据：看该词前 ~30 字符里有没有否定线索词。
    """
    start = 0
    while True:
        i = text.find(word, start)
        if i < 0:
            return False
        before = text[max(0, i - 30):i]
        if not any(cue in before for cue in _NEGATION_CUES):
            return True
        start = i + len(word)

# 会诱导模型在图上画字的词 —— planner 铁律 4 明令禁止
TEXT_INVITING_WORDS = [
    "calligraphy", "inscribed", "inscription", "signboard", "banner",
    "scroll with", "banner text", "written", "characters on",
    "decorative pattern", "embroidered with", "engraved",
]



def _f_punchline(p: dict) -> list[Finding]:
    out = []
    pl = (p.get("punchline") or "").strip()
    if not pl:
        out.append(Finding(p["page"], "warn", "PUNCH_EMPTY",
                           "缺 punchline —— 「定格瞬间」是本章节的记忆点"))
    elif len(pl) > 30:
        out.append(Finding(p["page"], "warn", "PUNCH_LONG",
                           f"punchline {len(pl)} 字偏长，记忆点要短（10-22 字）"))
    return out


def _f_dialogue(p: dict) -> list[Finding]:
    d = (p.get("dialogue") or "").strip()
    if not d:
        return [Finding(p["page"], "warn", "QUOTE_EMPTY",
                        "缺文言引文 —— 图下蒙版会空着")]
    if len(d) > 90:
        return [Finding(p["page"], "warn", "QUOTE_LONG",
                        f"文言引文 {len(d)} 字偏长，蒙版放不下")]
    return []


# --- 主入口 -----------------------------------------------------------------

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

    for p in pages:
        res.findings.extend(_f_kw(p))
        res.findings.extend(_f_body_len(p))
        res.findings.extend(_f_hedging(p))
        res.findings.extend(_f_modern_tone(p))
        res.findings.extend(_f_gender(p, style_id, allowed))
        res.findings.extend(_f_fabricated(p, allowed))
        res.findings.extend(_f_no_text_decl(p))
        res.findings.extend(_f_ragged_needs_plain(p))
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
