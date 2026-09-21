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

CHARACTER_ANCHORS: dict[str, str] = {
    "new_yorker": CHARACTER_SCIENTIST,
    "us_mid_century": CHARACTER_SCIENTIST,
    "cn_xuanfeng": CHARACTER_ANCIENT_CN,
    "guochao_manhua": CHARACTER_ANCIENT_GUOCHAO,
    "chinese_lianhuanhua_classic": CHARACTER_CN_LIANHUANHUA_ANCESTOR,
}


def get_character_anchor(style_id: str) -> str:
    """根据风格返回对应角色锚点。"""
    return CHARACTER_ANCHORS.get(style_id, CHARACTER_SCIENTIST)

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
            "NO neon palette, NO Risograph, NO vector flatness, NO text, NO letters"
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


def build_image_prompt(
    style_id: str,
    scene_description: str,
    character_anchor: str | None = None,
    extra_negative: str = "",
) -> str:
    """拼最终 image prompt。强制角色一致性 + 零文字硬约束。

    Args:
        style_id: 风格 ID（new_yorker / us_mid_century / cn_xuanfeng）
        scene_description: 单页画面描述（planner 拆出的 visual 字段）
        character_anchor: 角色一致性锚点（None = 自动按风格选）
        extra_negative: 额外负向词（如具体场景禁忌）
    """
    style = get_style(style_id)
    if character_anchor is None:
        character_anchor = get_character_anchor(style_id)
    negative = style.negative + (", " + extra_negative if extra_negative else "")

    # v0.2.3 升级：把七要素框架 + 镜头语言 + 景深三层 + 表情 anchor 库全部注入
    assembled = (
        f"{style.prompt_en} "
        f"{character_anchor} "
        f"Scene: {scene_description} "
        f"{CAMERA_LANGUAGE_KIT} "
        f"{DEPTH_LAYERS_BOOST} "
        f"{CINEMATIC_FRAMEWORK_BOOST} "
        f"{ZERO_TEXT_BOOST} "
        f"Avoid: {negative}"
    )
    # v0.2.4 升级：Agnes API 限制 10000 字符。超限时优先砍 scene_description（核心是其他套话）。
    if len(assembled) > 9800:
        scene_max = max(2000, 9800 - (len(assembled) - len(scene_description)))
        trimmed_scene = scene_description[:scene_max] + "..."
        assembled = (
            f"{style.prompt_en} "
            f"{character_anchor} "
            f"Scene: {trimmed_scene} "
            f"{CAMERA_LANGUAGE_KIT} "
            f"{DEPTH_LAYERS_BOOST} "
            f"{CINEMATIC_FRAMEWORK_BOOST} "
            f"{ZERO_TEXT_BOOST} "
            f"Avoid: {negative}"
        )
    return assembled


# === Mavis 推荐矩阵（按主题/受众 → 风格） ===
# v0.2.4（2026-09-21）按用户新反馈调整：
#   历史典故/中国故事 → chinese_epic_history 第一优先（中国题材 + 19 世纪欧洲古典/浪漫主义
#                          历史画语言，David、Delacroix、Géricault 的构图/光影/空间/群像/戏剧动作，
#                          严禁西方人面孔 + 西方审美）；guochao_manhua / cn_xuanfeng 降为备选。
#   经济学/心理学 → new_yorker（黑白 Risograph，知识严肃感）
#   商业模式/品牌/设计 → us_mid_century（mustard+teal+砖红，复古杂志）
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


def recommend_style(topic: str) -> tuple[str, list[str]]:
    """基于主题关键词推荐风格 ID + 备选。"""
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
    "通用/公众号": ("e", "c", "a"),
}


def recommend_template(topic: str) -> tuple[str, list[str]]:
    """基于主题关键词推荐排版模板 ID + 备选。"""
    for kw, templates in RECOMMEND_TEMPLATE_MATRIX.items():
        if any(k in topic for k in kw.split("/")):
            return templates[0], list(templates)
    return RECOMMEND_TEMPLATE_MATRIX["通用/公众号"][0], list(RECOMMEND_TEMPLATE_MATRIX["通用/公众号"])


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