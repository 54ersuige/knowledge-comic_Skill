"""Prompts - 锁定 4 个高质感风格 + 角色一致性 + 零文字硬约束。

v0.2 重构（2026-09-20）：
  - 砍掉 8 风格中的 4 个（kid_picture_book / kid_science_diagram /
    jp_kawaii_warm / jp_terada），锁定 3 个最有特点的成人向风格：
      1. new_yorker      知识/商业/严肃（黑白色块 Risograph 杂志感）
      2. us_mid_century  商业评论/设计/品牌（mustard+teal+砖红 复古杂志）
      3. cn_xuanfeng     历史典故/国学（飞白+朱砂+宣纸，中国水墨写意）
  - 加 ZERO_TEXT_BOOST：所有 prompt 强制 "NO TEXT/NUMBERS/DIGITS/LETTERS/SIGNS"
  - 加 CHARACTER_HOOKS：每张图描述强制同款角色，保证跨页一致
  - RECOMMEND_MATRIX 简化到合理映射

v0.2.2（2026-09-21）新增第 4 风格：
  4. guochao_manhua  历史典故/中国故事（《镖人》《一人之下》类现代国漫分镜语言 +
                          古装 + 鲜艳色块，赛璐璐上色；用户实际偏爱国潮赛璐璐/古风条漫
                          多于纯传统水墨写意）。历史/典故类 RECOMMEND 优先级第一。
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class StylePreset:
    id: str
    name_zh: str
    name_en: str
    category: str
    use_cases: tuple[str, ...]
    prompt_en: str
    prompt_zh: str
    negative: str


# === 零文字硬约束（每张图必带）===
ZERO_TEXT_BOOST = (
    "ABSOLUTELY NO TEXT on the image. NO English signage. NO fake letters. "
    "NO numbers. NO digits. NO math symbols. NO Japanese kana. NO Chinese characters. "
    "NO speech bubbles. NO caption boxes. NO watermarks. NO labels. NO arrows-with-words."
)

# === v0.3.18 代码层注入的三条硬约束 ===============================
# 设计依据：写在 planner prompt 里的祈使句**不可靠**（苏武那批遵守、
# 卧薪尝胆 10/10 页全没遵守）。ZERO_TEXT_BOOST 无条件注入才一直有效，
# 所以这三条照它的成功配方改成代码注入 —— LLM 漏不掉。
#
# 1) 纹样抑制：ZERO_TEXT_BOOST 管"别写字"，但管不住"别画纹样"——
#    实测 kc_1790586703 p04/p07、kc_1790664590 p01/p02/p06/p08/p09
#    袍上全是伪汉字，根因是描述里有 tattered/繁复/华丽/丝绸 这类
#    邀请纹样的词。要正面写"素面"才按得住。
PATTERN_SUPPRESS = (
    "Every garment and surface must be COMPLETELY BLANK: solid flat colour "
    "with no pattern, no motif, no embroidery, no brocade, no ornament, "
    "no trim, no decoration of any kind. No woven decoration, no printed "
    "design, no symbolic marks. Fabric is plain and unadorned like unbleached "
    "hemp or raw silk. Even worn or torn cloth shows plain weave only, never "
    "decorative texture or pseudo-script."
)

# 2) 连环画强锚：实测 10/10 页 visual 没有任何画风词，全靠 style.prompt_en
#    兜底，不够稳。单人构图 + 现代器物一进来就漂成 3D/宋画。
LIANHUANHUA_STYLE_LOCK = (
    "CRITICAL STYLE: every single element of this frame must be a classical "
    "Chinese lianhuanhua (连环画) brush painting on aged rice paper, in the "
    "Dai Dunbang / He Youzhi tradition. Flat mineral pigment washes, visible "
    "brush linework, paper grain and fibre texture showing through, muted "
    "earth palette of ochre / malachite / cinnabar / ink black on cream. "
    "NOT a photograph, NOT a 3D render, NOT anime, NOT modern digital "
    "illustration, NOT glossy CG, NOT a Song/Ming/Qing court painting, "
    "NOT photorealistic. If any part of the image looks photographic or "
    "renders in 3D, the whole image has failed. "
    # v0.3.22 (2026-09-29)：实测卧薪尝胆 p06/p09 暴露连环画强锚对现代室内物
    # 品 + 写实盔甲的吸引力不够 —— 模型默认走"现代办公环境"或"3D CG 铠
    # 甲"舒适区，连环画锚压不住。下面前缀是硬拒词，不是装饰建议。
    "HARD REJECT — modern interior objects: NO bookshelf, NO floor-to-ceiling "
    "window, NO office chair, NO sofa, NO glass window pane, NO porcelain tea "
    "set, NO gas lamp, NO electric light, NO mechanical clock. Indoor scenes "
    "must use bamboo screen / oil-paper umbrella / bronze brazier / wooden "
    "screen / paper lantern only. "
    "HARD REJECT — photoreal armor: NO chrome / metallic shine on armor, NO "
    "3D-rendered polished leather, NO CG specular highlight on bronze / iron. "
    "Armor must read as flat inked brushstroke with mineral pigment wash, the "
    "same density and finish as the figure's robe."
)

# 3) 时代穿帮词：用于 preflight 检测 characters[].visual_signature
#    是否被 planner 写成了后世帝王形象（实测夫差被写成"华丽丝绸+金质发冠"，
#    春秋吴王每页都画成明清帝王）。这些是**检测用**的表，不进 prompt。
#
# v0.3.23 修正：移出「玉璧」。玉璧是春秋战国**正统礼器**
# （蔺相如完璧归赵即战国故事），先秦人物佩玉璧完全合理。
# 原事故里夫差签名写的是「金质发冠 + 繁复的华丽丝绸」，
# 玉璧只是顺带被列进表里，被误当成穿帮主因。
# 保留真正错配项：金质发冠 / 龙纹 / 补子 / 乌纱 / 蟒袍 / 顶戴 / 朝珠 …
ANACHRONIC_MARKERS = [
    "金质发冠", "龙袍", "龙纹", "补子", "乌纱", "乌纱帽", "官帽",
    "朝服", "蟒袍", "雕龙", "织金", "点绣", "补服", "顶戴", "翎羽", "朝珠",
    "紫砂", "扶手椅", "沙发", "玻璃窗", "油灯", "蜡烛", "机械钟", "折扇",
    "繁复", "华丽",
]

# === v0.3.17 朝代服饰考据速查表（planner prompt 可见）===
# 根因（2026-09-29）：实测卧薪尝胆项目，planner 给春秋勾践写"圆领袍+武冠+幞头"，
# 三件全是唐/汉/宋才有，春秋错配。ANACHRONIC_MARKERS 只是事后检测，planner 看不到。
# 修复：把"朝代速查表"直接挂进 PLANNER_SYSTEM_PROMPT，planner 写 visual_signature 时
# 必须按 characters[].era 字段选对应朝代的服饰，并查本表对照禁忌。
CN_DYNASTY_COSTUME_GUIDE = """
## 朝代服饰考据速查表（planner 必读 · 严禁错配）

**规则**：characters[].era 字段确定年代 → visual_signature 必须严格用本表的服饰/冠帽/配饰。
**禁止**：把后世元素写进前朝（例：春秋人物写"圆领袍+武冠+幞头"是三件错配，唐/汉/宋才有）。

### 春秋战国（前770-前221）
- 主衣：曲裾深衣（衣襟绕身后数圈）/ 直裾单衣 / 素色麻袍
- 冠帽：峨冠 / 皮弁（白鹿皮帽）/ 鹖冠（武将装饰）/ 笄纚（发簪+头巾）
- 配饰：青铜佩剑 / 玉璧 / 组玉佩 / 丝绦腰带
- 禁忌：圆领袍（唐以后）/ 乌纱帽（明以后）/ 龙纹/补子（明以后）/ 金线刺绣

### 秦汉（前221-220）
- 主衣：曲裾深衣 / 直裾袍 / 襦裙（女性）
- 冠帽：长冠 / 进贤冠 / 武冠（汉定型）/ 委貌冠
- 配饰：佩剑 / 玉环 / 组绶（彩色丝带标识官阶）/ 笏板
- 禁忌：乌纱帽（明以后）/ 圆领袍（唐以后）/ 补服（明以后）

### 魏晋南北朝（220-589）
- 主衣：宽袍大袖 / 褒衣博带 / 交领宽袖衫
- 冠帽：笼冠（黑漆纱笼）/ 小冠 / 进贤冠
- 配饰：麈尾（清谈名士持）/ 羽扇 / 嵌宝剑
- 禁忌：圆领袍（唐以后）/ 蹀躞带（唐以后）/ 展脚幞头（宋以后）

### 隋唐（581-907）
- 主衣：圆领窄袖袍（官常服）/ 大袖襦裙 + 半臂（女性）
- 冠帽：软脚幞头（初唐）/ 翘脚幞头（盛唐）/ 浑脱帽（胡风）
- 配饰：鱼符（出入宫禁凭证）/ 玉带 + 蹀躞带（带銙+小袋）/ 佩剑 / 笏板
- 禁忌：乌纱帽（明以后）/ 补子（明以后）/ 顶戴花翎（清以后）/ 云肩（宋以后定型）

### 宋元（960-1368）
- 宋主衣：东越直领袍 / 圆领窄袖 / 鹤氅（道士风度）/ 背子（女性外衣）
- 元主衣：质孙服（连体紧身袍）/ 辫线袍 / 罟罟冠（蒙古贵族女性）
- 冠帽：宋 - 展脚幞头（长直脚）/ 元 - 钹笠帽
- 配饰：宋 - 玉骨朵 / 笏板 / 元 - 海东青（小猎鹰）/ 弓矢
- 禁忌：补子 / 乌纱帽 / 金线龙袍 / 清官服元素

### 明清（1368-1912）
- 明主衣：圆领袍 + 补子（前胸后背方形纹样区分官阶）/ 飞鱼服（赐服）
- 清主衣：箭衣 / 马褂 / 朝服（圆领+披肩领+补子）
- 冠帽：明 - 乌纱帽（黑圆顶，前低后高）/ 翼善冠（亲王）/ 凤冠（命妇）/ 清 - 顶戴花翎 + 红缨暖帽
- 配饰：明 - 牙牌 / 笏板 / 玉带 / 清 - 朝珠（108颗）/ 翎管 / 扳指 / 鼻烟壶
- 禁忌：不要把明以前人物写成"戴乌纱穿补服"（明专属）；不要把清以前人物写成"顶戴花翎朝珠"（清专属）
"""

# === 中国画构图 booster（替代 cinematic 三件套） ===
# v0.2.5 (2026-09-22)：历史典故类风格 (chinese_lianhuanhua_classic / cn_xuanfeng / guochao_manhua)
# 必须用中国画构图语言（散点透视/留白/平面色块/白描+朱砂勾线），不能用西方镜头语言，
# 否则模型会跑偏现代写实风（电影截图/3D 渲染/油画）。
CHINESE_PAINTING_BOOST = """
CHINESE PAINTING COMPOSITION (mandatory - this REPLACES the cinematic framework for traditional Chinese styles):
- FRAMING: traditional Chinese handscroll or vertical hanging scroll layout. ASYMMETRIC PLACEMENT: subject on one side, generous negative space on the other. NOT centered, NOT Western rule-of-thirds photo framing.
- PERSPECTIVE: classical Chinese multi-point perspective (散点透视). Background, midground, foreground can use DIFFERENT vantage points in the same frame. NO Western single-point perspective.
- NEGATIVE SPACE (留白): rice-paper-white space is a COMPOSITIONAL ELEMENT, not emptiness. Use it to convey atmosphere, vastness, fog, or dramatic tension.
- DEPTH LAYERS: each layer separated by ink-wash tone or brush stroke. NO photographic DoF blur, NO atmospheric haze, NO volumetric fog. Use ink-line separation between layers.
- LIGHTING: implied by color planes and brush direction (朱砂/靛青/赭石/墨 矿物色). NO volumetric light, NO cinematic shadows, NO chiaroscuro, NO rim light. Light is painted, not rendered.
- COLOR: FLAT GONGBI color planes (cinnabar + indigo + ochre + ink + bone-white). NO gradients, NO photographic shading, NO airbrush, NO smooth blending.
- LINES: white-line + red-line (白描+朱砂勾线) calligraphic outline on figures and key details. NO inked shadows, NO realistic shading on faces.
- EXPRESSION: theatrical intensity held in dignified restraint. Classical Chinese face coded by brush lines, NOT photographic realism.
- BRUSHWORK: visible brush bristle strokes, deliberate dry-brush edges (飞白), NOT smooth photorealistic surfaces.
"""

# === STRICT STYLE 前缀（中国画风格用，防止风格被场景覆盖） ===
# v0.2.5 (2026-09-22)：把"painted illustration"声明从场景描述里抢到最前，
# 因为场景描述会覆盖风格声明（这是 AI 图像模型的已知行为）。
CHINESE_STYLE_PREFIX = (
    "STRICT STYLE — the entire image is a classical Chinese painted illustration on rice paper "
    "(宣纸) using brush and mineral pigment. NOT a photograph, NOT a 3D render, NOT an oil "
    "painting, NOT cinematic, NOT photorealistic. Apply to every pixel of the frame. "
)

# === 角色一致性硬约束（按风格自动选 anchor）===
CHARACTER_SCIENTIST = (
    "Consistent character anchor (must remain identical across all panels): "
    "a small scientist figure with short black hair, round wire-frame glasses, "
    "light grey sweater, dark trousers, simple black shoes, neutral expression, "
    "age approximately 30. Same face, same body proportions, same outfit in every frame."
)

CHARACTER_OBSERVER = (
    "Consistent character anchor (must remain identical across all panels): "
    "a thoughtful observer figure with shoulder-length dark hair, no glasses, "
    "wearing a soft red knit sweater, dark skirt, simple shoes, contemplative expression, "
    "age approximately 30. Same face, same body proportions, same outfit in every frame."
)

CHARACTER_ANCIENT_CN = (
    "Consistent character anchor (must remain identical across all panels): "
    "a Han-Chinese historical person, either a refined young woman in traditional hanfu "
    "robe (crossed collar, wide sleeves, sash belt, hair pinned in classical style with "
    "subtle ornaments) or a dignified scholar-official in long scholarly robe with "
    "traditional headwear, both rendered with elegant elongated proportions typical of "
    "classical Chinese figure painting. Age approximately 20-30. Serene, contemplative "
    "expression. Same face, same outfit, same body proportions in every frame."
)

# === 角色一致性的"5-tuple bible"强化版（v0.2.3）===
# 经验教训：单一长段描述模型只会采纳前 30% 关键词，剩下的被忽略。
# 改成"五件套逐条列举"，每条都加权重，模型抓取率更高。
CHARACTER_ANCIENT_GUOCHAO = (
    "Consistent character bible (FIVE ANCHORS - all five must remain identical across all panels): "
    "(1) Face shape: oval face, sharp jawline, refined cheekbones. "
    "(2) Eyes: large double-lid expressive eyes with sharp winged eyeliner, dark brown irises. "
    "(3) Eyebrows: thin angled swordsman brows, slightly furrowed. "
    "(4) Lip & mouth: well-defined cupid's bow lips, normally closed, decisive line of jaw. "
    "(5) Hair: Han-Chinese historical figure, hair tied in high topknot bound with cloth ribbon (no metal crown), "
    "long black hair flowing behind when in motion. "
    "Modern manhua body proportions (about 1:2 head-to-body), NOT ancient painterly ratio. "
    "Age 20-30, sharp refined features. Cel-shaded manhua face. "
    "Outfit: traditional hanfu / scholarly robe (crossed collar, fitted waist sash with jade buckle, "
    "flowing wide sleeves). "
    "Shot variety mandatory - this figure appears across different framings and poses, "
    "NEVER as a static portrait."
)

# === Chinese epic history 角色锚点（v0.2.4 新增）===
# 5-tuple bible 强调"真实东亚人面部 + 中国古代审美"，
# 严禁任何赛璐璐 / 动漫 / 迪士尼脸特征。
CHARACTER_CN_EPIC_ANCESTOR = (
    "Realistic Han-Chinese historical figure anchor (must remain identical across all panels), "
    "academic oil-painting naturalism - NOT anime, NOT cel-shaded, NOT Disney, NOT kawaii: "
    "(1) Eyelid structure: single-eyelid or light-inner-fold Han-Chinese eyes, almond-shaped, "
    "deep-set under a heavy brow ridge, NEVER round anime eyes, NEVER large expressive Disney eyes. "
    "(2) Facial structure: refined Han-Chinese cheekbones, square-ish jaw, dignified weathered "
    "face with subtle age lines and slight nasolabial fold, NEVER a youthful pretty-boy face, "
    "NEVER a child-like face. "
    "(3) Skin tone: warm ivory to pale-olive Chinese complexion, visible pores, subtle sun "
    "weathering where appropriate, NEVER porcelain pink, NEVER pale pink skin, NEVER Caucasian flush. "
    "(4) Hair: Han-Chinese historical figure, hair tied in period-correct topknot OR wearing "
    "period-correct official's cap OR scholar's cloth binding, dark black hair, NEVER loose "
    "European-style hair, NEVER blond hair. "
    "(5) Body proportions: realistic 1:7 head-to-body, dignified adult height, framed by "
    "period-correct Chinese costume (crossed-collar hanfu / round-collar robe / official's "
    "belt plaque with rank / jade ornaments indicating rank). "
    "Expression base: dignified, composed, restrained emotion, the gravity of a person who "
    "has seen much. NEVER cutesy, NEVER playful. "
    "Age 25-55 depending on role. Posture: ceremonial gravity, NEVER slouching."
)

# === Chinese lianhuanhua classic 角色锚点（v0.2.4 新增，戴敦邦系）===
# 强调"戴敦邦式古典人物面部 + 工笔重彩质感 + 朝代服饰考据"
CHARACTER_CN_LIANHUANHUA_ANCESTOR = (
    "Dai Dunbang-style classical Chinese figure, INK BRUSH ON RICE PAPER (not oil/canvas/anime): "
    "(1) square jaw + classical Chinese cheekbones + dignified weathered age lines + light "
    "dry-brush hatch shadows; "
    "(2) narrow phoenix-eye 丹凤眼 or triangular-eye 三角眼 drawn in SINGLE firm ink-stroke "
    "contour, deep-set under heavy brow ridge; "
    "(3) sharp diagonal swordsman 剑眉 brows with calligraphic pressure variation; "
    "(4) period-correct facial hair (clean-shaven scholar / thin mustache official / short "
    "dignified beard commander / goatee elder), drawn with individual brush wisps; "
    "(5) period-correct Han-Chinese hair (high topknot 高髻 OR official's cap 幞头/官帽/乌纱), "
    "rendered with multiple ink-stroke hair lines. "
    "Body: classical Chinese figure proportions, slightly elongated dignified bearing. "
    "Costume: period-correct Chinese attire (Tang round-collar robe / Song straight-collar / "
    "Ming official's hat / period armor) with white-line + red-line calligraphic outline. "
    "Expression: theatrical intensity held in dignified restraint, never cutesy, never pretty-boy. "
    "Age 25-55 per role. Surface: RICE PAPER ink-and-pigment, NEVER Western canvas."
)

# Expression anchor 词汇库（planner 按章情绪选 1 个，明确写到 visual 里）
# 解决"defiant / sad"这类形容词描述模型画不出的问题——必须给可执行的具体面部元素
EXPRESSION_VOCAB: dict[str, str] = {
    "neutral": "serene closed lips, relaxed brow, eyes looking forward, neutral composed face",
    "rage_scream": "mouth FORCIBLY WIDE OPEN stretching jaw, eyes glaring skyward with visible white, "
                   "veins on neck bulging, brow deeply furrowed, brow drawn down hard over glaring eyes, "
                   "head tilted back",
    "sobbing_silence": "head bowed low, eyes closed tight, single tear visible on cheek, "
                       "knuckles white gripping object, mouth pressed in trembling thin line",
    "grim_resolve": "jaws clenched, eyes narrowed with cold focus, lips pressed in a thin "
                    "bloodless line, slight nod forward",
    "awed_stillness": "eyes wide round staring, lips parted in shock, breath held, "
                      "freezing mid-motion, body stillness while expression active",
    "sneering_scorn": "one corner of mouth lifted, eyes half-lidded looking down at subject, "
                     "chin tilted up, dismissive head tilt",
    "tender_grief": "soft downcast eyes, faint trembling smile of farewell, hand reaching toward "
                   "something / someone just out of frame, tears unshed",
    "fierce_command": "chin forward, eyes locked on viewer, brows drawn flat in cold authority, "
                      "arm extended forward with object, mouth open giving order",
}

# === 镜头库（CAMERA LANGUAGE KIT）===
# 12 元素：shot size × angle × lens × DoF。每个 prompt 必须至少选 1 shot + 1 angle + 1 lens + 1 DoF。
CAMERA_LANGUAGE_KIT = """
CAMERA FRAMING RULES (mandatory - state explicitly in every prompt):
- SHOT SIZE: pick exactly ONE per panel.
  * extreme_wide (subject tiny in vast environment, used for siege / battlefield / establishing shots)
  * wide (full body small in environment, used for action scenes)
  * medium (waist up, character + immediate context)
  * three_quarter (knee up, character occupies ~half frame)
  * close_up (shoulder/head fills most frame, ONLY for the SINGLE most dramatic moment)
  * insert_extreme_close (single detail: a hand, a blade edge, a blood drop, used for symbolic accents)
- ANGLE: pick exactly ONE.
  * eye_level (neutral documentary)
  * low_angle (looking up at subject → heroic / dominant / imposing)
  * high_angle (looking down at subject → vulnerable / observed / diminished)
  * dutch_tilt (tilted horizon → instability / tension / chaotic moment)
  * birds_eye (directly overhead → strategic / map-like / God view)
  * worms_eye (ground level looking up → monumentally large / surreal / inescapable fate)
- LENS (focal length feel): pick ONE.
  * 24mm_wide_angle (exaggerated depth, slight edge distortion, dramatic space)
  * 35mm_natural (human eye, documentary, balanced)
  * 50mm_standard (neutral closest to human view)
  * 85mm_portrait (compressed background, flattering face, cinematic isolation)
  * 135mm_telephoto (heavy compression, subject isolated from layered background)
- DEPTH OF FIELD: pick ONE.
  * shallow_dof (subject sharp, background creamy bokeh - emotional / portrait focus)
  * deep_focus (foreground + midground + background all sharp - tactical / story / establishing)
  * rack_focus (foreground blur, midground sharp, background blur again - layered attention)"""


# === DEPTH LAYERS（每页显式三层：前/中/背景）===
DEPTH_LAYERS_BOOST = """
DEPTH LAYERS (mandatory - state each of three layers explicitly):
- FOREGROUND (closest to camera): at least one prop / object / texture that frames the front edge of the scene
  (doorway threshold / weapon tip / paper fragment / rope end / armor plate / candle flame / dust particle)
- MIDGROUND (the action layer): where the main characters and core event happen
- BACKGROUND (receding depth): at least two distinct far-plane elements
  (architectural structures / distant figures / banners / smoke trails / mountain silhouette / sky gradient)
Together: subject SMALLER than the combined environment. The world, not the face, is the protagonist of the frame."""


# === 七要素结构（v0.2.3 顶级铁律）===
# 替换 v0.2.2 的 NARRATIVE_COMPOSITION_BOOST。visual 必须按这个结构组织，每要素 1-2 句必填。
CINEMATIC_FRAMEWORK_BOOST = """
CINEMATIC FRAMEWORK (mandatory - every panel prompt must be written in this 7-element structure,
each in its own short clause, IN THIS ORDER):

[1] SUBJECT: who is in the scene (one concrete character + immediate companions, listed as noun phrases
    like "the captive commander, three enemy soldiers, a low-lit brazier" — NOT as paragraphs).
[2] ACTION: what they are doing — use STRONG REACTION VERBS that imply cause-and-effect:
    "yanking the rope, causing straw dummies to dangle", "slashing downward, scattering sparks",
    "biting down hard, lips bleeding". Static poses like "stands" / "looks at" / "is shown" are FORBIDDEN.
[3] CAMERA: state ALL FOUR — shot size, angle, lens, depth of field
    (use the CAMERA FRAMING RULES vocabulary above).
[4] PLACEMENT: where the subject sits in the frame (rule of thirds, asymmetric composition).
    Example: "subject positioned on the left third, generous negative space on the right for tension".
[5] DEPTH LAYERS: foreground + midground + background, each as a noun-phrase fragment
    (NOT paragraphs - tokens the model can grab).
[6] LIGHTING: source, direction, color temperature, quality
    ("hard side-light from a single candle on the left, deep crimson wash from behind,
    ambient cinnabar smoke glow", NOT "dramatic lighting").
[7] MOOD/PALETTE: emotional baseline tied to color palette
    ("tense anticipation in desaturated ink black + cinnabar red + bone white",
    "defiant collapse in saturated crimson + cold iron grey + ash black").
"""

# === v0.3.0: chinese_lianhuanhua_classic 中性脸 + 妆发按性别分支 ===
# 2026-09-24 用户反馈:
#   - v0.2.9 默认 anchor 把妆发写成"女性化"(桃花腮+花钿+步摇+柳叶眉+樱桃小口),只能用于女性主角
#   - 当主题是男性主角(张巡/郭子仪),planner visual 写"Zhang Xun 40+ male" 但 anchor 强制桃花腮/步摇
#     → 模型脸部女性化 + 服饰中性 → 性转成女性
#   - 修复:把脸部特征 + 妆发分开,脸部中性任何性别共用,妆发按 FEMALE/MALE 独立分支

# v0.3.0 中性脸部特征 (任何性别都共用,不会导致性转)
CHARACTER_CN_LIANHUANHUA_FACE = (
    "Chinese illustrated figure on rice paper with ink-brush gongbi technique (NOT 3D, NOT anime, "
    "NOT photorealistic, NOT oil painting): "
    "(1) Face shape: distinctively pretty Chinese oval face (鹅蛋脸) with refined chin, smooth "
    "fair skin with subtle warm undertone, refined natural features that look attractive and "
    "individual — NOT generic, NOT interchangeable. "
    "(2) Eyes: elegant slightly upturned Chinese eyes with clear double eyelid, soft dark iris, "
    "natural lash line, gentle gaze — distinctive and pretty, NOT round anime eyes, NOT phoenix "
    "triangular. Each character has their OWN eye expression. "
    "(3) Eyebrows: well-groomed brows appropriate to the gender branch selected below. "
    "(4) Lip: refined cupid's bow lips with subtle natural color — see gender branch for tint. "
    "(5) Hair: period-correct Han-Chinese hairstyle with distinctive ornament — see gender branch. "
    "AGE-SPECIFIC STYLING: "
    "  - Young leads (20s): delicate refined features. "
    "  - Mature leads (30s-50s): dignified, composed, with subtle age lines where appropriate. "
    "Body: classical Chinese figure proportions, slender dignified bearing. "
    "Costume: period-correct Chinese attire (汉代深衣襦裙 / Tang round-collar robe / Song "
    "straight-collar) with white-line + red-line calligraphic outline. "
    "Expression: gentle resolute emotion held in natural restraint, beautiful but never flirtatious. "
    "OVERALL: museum-quality Chinese illustration that captures individual beauty and personality — "
    "the technique is traditional 戴敦邦派 but the subjects are lovely, distinctive, modern-feeling "
    "Chinese people from a top Chinese art book."
)

# v0.3.0 女性妆发分支 (桃花腮 + 花钿 + 步摇 + 柳叶眉 + 樱桃小口)
CHARACTER_CN_LIANHUANHUA_GENDER_FEMALE = (
    "FEMALE-GENDER STYLING (must apply to all female leads in the scene): "
    "(a) Cheek: subtle pink blush on cheek apples (桃花腮). "
    "(b) Eyebrows: 柳叶眉 — delicate willow-leaf shaped brows, gently arched, tapered to fine "
    "point at temple, drawn in single ink line. "
    "(c) Lip: 樱桃小口 — small refined cupid's bow lips with subtle vermilion tint (桃红), "
    "gentle and pretty. "
    "(d) Hair: high topknot 高髻 with gold-inlaid hairpin 步摇 + small delicate flower 簪花 + "
    "花钿(额间朱砂点) for young lead, simpler for mature female. "
    "(e) Skin: delicate, fair, subtle pink undertone."
)

# v0.3.0 男性妆发分支 (玉冠/束发 + 直眉 + 无桃花腮 + 无花钿 + 玉簪/金簪)
# 不写"square jaw + phoenix eyes + 蓄须"那种过度古典脸(用户反馈:太旧现代读者不亲近)
# 改写为"现代审美男性":清爽脸 + 适度男性化五官 + 朝代配饰 + 直眉或微剑眉
CHARACTER_CN_LIANHUANHUA_GENDER_MALE = (
    "MALE-GENDER STYLING (must apply to all male leads in the scene): "
    "(a) Cheek: NO pink blush, clean fair skin with subtle warm undertone, dignified. "
    "(b) Eyebrows: straight thick natural brows, masculine but refined — slightly thicker "
    "and straighter than female willow-leaf brows, drawn in single ink line. NEVER delicate "
    "willow-leaf, NEVER phoenix-triangular arch. "
    "(c) Lip: small to medium lips, natural muted color (NOT vermilion pink), restrained and "
    "decisive line of jaw. "
    "(d) Hair: period-correct Han-Chinese — official's cap 幞头/官帽/乌纱 for officials, "
    "high topknot 高髻 with jade or gold hairpin 玉簪/金簪 for warriors/scholars (NOT 步摇 — "
    "too feminine), NO 花钿, NO 簪花. Clean dignified, NOT flowing romantic long hair. "
    "(e) Facial hair: period-appropriate — clean-shaven scholar, thin mustache for officials, "
    "short dignified beard for commanders, goatee for elders, drawn with individual brush wisps. "
    "NEVER peach-fuzz, NEVER wispy pretty-boy beard. "
    "(f) Skin: clean, fair with subtle warm undertone, slightly more angular than female. "
    "Body posture: upright dignified, broad-shouldered masculine proportions when in armor/robe."
)

# v0.3.0 默认 anchor = 中性脸 + 女性妆发 (历史典故中国古典风格默认偏女性主角)
# build_image_prompt 会按 visual 里的 [GENDER:xx] 标记自动切换到对应分支
CHARACTER_CN_LIANHUANHUA_MODERN = (
    f"{CHARACTER_CN_LIANHUANHUA_FACE} {CHARACTER_CN_LIANHUANHUA_GENDER_FEMALE}"
)

CHARACTER_ANCHORS: dict[str, str] = {
    "new_yorker": CHARACTER_SCIENTIST,
    "us_mid_century": CHARACTER_SCIENTIST,
    "cn_xuanfeng": CHARACTER_ANCIENT_CN,
    "guochao_manhua": CHARACTER_ANCIENT_GUOCHAO,
    # v0.2.9: 默认走 modern face variant(用户 2026-09-23 反馈偏好),要纯古典戴敦邦脸
    # 可显式传 character_anchor=CHARACTER_CN_LIANHUANHUA_ANCESTOR 覆盖
    "chinese_lianhuanhua_classic": CHARACTER_CN_LIANHUANHUA_MODERN,
}


def get_character_anchor(style_id: str) -> str:
    """根据风格返回对应角色锚点。"""
    return CHARACTER_ANCHORS.get(style_id, CHARACTER_SCIENTIST)

# === v0.3.20 性别单一真源 =============================================
# 事故：page 级按 [GENDER:xx] 切男女分支，char 级拿写死默认锚点（含 FEMALE
# 妆发），导致 characters/夫差-front.png 被画成女性，再经 i2i 污染每一页。
# 修法：性别解析收敛到**一个函数**，page / char 两级共用。

# 中文名 → 已知性别（正史人物库）。用于 characters[] 没写 gender 时的兜底。
# 覆盖不了所有人物（planner 是动态生成的），所以只作 fallback。
KNOWN_GENDER: dict[str, str] = {
    # 先秦
    "孔子": "male", "老子": "male", "庄子": "male", "孟子": "male",
    "孙膑": "male", "廉颇": "male", "蔺相如": "male", "荆轲": "male",
    "勾践": "male", "夫差": "male", "文种": "male", "范蠡": "male",
    "伍子胥": "male", "伍员": "male", "专诸": "male", "要离": "male",
    "西施": "female", "妲己": "female", "貂蝉": "female",
    "管仲": "male", "鲍叔牙": "male", "晏婴": "male", "商鞅": "male",
    "屈原": "male", "荀子": "male", "墨子": "male", "韩非": "male",
    # 秦汉
    "秦始皇": "male", "刘邦": "male", "项羽": "male", "韩信": "male",
    "张良": "male", "萧何": "male", "霍去病": "male", "卫青": "male",
    "李广": "male", "苏武": "male", "李陵": "male", "常惠": "male",
    "卫律": "male", "司马迁": "male", "班超": "male", "王昭君": "female",
    "王莽": "male", "董仲舒": "male", "赵充国": "male", "冒顿": "male",
    "呼韩邪": "male", "细君公主": "female", "解忧公主": "female",
    # 三国两晋
    "诸葛亮": "male", "刘备": "male", "关羽": "male", "张飞": "male",
    "赵云": "male", "曹操": "male", "周瑜": "male", "陆逊": "male",
    "司马懿": "male", "司马昭": "male", "陶渊明": "male", "祖逖": "male",
    "谢安": "male", "王羲之": "male", "陈寿": "male",
    # 隋唐
    "李世民": "male", "李渊": "male", "李靖": "male", "魏征": "male",
    "郭子仪": "male", "张巡": "male", "许远": "male", "颜真卿": "male",
    "安禄山": "male", "史思明": "male", "李光弼": "male",
    "房玄龄": "male", "杜如晦": "male", "长孙无忌": "male",
    "武则天": "female", "杨贵妃": "female", "李白": "male", "杜甫": "male",
    "白居易": "male", "王维": "male", "李清照": "female",
    # 宋元明清
    "岳飞": "male", "文天祥": "male", "辛弃疾": "male", "陆游": "male",
    "苏轼": "male", "王安石": "male", "寇准": "male", "包拯": "male",
    "虞允文": "male", "毕再遇": "male", "王坚": "male", "余玠": "male",
    "曾国藩": "male", "左宗棠": "male", "林则徐": "male",
    "郑成功": "male", "戚继光": "male", "袁崇焕": "male", "李自成": "male",
    "朱元璋": "male", "朱棣": "male", "康熙": "male", "雍正": "male",
    "乾隆": "male", "崇祯": "male", "秦桧": "male", "韩世忠": "male",
    "孙中山": "male", "鲁迅": "male", "蔡元培": "male",
    "文成公主": "female", "杨门女将": "female",
    "王宝钏": "female", "秦香莲": "female", "卓文君": "female",
}

# 中文 → 英文 性别词映射
_GENDER_WORDS = {
    "male": ("male", "man", "men", "boy", "he", "his", "him", "himself",
             "gentleman", "warrior", "lord", "father", "son", "brother",
             "king", "emperor", "general", "duke", "prince", "official",
             "elder", "old man", "young man", "male character"),
    "female": ("female", "woman", "women", "girl", "she", "her", "hers",
               "herself", "lady", "mother", "daughter", "sister", "wife",
               "queen", "empress", "princess", "dame", "girl", "old woman",
               "young woman", "female character", "beauty"),
    # 中文
    "中": ("男", "女子", "女人", "她", "他的妻子", "夫人", "小姐", "姑娘", "母"),
    "中女": ("女", "母", "妻", "娘", "妇", "姑", "姊", "妹"),
}

_FEMALE_HINT_CN = ("女", "她", "母", "妻", "妾", "姑", "姊", "妹", "娘",
                   "夫人", "小姐", "姑娘", "妇", "妃", "后")
_MALE_HINT_CN = ("男", "他", "父", "子", "夫", "兄", "弟", "君", "侯",
                 "伯", "公", "将军", "大夫", "士", "臣")


def resolve_gender(
    text: str = "",
    explicit: str = "",
    name: str = "",
) -> str:
    """**性别解析的唯一入口**（v0.3.20）。page 级和 char 级都调这个。

    优先级（从强到弱，**越靠前越可信**）：
      1. explicit —— 调用方显式传的 gender 参数（characters[].gender 字段）
      2. text 里的 `[GENDER:xx]` 标记 —— planner 的显式声明
      3. name 在 KNOWN_GENDER 里 —— 正史人物性别
      4. text 里的性别代词/称谓 —— 中文 + 英文
      5. name 自身的构词线索（如「西施」「王昭君」）
      6. **默认 male**

    第 6 条的默认值是 v0.3.20 的关键改动：原默认是 female
    （`CHARACTER_CN_LIANHUANHUA_MODERN` 内含 FEMALE 妆发分支），
    对"主角多半是男性"的历史题材是错的默认值。
    **默认 male 是更安全的错** —— 错判成女性会让男性角色性转、
    污染 i2i 参考图并波及全部页面；错判成男性只影响女性角色，
    而女性角色在历史题材里通常有明确的女性称谓能被第 4/5 条抓到。
    """
    # 1) explicit
    if explicit:
        e = explicit.strip().lower()
        if e in ("male", "m", "男", "男性"):
            return "male"
        if e in ("female", "f", "女", "女性"):
            return "female"
        if e in ("mixed", "both", "混合"):
            return "mixed"

    t = (text or "").lower()

    # 2) [GENDER:xx] 标记
    import re as _re
    m = _re.search(r"\[gender:\s*(male|female|mixed)\]", t, _re.I)
    if m:
        return m.group(1).lower()

    # 3) 正史人物库
    nm = (name or "").strip()
    if nm in KNOWN_GENDER:
        return KNOWN_GENDER[nm]
    # 名字里含已知人物（如「吴王夫差」）
    for known, g in KNOWN_GENDER.items():
        if len(known) >= 2 and known in nm:
            return g

    # 4) 代词/称谓（英文优先，中文次之）
    for lang, groups in (("en", _GENDER_WORDS), ):
        for g, words in groups.items():
            for w in words:
                if _re.search(r"\b" + _re.escape(w) + r"\b", t):
                    return g
    # 中文线索（测试打脸过：原实现用 `sum(1 for w in ... if w in text)`，
    # 但「女子」这类词不含任何单字条目，且"男"常作为「男子/男人」出现，
    # 计数法被无关字稀释。改成**按词表顺序匹配，优先女性称谓** ——
    # 中文语境里明确写"女"是强信号，男性线索往往只是泛称）。
    txt = text or ""
    for w in ("女子", "女人", "女性", "少女", "妇人", "她"):
        if w in txt:
            return "female"
    for w in ("男子", "男人", "男性", "少年", "书生", "他"):
        if w in txt:
            return "male"

    # 5) 名字构词线索
    if nm:
        if any(w in nm for w in ("王昭君", "西施", "貂蝉", "妃", "后", "公主")):
            return "female"

    # 6) 默认 male（见 docstring）
    return "male"


def get_gender_anchor(gender: str) -> str:
    """按性别取连环画锚点片段（page / char 级共用）。"""
    base = CHARACTER_CN_LIANHUANHUA_FACE
    g = (gender or "").lower()
    if g == "female":
        return f"{base} {CHARACTER_CN_LIANHUANHUA_GENDER_FEMALE}"
    if g == "mixed":
        return (f"{base} {CHARACTER_CN_LIANHUANHUA_GENDER_FEMALE} "
                f"{CHARACTER_CN_LIANHUANHUA_GENDER_MALE}")
    return f"{base} {CHARACTER_CN_LIANHUANHUA_GENDER_MALE}"


def _resolve_cn_lianhuanhua_anchor(gender: str, scene_description: str) -> str:
    """v0.3.0: 按 gender 拼装 chinese_lianhuanhua_classic 锚点。

    v0.3.20：本函数已委托给 `resolve_gender()`（唯一真源），
    避免 page 级和 char 级两套逻辑漂移。

    优先级:
      1. 显式 gender 参数(female/male/mixed)— build_image_prompt 调用方直接指定
      2. 显式 [GENDER:female|male|mixed] 标记在 visual 开头
      3. visual 描述双向检测:中文代词 + 英文代词同时出现 → mixed
      4. 否则默认 female

    v0.3.0 背景:v0.2.9 anchor 把妆发硬写"女性化"(桃花腮+花钿+步摇+柳叶眉),
    导致男性主角(张巡/郭子仪等)被性转成女性。本函数让 build_image_prompt
    按性别选对应妆发分支,脸部特征共用中性 FACE 子块。
    """
    text = (scene_description or "")[:500]

    # 1) 显式 gender 参数(优先)
    if gender in ("female", "male", "mixed"):
        g = gender
    else:
        # 2) 显式 [GENDER:xx] tag
        m = re.search(r"\[GENDER:(female|male|mixed)\b\]", scene_description or "", re.IGNORECASE)
        if m:
            g = m.group(1).lower()
        else:
            # 3) 双向检测:男 + 女关键词都出现 → mixed
            # 常见中国男性名字识别(姓氏:Zhang/Wang/Li/Liu/Chen/Guo/Sun + 名字含"巡/云/义/为"等常见男性字)
            known_male_names = ("Zhang Xun", "Guo Ziyi", "Li Bai", "Du Fu", "Confucius", "Lao Tzu")
            known_female_names = ("Wang Zhaojun", "Yang Guifei", "Wu Zetian", "Princess")
            female_cn = "她" in text or "妻" in text or "妇" in text or "女" in text
            male_cn = "他" in text or "夫" in text or "郎" in text or "男" in text or "臣" in text or "将" in text
            female_pat = r"(?:^|\W)(she|her|woman|women|girl|lady|maiden|princess|wife)(?:\W|$)"
            male_pat = r"(?:^|\W)(he|his|him|man|men|boy|warrior|general|official|scholar|commander|soldier|husband)(?:\W|$)"
            female_en = bool(re.search(female_pat, text, re.IGNORECASE))
            male_en = bool(re.search(male_pat, text, re.IGNORECASE))
            f_count = int(female_cn) + int(female_en) + sum(1 for n in known_female_names if n in text)
            m_count = int(male_cn) + int(male_en) + sum(1 for n in known_male_names if n in text)
            if f_count > 0 and m_count > 0:
                g = "mixed"
            elif m_count > 0:
                g = "male"
            elif f_count > 0:
                g = "female"
            else:
                g = "female"  # 默认

    base = CHARACTER_CN_LIANHUANHUA_FACE
    if g == "female":
        return f"{base} {CHARACTER_CN_LIANHUANHUA_GENDER_FEMALE}"
    elif g == "male":
        return f"{base} {CHARACTER_CN_LIANHUANHUA_GENDER_MALE}"
    else:  # mixed
        return f"{base} {CHARACTER_CN_LIANHUANHUA_GENDER_FEMALE} {CHARACTER_CN_LIANHUANHUA_GENDER_MALE}"




# === 通用负向关键词 ===
COMMON_NEGATIVE = (
    "NO anime, NO Pixar, NO Disney, NO chibi, NO moe, NO big anime eyes, "
    "NO kawaii, NO photorealistic, NO 3D render, NO painterly, "
    "NO English signage, NO fake text, NO speech bubble, NO caption box, "
    "NO watermark, NO numbers, NO digits, NO letters, NO Japanese kana, "
    "NO Chinese characters, NO math symbols, NO year labels"
)


STYLES: dict[str, StylePreset] = {

    # === 1. new_yorker · 纽约客式 · 报刊讽刺 ===
    "new_yorker": StylePreset(
        id="new_yorker",
        name_zh="纽约客式 · 报刊讽刺",
        name_en="New Yorker editorial cartoon",
        category="A · 黑白 Risograph 杂志风",
        use_cases=("知识科普", "商业评论", "社会议题", "严肃话题", "成人读者"),
        prompt_en=(
            "Single-panel editorial cartoon in style of The New Yorker magazine, "
            "like a cartoon by Tom Bachtell or Liam Walsh. Risograph print style on cream paper. "
            "Subtle cream paper texture, slight ink bleed on edges, slight Risograph "
            "misregistration where color blocks don't perfectly align, subtle halftone dot "
            "pattern in flat color areas, slight grain. Clean hand-drawn ink lines, thin to "
            "medium weight, slight hand-drawn imperfection, pen on paper feel. "
            "Flat low-saturation color blocks (limited palette: cream, black, soft grey, "
            "muted teal accent), no gradients, no airbrush. Editorial composition with "
            "deliberate negative space, focal subject anchored off-center, "
            "subtle visual metaphor through objects and spatial relationships."
        ),
        prompt_zh="纽约客式单格漫画，Risograph 印刷质感，米色纸 + 平面色块 + 细线条。",
        negative=COMMON_NEGATIVE,
    ),

    # === 2. us_mid_century · 美式中世纪 · 复古杂志 ===
    "us_mid_century": StylePreset(
        id="us_mid_century",
        name_zh="美式中世纪 · 复古杂志",
        name_en="US mid-century retro editorial",
        category="B · 50-60 年代杂志风",
        use_cases=("商业评论", "品牌故事", "设计感", "生活美学", "职场/财经"),
        prompt_en=(
            "Single-panel illustration in mid-century American editorial style "
            "(1950s-60s magazine illustration). Bold flat color shapes with confident edges, "
            "limited muted retro palette (mustard yellow, teal, brick red, cream, ink black). "
            "Confident ink contour with slight unevenness, retro typographic sensibility. "
            "Composition is geometric and balanced, often with diagonal energy and "
            "strong foreground framing. Subjects rendered with stylized simplicity "
            "but recognizable human proportions, not chibi or cartoonish. "
            "Surface feels printed, slight color overlay between blocks. "
            "Atmosphere evokes optimistic mid-century commercial art."
        ),
        prompt_zh="美式中世纪复古风，1950-60s 杂志插画感，扁平色块 + 复古调色。",
        negative=COMMON_NEGATIVE + ", NOT digital gradient, NOT vector flatness",
    ),

    # === 3. cn_xuanfeng · 宣风 · 国风写意 ===
    "cn_xuanfeng": StylePreset(
        id="cn_xuanfeng",
        name_zh="宣风 · 国风写意",
        name_en="Xuanfeng Chinese freehand brushwork",
        category="C · 中国水墨写意",
        use_cases=("历史典故", "古籍解读", "东方美学", "国学", "哲学/心理学"),
        prompt_en=(
            "Single-panel educational illustration in Chinese xuanfeng (freehand brush) style. "
            "Bold ink brushstrokes, rice paper texture, splashed ink effects, "
            "calligraphic line quality with deliberate gaps and dry-brush edges. "
            "Limited ink-black + cinnabar red + bamboo green palette. "
            "Subjects rendered with energy and movement, never stiff. "
            "Composition balances dense ink details with generous white space, "
            "evoking classical Chinese scroll painting atmosphere. "
            "Mood is contemplative, literary, historical. "
            "No pixel-perfect detail; embrace painterly imperfection."
        ),
        prompt_zh="中国水墨写意风，大胆笔触，留白与飞白兼具，墨色为主、朱砂为辅。",
        negative=COMMON_NEGATIVE + ", NO pencil sketch, NO graphite texture, NO flat anime style",
    ),

    # === 4. guochao_manhua · 国潮古风条漫 ===
    # 2026-09-21 新增：用户实际偏爱国潮赛璐璐 / 古风条漫（《镖人》《一人之下》类）
    # 多于纯传统水墨写意。历史/典故类知识漫画第一推荐。
    "guochao_manhua": StylePreset(
        id="guochao_manhua",
        name_zh="国潮古风条漫",
        name_en="Guochao ancient Chinese manhua (cel-shaded)",
        category="D · 国潮赛璐璐 + 古装 + 现代条漫分镜",
        use_cases=("历史典故", "中国故事", "古籍解读", "武侠/江湖", "东方美学"),
        prompt_en=(
            "Single-panel illustration in modern Chinese guochao manhua style, "
            "blending contemporary webcomic aesthetics with classical Chinese subject matter. "
            "Influenced by Renshi Xiami (一人之下), Biao Ren (镖人), Feng Shen Ji (封神记): "
            "bold flat color blocks with clean dark contour lines, no gradients, no soft airbrush. "
            "Cinnabar red + crow black + jade green + gold + moon white palette. "
            "Cel-shaded shading with solid shadow shapes, not soft transitions. "
            "Character body proportions are modern manhua ratio (about 1:2 head-to-body), "
            "with large expressive eyes, sharp jawline, dynamic pose, strong movement. "
            "Subjects in hanfu/scholarly robe with crossed collar, fitted waist sash, "
            "flowing wide sleeves, jade ornaments; hair tied in high topknot with cloth ribbon. "
            "Composition balances dramatic close-up with environmental storytelling. "
            "Mood: dramatic, vivid, contemporary Chinese action comic, respectful of history."
        ),
        prompt_zh="国潮古风条漫：现代国漫分镜语言（《镖人》《一人之下》类）+ 古装人物 + 赛璐璐平涂 + 鲜艳色块（朱砂+鸦青+玉绿+金+月白）。",
        negative=COMMON_NEGATIVE + ", NO watercolor, NO ink wash, NO painterly texture, "
        + "NO pencil sketch, NO traditional Chinese scroll painting, NO gongbi realism, "
        + "NOT weak pale palette, NOT water-ink feel",
    ),

    # === 5. chinese_lianhuanhua_classic · 中国古典连环画 ===
    # 2026-09-21 新增（用户反馈）：以戴敦邦为绝对核心，融合 6 脉中国古典连环画/人物画派。
    # 戴敦邦 — 中国古典人物画底子（红楼/三国/水浒插图）：
    #                戏剧化表情与夸张动作但有节制、古典人物面部（方颌、丹凤/三角眼、短须）、
    #                大笔触水墨淡彩渲染 + 白描红线勾描、朝代服饰礼制考据。
    # 刘继卣 — 史诗感：《大闹天宫》《武松打虎》系列的水墨 + 白描 + 工笔结合，纪念碑式构图。
    # 王叔晖 — 东方高级审美：《西厢记》仕女图的线条高洁、装饰感与工笔重彩。
    # 冯远 — 当代历史绘画：《人民公仆》系的主题性水墨人物群像。
    # 伍 — 历史考据派：服饰、兵器、礼制、器物按朝代严考。
    # 顾炳鑫 / 贺友直 — 上海连环画叙事派：左→右、上→下分镜编排、动作连贯、人物关系清晰。
    # 学习：戴敦邦人物画、刘继卣史诗构图、王叔晖线条审美、冯远厚重、伍考据、顾炳鑫/贺友直分镜。
    # 绝不学：欧洲人面孔 / 西方服饰 / 西方审美 / 卡通化 / 赛璐璐。
    "chinese_lianhuanhua_classic": StylePreset(
        id="chinese_lianhuanhua_classic",
        name_zh="中国古典连环画",
        name_en="Chinese classic lianhuanhua (serial illustrated narrative art, Dai Dunbang lineage)",
        category="E · 中国古典连环画派 · 戴敦邦核心 + 刘继卣史诗 + 王叔晖审美 + 冯远笔法 + 顾炳鑫/贺友直分镜",
        use_cases=(
            "历史典故", "中国故事", "古籍解读", "圣贤帝王", "江湖侠义",
            "古典小说插图", "连环画叙事", "宏大叙事",
        ),
        prompt_en=(
            "Chinese lianhuanhua (连环画) illustrated narrative art on traditional XUAN PAPER "
            "(rice paper), NOT on canvas. Gongbi (工笔) + baimiao (白描) + xieyi (写意) ink "
            "wash technique with hand-held Chinese brush (毛笔). "
            "STYLE LOCK: classical Chinese hand-painted illustration in the tradition of Dai "
            "Dunbang, Liu Jiyou, Wang Shuhui, He Youzhi. FLAT-INK + COLORED INK illustration, "
            "NOT oil painting, NOT photorealism, NOT 3D, NOT anime, NOT Disney, NOT "
            "storybook-CG. "
            "Distinct technique marks the medium: visible brush bristle strokes, deliberate "
            "ink-bleed, dry-brush edges (飞白), rice-paper-white space used as compositional "
            "breathing room, vermilion-detail line work (朱砂勾线) on faces and garment folds, "
            "gongbi color planes (cinnabar + indigo + ochre + ink + bone-white), no "
            "photographic shading. "
            "Faces: Dai Dunbang classical Chinese face - square jaw, narrow phoenix-eye 丹凤眼 or "
            "triangular-eye 三角眼 drawn in single firm brush line, sword-brow 剑眉, period-"
            "correct beard or clean-shaven per role, dignified weathered age, theatrical "
            "intensity held in restraint. "
            "Period-accurate Chinese costume: Tang round-collar robe + soft-brim 幞头; Song "
            "straight-collar scholar robe; Ming official's wushamao 乌纱帽, etc. "
            "Auxiliary influences: Liu Jiyou's epic ink drama, Wang Shuhui's linework, Wu "
            "lianhuanhua school rigorous period research, Gu Bingxin / He Youzhi serial "
            "narrative composition. "
            "HARD PROHIBITIONS: NO oil paint, NO impasto, NO canvas, NO Turner-style haze, NO "
            "Western classical painting, NO European faces, NO Disney, NO anime, NO neon."
        ),
        prompt_zh=(
            "中国古典连环画派（戴敦邦、刘继卣、王叔晖、贺友直系）：毛笔宣纸 + 工笔 + 白描 + "
            "写意，宣纸为底。飞白笔触 + 朱砂勾线 + 工笔重彩设色（朱砂/靛青/赭石/墨/留白） + "
            "留白构图。面方颌丹凤眼剑眉，寿星额，戏剧化但有节制的表情。朝代服饰按考据。"
            "绝不油画、绝不 impasto、绝不西方审美。"
        ),
        negative=(
            "NO oil paint, NO impasto, NO canvas, NO Western painting, NO Turner haze, "
            "NO European face, NO Disney, NO anime, NO photorealism, NO 3D, NO Pixar, "
            "NO Western costume, NO round anime eyes, NO pale pink skin, "
            "NO neon palette, NO Risograph, NO vector flatness, "
            "NO digital illustration, NO commercial CG, NO modern manga, "
            "NO watercolor wash, NO soft pastel, NO airbrush, NO gradient shading, "
            "NO modern flat-design illustration, NO commercial concept art, "
            "NO text, NO letters, NO Chinese characters, NO kana, NO digits, NO watermark"
        ),
    ),
}


def get_style(style_id: str) -> StylePreset:
    return STYLES.get(style_id, STYLES["new_yorker"])


def list_styles() -> list[dict]:
    return [
        {
            "id": s.id,
            "name_zh": s.name_zh,
            "name_en": s.name_en,
            "category": s.category,
            "use_cases": list(s.use_cases),
        }
        for s in STYLES.values()
    ]


# v0.2.5 (2026-09-22)：中国画风格分流。哪些风格走 CHINESE_PAINTING_BOOST 而不是 cinematic 三件套。
TRADITIONAL_CN_STYLES: frozenset[str] = frozenset({
    "chinese_lianhuanhua_classic",
    "cn_xuanfeng",
    "guochao_manhua",
})


# === v0.2.6: scene_description cinematic 词剥离器 ===
# planner LLM 经常在 visual 字段里写 cinematic 镜头语言（35mm/low angle/deep focus），
# 这些词会覆盖中国画风格的"painted illustration"声明，导致模型跑偏现代写实。
# 在中国画风格时自动剥离并替换为构图词。
import re as _re

_CINEMATIC_TERM_PATTERNS: list[tuple[_re.Pattern, str]] = [
    (_re.compile(r"\(\s*\d+\s*mm[^)]*\)", _re.IGNORECASE), ""),
    (_re.compile(r",\s*\d+\s*mm[^,)]*", _re.IGNORECASE), ""),
    (_re.compile(r"\s\d+\s*mm\s*lens", _re.IGNORECASE), ""),
    (_re.compile(r"\bwide shot\b", _re.IGNORECASE), "Expansive composition"),
    (_re.compile(r"\bextreme wide shot\b", _re.IGNORECASE), "Panoramic composition"),
    (_re.compile(r"\bmedium shot\b", _re.IGNORECASE), "Mid-range composition"),
    (_re.compile(r"\bclose-up shot\b", _re.IGNORECASE), "Tight facial composition"),
    (_re.compile(r"\bthree[\s_-]quarter(?:\s+shot)?\b", _re.IGNORECASE), "Mid-range composition"),
    (_re.compile(r"\blow[\s_-]angle\b", _re.IGNORECASE), "from a low position"),
    (_re.compile(r"\bhigh[\s_-]angle\b", _re.IGNORECASE), "from a raised position"),
    (_re.compile(r"\bbird'?s[\s_-]eye\b", _re.IGNORECASE), "from above"),
    (_re.compile(r"\bdutch[\s_-]tilt\b", _re.IGNORECASE), "oblique perspective"),
    (_re.compile(r"\bshallow[\s_-]*dof\b", _re.IGNORECASE), "with crisp outlines"),
    (_re.compile(r"\bdeep[\s_-]*focus\b", _re.IGNORECASE), "with crisp layering"),
    (_re.compile(r"\bshallow[\s_-]*depth\b", _re.IGNORECASE), "with crisp outlines"),
    (_re.compile(r"\bdeep[\s_-]*depth\b", _re.IGNORECASE), "with crisp layering"),
    (_re.compile(r"\beye[\s_-]*level\b", _re.IGNORECASE), "at eye height"),
    (_re.compile(r"\bcamera\b", _re.IGNORECASE), "viewpoint"),
    # v0.2.6+: 七要素段标题剥离（planner LLM 写 "CAMERA:" / "PLACEMENT:" 等）
    (_re.compile(r"\bCAMERA\s*:\s*", _re.IGNORECASE), "Composition: "),
    (_re.compile(r"\bPLACEMENT\s*:\s*", _re.IGNORECASE), "Position: "),
    (_re.compile(r"\bDEPTH\s+LAYERS?\s*:\s*", _re.IGNORECASE), "Layers: "),
    (_re.compile(r"\bLIGHTING\s*:\s*", _re.IGNORECASE), "Light: "),
    (_re.compile(r"\bMOOD(?:P\s*:\s*|/PALETTE)?\s*:\s*", _re.IGNORECASE), "Mood: "),
    (_re.compile(r"\bSUBJECT\s*:\s*", _re.IGNORECASE), "Subject: "),
    (_re.compile(r"\bBACKGROUND\s*:\s*", _re.IGNORECASE), "Background: "),
    (_re.compile(r"\bACTION\s*:\s*", _re.IGNORECASE), "Action: "),
]


# v0.3.9: 匹配 v0.3.7 让 LLM 写的 `// 中文速记`。
# 速记只用于**审阅展示**，绝不能进图像 prompt（见 build_image_prompt 里的说明）。
#
# v0.3.15 修复：原正则的 `$` 兜底分支会在「速记后面还有英文内容」时
# 把它一起吃掉 —— 实测把 p1 的 visual 从 981 字符截到 171 字符，
# CAMERA/MOOD 等要素整段丢失。
# 现在改成：**只删 `//` + 连续中文速记词**，遇到任何非中文字符立即停止。
_ZH_NOTE_RE = _re.compile(r"\s*//\s*[一-鿿][一-鿿\s·、,，]*")
# 兼容旧数据：速记后紧跟下一个大写要素标签的情况（保留标签，只删速记）
_ZH_NOTE_RE2 = _re.compile(r"\s*//\s*[一-鿿][一-鿿\s·、,，]*?(?=\b[A-Z][A-Za-z ]{2,}\s*[:：])")

# v0.3.15: 剥掉**纯中文夹注**（如 `black official cap (帻)` / `圆领袍（深灰）`）。
# 这类单汉字/短词混在英文 prompt 里同样会冲淡风格锁定，但它们不是 `//` 速记，
# 上面两条正则管不到。
#
# **安全性论证**：右括号 `)` 硬性界定匹配边界，匹配内容 100% 是汉字，
# 因此**不可能吞掉括号外的任何英文**。这与 v0.3.15 之前那个带 `$` 兜底的
# 宽泛正则（把 p1 visual 从 981 截到 171 字符）有本质区别。
_ZH_GLOSS_RE = _re.compile(r"\s*[（(][一-鿿]{1,8}[)）]\s*")

# v0.3.18：CONCEPT 段抽取正则。
# planner 要求每页 visual 首段写 `CONCEPT: <核心概念> → <画面里的具体元素> // 中文速记`，
# build_image_prompt 把它整段提到 prompt 头部（最高权重区）。
# 右边界用「下一个大写要素标签」或行尾，双保险，避免吞掉 SUBJECT 及之后的内容。
_CONCEPT_RE = _re.compile(
    r"CONCEPT\s*[:：]\s*(.*?)(?=\n\s*(?:SUBJECT|ACTION|CAMERA|PLACEMENT|DEPTH|LIGHTING|MOOD)\b|\Z)",
    _re.IGNORECASE | _re.DOTALL,
)


def _strip_cinematic_terms(text: str) -> str:
    """v0.2.6: 从 scene_description 里剥掉/替换 cinematic 词。"""
    out = text
    for pattern, replacement in _CINEMATIC_TERM_PATTERNS:
        out = pattern.sub(replacement, out)
    # 折叠多空格
    out = _re.sub(r"\s{2,}", " ", out).strip()
    return out


def build_image_prompt(
    style_id: str,
    scene_description: str,
    character_anchor: str | None = None,
    extra_negative: str = "",
    gender: str = "auto",
) -> str:
    """拼最终 image prompt。强制角色一致性 + 零文字硬约束。

    v0.2.5 (2026-09-22): 按风格分流 booster —— 中国画风格走 CHINESE_PAINTING_BOOST，
    避免被 cinematic 镜头语言覆盖到现代写实。

    v0.2.6 (2026-09-22): 中国画风格自动从 scene_description 剥掉 cinematic 词（35mm/low angle...），
    防止 planner LLM 输出的镜头术语覆盖风格声明。

    v0.3.0 (2026-09-24): 加 gender 参数,chinese_lianhuanhua_classic 按性别拼装 anchor,
    防止男性主角被性转成女性。gender="auto" 时从 scene_description 检测
    ([GENDER:xx] tag / 中文代词 / 英文代词)。

    Args:
        style_id: 风格 ID（new_yorker / us_mid_century / cn_xuanfeng / guochao_manhua / chinese_lianhuanhua_classic）
        scene_description: 单页画面描述（planner 拆出的 visual 字段）
        character_anchor: 角色一致性锚点（None = 自动按风格 + gender 选）
        extra_negative: 额外负向词（如具体场景禁忌）
        gender: v0.3.0 新增 - auto/female/male/mixed。仅 chinese_lianhuanhua_classic 生效。
    """
    style = get_style(style_id)
    if character_anchor is None:
        if style_id == "chinese_lianhuanhua_classic":
            character_anchor = _resolve_cn_lianhuanhua_anchor(gender, scene_description)
        else:
            character_anchor = get_character_anchor(style_id)
    negative = style.negative + (", " + extra_negative if extra_negative else "")

    # v0.2.5/0.2.6: 中国画风格用专属 booster + 前置风格声明 + 剥 cinematic 词
    is_traditional_cn = style_id in TRADITIONAL_CN_STYLES
    style_prefix = CHINESE_STYLE_PREFIX if is_traditional_cn else ""
    composition_boost = CHINESE_PAINTING_BOOST if is_traditional_cn else (
        f"{CAMERA_LANGUAGE_KIT} "
        f"{DEPTH_LAYERS_BOOST} "
        f"{CINEMATIC_FRAMEWORK_BOOST} "
    )
    if is_traditional_cn:
        scene_description = _strip_cinematic_terms(scene_description)
        # v0.3.9 关键修复：剥掉 v0.3.7 引入的 `// 中文速记`。
        # 速记是**给人看**的（审阅 layout_preview 时显示），绝不能进图像 prompt ——
        # 实测苏武牧羊：带速记跑图 10 张全部跑偏成彩绘风/庭院景，
        # 完全不是宣纸工笔连环画，且雪原/地窖/草原全被画成中式庭院。
        # 根因是中文速记混进英文 prompt 后，风格锁定被中文语义冲淡。
        #
        # v0.3.18 关键修复：CONCEPT 段**必须原样保留**。
        # 之前它跟中文速记一起被 _ZH_GLOSS_RE 抹成了 " "，
        # 导致 CONCEPT 文字残留但分隔符消失，直接粘在 SUBJECT 上
        # （"...摸向腰间佩剑Subject: Zhaowu..."）。
        concept_zh = _CONCEPT_RE.search(scene_description)
        concept_text = concept_zh.group(1).strip() if concept_zh else ""
        scene_description = _ZH_NOTE_RE2.sub("", scene_description)
        scene_description = _ZH_NOTE_RE.sub("", scene_description)
        scene_description = _ZH_GLOSS_RE.sub(" ", scene_description)
        # CONCEPT 段整体从 scene 移出（下面单独提到 prompt 头部）
        scene_description = _CONCEPT_RE.sub(" ", scene_description)
        scene_description = _re.sub(r"\s{2,}", " ", scene_description).strip()
    else:
        concept_text = ""

    # v0.2.10 修复: 中国画风格强化 STRICT STYLE 夹击 —— 头部 + 角色锚点后再次重复,
    # 防止 agnes 看到 subject 描述里的"armor / map table / looking up"等现代写实关键词跑偏。
    style_lock_repeat = ""
    if is_traditional_cn:
        style_lock_repeat = (
            " CRITICAL STYLE LOCK: the entire frame is a classical Chinese painted illustration on rice paper, "
            "NOT a photograph, NOT a 3D render, NOT commercial CG, NOT modern digital illustration, NOT anime. "
            "Brush technique and pigment flatness required throughout. "
        )

    def _assemble(scene: str) -> str:
        """唯一的 prompt 拼装点（v0.3.21）。

        v0.3.21 前这里有两份几乎相同的代码（主路径 + 超限截断路径），
        结果 v0.3.18 加 boost 时只改了主路径，截断路径漏掉
        LIANHUANHUA_STYLE_LOCK + PATTERN_SUPPRESS —— 场景描述一长就走
        截断路径，两条约束全丢，图直接崩成西式书房（kc_1790664590 p09）。

        **消除重复而不是再补一次**，这样结构上不可能再漏。

        v0.3.18 关键改动：**CONCEPT 段提到 prompt 头部**。
        实测 kc_1790740537：CONCEPT 原本落在第 4703/9700 字符（正中间），
        而图像模型对 prompt **前 30%** 的关键词权重最高。位置一挪到中间，
        CONCEPT 里的「皮卷地图」「大开城门」「十万魏军」全被 i2i 角色参考图
        挤掉，8 页里 7 页跑偏（日式客厅 / 日本武士 / 3D 渲染桌面）。
        CONCEPT 是「这页要画什么」的唯一指令，必须占最高权重区。
        """
        concept_block = ""
        if concept_text:
            # 剥掉 CONCEPT 段里的 `// 中文速记`（给人看的，不进图像 prompt）
            concept_en = _ZH_NOTE_RE.sub("", concept_text).strip()
            concept_en = _re.sub(r"\s{2,}", " ", concept_en)
            if concept_en:
                concept_block = (
                    "\n\n=== WHAT THIS FRAME MUST SHOW (highest priority, "
                    "these elements MUST be visibly present in the image) ===\n"
                    f"{concept_en}\n"
                    "=== END OF MUST-SHOW BLOCK ===\n\n"
                )
        return (
            f"{concept_block}"
            f"{style_prefix}"
            f"{style.prompt_en} "
            f"{character_anchor} "
            f"{style_lock_repeat}"
            f"Scene: {scene} "
            f"{composition_boost} "
            f"{LIANHUANHUA_STYLE_LOCK} "
            f"{PATTERN_SUPPRESS} "
            f"{ZERO_TEXT_BOOST} "
            f"Avoid: {negative}"
        )

    assembled = _assemble(scene_description)

    # v0.2.4 升级：Agnes API 限制 10000 字符。超限时优先砍 scene_description
    # （核心是其他套话）。v0.3.21 改成复用 _assemble，不走第二份拼装代码。
    # v0.3.22 强化：fallback 不再 `assembled[:9790]` 硬切 —— 那会把 ZERO_TEXT_BOOST
    # 和 Avoid:negative 一起切掉。改为**只砍 scene**且**保底再砍一定保留尾部**。
    if len(assembled) > 9800:
        overhead = len(assembled) - len(scene_description)
        scene_max = max(2000, 9800 - overhead - 100)  # 余 100 防边界
        assembled = _assemble(scene_description[:scene_max] + "...")
        # 仍超限（极少见，scene 自身就接近 9800）→ 砍 SCENE 而不是砍整体
        # 永远保留 _assemble 的后段（ZERO_TEXT_BOOST + Avoid）。
        if len(assembled) > 9800:
            overhead2 = len(assembled) - len(scene_description[:scene_max])
            scene_max2 = max(500, 9800 - overhead2 - 100)
            assembled = _assemble(scene_description[:scene_max2] + "...")
    return assembled


# === Mavis 推荐矩阵（按主题/受众 → 风格） ===
# v0.3.2（2026-09-28）修复 P0 bug：
#   旧实现拿 **主题类型词**（"历史"/"典故"/"国学"…）去 `k in topic` 匹配真实主题，
#   而用户输入的是"张巡守睢阳""王昭君出塞"这类**具体题材**，几乎永远不命中，
#   全部掉进 new_yorker 兜底 —— 导致"历史典故第一推荐 chinese_lianhuanhua_classic"
#   这条铁律在自动推荐路径上完全失效。
#   新实现改为「加权信号分类器」(_classify_signals)，见下方 _SIGNAL_TABLES。
#
#   RECOMMEND_MATRIX / RECOMMEND_TEMPLATE_MATRIX 保留为：
#     1) guide.py 的展示表（按 key 配对风格/模板）
#     2) 分类器全部落空时的兜底
#   v0.3.2 同时补齐模板矩阵缺失的 武侠 / 宏大 两类 key（原先只有风格矩阵有）。

RECOMMEND_MATRIX: dict[str, tuple[str, ...]] = {
    "历史/典故/国学/古籍/古典": ("chinese_lianhuanhua_classic", "guochao_manhua", "cn_xuanfeng"),
    "经济/商业/职场/管理": ("new_yorker", "us_mid_century", "cn_xuanfeng"),
    "商业模式/品牌/设计/财经": ("us_mid_century", "new_yorker", "cn_xuanfeng"),
    "哲学/情感/心理/认知": ("new_yorker", "cn_xuanfeng", "us_mid_century"),
    "AI/算法/工程/科技/互联网": ("new_yorker", "us_mid_century", "cn_xuanfeng"),
    "科学/物理/化学/生物/医学": ("new_yorker", "us_mid_century", "cn_xuanfeng"),
    "文学/人物/哲学/文化": ("chinese_lianhuanhua_classic", "guochao_manhua", "cn_xuanfeng"),
    "古风/东方/意境/禅意": ("chinese_lianhuanhua_classic", "guochao_manhua", "cn_xuanfeng"),
    "武侠/江湖/侠义": ("chinese_lianhuanhua_classic", "guochao_manhua", "cn_xuanfeng"),
    "宏大/史诗/战争/重大事件": ("chinese_lianhuanhua_classic", "new_yorker", "guochao_manhua"),
    "通用/公众号": ("new_yorker", "us_mid_century", "chinese_lianhuanhua_classic"),
}


# === v0.3.2 加权信号分类器 ===
# 权重档位：
#   10 = 决定性信号（专有名词 / 强领域词），单独出现即可锁定风格
#    5 = 中等信号（领域通用词）
#    1 = 弱信号（单字朝代等高误伤风险的词）
# 匹配规则：子串包含；同一关键词只计一次（取最高权重）；
#           **长词优先** —— 短词若是被更长命中词的子串则抑制
#           （保证 "商业模式"(us_mid_century) 能压过 "商业"(new_yorker)，
#             "西汉" 能压过 "汉"，"王昭君" 能压过 "昭君"）

_CN_PERSON_NAMES: tuple[str, ...] = (
    # 先秦 / 春秋战国
    "孔子", "老子", "庄子", "孟子", "荀子", "墨子", "韩非", "商鞅", "屈原", "孙膑",
    "廉颇", "蔺相如", "赵武灵王", "荆轲", "西施", "王昭君", "昭君", "杨贵妃", "貂蝉",
    # 秦汉
    "秦始皇", "刘邦", "项羽", "韩信", "张良", "萧何", "霍去病", "卫青", "李广",
    "司马迁", "班超", "王莽", "董仲舒",
    # 三国两晋南北朝
    "诸葛亮", "刘备", "关羽", "张飞", "赵云", "曹操", "周瑜", "陆逊", "司马懿",
    "陶渊明", "祖逖", "谢安", "王羲之",
    # 隋唐
    "隋炀帝", "李渊", "李世民", "武则天", "唐玄宗", "李白", "杜甫", "白居易", "王维",
    "李靖", "魏征", "郭子仪", "药葛罗", "仆固怀恩", "张巡", "许远", "南霁云",
    "颜真卿", "段秀实", "李光弼", "安禄山", "史思明",
    # 宋元明清
    "岳飞", "文天祥", "辛弃疾", "陆游", "苏轼", "王安石", "寇准", "包拯",
    "曾国藩", "左宗棠", "林则徐", "郑成功", "戚继光", "袁崇焕", "李自成", "崇祯",
    "朱元璋", "朱棣", "康熙", "雍正", "乾隆",
    # 近现代
    "孙中山", "鲁迅", "蔡元培",
)

_CN_DYNASTY_STRONG: tuple[str, ...] = (
    "西汉", "东汉", "两汉", "汉朝", "西晋", "东晋", "晋朝", "南北朝", "隋朝", "唐朝",
    "武周", "北宋", "南宋", "宋朝", "元朝", "明朝", "清朝", "春秋", "战国", "秦朝",
    "三国", "五代十国", "盛唐", "晚唐", "初唐", "明末", "清末", "元末", "民国",
    "先秦", "上古",
)

_CN_DYNASTY_WEAK: tuple[str, ...] = ("汉", "唐", "宋", "明", "清", "秦", "晋", "隋", "楚", "齐", "赵", "魏")

_CN_EVENT_STRONG: tuple[str, ...] = (
    "之战", "之变", "之乱", "之祸", "北伐", "东征", "西征", "南征", "出塞",
    "围城", "死守", "退敌", "和亲", "政变", "篡位", "登基", "起兵", "勤王",
    "殉国", "血战", "孤城", "守城", "勤王",
)

_CN_CLASSIC_MEDIUM: tuple[str, ...] = (
    "典故", "成语", "寓言", "神话", "传说", "论语", "史记", "资治通鉴", "二十四史",
    "诗词", "唐诗", "宋词", "古诗", "诗经", "楚辞", "古文", "文言", "国学家",
    "古籍", "国学", "书法", "水墨",
    # v0.3.2 补充：古典掌故类题眼（名单覆盖不到的历史轶事靠这些词兜底）
    "争豪", "斗富", "逸事", "轶事", "掌故", "旧事", "往事", "奇闻", "异闻",
    "恩仇", "恩怨", "风流", "才子佳人", "红尘",
)

_WUXIA_MEDIUM: tuple[str, ...] = (
    "武侠", "江湖", "侠客", "侠义", "门派", "武林", "剑客", "刀客", "镖师",
)

_NY_STRONG: tuple[str, ...] = (
    "人工智能", "大模型", "机器学习", "深度学习", "神经网络", "注意力机制",
    "Transformer", "LLM", "GPT", "算法", "心理学", "认知科学", "行为经济学",
    "经济学", "峰终定律", "心智", "博弈论", "斯多葛", "芒格", "熵增",
)

_NY_MEDIUM: tuple[str, ...] = (
    "心理", "经济", "金融", "投资", "管理学", "科学", "物理", "化学", "生物",
    "医学", "神经", "演化", "量子", "决策", "情绪", "认知", "科学史",
)

_MC_STRONG: tuple[str, ...] = (
    "商业模式", "品牌", "设计", "创业", "增长", "营销", "品牌故事", "视觉设计",
    "文案", "排版", "配色",
)

_MC_MEDIUM: tuple[str, ...] = ("商业", "美学", "生活美学", "复古", "包豪斯")

# (关键词, 权重, 目标风格)
_SIGNAL_TABLE: tuple[tuple[str, int, str], ...] = (
    *((k, 10, "chinese_lianhuanhua_classic") for k in _CN_PERSON_NAMES),
    *((k, 10, "chinese_lianhuanhua_classic") for k in _CN_DYNASTY_STRONG),
    *((k, 10, "chinese_lianhuanhua_classic") for k in _CN_EVENT_STRONG),
    *((k, 5, "chinese_lianhuanhua_classic") for k in _CN_CLASSIC_MEDIUM),
    *((k, 5, "chinese_lianhuanhua_classic") for k in _WUXIA_MEDIUM),
    *((k, 1, "chinese_lianhuanhua_classic") for k in _CN_DYNASTY_WEAK),
    *((k, 10, "new_yorker") for k in _NY_STRONG),
    *((k, 5, "new_yorker") for k in _NY_MEDIUM),
    *((k, 10, "us_mid_century") for k in _MC_STRONG),
    *((k, 5, "us_mid_century") for k in _MC_MEDIUM),
)

# 同分时的稳定优先级（越靠前越优先）
_STYLE_TIEBREAK: tuple[str, ...] = (
    "chinese_lianhuanhua_classic", "guochao_manhua", "cn_xuanfeng",
    "new_yorker", "us_mid_century",
)

# 风格 → 模板默认映射
_STYLE_TEMPLATE: dict[str, str] = {
    "chinese_lianhuanhua_classic": "c",
    "guochao_manhua": "c",
    "cn_xuanfeng": "c",
    "new_yorker": "e",
    "us_mid_century": "e",
}

# 模板 a（撕纸手账）的专属场景：情感 / 旅行 / 生活
_TEMPLATE_A_SIGNALS: tuple[str, ...] = ("情感", "旅行", "游记", "手账", "生活随笔", "成长")

# === v0.3.3 史事动作词兜底层 ===
# 真实案例："苏武牧羊" 三类信号全落空（苏武不在人物名表 / 无朝代词 /
# "牧羊" 不在古典双人物句式里）→ 被误判成 new_yorker。
# 结论：名单永远补不完，必须有一层**不依赖具体人名**的通用规则。
# 史事动作词（守/牧/贬/谪/流放/乞食/负荆/刺股/卧薪/尝胆…）极强地指示
# "中国历史人物故事"，且几乎不出现在商业/科技题眼里。
_CN_HISTORIC_ACTIONS: tuple[str, ...] = (
    "牧羊", "牧", "守城", "守", "被贬", "贬", "谪", "流放", "流", "乞食", "负荆",
    "刺股", "卧薪", "尝胆", "投笔", "闻鸡", "凿壁", "悬梁", "囊萤", "映雪",
    "挂帅", "从军", "戍边", "镇守", "远征", "和亲", "纳谏", "进谏", "谏",
    "称帝", "登基", "谋反", "兵败", "战死", "殉国", "班师", "凯旋", "班师回朝",
    "联姻", "纳妃", "封禅", "削藩", "抄家", "流放边疆", "孤军", "苦守",
)

# 历史人物常见的"姓 + 名"双字结构（列表无法穷举时，靠叙事语境兜底）
_CN_ASPECT_CONTEXT: tuple[str, ...] = (
    "中原", "漠北", "塞外", "边关", "西域", "岭南", "中原大地", "匈奴", "胡人",
    "朝廷", "皇帝", "大臣", "将军", "使节", "朝堂", "皇权", "宫廷", "后宫",
)


def _looks_like_cn_history(topic: str) -> bool:
    """不依赖人名表的通用中国历史题材识别。

    命中条件（任一）：
      1. 含史事动作词（牧羊 / 被贬 / 流放 / 卧薪…）
      2. 含史事语境词（漠北 / 塞外 / 朝廷 / 匈奴…）
      3. 古典双人物叙事句式

    排除：含拉丁字母/数字，或命中现代商战排除词 —— 那些是现代题眼。
    """
    t = topic or ""
    if not t:
        return False
    if _re.search(r"[A-Za-z0-9]", t):
        return False
    if any(w in t for w in _MODERN_BLOCKLIST):
        return False
    if any(a in t for a in _CN_HISTORIC_ACTIONS):
        return True
    if any(c in t for c in _CN_ASPECT_CONTEXT):
        return True
    return _looks_like_classical_story(t)


def _classify_signals(topic: str) -> tuple[dict[str, int], list[str]]:
    """加权信号分类。返回 (各风格得分, 命中关键词列表)。

    同一关键词被多档命中时只取最高权重；长词优先，短词被更长命中词包含时抑制。
    """
    t = topic or ""
    best: dict[str, tuple[str, int]] = {}
    for kw, weight, style_id in _SIGNAL_TABLE:
        if kw not in t:
            continue
        prev = best.get(kw)
        if prev is None or weight > prev[1]:
            best[kw] = (style_id, weight)

    scores: dict[str, int] = {}
    hits: list[str] = []
    for kw in sorted(best, key=len, reverse=True):
        if any(kw in h for h in hits):   # 短词被更长命中词包含 → 抑制
            continue
        hits.append(kw)
        style_id, weight = best[kw]
        scores[style_id] = scores.get(style_id, 0) + weight

    return scores, hits


# 古典双人物叙事模式（v0.3.2）：像"看石崇与王恺争豪"这种——
# 纯中文 + 双人物对举 + 古典叙事词。这类题眼不会出现在现代商业/科技主题里
#（后者通常含拉丁字母或数字），所以可以作为名单覆盖不到时的兜底信号。
_CLASSICAL_PAIR_PATTERN = _re.compile(
    r"[\u4e00-\u9fff]{2,4}(?:与|和|同|对)[^\s]{0,2}[\u4e00-\u9fff]{2,4}"
)
_CLASSICAL_NARRATIVE_MARKERS: tuple[str, ...] = (
    "争", "斗", "豪", "富", "义", "仇", "恩", "情", "死", "战", "守", "谏",
)

# 现代题眼排除词：这些词出现时，"与/和"结构多半是公司/产品对比，不是古典双人物叙事。
# 不加这个排除，"华为与腾讯的竞争" 会因命中"争"被误判成历史典故。
_MODERN_BLOCKLIST: tuple[str, ...] = (
    "竞争", "对比", "哪家", "排名", "评测", "推荐", "公司", "企业", "市场",
    "品牌", "用户", "产品", "平台", "行业", "股价", "融资", "上市", "估值",
    "现代", "科技", "互联网", "手机", "创业",
)


def _looks_like_classical_story(topic: str) -> bool:
    """纯中文双人物 + 古典叙事词 → 判定为历史典故类题眼。

    排除条件：
      - 含拉丁字母 / 数字（现代商业、科技、财经题眼几乎必含）
      - 命中现代题眼排除词（"竞争"/"对比"/"公司"… 属于现代商战叙事）
    """
    t = topic or ""
    if not t or _re.search(r"[A-Za-z0-9]", t):
        return False
    if any(w in t for w in _MODERN_BLOCKLIST):
        return False
    if not _CLASSICAL_PAIR_PATTERN.search(t):
        return False
    return any(m in t for m in _CLASSICAL_NARRATIVE_MARKERS)


def recommend_style(topic: str) -> tuple[str, list[str]]:
    """基于主题分类推荐风格 ID + 备选（v0.3.2 加权信号分类器）。"""
    scores, _ = _classify_signals(topic)
    if scores:
        top = max(
            scores,
            key=lambda s: (scores[s], -_STYLE_TIEBREAK.index(s) if s in _STYLE_TIEBREAK else 99),
        )
        alternates = [top] + [s for s in _STYLE_TIEBREAK if s != top]
        return top, alternates

    # v0.3.3：名单/关键词覆盖不到，但句式是史事动作或古典双人物叙事 → 仍判为连环画
    # （真实案例："苏武牧羊" 人名表里没有苏武，也没有朝代词）
    if _looks_like_cn_history(topic):
        return "chinese_lianhuanhua_classic", list(
            RECOMMEND_MATRIX["历史/典故/国学/古籍/古典"]
        )

    # 分类器全落空 → 回退到旧的类型词匹配（兼容 "历史故事" 这类元描述输入）
    for kw, styles in RECOMMEND_MATRIX.items():
        if any(k in topic for k in kw.split("/")):
            return styles[0], list(styles)
    return "new_yorker", list(RECOMMEND_MATRIX["通用/公众号"])


# === Mavis 推荐模板（按主题 → 排版 ID） ===
# 锁定 3 个模板：e（典雅知识风，深蓝灰）+ c（中国古典故事专版，朱砂红）+ a（撕纸手账兜底）
# 历史典故 → c（朱砂红+印章，最有古典感）
# 经济学/商业/心理 → e（深蓝灰，最有理性感）
# 通用兜底 → a（撕纸手账）
RECOMMEND_TEMPLATE_MATRIX: dict[str, tuple[str, ...]] = {
    "历史/典故/国学/古籍/古典": ("c", "e", "a"),
    "经济/商业/职场/管理": ("e", "c", "a"),
    "商业模式/品牌/设计/财经": ("e", "c", "a"),
    "哲学/情感/心理/认知": ("e", "c", "a"),
    "AI/算法/工程/科技/互联网": ("e", "c", "a"),
    "科学/物理/化学/生物/医学": ("e", "c", "a"),
    "文学/人物/哲学/文化": ("c", "e", "a"),
    "古风/东方/意境/禅意": ("c", "e", "a"),
    # v0.3.2 补齐：原先这两类只在风格矩阵里有，模板矩阵缺失 → 掉进兜底拿到 e
    "武侠/江湖/侠义": ("c", "e", "a"),
    "宏大/史诗/战争/重大事件": ("c", "e", "a"),
    "通用/公众号": ("e", "c", "a"),
}


def recommend_template(topic: str) -> tuple[str, list[str]]:
    """基于主题推荐排版模板 ID + 备选（v0.3.2：跟随风格派生 + a 场景信号）。

    v0.3.3 修复：原先第 3 步"分类器落空 → 回退类型词匹配"会覆盖第 2 步的风格派生结果。
    命中兜底层（如"苏武牧羊"）时 _classify_signals 为空但 recommend_style 已正确判为
    连环画，这里却又按类型词匹配返回 e，导致"风格对、模板错"的分裂输出。
    现在只保留纯粹的元描述输入回退（如"历史故事 XXX"），且必须在风格未命中兜底层时才走。
    """
    # 1) 情感/旅行/生活 → a（撕纸手账）
    if any(k in (topic or "") for k in _TEMPLATE_A_SIGNALS):
        return "a", ["a", "e", "c"]

    # 2) 跟随推荐风格：中国画三风格 → c（朱砂红 + 印章），其余 → e（深蓝灰）
    style_id, _ = recommend_style(topic)
    primary = _STYLE_TEMPLATE.get(style_id, "e")

    # 3) 显式类型词输入（"历史故事 XXX" / "心理学 XXX"）优先于默认兜底，
    #    但仅在风格不是靠 _looks_like_cn_history 兜底判出来时才生效，避免覆盖 2 的结果。
    if not _classify_signals(topic)[0] and not _looks_like_cn_history(topic):
        for kw, templates in RECOMMEND_TEMPLATE_MATRIX.items():
            if any(k in topic for k in kw.split("/")):
                return templates[0], list(templates)

    order = ["c", "e", "a"] if primary == "c" else ["e", "c", "a"]
    if order[0] != primary:
        order = [primary] + [t for t in order if t != primary]
    return order[0], order


def recommend_style_rationale(topic: str) -> str:
    """推荐 + 理由（给用户看）。"""
    primary, alternates = recommend_style(topic)
    style = get_style(primary)
    alts_zh = "、".join(get_style(a).name_zh for a in alternates[1:])
    return (
        f"主题「{topic}」 → 推荐主风格：**{style.name_zh}** "
        f"（{style.category}，适合：{('、').join(style.use_cases)}）\n"
        f"备选：{alts_zh}"
    )