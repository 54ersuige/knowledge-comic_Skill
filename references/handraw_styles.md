# 5 个锁定风格 · v0.2.4 完整定义

引用自 [handraw-style 项目](https://github.com/yang0/handraw-style)（2.2k stars）。

v0.2.4（2026-09-21）从早期 8 风格演变到 **5 风格**：
- ✅ 保留：`new_yorker` / `us_mid_century` / `cn_xuanfeng` / `guochao_manhua` / `chinese_lianhuanhua_classic`
- ❌ 砍掉：`kid_picture_book` / `kid_science_diagram` / `cn_contemporary` / `jp_kawaii_warm` / `jp_terada`

砍掉的理由：保留 5 个最有特点、互不重叠的成人向风格，每个打磨到位比 8 个"半桶水"强。

---

## 1. `new_yorker` · 纽约客式 · 报刊讽刺 ⭐ 推荐

**适合**：商业评论、社会议题、严肃话题、成人读者、知识科普、经济学/心理学

**视觉特征**：米色纸 + Risograph 印刷质感 + 平面色块 + 细线条 + 网点 + 留白编辑构图

**Prompt 锚点**（最稳健，验证可用）：
```
Single-panel editorial cartoon in style of The New Yorker magazine,
like a cartoon by Tom Bachtell or Liam Walsh. Risograph print style on cream paper.
Subtle cream paper texture, slight ink bleed on edges, slight Risograph
misregistration where color blocks don't perfectly align, subtle halftone dot
pattern in flat color areas, slight grain. Clean hand-drawn ink lines, thin to
medium weight, slight hand-drawn imperfection, pen on paper feel.
Flat low-saturation color blocks (limited palette: cream, black, soft grey,
muted teal accent), no gradients, no airbrush.
```

**关键负向**：`NO anime, NO Pixar, NO Disney, NO chibi, NO moe, NO kawaii, NO photorealistic, NO 3D render, NO painterly, NO big anime eyes`

**角色锚点**：现代/科学家版
```
Consistent character anchor (must remain identical across all panels):
a small scientist figure with short black hair, round wire-frame glasses,
light grey sweater, dark trousers, simple black shoes, neutral expression,
age approximately 30. Same face, same body proportions, same outfit in every frame.
```

---

## 2. `us_mid_century` · 美式中世纪 · 复古杂志 ⭐ 推荐

**适合**：品牌故事、设计感、复古议题、生活美学、职场/财经、商业模式

**视觉特征**：1950-60s 杂志插画感 + 扁平色块 + mustang 黄 + teal + 砖红 + 几何构图 + 强烈前景框

**Prompt 锚点**：
```
Single-panel illustration in mid-century American editorial style
(1950s-60s magazine illustration). Bold flat color shapes with confident edges,
limited muted retro palette (mustard yellow, teal, brick red, cream, ink black).
Confident ink contour with slight unevenness, retro typographic sensibility.
Composition is geometric and balanced, often with diagonal energy and
strong foreground framing. Subjects rendered with stylized simplicity
but recognizable human proportions, not chibi or cartoonish.
Surface feels printed, slight color overlay between blocks.
Atmosphere evokes optimistic mid-century commercial art.
```

**关键负向**：`NO digital gradient, NOT vector flatness`

**角色锚点**：同 `new_yorker`（现代/科学家版）

---

## 3. `cn_xuanfeng` · 宣风 · 国风写意

**适合**：历史典故（要传统水墨时）、国学、古籍解读、东方美学、禅意

**视觉特征**：飞白 + 朱砂 + 宣纸 + 大胆水墨笔触 + 留白 + 朝代服饰 + 意境

**Prompt 锚点**：
```
In the xuanfeng (宣风) style of contemporary Chinese ink wash illustration.
Brush-painted on rice paper (宣纸), bold xieyi (写意) brushwork, deliberate
ink-bleed, dry-brush edges (飞白), generous white space as compositional
breathing room. Cinnabar-red accent strokes (朱砂勾线) on key figures.
Limited palette: ink black + cinnabar red + rice-paper-white + aged ochre +
indigo. Subjects rendered with classical Chinese proportions, slightly
elongated, dignified. Mood contemplative, literary, observational.
```

**关键负向**：`NOT Western oil, NOT watercolor, NOT photorealism, NOT Risograph, NOT anime`

**角色锚点**：古代中国版
```
Consistent character anchor: a Han-Chinese historical person, either a
refined young woman in traditional hanfu robe (crossed collar, wide sleeves,
sash belt, hair pinned in classical style with subtle ornaments) or a
dignified scholar-official in long scholarly robe with traditional headwear,
both rendered with elegant elongated proportions typical of classical Chinese
figure painting. Age approximately 20-30. Serene, contemplative expression.
```

---

## 4. `guochao_manhua` · 国潮古风条漫 ⭐ 历史典故国潮派

**适合**：历史典故（要现代国潮感时）、中国故事、武侠、江湖、侠义、宏大叙事

**视觉特征**：国潮赛璐璐 + 古装 + 现代条漫分镜 + 朱砂 + 鸦青 + 玉绿 + 金 + 月白 + 现代 1:2 头身比

**Prompt 锚点**：
```
Guochao (国潮) cel-shaded manhua illustration in the style of Chinese comics
like 《镖人》or 《一人之下》, historical costume, bold flat color blocks
(cinnabar + crow-blue + jade-green + gold + moon-white), cel-shaded rendering
with hand-drawn ink contour, modern dynamic panel composition with strong
foreground framing. Modern manhua body proportions (1:2 head-to-body),
NOT ancient painterly ratio. Subjects depicted with dramatic action poses,
sharp-featured Han-Chinese faces with refined cheekbones, swordsman brows,
distinct period costumes (Tang round-collar / Song straight-collar /
Ming official's hat). NO kawaii, NO chibi, NO Disney.
```

**关键负向**：`NOT young-looking, NOT teenage, NOT youthful cute girl, NOT blushy cheeks, NOT schoolgirl, NOT moe, NOT shoujo`

**角色锚点**：5-tuple bible
```
Consistent character bible (FIVE ANCHORS - all five must remain identical
across all panels):
(1) Face shape: oval face, sharp jawline, refined cheekbones.
(2) Eyes: large double-lid expressive eyes with sharp winged eyeliner, dark brown irises.
(3) Eyebrows: thin angled swordsman brows, slightly furrowed.
(4) Lip & mouth: well-defined cupid's bow lips, normally closed, decisive line of jaw.
(5) Hair: Han-Chinese historical figure, hair tied in high topknot bound with cloth ribbon (no metal crown), long black hair flowing behind when in motion.
Modern manhua body proportions (about 1:2 head-to-body), NOT ancient painterly ratio.
Age 20-30, sharp refined features. Cel-shaded manhua face.
Outfit: traditional hanfu / scholarly robe (crossed collar, fitted waist sash with jade buckle, flowing wide sleeves).
```

---

## 5. `chinese_lianhuanhua_classic` · 中国古典连环画（戴敦邦派）⭐ 历史典故第一推荐 ★ v0.2.4 新增

**适合**：历史典故（中国故事、典故解读、古典小说插图、圣贤帝王、江湖侠义、宏大叙事）

**视觉特征**：宣纸 + 毛笔 + 工笔 + 白描红线 + 水墨淡彩连环画派 + 戴敦邦派古典人物脸 + 朝代服饰礼制考据

**Prompt 锚点**：
```
Chinese lianhuanhua (连环画) illustrated narrative art on traditional XUAN PAPER
(rice paper), NOT on canvas. Gongbi (工笔) + baimiao (白描) + xieyi (写意) ink
wash technique with hand-held Chinese brush (毛笔).
STYLE LOCK: classical Chinese hand-painted illustration in the tradition of Dai
Dunbang, Liu Jiyou, Wang Shuhui, He Youzhi. FLAT-INK + COLORED INK illustration,
NOT oil painting, NOT photorealism, NOT 3D, NOT anime, NOT Disney, NOT
storybook-CG.
Distinct technique marks the medium: visible brush bristle strokes, deliberate
ink-bleed, dry-brush edges (飞白), rice-paper-white space used as compositional
breathing room, vermilion-detail line work (朱砂勾线) on faces and garment folds,
gongbi color planes (cinnabar + indigo + ochre + ink + bone-white), no
photographic shading.
Faces: Dai Dunbang classical Chinese face - square jaw, narrow phoenix-eye 丹凤眼 or
triangular-eye 三角眼 drawn in single firm brush line, sword-brow 剑眉, period-
correct beard or clean-shaven per role, dignified weathered age, theatrical
intensity held in restraint.
Period-accurate Chinese costume: Tang round-collar robe + soft-brim 幞头; Song
straight-collar scholar robe; Ming official's wushamao 乌纱帽, etc.
Auxiliary influences: Liu Jiyou's epic ink drama, Wang Shuhui's linework, Wu
lianhuanhua school rigorous period research, Gu Bingxin / He Youzhi serial
narrative composition.
HARD PROHIBITIONS: NO oil paint, NO impasto, NO canvas, NO Turner-style haze, NO
Western classical painting, NO European faces, NO Disney, NO anime, NO neon.
```

**关键负向**：`NO oil paint, NO impasto, NO canvas, NO Western painting, NO Turner haze, NO European face, NO Disney, NO anime, NO photorealism, NO 3D, NO Pixar, NO Western costume, NO round anime eyes, NO pale pink skin, NO neon palette, NO Risograph, NO vector flatness`

**角色锚点**：戴敦邦派 5-tuple
```
Dai Dunbang-style classical Chinese figure, INK BRUSH ON RICE PAPER (not oil/canvas/anime):
(1) square jaw + classical Chinese cheekbones + dignified weathered age lines +
    light dry-brush hatch shadows;
(2) narrow phoenix-eye 丹凤眼 or triangular-eye 三角眼 drawn in SINGLE firm
    ink-stroke contour, deep-set under heavy brow ridge;
(3) sharp diagonal swordsman 剑眉 brows with calligraphic pressure variation;
(4) period-correct facial hair (clean-shaven scholar / thin mustache official /
    short dignified beard commander / goatee elder), drawn with individual
    brush wisps;
(5) period-correct Han-Chinese hair (high topknot 高髻 OR official's cap
    幞头/官帽/乌纱), rendered with multiple ink-stroke hair lines.
Body: classical Chinese figure proportions, slightly elongated dignified bearing.
Costume: period-correct Chinese attire (Tang round-collar robe / Song
straight-collar / Ming official's hat / period armor) with white-line +
red-line calligraphic outline.
Expression: theatrical intensity held in dignified restraint, never cutesy,
never pretty-boy. Age 25-55 per role. Surface: RICE PAPER ink-and-pigment,
NEVER Western canvas.
```

### 5.1 chinese_lianhuanhua_classic 防跑偏铁律（v0.2.4 关键经验）

**症状**：做连环画派时，凡涉及"书房 / 学者 / 灯具"场景，模型自动走"现代写实油画 / 3D 渲染 / 摄影"风。

**修复**：
1. 把"painted illustration"声明放 SUBJECT 第一句：`CRITICAL — The entire frame is rendered as a classical Chinese lianhuanhua painted illustration, NOT a photograph, NOT a 3D render...`
2. 把人物描述成 `brush-painted figure on rice paper, NOT a photorealistic person`
3. 视觉描述里**避免**：`candle / lantern / desk / porcelain rest / modern Chinese minimalism / cinematic studio lighting / volumetric light` 等现代写实物件词
4. 把"volumetric light"改成"painted warm wash"

**验证**：张巡守睢阳 v0.2.4 — p1-p9（战场 / 粮仓 / 城墙）自动到位，p10-p11（书房 + 学者）反复跑偏现代写实风，重写 visual 加 v2 fix 后到位。

---

## 通用硬约束（所有风格适用）

### 1. 零文字铁律

每张图都强制（`prompts.py:ZERO_TEXT_BOOST`）：
```
ABSOLUTELY NO TEXT on the image. NO English signage. NO fake letters.
NO numbers. NO digits. NO math symbols. NO Japanese kana. NO Chinese characters.
NO speech bubbles. NO caption boxes. NO watermarks. NO labels. NO arrows-with-words.
```

特别注意：planner 的 visual 字段**严禁**包含具体年份/字母/数学符号（即使概念正确，模型会把字面文字画出来）。
- ❌ "clock showing 2017" → 字面画 "2017"
- ❌ "labeled A and B" → 字面画 A 和 B
- ✅ "a wall clock with two hands but no numerals"

### 2. 角色一致性铁律

所有页面复用同一角色（按风格自动选锚点）。每页 visual 字段开头重复完整描述。动作/表情可变化（拿着放大镜 / 沉思 / 指着图表），但外貌不变。

### 3. 视觉概念具象化铁律

抽象概念必须转成具体可见的视觉元素：
- ❌ "showing the concept of attention" → 太空
- ✅ "three glowing dots floating in air, connected by golden threads to the character" → 视觉可读

### 4. 七要素结构铁律（v0.2.3）

每页 visual 按 7 段组织：SUBJECT / ACTION / CAMERA（shot+angle+lens+DoF）/ PLACEMENT / DEPTH LAYERS（foreground+midground+background）/ LIGHTING / MOOD-PALETTE

完整结构见 `SKILL.md` §6。

---

## 推荐矩阵（Mavis 主对话用）

```python
from scripts.core.prompts import recommend_style_rationale

print(recommend_style_rationale("张巡守睢阳"))
# 主题「张巡守睢阳」 → 推荐主风格：**中国古典连环画（戴敦邦派）**
# （E · 中国古典连环画派 · 戴敦邦核心 + 刘继卣史诗 + 王叔晖审美 + 冯远笔法 + 顾炳鑫/贺友直分镜，
#   适合：历史典故、中国故事、古籍解读、圣贤帝王、江湖侠义、古典小说插图、连环画叙事、宏大叙事）
# 备选：国潮古风条漫、宣风 · 国风写意
```

完整映射（v0.2.4）：
| 主题 | 主风格 | 备选 |
|---|---|---|
| **历史典故 / 国学 / 古籍 / 古典** | **chinese_lianhuanhua_classic** | guochao_manhua, cn_xuanfeng |
| **经济 / 商业 / 职场 / 管理** | new_yorker | us_mid_century, cn_xuanfeng |
| **商业模式 / 品牌 / 设计 / 财经** | us_mid_century | new_yorker, cn_xuanfeng |
| **哲学 / 情感 / 心理 / 认知** | new_yorker | cn_xuanfeng, us_mid_century |
| **AI / 算法 / 工程 / 科技 / 互联网** | new_yorker | us_mid_century, cn_xuanfeng |
| **科学 / 物理 / 化学 / 生物 / 医学** | new_yorker | us_mid_century, cn_xuanfeng |
| **文学 / 人物 / 哲学 / 文化** | chinese_lianhuanhua_classic | guochao_manhua, cn_xuanfeng |
| **古风 / 东方 / 意境 / 禅意** | chinese_lianhuanhua_classic | guochao_manhua, cn_xuanfeng |
| **武侠 / 江湖 / 侠义** | chinese_lianhuanhua_classic | guochao_manhua, cn_xuanfeng |
| **宏大 / 史诗 / 战争 / 重大事件** | chinese_lianhuanhua_classic | new_yorker, guochao_manhua |
| **通用 / 公众号** | new_yorker | us_mid_century, chinese_lianhuanhua_classic |