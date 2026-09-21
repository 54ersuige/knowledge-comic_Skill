# Knowledge Comic · v0.2.4

把"主题 + 要点"变成可一键发布到公众号草稿箱的知识漫画图文。戴敦邦派连环画 / 国潮条漫 / 纽约客式 / 美式中世纪 / 水墨写意 — 5 种风格可选。

---

## ⚡ 一键安装（跨设备同步）

**新设备**（Windows / macOS / Linux 都行）：

```bash
# Windows PowerShell
irm https://raw.githubusercontent.com/54ersuige/knowledge-comic_Skill/main/install.ps1 | iex

# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/54ersuige/knowledge-comic_Skill/main/install.sh | bash
```

装完后脚本会：
1. 自动 clone 到 `~/.minimax/skills/knowledge-comic`
2. 装 Python 依赖
3. 复制 `.env.example` → `.env`
4. 提示你填凭证
5. 显示本机公网 IP（**加到公众号 IP 白名单**）
6. 跑 smoke test 验证

**手动安装**（不跑脚本）：

```bash
git clone https://github.com/54ersuige/knowledge-comic_Skill.git ~/.minimax/skills/knowledge-comic
cd ~/.minimax/skills/knowledge-comic
python -m pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 填 AGNES_API_KEY / WECHAT_APPID / WECHAT_APPSECRET
# 公众号加本机公网 IP 到 IP 白名单
```

---

## 🎨 5 种风格（v0.2.4）

| ID | 名字 | 适合 |
|---|---|---|
| `chinese_lianhuanhua_classic` | **中国古典连环画（戴敦邦派）** ★ 历史典故第一推荐 | 历史典故 / 古典小说 / 圣贤帝王 / 江湖侠义 |
| `guochao_manhua` | 国潮古风条漫 | 中国故事 / 武侠 / 宏大叙事 |
| `cn_xuanfeng` | 宣风 · 国风写意 | 国学 / 古籍解读 / 东方美学 |
| `new_yorker` | 纽约客式 · 报刊讽刺 | 经济学 / 心理学 / 严肃 / 成人 |
| `us_mid_century` | 美式中世纪 · 复古杂志 | 商业模式 / 品牌 / 设计 |

详见 `references/handraw_styles.md`。

## 📐 3 种排版模板

| ID | 名字 | 适合 |
|---|---|---|
| `c` | **中国古典故事专版（朱砂红 + 印章）** | 历史典故 / 古文 / 国学 |
| `e` | **典雅知识风（深蓝灰 + 印章）** | 知识 / 科普 / 商业 / 严肃 |
| `a` | 撕纸手账风 | 情感 / 旅行 / 通用兜底 |

详见 `references/templates.md`。

---

## 🚀 4 步 API 用法（Python 直接 import）

```python
from scripts.run import (
    step_plan,              # Step 1: 主题 → 分镜 JSON
    step_gen_images,         # Step 2: 分镜 → PNG
    step_render_article,     # Step 3: PNG → HTML
    step_publish_draft,     # Step 4: HTML → 公众号草稿
    # v0.2.4 辅助
    step_rewrite_visual,    # 重写某页 + 立即重跑
    step_show_intent_vs_actual,  # 输出分镜意图 vs 实际画面对照表
    step_dry_publish,       # dry-run 渲染 publish html
    step_preflight,         # 发布前 6 项自检
)

# Step 1
sb, job_id, work_dir = step_plan(
    topic="张巡守睢阳",
    bullets=["燕军围城", "六千八百人", "粮尽食人", "骂贼至死"],
    style_id="chinese_lianhuanhua_classic",
    template_id="c",
)

# Step 2
image_paths = step_gen_images(job_id)
# 或只重画某些页：
# image_paths = step_gen_images(job_id, regenerate_pages=[10, 11])

# Step 3（template_id=None 自动用 recommended_template）
html_path = step_render_article(job_id)

# Step 4（template_id=None 自动用 recommended_template）
result = step_publish_draft(job_id)
print(result["draft_media_id"])
```

---

## 🛠 辅助脚本

```bash
python guide.py              # 列所有 step + 推荐矩阵
python guide.py "张巡守睢阳"   # 拿主题推荐（JSON 输出）
python guide.py "Transformer" # 英文主题
python diagnose_prompt.py <job_id>  # 检查 prompt 是否超 9800 字符
python diagnose_terms.py <job_id>   # 检查 visual 是否含风格锚点
```

---

## 🔧 排错清单

| 问题 | 原因 | 解决 |
|---|---|---|
| `Missing required env var: AGNES_API_KEY` | `.env` 没填 | 编辑 `.env` 填 AGNES_API_KEY |
| `WeChat get_access_token failed: errcode=40164` | 公网 IP 没加白名单 | 公众号后台加 IP |
| `get_access_token failed: errcode=40125` | AppID/Secret 错 | 检查 `.env` |
| 图里有中文对话气泡 | visual 写了对话 | 重写 visual（不带对话） |
| 风格跑偏到现代写实 | visual 含 candle/lantern/desk | v0.2.4 §6 现代写实锚点防范 |
| Agnes 队列 503 | 高峰期 | 自动 retry 等几秒 |
| `prompt_len > 9800` | visual 太长 | `diagnose_prompt.py` 看哪页 |

详见 `references/workflow.md` 调试指南。

---

## 📂 文件结构

```
knowledge-comic_Skill/
├── SKILL.md                  # Mavis 触发入口
├── README.md                 # 本文件
├── install.ps1               # Windows 一键安装
├── install.sh                # macOS / Linux 一键安装
├── guide.py                  # 风格推荐 + 矩阵展示
├── diagnose_prompt.py        # prompt 长度诊断
├── diagnose_terms.py         # 风格锚点诊断
├── .env.example              # 凭证模板（不提交 .env）
├── requirements.txt
├── references/               # 文档
│   ├── handraw_styles.md     # 5 风格完整定义
│   ├── templates.md          # 3 排版模板
│   ├── user-review.md        # Mavis 对话流 + 对照表模板
│   ├── workflow.md           # 端到端流程 + 调试
│   └── style_guide.md        # 文章内容评分维度
└── scripts/
    ├── run.py                # 4 个 step API + 4 个辅助 + CLI
    ├── canon.py / image_review.py / recommend.py
    └── core/                 # planner/image_gen/article/publisher/prompts/config
```

---

## 📜 License

MIT