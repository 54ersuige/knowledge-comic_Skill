# 3 个公众号排版模板（v0.2.4 锁定版）

v0.2（2026-09-20）从 5 模板砍到 **3 模板**（v0.2.4 维持 3 模板不变）：
- ✅ 保留：`a`（撕纸手账）、`c`（中国古典故事专版）、`e`（典雅知识风）
- ❌ 砍掉：`b`（复古报纸）、`c_v3`（现代极简）、`d`（多巴胺手绘）

3 个模板覆盖 95% 场景：
- **e** = 知识 / 商业 / 严肃
- **c** = 古风 / 历史 / 典故 / 长文叙事
- **a** = 情感 / 旅行 / 通用兜底

所有模板都遵循 **图文分离铁律**（对话/旁白进文章层，画面零文字）。

---

## 模板 A · 撕纸手账风

**适合**：情感 / 旅行 / 文艺随笔 / 通用科普 / 公众号兜底

**视觉特征**：
- 黄便签背景 `#fef3c7`
- 撕纸边形（CSS clip-path）
- 装饰胶带（黄 / 蓝 / 粉 / 绿 / 橙）
- 手写体（STKaiti / 楷体 italic）
- 段落错落旋转 ±0.5°

**结构**：
```
撕纸标题 + 胶带装饰
  ↓
便签卡 1（胶带 + caption + dialogue + 图）
  ↓
便签卡 2（错落旋转）
  ↓
...
  ↓
结尾金句（黄底 + 虚线边框 + 「」斜体）
```

**配对风格**：new_yorker / us_mid_century / chinese_lianhuanhua_classic

---

## 模板 C · 中国古典故事专版 ⭐ 历史典故 / 长文叙事第一推荐

**适合**：历史典故、古籍解读、经典文章、人物传记、武侠江湖、宏大叙事

**视觉特征**：
- 米色羊皮纸 `#eee8da` 背景 + 手机框模拟（max-width:420px + box-shadow）
- **朱砂红主色 `#9b2332`**
- 宋体 / 楷体（STSong / STKaiti）
- 章节题 h2 + 朱砂红底线 2px
- 正文 line-height:1.9 + 段首缩进 2em + 两端对齐
- 朱砂印章"完"方块（结尾）

**结构**：
```
开篇：
  卷首题词（顶部小字 朱砂红 letter-spacing:2px）
  大标题 h1（30px #222 letter-spacing:8px）
  副标题（出处 / 作者 #888）
  导语（18px 加粗 + 17px 普通 段首缩进 2em）
  题记（朱砂红 诗句居中 letter-spacing:2px）
  朱砂红双线分隔

正文（每章）：
  第 壹 / 贰 / 叁... 章 中文数字章节号（朱砂红 80px 大字标识）
  h2 章节题（朱砂红 + 底部 2px 红线）
  章节插图
  长段落正文（15px line-height:1.9 段首缩进 两端对齐 #4a4a4a）
  关键节点卡（米色 #f5f0e8 背景 + 朱砂红左 border + 关键引文 ≤ 30 字）

结尾：
  朱砂印章 "完"（60x60 朱砂红方块 + 发光阴影）
  现代启示（朱砂红副标题 + 长段金句）
  后记（朱砂红副标题 + 长段文字）
```

**配对风格**（v0.2.4 历史典故优先）：
- **第一优先 = `chinese_lianhuanhua_classic`**（戴敦邦派工笔重彩连环画）
- 第二 = `guochao_manhua`（国潮赛璐璐 + 古风条漫）
- 第三 = `cn_xuanfeng`（传统水墨写意）

---

## 模板 E · 典雅知识风（推荐：知识 / 科普 / 心理 / 认知）

**适合**：科学 / 科普 / 认知科学 / 心理学 / STEM / 经济评论 — 任何需要理性 + 严谨基调的知识类内容

**视觉特征**：
- 米色羊皮纸 `#eee8da` 背景 + 手机框模拟（max-width:420px + box-shadow）
- **深蓝灰主色 `#2c3e5a`**（理性科学感，参考 HBR / 三联 / 财新 配色）
- 宋体 / 楷体（STSong / STKaiti）
- 章节题 h2 + 深蓝灰底线 2px
- 正文 line-height:2.0 + 段首缩进 2em + 两端对齐
- 深蓝印章"完"方块（结尾）

**结构**（与 C 模板完全一致，仅配色不同）：
```
开篇：
  卷首题词（顶部小字 深蓝灰 letter-spacing:3px）
  大标题 h1（32px #1a1a1a letter-spacing:6px）
  副标题（出处 / 作者 #2c3e5a + 装饰短线）
  导语（18px 加粗 + 17px 普通 段首缩进 2em）
  题记（深蓝灰 诗句居中 letter-spacing:2px）
  深蓝灰双线分隔

正文（每章）：
  第 壹 / 贰 / 叁... 章 中文数字章节号（深蓝灰 80px 大字标识）
  h2 章节题（深蓝灰 + 底部 2px 深蓝灰线）
  章节插图
  长段落正文（15px line-height:2.0 段首缩进 #2a2a2a）
  数据卡 / 关键节点（浅蓝灰 #eef1f6 背景 + 深蓝灰左 border）

结尾：
  深蓝印章 "完"（64x64 深蓝灰方块 + 发光阴影）
  后记（深蓝灰副标题 + 长段文字）
```

**配对风格**：new_yorker / us_mid_century / cn_xuanfeng

---

## 配色对照（C vs E）

| 元素 | C 模板（朱砂红）| E 模板（深蓝灰）|
|---|---|---|
| 主色 | `#9b2332` 朱砂红 | `#2c3e5a` 深蓝灰 |
| 渐变副色 | `#c4644a` | `#5a7aa3` |
| 引用块背景 | `#f5f0e8` 米色 | `#eef1f6` 浅蓝灰 |
| 透明叠加 | rgba(155,35,50,X) | rgba(44,62,90,X) |
| 外壳背景 | `#eee8da` 米色 | `#eee8da` 米色（保留暖色调） |
| 数据卡底色 | `#f5f0e8` 米色 + 朱砂红左 border | `#eef1f6` 浅蓝灰 + 深蓝灰左 border |

---

## 风格 × 模板配对矩阵（v0.2.4）

| 主题类型 | 风格 | 模板 |
|---|---|---|
| **历史典故 / 国学 / 古籍解读** | **chinese_lianhuanhua_classic**（戴敦邦派，第一推荐）/ guochao_manhua / cn_xuanfeng | **c**（朱砂红 + 印章） |
| **武侠 / 江湖 / 侠义** | **chinese_lianhuanhua_classic** / guochao_manhua | **c** |
| **宏大 / 史诗 / 战争 / 重大事件** | **chinese_lianhuanhua_classic** / new_yorker / guochao_manhua | **c** 或 **e** |
| **文学 / 人物 / 哲学 / 文化** | chinese_lianhuanhua_classic / guochao_manhua / cn_xuanfeng | **c** |
| **经济学知识 / 心理学 / 严肃** | new_yorker | **e**（深蓝灰） |
| **商业模式 / 品牌 / 设计** | us_mid_century | **e** |
| **AI / 算法 / 工程 / 科技 / 互联网** | new_yorker / us_mid_century | **e** |
| **科学 / 物理 / 化学 / 生物 / 医学** | new_yorker / us_mid_century | **e** |
| **哲学 / 情感 / 心理 / 认知** | new_yorker / cn_xuanfeng / us_mid_century | **e** |
| **情感 / 旅行 / 通用兜底** | new_yorker / us_mid_century / chinese_lianhuanhua_classic | a |

---

## 选模板的逻辑

| 场景 | 推荐模板 | 配对风格 |
|---|---|---|
| 情感故事 / 旅行 / 通用科普 | **A 撕纸手账** | new_yorker / chinese_lianhuanhua_classic |
| **历史典故 / 经典解读 / 长文叙事 / 武侠** | **C 中国古典故事专版** | **chinese_lianhuanhua_classic** / guochao_manhua / cn_xuanfeng |
| **科学 / 科普 / 认知 / 心理 / 经济学** | **E 典雅知识风** | new_yorker / us_mid_century |

调用：
```python
from scripts.core import article as article_mod

# 预览模板渲染
html = article_mod.render_mock_preview("c")  # c = 中国古典故事专版

# 真实渲染（用 storyboard + wechat_image_urls）
html = article_mod.render_publish_article(storyboard, wechat_image_urls, template="c")
```

---

## 公众号渲染注意事项

1. **图片 URL 必须用微信 CDN URL**（mmbiz.qpic.cn），否则会被删除
2. **确保 `ensure_ascii=False`** —— `publisher.py` 已封装
3. **`content_source_url` 留空** —— 不是转载
5. **digest 不要发** —— 让微信自动取前 54 字
5. **`<img>` 标签必须 `max-width:100%`** —— 适配手机宽度
6. **不要用 `<script>` / `<iframe>`** —— 公众号编辑器过滤
7. **不要用外部 CSS 字体链接** —— 用 `font-family: STKaiti, KaiTi, 楷体, serif;` 系统字体 fallback

---

## 变更记录

- 0.2.4（2026-09-21）：更新配对风格（历史典故 → chinese_lianhuanhua_classic 第一推荐）；新增"风格 × 模板配对矩阵"v0.2.4 版；新增"公众号渲染注意事项"
- 0.2（2026-09-20）：砍 5 模板 → 3 模板（去掉复古报纸 / 现代极简 / 多巴胺手绘）