# Workflow · 详细流程 + 调试指南（v0.2.4）

## Mavis 对话流专用规则（v0.2.4，2026-09-21 沉淀）

### 流程总览（每一步都要用户拍板才能进下一步）

```
[1] 用户说"做一个知识漫画"
       → Mavis 问主题 + 要点（≥2 条）
[2] Mavis 推荐风格 + 模板（基于主题关键词 / RECOMMEND_MATRIX）
       → ask_user 让用户拍板
[3] step_plan(topic, bullets, style_id, template_id)
       → 读 storyboard.json 展示分镜给用户
       → ask_user 让用户拍板（接受 / 改某页字段 / 重跑）
[4] step_gen_images(job_id)
       → ★ 用 deliver-assets 展示图，**必须附"分镜意图 vs 实际画面"对照表** ★
       → ask_user 让用户拍板（接受 / 重画某些页 / 重画全部）
[5] step_render_article(job_id, template_id=None)
       → 读 HTML 预览给用户
       → ask_user 让用户拍板（接受 / 改模板 / 拒绝）
[6] step_publish_draft(job_id, template_id=None)
       → 报告 draft_media_id + 公众号后台链接
```

### 关键铁律（Mavis 必遵守）

#### A. 每张图必附"分镜意图 vs 实际画面"对照表 ★★★

**为什么**：用户在 2026-09-21 张巡守睢阳项目明确抱怨：
> "你现在堆出来一堆画，每个画表达的是什么内容，我也不知道，怎么能判断是否合适？这个要优化，并且更新到 skill 中。"

**怎么做**：Mavis 在 step_gen_images 完成后，**必须**用 read tool 把 12 张图实际读出来，对照 storyboard.json 的 caption + key_visual + body 摘要，输出对照表：

| 页 | 章节 | 分镜意图 | 实际画面 | 评估 |
|---|---|---|---|---|
| p1 烽起 | 张巡赴任真源 | 烛光 + 持卷轴 + 看地图 + 风雪夜 | ✅ 张巡持卷轴 ✅ 烛光 ✅ 桌上地图 ✅ 窗外飞雪 | ✅ 完全符合 |
| p9 骂贼 | 嚼齿穿龈、骂贼至死 | 被绑木桩 + 嘴角带血 + 仰天长啸 | ✅ 张巡站姿仰望 ✅ 敌人执矛剪影 ⚠ 未呈现"被绑" ⚠ 未呈现"血" | ❌ 关键元素缺失 |

每页用 ✅ / ⚠ / ❌ 标记关键元素是否到位。

#### B. 端到端长任务实时进度同步

跑图 / 批量任务 > 30s 必须实时给进度信号，禁止连续 silent：
- 启动 → 告知"开始 + 预计耗时"
- 跑图期间 → 每 60s 至少发"X/N done" 或"还在跑"
- 任务完成 → 立即送图 + 评估对照表

#### C. 用户主导（User-in-the-loop）

**每一篇知识漫画的核心创作决策，用户必须亲自介入**：
- 风格 + 模板拍板 → ask_user
- 分镜审阅 → read tool 读 JSON + ask_user
- 图片审阅 → **deliver-assets + 对照表 + ask_user**（不能只 deliver-assets）
- HTML 预览拍板 → read tool 读 HTML + ask_user

不能跳过介入直接跑完发草稿。

---

## 完整流程图

```
用户说"做一个知识漫画"
       │
       ▼
Mavis：问主题 + 要点（用 AskUserQuestion）
       │
       ▼
Mavis：recommend_style(topic) + recommend_template(topic) → 推荐 + 理由
       │
       ▼
用户拍板风格 + 模板（ask_user）
       │
       ▼
Mavis：step_plan(topic, bullets, style_id, template_id)
       │
       ▼
   ┌───────────┐
   │  Step 1   │ Planner (LLM/Mock) → storyboard.json
   └─────┬─────┘
         ▼
   Mavis：read storyboard.json → 展示分镜 → ask_user
         │
   ┌───────────┐
   │  Step 2   │ Image gen (Agnes) → pages/NN-page.png
   └─────┬─────┘
         ▼
   Mavis：deliver-assets + 对照表 → ask_user
         │ (可选) regenerate_pages=[N,...]
   ┌───────────┐
   │  Step 3   │ Render article (WeChat HTML)
   └─────┬─────┘
         ▼
   Mavis：read HTML → ask_user
         │ (可选) 换模板
   ┌───────────┐
   │  Step 4   │ Publish to WeChat (上传 + draft/add)
   └─────┬─────┘
         ▼
   Mavis：报告 draft_media_id + 公众号后台链接
```

---

## 调试指南

### 1. 验证 Agnes + WeChat 凭证

```python
from scripts.run import step_publish_draft

# dry-run 测链路（不真实上传）
result = step_publish_draft("kc_xxx", dry_run=True)
print(result)  # {'dry_run': True, 'job_id': 'kc_xxx', 'work_dir': '...'}
```

如果上传 / draft/add 报错：
- `Missing required env var: AGNES_API_KEY` → 检查 `.env`
- `WeChat get_access_token failed: errcode=40164` → 加 IP 白名单

### 2. 看草稿但不发布（推荐先 dry-run）

```python
result = step_publish_draft("kc_xxx", dry_run=True)
```

只跑 upload + 渲染 + publish_xxx.html，**不**真正调 `/cgi-bin/draft/add`。

### 3. 重发草稿（图片复用）

如果图没问题但草稿没创建成功，直接重跑 `step_publish_draft(job_id)`（publisher 自动上传 + 创建草稿）。

### 4. 推荐风格 / 模板

```python
from scripts.core.prompts import recommend_style_rationale, recommend_template
print(recommend_style_rationale("张巡守睢阳"))
print(recommend_template("张巡守睢阳"))
```

### 5. 单独测试模板

```python
from scripts.core.article import render_mock_preview
print(render_mock_preview("c"))  # 模拟模板 c（朱砂红 + 印章）
print(render_mock_preview("e"))  # 模拟模板 e（深蓝灰 + 印章）
```

### 6. 检查 prompt 是否超 9800 字符

```python
from scripts.core.prompts import build_image_prompt
full = build_image_prompt("chinese_lianhuanhua_classic", "your visual description...")
print(f"prompt len: {len(full)}")
# > 9800 → 会被截断（保 style + 七要素套话，砍 scene_description）
```

---

## 常见问题

### Q：草稿里中文是 `\u4e00` 乱码？

A：`requests.post` 没设置 `ensure_ascii=False`。检查 `scripts/core/publisher.py` 的 `create_draft()` 函数（已封装）。

### Q：图片里出现中文对话气泡？

A：planner 的 `visual` 字段写了对话文字。检查：
- mock_storyboard 是否污染
- 真 LLM 输出时 prompt 是否带"NO text"
- `scripts/core/prompts.py:build_image_prompt` 是否强制 "ABSOLUTELY NO TEXT on the image"

### Q：Agnes 报 503 队列满？

A：自动 retry。也可手动等几秒重跑，或减少 `--batch-size`。

### Q：微信公众号 IP 白名单加错了 IP？

A：登录 mp.weixin.qq.com → 设置与开发 → 基本配置 → 公众号开发信息 → IP 白名单 → 修改。
- 开发机公网 IP 查：`curl https://api.ipify.org`
- 一次能加多个，用回车或逗号分隔

### Q：风格跑偏到现代写实（连环画派跑出了油画感）？

A：v0.2.4 §6 现代写实锚点防范：
1. 把 "painted illustration" 声明放 SUBJECT 第一句
2. 砍掉 candle / lantern / desk / porcelain / modern Chinese minimalism / volumetric light
3. 把人物描述成 brush-painted figure on rice paper

### Q：草稿已发但想换图重发？

A：调 `step_publish_draft(job_id)` 即可，publisher 会重传全部图 + 重创建草稿（旧草稿不会自动删，去后台清）。

### Q：端到端跑很久还没完？

A：6-12 张图 × 120-160 秒/张 = 12-32 分钟（v0.2.3+ 戴敦邦派构图复杂）。如果超过 1 小时，看 Agnes 是否 503。
- 临时 workaround：用 `step_gen_images(job_id, regenerate_pages=[已完成页])` 跳过已完成页
- 永久 fix：优化 batch + 并发（v0.3+ 计划）

### Q：step_render_article 不传 template_id 用了默认 e 而不是 c？

A：v0.2.4 已修复。Storyboard dataclass 加了 `recommended_template` 字段 + `to_dict()` 返回 + `_load_storyboard` 读。如果旧 storyboard.json 是修复前生成的，需要：
- 重新 step_plan 一次（新 storyboard 才会带 recommended_template）
- 或者手动编辑 storyboard.json 加 `"recommended_template": "c"` 字段

---

## 高级用法

### 自定义风格

改 `scripts/core/prompts.py` 的 `STYLES` dict 加新风格：

```python
"my_style": StylePreset(
    id="my_style",
    name_zh="我的风格",
    name_en="My Style",
    category="X · 自定义",
    use_cases=("场景1", "场景2"),
    prompt_en="Single-panel illustration in ...",
    prompt_zh="...",
    negative="...",
),
```

加完后：
1. `RECOMMEND_MATRIX` 加新主题映射
2. `CHARACTER_ANCHORS` 加新角色锚点（按风格）
3. 文档：`references/handraw_styles.md` + `SKILL.md`

### 自定义模板

改 `scripts/core/article.py`：

```python
def render_template_my(inp):
    """我的自定义模板"""
    ...

TEMPLATES["my"] = ("M · 我的模板", render_template_my)
```

加完后：
1. `RECOMMEND_TEMPLATE_MATRIX` 加新主题映射
2. 文档：`templates.md` + `SKILL.md`

### 数据管理

```
data/
├── kc_1727123456/             # job_id
│   ├── storyboard.json        # 拆解结果
│   ├── article_a.html         # 预览版（本地 data URI / 占位）
│   ├── article_c.html         # 预览版 c 模板
│   ├── article_e.html         # 预览版 e 模板
│   ├── publish_c.html         # 发布版（WeChat CDN URL）
│   └── pages/
│       ├── 01-page.png
│       └── ...
└── smoke.png                  # 单图调试用
```

`.gitignore` 应该加：
```
data/
.env
__pycache__/
*.pyc
```