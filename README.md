# Knowledge Comic · Skill

把"主题 + 要点"变成可一键发布到公众号草稿箱的知识漫画图文。

## 装

```powershell
# 1. 装依赖（清华镜像）
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 2. 复制 .env.example 到 .env 并填入真实凭证
Copy-Item .env.example .env
# 用编辑器打开 .env 填 AGNES_API_KEY / WECHAT_APPID / WECHAT_APPSECRET
# 关键：把开发机公网 IP 加到公众号后台 IP 白名单（mp.weixin.qq.com → 设置与开发 → 基本配置）

# 3. 跑 dry-run 验证
python scripts/run.py "什么是 Transformer" -b "注意力机制" -b "Q/K/V 矩阵" -s new_yorker -t a --dry-run

# 4. 真实跑（带发布）
python scripts/run.py "什么是 Transformer" -b "注意力机制" -b "Q/K/V 矩阵" -s new_yorker -t a
```

## 用

| 命令 | 作用 |
|---|---|
| `python scripts/run.py "主题" -b "..." -b "..." --dry-run` | 跑图 + HTML，不发公众号 |
| `python scripts/run.py "主题" -b "..." -b "..." -s STYLE -t TPL` | 完整跑（生成 + 上传 + 发草稿） |
| `python scripts/recommend.py "主题"` | Mavis 风格推荐 |

## 文件结构

```
knowledge-comic/
├── SKILL.md                  # Skill 入口（MiniMax Code 触发）
├── references/               # 文档
│   ├── handraw_styles.md     # 8 个手绘风格
│   ├── templates.md          # 4 个排版模板
│   └── workflow.md           # 流程 + 调试
├── scripts/
│   ├── run.py                # 端到端 CLI 入口
│   ├── recommend.py          # 风格推荐
│   └── core/                 # 核心模块（planner/image_gen/article/publisher/prompts/config）
├── data/                     # 生成产物（git ignore）
├── .env.example
├── requirements.txt
└── README.md
```

## 风格 + 排版矩阵

| 主题 | 推荐风格 | 推荐排版 |
|---|---|---|
| AI / 算法 / 工程 | new_yorker | A 撕纸手账 |
| 经济 / 商业 / 职场 | new_yorker / us_mid_century | A 撕纸手账 |
| **历史典故 / 经典解读** | **cn_xuanfeng** | **C 中国古典故事专版** |
| 科学 / STEM | kid_science_diagram | A 撕纸手账 |
| 哲学 / 情感 | jp_kawaii_warm | A 撕纸手账 |
| 亲子 / 教育 | kid_picture_book | D 多巴胺手绘 |
| 城市 / 生活 / 速写 | jp_terada | A 撕纸手账 |

详见 `references/handraw_styles.md` 和 `references/templates.md`。

## License

MIT