---
name: knowledge-comic
description: Knowledge comic generator that turns a topic + bullet list into a publication-ready WeChat MP draft. Use when user asks for "知识漫画", "公众号知识漫画", "科普漫画", "典故解读", "历史故事漫画", "一图读懂", "科普文章配图". Hands off the entire pipeline — style recommendation, storyboard split, image generation, article HTML render, and WeChat draft creation — through step-by-step Python APIs that Mavis calls directly inside the conversation.
version: 0.3.25
---

# Knowledge Comic (WeChat MP) — v0.3.25

把「主题 + 要点」变成可一键发布到公众号草稿箱的知识漫画图文。**端到端在 Mavis 对话里逐步执行 + 用户拍板**。

## v0.3.25 核心变化（2026-10-08，live 验证抓出的静默降级）

**背景**：v0.3.24 重写了 22K 的 planner prompt，但**没有用真 LLM 验证过**。
补跑 `test_live_smoke.py --live` 立刻炸出一个真问题 —— 也说明
**改了驱动全部生成的 prompt 却不做 live 验证，等于没改**。

### 1. 【真故障】LLM 返回合法 JSON，却被判「non-JSON」并静默降级到 mock

live 冒烟报「每页都有 keywords 0/10」「每页都有 [GENDER] 0/10」。
抓原始响应后发现：**LLM 返回的是完全合法的 JSON** ——
`finish_reason=stop`（没被截断）、大括号闭合、16,217 字符、
content 首尾截取 `json.loads` **直接成功**、而且 `"gender": "male"`
正是裸字符串（v0.3.24 那个阻塞级修复生效了）。

**根因**：旧解析层靠**手写大括号计数**找最外层 `{...}`，有两个真实缺陷：
1. **大括号计数不认字符串字面量** —— visual/正文/引文里出现一个不平衡的
   `{` 或 `}`（英文缩写、引文、代码片段），`depth` 再也回不到 0，整段失败
2. 尾部有多余文字（模型爱在 JSON 后面补一句"以上"）同样连带失败

`temperature=0.7`，所以是**偶发的** —— 也就是说"看起来跑通了"。

**修复**：改用 stdlib 的 `JSONDecoder.raw_decode`（json 自己的扫描器，
正确处理字符串与转义，解析完第一个完整 JSON 值即停、**尾部多余内容不影响**），
并按可靠度分 4 层尝试：整段直解 → ```json``` 围栏 → 剥 `<think>` →
`raw_decode` → 多围栏合并。失败时报错信息带上**尝试记录 + `finish_reason` +
首尾各 300 字符**，能一眼分清"是解析问题还是 LLM 截断"。

### 2. 【更严重】解析失败会**静默降级**到 mock

`plan_storyboard` 捕获 `RuntimeError` 后无条件 `return mock_storyboard(...)`。
而 **mock 分镜没有 `keywords`、没有 `[GENDER:xx]`** —— 等于把朱砂红高亮和
性别锚点**整条链路静默废掉**。用户看到的只是"跑完了"，一路拖到审阅阶段
才炸出 30 个 error，再往后跑图会烧额度。

**修复：把"合法的离线模式"和"真故障"拆成两类。**

| 场景 | 行为 |
|---|---|
| `use_llm=False` | 直接 mock，不调 LLM |
| **没配 `LLM_API_KEY`**（`LLMNotConfigured`） | **合法离线模式** → 降级 + 明确告知 |
| 配了 key 但调用/解析失败，`allow_mock_fallback=False`（**默认**） | **当场抛错**，带可诊断信息 |
| 同上 + `allow_mock_fallback=True` | 降级（仅 CI / 离线批量场景用） |

`allow_mock_fallback` 已从 `plan_storyboard` 透传到 `run.py` 的 `step_plan`。

### 3. 修 v0.3.24 重编号留下的过期交叉引用

把 prompt 章节重编号成 §1~§7 后，代码与文档里 8 处引用仍指向旧的"铁律 N"：
`preflight.py`（keywords/punchline/dialogue 三处）、`thresholds.py`（两处）、
`test_preflight_v0315.py`、`references/style_guide.md` §2.5.1/§2.5.2。
不影响运行，但会把下一个读代码的人引到 prompt 里不存在的地方 ——
与本项目反复栽跟头的文档漂移同源。全部改到新编号。

### 4. 新增 3 个测试文件（不烧额度）

- `test_json_extract_v0324.py`（24 项）—— JSON 提取层：围栏 / `<think>` 前缀 /
  **尾部多余文字** / **字符串里不平衡的大括号**（旧实现必挂的两种形态）/ 转义往返
- `test_fallback_v0324.py`（11 项）—— 降级契约四象限，用桩函数替掉 LLM 调用
- `test_drift_v0324.py`（v0.3.24）—— CRLF/LF/BOM/老式 CR 四种表示必须同哈希

**当前：11 个测试文件全绿，`ruff check scripts/` 0 error。**

## v0.3.24 核心变化（2026-10-08，可观察性 + 结构性瘦身）

**背景**：全量代码审计 + 7 个测试文件实跑 + prompt 逐段体积测量。发现的不是
"某个值定错了"，而是四类**同一份东西被复制多份**导致的问题 —— 这个失效模式
在项目里已经出现 4 次（v0.3.3 keywords 解析层漏字段 / v0.3.18 CONCEPT 段漏加黑名单 /
v0.3.21 prompt 拼装双路径 / 本次阈值漂移）。

### 0. 【阻塞级】planner prompt 里的 JSON 示例本身是非法 JSON

`gender` 写成 `"gender": {"enum": ["male", "female"]}` —— **JSON 没有 `enum`
这个关键字**，这写法等于教 LLM 输出嵌套对象。而 `resolve_gender()` 只认字符串，
LLM 照抄示例 → `CHAR_GENDER_MISSING` 阻塞 → **一张图都不跑**。
`characters` 那段还是两段对象字面量拼接（`[{...}]` 后面又跟 `{...}]`），
`sources` 行有未转义的双引号。**整块"严格 JSON"示例三处语法错误。**

更麻烦的是 v0.3.22 的测试 `test_v0322.py` 断言 prompt 里**必须出现**那个假 enum
—— 测试把 bug 锁成了"规范"。现已改写为断言真实意图（示例块能被 `json.loads`
吃下 + gender 是裸字符串 + 显式禁止嵌套对象）。

**规则**：prompt 里给 LLM 看的 JSON 示例，必须能被 `json.loads()` 解析。
`test_prompt_v0324.py` 现在每次都验这一条。

### 1. 跑图全程无进度输出（每次都疼）

`image_gen.generate_pages` 一直有 `progress_cb` 形参，但 `run.py` 两个调用点
**都没传** —— 8~12 页每页 20~40s，整段 3~6 分钟零输出，用户既不知道在跑还是死了，
也看不到跑到第几张。角色参考图（2 角色 × 4 视图）同样静默。

现在 `_progress_printer()` 打印 `page 3/10 done (62s, 约还需 124s) -> p3`，
ETA 按实测速率算。角色参考图也补了 `progress_cb`（缓存命中也算一步，
否则命中多时进度条"卡住不动"反而更像挂死）。

### 2. 测试跑不了一条命令

`pytest scripts/tests` → **INTERNALERROR 退出码 3**。7 个测试文件是 standalone
脚本（顶层 `assert` + 结尾 `sys.exit(0)`），pytest 收集阶段撞 `SystemExit`
把整个 session 撞崩，只能一个一个手敲。

新增 `scripts/run_tests.py`：子进程逐个跑 + 汇总表 + 明确退出码，
不改动已验证的断言。`--live` 才跑烧额度的 live 冒烟，`-k` 按文件名过滤，
`-v` 透传完整输出。当前 **7/7 通过，约 8s**。

### 3. 五道检查层阈值已实际漂移 → 收敛到 `core/thresholds.py`

| 规则 | preflight（阻塞关卡） | review_page（体检报告） | 后果 |
|---|---|---|---|
| body > 150 | warn | **error** | 同一次跑两份矛盾结论 |
| body > 170 | block | 无此档 | 阻塞线比报告线还松 |
| body < 90 | warn | 无此档 | 95 字正文被判「低于下限」 |
| keywords < 3 | **无检查** | warn | 1 个关键词的页面能过阻塞关卡 |
| punchline | 实按 30 放行，文案却写「10-22 字」 | 无检查 | 代码与自己的提示打架 |
| dialogue | 实按 90 放行，与规则 50 脱节 | 无检查 | 同上 |

新增 `core/thresholds.py` 作为**唯一真源**，preflight / review_page 都 import。
修 `review_page` 的方向：preflight v0.3.15 的 docstring 记着事故原因
（93/95/154 字全被判不合格），**preflight 是对的、review_page 是陈旧的**。
补 preflight 缺失的 `KW_TOO_FEW`。`test_thresholds_v0324.py` 的重点不是
"数值对不对"，而是**"某层偷偷自己写死一个数字"这件事会失败**。

### 4. 22K 字符 system prompt 瘦身

`PLANNER_SYSTEM_PROMPT` 22,064 → **14,578（历史题材，-34%）/ 13,297（非历史，-40%）**。

做法不是删规则，是删三类**对 LLM 没有信息量**的内容：
- **版本考古**：「v0.2.3 升级」「v0.3.0 新增，2026-09-24」
- **事故复盘**：「**根因**：实测卧薪尝胆项目，planner 给勾践写圆领袍+武冠+幞头…」
  —— 这是给人读的 changelog，模型只需要规则本身
- **重复**：角色一致性原本散在 6 处（硬约束 / 视觉签名 / 五件套 bible /
  v0.2.5 人物一致性 / 密度铁律 / 铁律 1）→ 合并成 §4.5；零文字 2 处 → 1 处；
  镜头规则 2 处 → 1 处

**朝代速查表改条件注入**（新增 `build_system_prompt()`）：速查表正文只存一份
（`prompts.CN_DYNASTY_COSTUME_GUIDE`，与 preflight 共用），只在
`chinese_lianhuanhua_classic` / `cn_xuanfeng` / `guochao_manhua` 三个风格注入。
跑「峰终定律」这类经济学题材时，1.2K 字朝代服饰表是纯噪声。历史题材的考据
约束一点没丢。顺带把 `PLANNER_SYSTEM_PROMPT.replace("输出 6-10 页", ...)`
换成显式 `build_system_prompt(style_id, target_pages)` —— 原写法一旦改文案就静默失效。

`test_prompt_v0324.py` 双向锁死：**22 条硬规则一条都不能丢**（CONCEPT / 三拍 /
术语翻译 / 五件套 / GENDER / era / 零文字 / 七要素 / 中文速记 / 表情 anchor /
连环画多人物 / 镜头分配 / caption 匹配 / dialogue 必填 / 史实 …），
**7 类噪音必须消失**，条件注入逐风格验证。

### 5. canon 一致性约束在主流程里是死的

`canon_injection` 参数从 `plan_storyboard` 一路传到 `_build_planner_user_msg`，
看起来是活的 —— 但 v0.3.24 之前**只有 `scripts/run_plain.py` 调
`get_canon_injection()`，主流程 `run.py` 从没接过**，恒为 `""`。
`data/canon.md` 是死配置。（`run_plain.py` 本身依赖一个已被删除的评分 API，
在 HEAD 上就无法 import，v0.3.24 一并归档到 `_archive/`。）

接上之前先处理了一个雷：该文件装的是**黑死病项目的专属数据**（"不要用
鼠疫/黑死病"、1347 欧洲死亡率、墨西拿港口）。`canon.py` 会把解析结果
**无条件注入每一次 planner 调用**，接上主流程后会污染所有无关主题。
原内容完整保留为 `data/canon.blackdeath.md`（格式范例），`data/canon.md`
改为**空模板**（注入长度实测 0，行为与之前完全一致）。

顺带一个坑：`canon.py` 的解析器**不跳过 HTML 注释**，写在 `<!-- -->` 里的
示例表格照样被当真规则解析（实测注释里的 1 行示例被读成 1 条术语 + 1 条数字）。
所以空模板里一行表格都不能有。

### 6. dev 镜像漂移校验自动化

`AGENTS.md` 要求"同步完必须跑漂移校验"，但那条校验是**要人手动敲的 PowerShell**，
所以从来没被稳定执行过 —— 实测 `article.py` 真源 1727 行 / 镜像 1721 行，
**镜像缺 v0.3.18 双层蒙版修复**。

新增 `scripts/check_drift.py`：逐文件行数 + SHA-256 比对，列出缺失 / 多余 /
不一致三类漂移，退出码有意义。`--sync` 一步同步并复校。
**纯人工约定 = 不会执行**，现在它是可跑的。

### 7. 卫生

- v0.3.23 一直没提交（13 个文件 modified，git HEAD 还停在 v0.3.22）→ 本版一并提交
- SKILL.md 内部版本号又不对齐（frontmatter 0.3.23 vs 文件结构段 v0.3.22）——
  正是 v0.3.2 修过的"三处版本号不一"同类复发，已对齐
- `diagnose_prompt.py` / `diagnose_terms.py` 违反 v0.3.2 自己的规矩进了库
  （一次性脚本该归 `_archive/`，它们不以 `_` 开头绕过了 `.gitignore`）→ 已 `git mv`
- 根目录 9 个 `_*.txt` / `_tmp_*.py` 临时文件清掉（可恢复删除）


## When to use

- 用户说"做一个知识漫画" / "科普配图" / "典故解读漫画"
- 用户给主题 + 要点列表（≥2 条），想直接看到公众号草稿
- 用户明确要 5 种锁定风格里的某一类（new_yorker / us_mid_century / cn_xuanfeng / guochao_manhua / chinese_lianhuanhua_classic）

## Mavis 触发引导（/knowledge-comic 后第一步）

**用户说 `/knowledge-comic` 或 "做个知识漫画 / 科普配图 / 典故解读"**：

1. **如果用户没说主题 + 要点**：用 `ask_user` 问：
   - 主题（一个具体短问）
   - 要点列表（≥2 条，每条一行）
2. **如果只说主题没说要点**：用 `ask_user` 追问要点列表
3. **拿到主题 + 要点后**：调下面的 `guide.recommend(topic)` 拿到推荐
4. **用 `ask_user` 让用户拍板**：
   - 选项 1：风格 A + 模板 X（推荐第一选择）
   - 选项 2：风格 B + 模板 Y（备选第二）
   - 选项 3：风格 C + 模板 Z（备选第三）
   - 选项 4（Other）：自定义风格 / 模板
5. **拍板后**：调 `step_plan(topic, bullets, style_id, template_id)` 开始 Step 1
6. **遇到歧义**：先调 `guide.show_intent(topic, bullets, style_id, template_id)` 展示完整推荐 + 理由

**辅助脚本**：

```bash
python guide.py              # 列所有可用脚本 + 推荐矩阵
python guide.py "Transformer" # 拿主题推荐
python guide.py "张巡守睢阳"   # 中文主题
```

返回 JSON：`{"style_id": "chinese_lianhuanhua_classic", "template_id": "c", "alternates": [...], "rationale": "..."}`

## v0.3.23 核心变化（2026-09-30，两个可移植性 bug）

**背景**：用户问「不依赖 Mavis、只靠这个 Skill 本身能不能跑」。实测跑
`run.py all --dry-run`（勾践复国，真调 LLM，157s / 8 页 / 提取 2 个角色）
暴露两个真问题。

### 1. Windows GBK 崩溃（阻塞级 · 独立使用必挂）

**症状**：`UnicodeEncodeError: 'gbk' codec can't encode character '\U0001f534'`
崩在 `run.py` 的 `print(pre.report())`。

**根因**：`preflight.py` 报告用 🔴 / 🟡 标记，**非 BMP 字符**在中文 Windows
控制台（cp936）里编不了。三个放大因素：

- **只在阻塞分支触发** —— 体检通过时不 print 报告，所以容易漏测
- **崩在最不该崩的地方** —— 是 preflight 在**拦你**，结果拦截器自己先炸了
- **Mavis 里测不出来** —— 宿主重定向了 stdout，UTF-8 编码，emoji 正常

**修复**（两道）：
1. `preflight.py` / `visual_qa.py` / `review_page.py` / `run.py` 四处报告
   标记改**纯文本** `[阻塞]` / `[建议]`（✅❌⚠ 保留，GBK 能编）
2. `run.py` 入口加 `_safe_stdout()` —— `stream.reconfigure(errors="replace")`，
   任何未来新增的非 ASCII 字符退化成 `?` 而非抛异常

### 2. `玉璧` 假阳性（阻塞级 · 春秋战国题材全中）

**症状**：planner 给勾践写「佩玉璧」→ `ERA_ANACHRONISM` 硬阻塞。

**根因**：`ANACHRONIC_MARKERS` 把 `玉璧` 列为先秦穿帮词。但**玉璧是春秋战国
正统礼器**（蔺相如完璧归赵即战国故事）。原始事故 kc_1790664590 里，夫差真正
穿帮的是「金质发冠 + 繁复的华丽丝绸」，`玉璧`只是顺带被列进表里当成了主因。

**影响面**：这个 Skill 的主力题材就是春秋战国，**只要角色佩玉璧就必被阻塞**。

**修复**：`玉璧` 从 `prompts.ANACHRONIC_MARKERS` 和 `preflight` 兜底副本中移除，
并在 `_f_era_anachronism` 的 docstring 写清归因澄清。保留真正错配项：
金质发冠 / 龙袍 / 龙纹 / 补子 / 乌纱 / 蟒袍 / 顶戴 / 朝珠 …
**词表从 27 降到 26，但精度显著提升。**

### 3. 附带修复：测试文件编码损坏

`tests/test_preflight_v0315.py:271` 测试名含损坏字符 `单\ufffd\ufffd弱信号不报`
（疑似历史编码事故），在 GBK 控制台下 `print` 抛 UnicodeEncodeError →
**测试逻辑 93/93 全过但退出码 1**。已修正为「单独弱信号不报」。

**验证**：7 个测试文件全部 rc=0（无任何编码豁免）；11 文件哈希一致。

---

## v0.3.19 - 0.3.22 核心变化（2026-09-29 ~ 09-30，角色锚点工程化）

这四个版本是一组**「性别锚点」加固**，根因都是：角色参考图经 i2i 传进每一页，
锚点一旦猜错，整批图全崩（实测 kc_1790664590 夫差被画成女性，污染全部含他的页面）。

| 版本 | 改了什么 | 位置 |
|---|---|---|
| **0.3.19** | 角色签名指纹 —— `visual_signature` 变了就必须重画 4 视图参考图，不复用旧的 | `image_gen.py` |
| **0.3.20** | **性别解析收敛为单一真源** `resolve_gender()`；page 级和 char 级都走它。原默认 `female` 改掉（男性主题会被默认成女性）；preflight 修两个真实缺陷 | `prompts.py` / `preflight.py` |
| **0.3.21** | prompt 拼装唯一化 —— 原先主路径和超限截断路径有**两份几乎相同的拼装代码**，改一处漏另一处。统一为 `_assemble()` | `prompts.py` |
| **0.3.22** | ① JSON schema `gender` 改 `enum: ["male","female"]`；② **`KNOWN_GENDER` 兜底表停止兜底** —— planner 必须自己填；③ MUST-SHOW fallback 复用 `_assemble`，不再 `assembled[:9790]` 硬切（那会砍掉 ZERO_TEXT_BOOST）；④ 连环画强锚不再锚现代室内物（卧薪尝胆 p06/p09 暴露）；⑤ preflight / visual_qa 落盘 JSON 报告 | 全模块 |

**0.3.22 行为变更（重要）**：`CHAR_GENDER_MISSING` 现在是**阻塞**项，
且不再用内置人名表兜底。`gender` 缺失 = 跑图前 SystemExit(1)，一张图都不跑。
**用户手动传 `characters=` 时必须自己带上 `gender`。**

---

## v0.3.18 核心变化（2026-09-30，图文关联 + 文风定版）

**根因**：用户实图反馈「看不懂」+「图文对不上」。两条都是文风问题，不只是画面问题。

1. **术语翻译铁律（planner 4.1）** —— 「看不懂」的唯一根因是**文言术语裸奔**。
   任何术语首次出现必须 `术语（大白话解释）`，且**一页最多 1 个**。
   专有名词（人名/地名/朝代/官职）免解释。完整禁用清单 + 改写对照表见
   `references/style_guide.md` §2.5.1。
2. **正文三拍结构（planner 4.2）** —— 讲事 40-50 字 → **说破 40-60 字（最容易丢也最关键）** → 落点 20-30 字。
3. **`CONCEPT:` 段** —— 画概念不画场景。`prompts.py` 把 MUST-SHOW 块提到最终 prompt
   **第 6 字符**（原第 4703/9700 ≈ 48% 的位置，模型高权重区拿不到概念）。
4. **负面提示词在本管线基本无效** —— 顽固偏差（明代乌纱帽、斗笠）要**改正面描述 + 塞进 CONCEPT 段**才压得住。
5. **概念页 / 大场面页必须 `auto_char_refs=False`** —— i2i 角色参考图会压制 CONCEPT 里的场景。
6. **模板 c 段数上限 `max_paras=3`** —— `max_len` 只管单句超长，4 个 20-50 字短句会原样切 4 段。
7. **修史料脚注被逐字插空格** —— `" ".join(src)` 把《孙子兵法》渲染成《 孙 子 兵 法 》，无法检索/复制。
8. **preflight 七要素黑名单补 5 项**（`concept` / `headwear` / `negative` / `avoid` / `wardrobe`）
   —— v0.3.17 建的 `_SEVEN_ELEMENT_LABELS` 漏了 v0.3.18 新增的 `CONCEPT:`，
   被 `_ACTOR_LINE_RE` 当成角色段 → `GENDER_PARTIAL` **永久误报阻塞**。

---

## v0.3.17 核心变化（2026-09-29，朝代服饰考据铁律）

**根因**：卧薪尝胆项目实跑发现 planner 给春秋勾践写"圆领袍 + 武冠 + 幞头"，三件全是唐/汉/宋才有，春秋错配。`ANACHRONIC_MARKERS` 只是事后检测表（不进 prompt），planner 拆镜时根本看不到禁忌。

**修复**：
1. **`characters[]` 加 `era` 字段**（v0.3.17 必填）— 朝代/年代，如"春秋末年"/"唐代"/"北宋"/"明中期"。
2. **`CN_DYNASTY_COSTUME_GUIDE` 嵌入 PLANNER_SYSTEM_PROMPT**（不再只进 preflight 检测表）— 6 段朝代速查表（春秋战国/秦汉/魏晋/隋唐/宋元/明清），每段列主衣 + 冠帽 + 配饰 + 禁忌。
3. **新增铁律 7.4「朝代服饰考据铁律」** — 4 条强制：(a) 每个角色必填 era；(b) visual_signature 必须按 era 查速查表；(c) "圆领袍+武冠+幞头"等三朝错配自检；(d) 不要为"画面好看"用后世元素。
4. **JSON schema characters 字段更新** — visual_signature 例句改成"戴黑色软脚幞头, 穿朱砂色圆领窄袖袍配玉带蹀躞带"，避免 LLM 抄旧例沿用错配词。
5. **同步 dev 源** `D:\minimax-agent_cn-project\知识漫画微信公众号\src\core\` prompts.py + planner.py。

**验证**：3 个 smoke 测试全部 rc=0（test_smoke_v029 / test_gender_v030 / test_regression_v032）；PLANNER_SYSTEM_PROMPT 18.4KB（增 5KB 速查表）；6 段关键词全到位（曲裾深衣/峨冠/乌纱帽/顶戴花翎/朝珠/...）。

**边界**：planner LLM 不一定真按速查表写，需要用户在 Layout Preview 阶段肉眼核 p1/p5/p10 的视觉签名。下次跑建议手动传 `characters=[{name, role, era, visual_signature}, ...]` 双保险。

---

## v0.3.16 / v0.3.15 核心变化（2026-09-28，两道自动关卡）

**背景**：苏武牧羊项目跑了 4 天，挖出的 bug 绝大多数是**静默失败** ——
不报错、行为与预期不符，跑完才发现。v0.3.15/16 的目的不是"零错误"，
而是**把静默失败变成可见的**，第一次就拦住，不烧图、不烧额度。

### 关卡 1：生图前体检（preflight，阻塞）

`step_gen_images` 开头自动跑，位置在角色参考图**之前**（那里开始就烧钱）。
有阻塞项则 `SystemExit(1)`，**一张图都不跑**。

```python
# 独立体检（改完 storyboard.json 后先验一遍，不跑图）
from scripts.run import step_preflight_images
r = step_preflight_images(job_id)
print(r["report"])   # {"blocked": bool, "blocks": [...], "warns": [...]}
```

13 个检查函数 / 21 个 code（以 `core/preflight.py` 为准）：

**阻塞项（block）—— 一条不过就 SystemExit(1)，一张图都不跑**

| code | 检查函数 | 拦什么 |
|---|---|---|
| `KW_EMPTY` | `_f_kw` | keywords 为空 → 朱砂高亮整条链路失效 |
| `KW_TOO_MANY` | `_f_kw` | keywords 过密 → 高亮碎成一片（warn） |
| `BODY_EMPTY` | `_f_body_len` | 正文为空 |
| `BODY_LONG` | `_f_body_len` | 正文 > 170 字（硬上限；>150 软超为 warn） |
| `HEDGING` | `_f_hedging` | 「（或…）」「（实际为…）」「我不确定」→ LLM 不确定时的自我暴露 |
| `GENDER_PARTIAL` | `_f_gender` | 前缀式多角色页有段漏标 `[GENDER]`（p9 常惠事故） |
| `TEXT_INVITING` | `_f_no_text_decl` | visual 含 calligraphy/inscribed/banner → 模型会当真画字 |
| `CHAR_GENDER_MISSING` | `_f_char_gender` | **v0.3.22 起**：角色没填 `gender` → 阻塞，且 `KNOWN_GENDER` 表**不再兜底** |
| `ERA_ANACHRONISM` | `_f_era_anachronism` | 角色 `visual_signature` 含后世器物（春秋角色写幞头等） |
| `ALIGN_HIGH` | `run_preflight` | 图文不符高风险页（需传 `alignment`） |

**建议项（warn）—— 只打印报告，不拦**

| code | 检查函数 | 提示什么 |
|---|---|---|
| `BODY_LONG_SOFT` | `_f_body_len` | 正文略超 150 字目标 |
| `BODY_SHORT` | `_f_body_len` | 正文 < 90 字偏薄 |
| `MODERN_TONE` | `_f_modern_tone` | 「极限测试」「破防」「内卷」等现代口水词 |
| `GENDER_NONE` | `_f_gender` | 无性别标记且角色未登记进 `characters[]` |
| `NAME_UNKNOWN` | `_f_fabricated` | 带身份头衔却不在正史表 → 疑似编造人物 |
| `RAGGED_NO_PLAIN` | `_f_ragged_needs_plain` | 衣物写破损但无 `PLAIN unadorned` → 出字风险 |
| `NO_TEXT_MISSING` | `_f_no_text_missing` | visual 没写零文字声明（代码层已兜底） |
| `PUNCH_EMPTY` / `PUNCH_LONG` | `_f_punchline` | 「定格瞬间」金句为空 / 超 22 字 |
| `QUOTE_EMPTY` / `QUOTE_LONG` | `_f_dialogue` | 文言引句为空 / 超 50 字 |

⚠️ **v0.3.18 踩过的坑**：`_SEVEN_ELEMENT_LABELS` 漏了新增的 `CONCEPT:` 段，
被 `_ACTOR_LINE_RE` 当成角色段 → `GENDER_PARTIAL` **永久误报阻塞**，整条管线卡死。
新增七要素段名时，**必须同步 `_SEVEN_ELEMENT_LABELS` 和 preflight 黑名单**。

逃生阀：`step_gen_images(job_id, skip_preflight=True)`（用户确认要硬跑时才用）。

### 关卡 2：跑图后视觉审核（visual_qa，不阻塞）

`step_gen_images` 跑完图自动跑（`auto_visual_qa=True`）。
用 LLM 视觉能力逐页看图，查**只能看图才知道**的问题：
`TEXT_ON_IMAGE` / `STYLE_DRIFT` / `GENDER_WRONG` / `PEOPLE_COUNT` / `NOTE_MISMATCH`。

```python
from scripts.run import step_visual_qa
r = step_visual_qa(job_id)              # 全审
r = step_visual_qa(job_id, pages=[4,8]) # 只复审某几页
```

**刻意不阻塞**，与关卡 1 定位不同：

| | 关卡 1 preflight | 关卡 2 visual_qa |
|---|---|---|
| 时机 | 跑图**前** | 跑图**后** |
| 对象 | 输入（描述写得对不对） | 输出（图画得对不对） |
| 确定性 | **确定**的规则违反 | **概率性**的 LLM 判断 |
| 处置 | 阻塞 SystemExit(1) | 只打印报告，用户拍板 |
| 成本 | 0 | token + 时间 |

理由：preflight 拦的是确定的错误，可以拦；LLM 视觉判断有方差，
拦不住就只会变成"狼来了"。且只有 confidence ≥ 0.85 才升级为 block。

**实机验证抓到了用户验收时漏掉的真 bug**：
审 kc_1790586703 时 LLM 对 p04 报 95% 置信 `TEXT_ON_IMAGE`，
肉眼复核确认苏武破袍上画满伪汉字 —— 用户当初只看了画风和构图，
没放大看衣物。p01 干净无字、未报（无误报）。
**图上出字是本项目最常复发的 bug，而它肉眼容易漏** —— 这就是这层的价值。

### ⚠️ 能力边界（不回避）

这两道关卡**不能保证**以下问题被发现：

- **语义层面的史实错误** —— 把 A 的事迹安到 B 头上、年份写错、因果搞反。
  preflight 只能拦 hedging 和编造人名**结构**，语义错还得人核。
- **画风漂移** —— 图像有固有方差，即使 prompt 完全正确仍有 10-20% 漂移率，
  无法消除，只能检出。
- **LLM 内容质量** —— 史实、遣词、逻辑依然依赖 planner 的一次发挥。

所以流程仍然是**用户拍板制**（见下方"用户主导"）。关卡是把
"跑完才发现"变成"当场发现"，不是把用户从流程里拿掉。

## v0.3.8 核心变化（2026-09-28，排版结构化定版）

**背景**：用户审阅苏武牧羊的 layout_preview 后提出「文字内容尽量结构化些，不要出现大段大段文字，现在的读者没有耐心」+「第一句话需要空两格吗」。**这套排版已定为历史/经典故事类的默认规范，后续照此执行，不需再逐条讨论。**

1. **正文切成一句一段**
   - 新增 `article._split_paragraphs()`：先按句末标点断 → 仍超长（>42 字）按逗号二次切 → 合并 <12 字碎片
   - planner prompt 侧同步要求：body 写成 **3-5 个短句**（每句 15-40 字），而非一整段
   - 实测：正文最长块 124 字 → 33 字

2. **去掉首行缩进**
   - 首行缩进是"印刷体连续正文"的规矩，靠它标识段首。现在一句一段、边界由段间距标明，缩进只会让左边参差
   - c / e 两个模板统一去掉；段间距 10px → 14px 补偿呼吸感

3. **修引号被劈开**
   - 根因：`re.split(r'(?<=[。！？])', body)` 会在**引号内部**切开 ——「他说"好。"然后走了。」被拆成 `他说"好。` + `」然后走了。`，渲染出裸露的 `”`
   - 统一改为引号感知切分：切点必须在右引号/右括号闭合之后

4. **修「定格瞬间」与正文重复**
   - 根因：`quote` 来自 `_extract_quote(body)` —— 从正文抽一句话当引文，必然和正文段落重复
   - 现在只渲染 `page.dialogue`（真正的对话/旁白），没有就不渲染这张卡。宁可少一个装饰，也不要重复内容
   - planner prompt 新增 dialogue 用法说明：只写画面里真有"人说的话"，不得复制 body 里的句子

5. **排版规范写入 `references/templates.md`**，作为历史/经典故事类的默认约定

## v0.3.7 核心变化（2026-09-28，分镜速记全中文 + 兼容 LLM 两种七要素写法）

**背景**：用户看 layout_preview 的「本图分镜意图」区后指出「有英文看不懂 + 内容显示不全」。

1. **planner prompt 要求每段写 `// 中文速记`** —— 让 LLM 自己写中文，比事后拿词表猜着翻译准得多
2. **取消 46 字硬截断**，抬到 60 且只在分隔符处收刀（之前 `flying…` 砍半，信息残缺）
3. **术语词典补五类**：镜头（大远景/仰拍/全景深）、配色（肃穆/低饱和）、场景道具（雪原/地窖/铁链）、形容词
4. **兼容 LLM 的两种七要素写法**（关键修复）—— 实测 LLM 会改用自然段写法：
   - A) `SUBJECT:` / `ACTION:` / `CAMERA:` / `MOOD:` / `BACKGROUND:`
   - B) `Character bible:` / 无标签镜头句 / `Foreground:` / `Midground:` / `Background:` / `Lighting:` / `Mood:`

   只认 A 会导致「主体/景别」两栏空、「背景」显示英文。`_split_segments()` 现在两种都认并归一化。
5. **诚实优先**：只译出一小半时保留完整英文，不给"半吊子中文"

**验证**：苏武牧羊重跑 → 60 条要素 59 条全中文（98%），六要素无空缺，无「…」截断

## v0.3.5 / v0.3.6 核心变化（2026-09-28，Checkpoint 1 收敛为一个产物）

用户连续三次纠正同一件事：**审阅分镜的唯一产物是 `layout_preview.html`，排版和分镜内容必须在同一个文件里**。

- v0.3.4 只给排版（看不出画面画什么）→ v0.3.5 又另开一个分镜脚本文件（用户要两边对照，反而是负担）→ **v0.3.6 合并为一个文件**
- 现在 `step_layout_preview(job_id)` 同时展示：成品排版 + 每页分镜意图（主体/动作/配角/背景/景别/情绪 + 关键词）
- 实现坑（都写在代码注释里）：分镜说明**不能**走 `page_image_urls` 通道（模板会 `_esc()` 把 URL 塞进 `<img src>`，整段 HTML 被转义成可见文本）；也**不能用 `<section>` 包裹**（会打乱模板的 section 配平导致整页塌掉）。正解是先用占位图渲染版式，再按 `data-page="N"` 注入说明块
- `step_story_script()` 降级为**图文对齐诊断**辅助工具：用户发现某页图文不符时调它，直接指出缺哪个动作/哪个人物

## v0.3.4 核心变化（2026-09-28，分镜审阅页 + 真实题材冒烟测试）

**背景**：用户看完 v0.3.3 产出的 storyboard JSON 提了两个问题——「用户不一定能看懂 JSON」和「这一步是要在生图前确定方向和内容，对吗」。第二个答案是**对的**：`references/user-review.md` 的 Checkpoint 1 就是这个设计，跑图很贵、分镜错了后面全白费。但原来的审阅方式确实不可用——只能让用户看多层嵌套的 JSON 原文。

1. **排版 + 分镜合并为一个审阅产物（`step_layout_preview` + `core/story_script.py`）—— Checkpoint 1 的唯一产物**
   - 用户在生图前打开**一个文件** `layout_preview_<template>.html` 就能确认：
     1. **文字排版效果** —— 标题/章节题/正文/朱砂红高亮/印章/收束段落的成品版式
     2. **每页画面要画什么** —— 占位图正下方列出 `主体/动作/配角/背景/景别/情绪` + 关键词
   - **为什么合并**：v0.3.4 只给排版（看不出画面画什么），v0.3.5 又另开一个分镜脚本文件 —— 等于让用户两边对照，反而增加负担。v0.3.6 合并为一个文件。
   - 实现要点：分镜说明**不能**走 `page_image_urls` 通道 —— 模板会 `_esc()` 把 URL 塞进 `<img src>`，整段 HTML 会被转义成可见文本。正确做法是先渲染占位图版式，再按 `data-page="N"` 注入说明块。
   - 画面速记走「抽取而非翻译」：逐词替换 LLM 自由英文必然产出「雪y / 跪ing」这类中英残骸，比原文更难读。规则是**要么干净中文，要么完整英文**，不产拼接垃圾。

2. **图文对齐诊断（`step_story_script()`）—— 辅助工具**
   - 用户在 preview 里发现某页图文对不上时调它，直接指出缺哪个动作/哪个人物，省去人工比对 800 字 visual 原文
   - 复用 `check_alignment` 的 `caption_missing_actions` / `entities`、`body_missing_*`

3. **分镜体检报告（`step_review_storyboard()` + `core/review_page.py`）—— 辅助工具**
   - 8 项硬约束自动体检，输出 Markdown 审阅卡 + HTML 报告页
   - **定位**：补充检查，**不是** Checkpoint 1 的主角
   - 检查项：正文 100-150 字 / keywords ≥3 / `[GENDER:xx]` / caption 非空 / visual ≥300 字 / 零文字声明 / 多人物构图 / 章节大字唯一

2. **新增真实题材冒烟测试（`scripts/tests/test_live_smoke.py`）**
   - **动机**：v0.3.2 / v0.3.3 的两个真 bug（苏武牧羊分类失败、keywords 被解析层丢弃）**都是只有真跑才现形的**，纯 mock 回归看不见「LLM 是否真的按 schema 输出」「解析层是否接住了」。
   - 默认 **skip**（不烧额度），加 `--live` 才调真 LLM
   - 题材固定用「苏武牧羊」—— 苏武不在人名表里、又无朝代词，是 v0.3.3 兜底层最易回退的用例
   - 断言全部对着踩过的坑：风格 / 模板跟随 / keywords 非空 / GENDER 齐全 / 页数 / 审阅模块能处理真实数据

## v0.3.3 核心变化（2026-09-28，苏武牧羊真实端到端测试暴露的 2 个 bug）

**背景**：v0.3.2 修复后，用「苏武牧羊」跑真实端到端测试（调真 LLM），又暴露 2 个问题。都是**只靠静态审查发现不了、必须真跑才现形**的。

1. **分类器对「名单外人名」失效** — 根因：v0.3.2 的分类器依赖 120+ 人物名表，而名单永远补不完。苏武不在表里、没有朝代词、"牧羊"不匹配古典双人物句式 → 三类信号全落空 → 被误判成 `new_yorker`。
   - 修复：新增 `_looks_like_cn_history()` —— **不依赖人名表**的通用中国历史题材识别，三条命中任一即可：
     1. 史事动作词（牧羊 / 被贬 / 流放 / 卧薪 / 戍边 / 殉国 / 纳谏 …）
     2. 史事语境词（漠北 / 塞外 / 朝廷 / 匈奴 / 朝堂 …）
     3. 古典双人物叙事句式
     排除含拉丁字母/数字 及 `_MODERN_BLOCKLIST` 命中的现代题眼
   - 同时修 `recommend_template` 逻辑漏洞：原"分类器落空 → 回退类型词匹配"会**覆盖**风格派生结果，导致兜底层命中时出现"风格对、模板错"的分裂输出
   - 回归测试补 6 组**名单外用例**（苏武牧羊 / 范仲淹被贬 / 卧薪尝胆 / 负荆请罪 …）防止回退

2. **keywords 在 LLM 解析层被静默丢弃** —— 根因：`planner.py` 构造 `StoryPage` 时漏了 `keywords` 字段。v0.2.9 加 keywords 时只改了 prompt schema 和 dataclass 定义，**忘了同步解析层** —— LLM 按 schema 正常输出了，却在解析时被丢掉。朱砂红高亮整条链路失效。
   - 这是典型的"改了一处没改另一处"漏改：prompt 侧看起来一切正常，只有端到端实跑才暴露。
   - 实测对比（苏武牧羊 10 页）：

     | 指标 | 修复前 | 修复后 |
     |---|---|---|
     | 有 keywords 的页 | 0/10 | **10/10** |
     | body 在 100-150 字 | 2/10 | **9/10** |
     | body 平均字数 | 93 | **114** |

   - 修复：`keywords=p.get("keywords", []) or []` 补进解析层

**验证**：苏武牧羊 10 页实跑 → 风格 `chinese_lianhuanhua_classic` + 模板 `c` 正确，GENDER 标记 10/10，keywords 10/10；3 个测试全绿（26 组分类用例）

## v0.3.2 核心变化（2026-09-28，代码审核修复 7 个 bug）

**背景**：2026-09-28 对 skill 做了一轮全量代码审核（读 run/planner/prompts/image_gen/article/publisher/check_alignment 全模块 + 实测），修掉 7 个 bug。其中 1 个是 P0 功能性 bug，直接让"历史典故第一推荐 chinese_lianhuanhua_classic"在自动推荐路径上完全失效。

1. **【P0】风格/模板推荐对真实题材失效** —— 根因：推荐矩阵的 key 是**主题类型词**（"历史"/"典故"/"国学"），而 `recommend_style()` 拿**真实主题**（"张巡守睢阳"）做 `k in topic` 字面匹配，几乎永远不命中，全部掉进 `new_yorker` 兜底。
   - 实测修复前：张巡守睢阳 / 王昭君出塞 / 岳飞抗金 / 赤壁之战 / 三国演义 / 论语 → 全部误判 `new_yorker` + `e`
   - 修复：改为**加权信号分类器** `_classify_signals()` —— 专有名词表（120+ 历史人物）+ 朝代词（强/弱两档）+ 事件词 + 领域词，三档权重（10/5/1），**长词优先**（"商业模式" 压过 "商业"，"西汉" 压过 "汉"，"王昭君" 压过 "昭君"）
   - 补一层**古典双人物叙事句式识别**：纯中文 + "X与Y" 对举 + 古典叙事词 → 判为连环画（覆盖名单外的历史轶事，如"看石崇与王恺争豪"）；带 `_MODERN_BLOCKLIST` 排除现代商战题眼（"华为与腾讯的竞争" 不再被"争"字误判）
   - 同步补齐 `RECOMMEND_TEMPLATE_MATRIX` 缺失的 **武侠 / 宏大** 两类 key（原先只有风格矩阵有，模板掉进兜底拿到 e）
   - 应用到：`scripts/core/prompts.py` `_SIGNAL_TABLE` + `recommend_style()` + `recommend_template()`

2. **【P1】LLM 调用无 timeout，会无限挂死** —— `OpenAI(...)` 客户端没传 `timeout`/`max_retries`，卡住时对话里表现为"跑着跑着没动静"，无法区分在跑还是在死（实测挂 90s 无输出只能手动 kill）。
   - 修复：`LLM_TIMEOUT = 180.0` + `LLM_MAX_RETRIES = 1`；超时后由 `plan_storyboard` 捕获并降级 mock，不再挂死
   - 应用到：`scripts/core/planner.py`

3. **【P1】`num_pages` 在真 LLM 路径被丢弃** —— `plan_storyboard` 调 `_call_llm_storyboard()` 时漏传 `num_pages`，用户显式指定的页数被静默忽略（只有 mock 路径认）。
   - 修复：补传 `num_pages=num_pages`

4. **【P1】mock 路径忽略 `num_pages`** —— 原 docstring 写"仅作 informational"，实测 `num_pages=6` 只产出 5 页。
   - 修复：按 `target_pages` 补齐/截断（保留开场 + 结尾金句），并重排页码保证连续

5. **【P1】mock 历史风格画出现代科学家** —— `mock_storyboard` 只有 `cn_xuanfeng` 分支，其余风格一律套"戴眼镜现代科学家"，降级后连环画里站着个现代人。
   - 修复：为 `chinese_lianhuanhua_classic` / `guochao_manhua` 补专属锚点

6. **【P1】跑图失败写 0 字节 PNG 占位** —— 0 字节文件仍匹配 `pages/*.png` → 被 `_current_images()` 收进列表 → render 塞进 HTML → publish 上传时被 WeChat 拒掉（但前面 N-1 张已传，素材库留垃圾）。`step_preflight` 只查 >2MB 上限，**拦不住 0 字节**。
   - 修复：失败改为删占位 + 记入 `failed` 列表，最终抛异常暴露（附可重试命令）；`step_preflight` 新增 `image_empty` 检查项
   - 应用到：`scripts/core/image_gen.py` `generate_pages()`、`scripts/run.py` `step_preflight()`

7. **【P2】`step_rewrite_visual` 返回错页** —— `step_gen_images(regenerate_pages=[N])` 返回的是**全部页面**有序列表，原 `return paths[0]` 把 p1 当成"重画 p10 的结果"返回。
   - 修复：按页码匹配返回

**其它清理**：
- `CHARACTER_LOCK_COMPACT` → `CHARACTER_LOCK_COMPACT_LEGACY`，主路径改为从 `storyboard.characters[].visual_signature` 动态派生（原先硬编码郭子仪/药葛罗/仆固怀恩三条，换项目静默失效）
- `config.py` 硬编码 `D:/minimax-agent_cn-project/...` 绝对路径 → 改由 `KNOWLEDGE_COMIC_DEV_ENV` 环境变量驱动
- 删除死代码：`_CHARACTER_STORY_KEYWORDS`、`publisher._post_json_no_ascii_escape`（零引用）

**工程整理**：
- 新增 `scripts/tests/` 收编 3 个正式测试（`test_smoke_v029` / `test_gender_v030` / `test_regression_v032`），全部改为**路径自解析**，任意目录可运行
- 70 个一次性调试脚本（`_v30_*` / `_fix_kc_zhangxun` / `_test_gender*` 等）移入 `_archive/`，**保留可回溯但不再进版本库**
- `.gitignore` 补 `_*_*.py` + `_*.py` + `_archive/`，并显式放行 `scripts/check_alignment.py`（该文件自 v0.2.6 起就被 `run.py` 直接 import，却一直未入库）
- 同步开发源 `src/core/`（5 个文件），消除双份漂移
- SKILL.md 版本号三处对齐（原 frontmatter 0.3.0 / 标题 0.3.0 / 文件结构 0.2.4 三处不一）

**验证**：三个测试从 skill 根目录和 `C:\` 各跑一轮全部通过；`guide.py "张巡守睢阳"` 正确输出 `chinese_lianhuanhua_classic` + `c`

## v0.2.4 核心变化（2026-09-21，戴敦邦派连环画定版）

1. **风格锁定到 5 种**（v0.2 砍到 4，v0.2.4 增到 5）：
   - `new_yorker`（经济学/心理学/严肃）
   - `us_mid_century`（商业模式/品牌/设计）
   - `cn_xuanfeng`（历史典故/国学/东方美学 — 传统水墨写意）
   - `guochao_manhua`（历史典故/中国故事/武侠 — 国潮赛璐璐/古风条漫，《镖人》《一人之下》类现代国漫分镜语言）
   - `chinese_lianhuanhua_classic`（**v0.2.4 新增** · 历史典故/中国故事第一推荐 — 戴敦邦派工笔重彩连环画，刘继卣史诗构图 + 王叔晖线条 + 顾炳鑫/贺友直分镜，宣纸 + 飞白 + 朱砂勾线 + 工笔重彩）
2. **排版锁定到 3 个**：`a`（撕纸手账）、`c`（中国古典故事专版）、`e`（典雅知识风）
3. **工作流：纯对话流**——Mavis 在对话里直接调 `step_plan / step_gen_images / step_render_article / step_publish_draft`，每步用 `ask_user` 让用户拍板
4. **画面质量三重硬约束**（v0.2.3）：
   - **零文字铁律**：禁年份/数字/字母/符号/对话气泡/字幕/招牌字
   - **角色一致性铁律**：5-tuple bible（面 + 眼 + 眉 + 唇 + 发 + 服）逐页一致
   - **视觉概念具象化铁律**：抽象概念转具体可见元素（数据符号 + 隐喻物 + 时间指示器）
5. **七要素铁律**（v0.2.3）——每页 visual 按 SUBJECT / ACTION / CAMERA / PLACEMENT / DEPTH LAYERS / LIGHTING / MOOD 七段结构组织
6. **Prompt 截断保护**（v0.2.4）——拼出 prompt > 9800 字符时自动砍 scene_description

## Mavis 对话工作流（端到端）

```
[1] 用户说"做个知识漫画" → Mavis 问主题 + 要点（≥2 条）
[2] Mavis 用 recommend_style() + recommend_template() 推荐（基于主题关键词）
    + 用 `planner.recommend_pages(len(bullets))` 推荐页数（≤3 bullets=8 / 4-6=10 / ≥7=12）
[3] Mavis 用 ask_user 让用户拍板风格 + 模板 + 页数
[4] step_plan(topic, bullets, style_id, template_id, num_pages=None)
    num_pages 默认 None = 按 bullets 数量自动推荐（8/10/12）。用户可显式传 6-15 覆盖。
    → 拿到 (storyboard, job_id, work_dir)
[5] ★ step_layout_preview(job_id) → html_path ★【生图前审阅 · 唯一产物】
    一个文件同时展示：成品排版 + 每页分镜意图(主体/动作/配角/背景/景别/情绪 + 关键词)
    → Mavis 用 deliver-assets 送 html（或 Browser 打开）+ 报摘要
    → Mavis 用 ask_user 让用户拍板（图文相符 → 生图 / 换模板 / 改文案 / 重跑分镜）
    (可选) step_layout_preview(job_id, compare_templates=["c","e"]) 多模板对比
    (可选) 用户发现某页图文不符 → step_story_script(job_id) 出对齐诊断
    (可选) review.set_page_field(job_id, page, field, value) 改字段后重看预览
[6] step_gen_images(job_id)
    → 拿到 [Path, ...] PNG 列表
    → Mavis 用 deliver-assets 展示给用户
[7] ★ 必附"分镜意图 vs 实际画面"对照表 ★ → ask_user 让用户拍板（接受 / 重画某些页）
    (可选) step_gen_images(job_id, regenerate_pages=[N, ...]) 只重画指定页
[8] step_render_article(job_id)  # template_id=None 自动用 recommended_template
    → 拿到 html_path
[9] Mavis 用 read tool 读 HTML 预览 → ask_user 让用户拍板（接受发草稿 / 改模板 / 拒绝）
[10] step_publish_draft(job_id)  # template_id=None 自动用 recommended_template
    → 拿到 draft_media_id
    → Mavis 报告 draft_media_id + 公众号后台链接
```

**关键：每个 step 都要用户拍板才进下一步**，Mavis 不能全自动跑完。

## 锁定的 5 风格

| ID | 中文名 | 类别 | 适合 | 视觉特征 |
|---|---|---|---|---|
| **new_yorker** | 纽约客式 · 报刊讽刺 | 黑白 Risograph | **经济学 / 心理学 / 严肃 / 成人** | 米色纸 + 平面色块 + 细线条 + 网点 |
| **us_mid_century** | 美式中世纪 · 复古杂志 | 50-60s 杂志 | **商业模式 / 品牌 / 设计 / 生活美学** | mustard + teal + 砖红 + 平面色块 + 几何构图 |
| **cn_xuanfeng** | 宣风 · 国风写意 | 中国水墨 | **历史典故 / 国学 / 古籍解读 / 东方美学** | 飞白 + 朱砂 + 宣纸 + 大胆笔触 + 留白 |
| **guochao_manhua** | 国潮古风条漫 | 国潮赛璐璐 + 古装 + 现代条漫分镜 | **历史典故 / 中国故事 / 武侠 / 江湖** | 朱砂 + 鸦青 + 玉绿 + 金 + 月白 + 赛璐璐平涂 + 现代 1:2 头身比 |
| **chinese_lianhuanhua_classic** | **中国古典连环画（戴敦邦派体裁 + 中性脸 v0.3.0 + 性别分支）** ★ 历史典故第一推荐 | 工笔重彩 + 白描红线 + 水墨淡彩连环画派 | **历史典故 / 古典小说插图 / 圣贤帝王 / 江湖侠义** | 宣纸 + 毛笔 + 工笔 + 白描 + 飞白 + 朱砂勾线 + 工笔重彩（朱砂/靛青/赭石/墨/留白）+ **中性脸 v0.3.0**（FACE 子块：鹅蛋脸/精致五官/自然肤色）+ **性别分支按 [GENDER:xx] 自动选妆发**：女性 = 桃花腮 + 花钿 + 步摇簪花 + 柳叶眉 + 樱桃小口；男性 = 玉冠/幞头/束发 + 直眉/剑眉 + 无桃花腮 + 玉簪/金簪 + 朝代配饰 + 短须或无须。**planner 必须每页 visual 第二行写 [GENDER:male\|female\|mixed] tag**。要纯古典戴敦邦派脸可显式传 `character_anchor=CHARACTER_CN_LIANHUANHUA_ANCESTOR` 覆盖。 |

**历史典故类第一推荐：`chinese_lianhuanhua_classic`**（2026-09-21 校准，戴敦邦派连环画 + 2026-09-23 校准，现代审美脸）。备选按顺序：`guochao_manhua`（现代国潮条漫）→ `cn_xuanfeng`（传统水墨写意）。
**已砍掉 5 个风格**（kid_picture_book / kid_science_diagram / cn_contemporary / jp_kawaii_warm / jp_terada）—— 砍掉是为了每个风格打磨到位。

## 锁定的 3 模板

| ID | 中文名 | 配色 | 适合 |
|---|---|---|---|
| **a** | 撕纸手账风 | 黄便签 + 胶带 + 手写体 | 情感/旅行/通用兜底 |
| **c** | 中国古典故事专版 | 米色羊皮纸 + **朱砂红** + 印章 | 历史典故/古文/国学 |
| **e** | 典雅知识风 | 米色羊皮纸 + **深蓝灰** + 印章 | 知识/科普/商业/严肃 |

## 风格 + 模板配对推荐

| 主题类型 | 风格 | 模板 |
|---|---|---|
| **历史典故 / 国学 / 古籍解读** | **chinese_lianhuanhua_classic**（戴敦邦派，第一推荐）/ guochao_manhua / cn_xuanfeng | **c（朱砂红 + 印章）** |
| **武侠 / 江湖 / 侠义** | **chinese_lianhuanhua_classic** / guochao_manhua | **c（朱砂红 + 印章）** |
| **宏大 / 史诗 / 战争 / 重大事件** | **chinese_lianhuanhua_classic** / new_yorker / guochao_manhua | **c** 或 **e** |
| **文学 / 人物 / 哲学 / 文化** | chinese_lianhuanhua_classic / guochao_manhua / cn_xuanfeng | **c** |
| **经济学知识 / 心理学 / 严肃** | new_yorker | **e（深蓝灰）** |
| **商业模式 / 品牌 / 设计** | us_mid_century | **e（深蓝灰）** |
| **AI / 算法 / 工程 / 科技 / 互联网** | new_yorker / us_mid_century | **e** |
| **科学 / 物理 / 化学 / 生物 / 医学** | new_yorker / us_mid_century | **e** |
| **通用兜底 / 情感 / 旅行** | new_yorker / us_mid_century / chinese_lianhuanhua_classic | a |

## 4 个 step API（Python 直接 import 调）

```python
from scripts.run import (
    step_plan,              # → (storyboard, job_id, work_dir)
    step_gen_images,        # → [Path, ...] PNG（regenerate_pages=[N,...] 单页重跑）
    step_render_article,    # → html_path（template_id=None 自动用 storyboard 推荐）
    step_publish_draft,     # → {"draft_media_id": ..., ...}（template_id=None 自动用推荐）
    step_preflight_images,  # v0.3.15 生图前体检（不跑图）
    step_visual_qa,         # v0.3.16 跑图后视觉审核（不跑图）
    step_story_script,      # v0.3.5 分镜要素抽取
    step_layout_preview,    # v0.3.5 排版+分镜审阅页
)

sb, job_id, work_dir = step_plan(
    topic="峰终定律",
    bullets=["1993 年卡尼曼实验", "峰 = 最高点 终 = 结束感", "持续时间被忽略"],
    style_id="new_yorker",     # 可选,默认自动推荐
    template_id="e",           # 可选,默认自动推荐
    num_pages=10,              # 可选,默认按 bullets 数量自动推荐 (≤3=8 / 4-6=10 / ≥7=12)
    characters=[               # v0.2.5 人物故事必填（其它类型 None）
        # {"name": "卡尼曼", "role": "心理学家",
        #  "visual_signature": "70 岁学者, 圆框眼镜, 短发, 灰色西装, 白衬衫, 沉静表情"}
    ],
)

image_paths = step_gen_images(job_id)  # 全跑。v0.2.5: 如果 step_plan 传了 characters，会先跑角色 4 视图参考图 + 用 i2i 跑每页
# 或：image_paths = step_gen_images(job_id, regenerate_pages=[10, 11])  # 只重画
# 或：image_paths = step_gen_images(job_id, auto_char_refs=False)  # 跳过角色参考（用纯 t2i 跑）
# v0.3.15/16：step_gen_images 前后各有一道自动关卡
#   前：preflight 体检，有阻塞项直接 SystemExit(1)，一张图不跑
#   后：visual_qa 视觉审核，只打印报告不阻塞
# 开关：skip_preflight=True（逃生阀）/ auto_visual_qa=False（关掉后审）

html_path = step_render_article(job_id)  # template_id=None 自动用 storyboard.json 里 recommended_template

result = step_publish_draft(job_id)  # template_id=None 自动用推荐
# result = {"draft_media_id": "...", "uploaded_count": N, "title": "...", "work_dir": "..."}
```

## CLI 兼容入口（cron / CI 场景）

```bash
# 一键跑完整链路
python scripts/run.py all "峰终定律" -b "1993 年卡尼曼实验" -b "峰终概念" -b "应用启示" -s new_yorker -t e

# 单步
python scripts/run.py plan "峰终定律" -b "..." -s new_yorker -t e
python scripts/run.py gen --job-id kc_xxx
python scripts/run.py render --job-id kc_xxx
python scripts/run.py publish --job-id kc_xxx
```

## 核心原则（不可破坏）

### 1. 用户主导（User-in-the-loop）

**每一篇知识漫画的核心创作决策,用户必须亲自介入**。
- 风格 + 模板拍板 → Mavis 用 `ask_user`
- 分镜审阅 → Mavis 用 `read tool` 读 `work_dir/storyboard.json` 展示 + `ask_user` 拍板
- 图片审阅 → Mavis 用 `deliver-assets` 展示 PNG + **必附"分镜意图 vs 实际画面"对照表** + `ask_user` 拍板
- HTML 预览拍板 → Mavis 用 `read tool` 读 HTML + `ask_user` 拍板

**不能跳过介入**：Mavis 不能全自动跑完发草稿。自动化是减少体力劳动,不是替代用户审美。

### 2. 图文分离铁律

- 对话/旁白/标题/正文 → 进 HTML 文章层
- image 里严禁出现文字（年份/数字/字母/符号/对话气泡/字幕/招牌字）

### 3. 角色一致性铁律（v0.2.3 五件套）

跨页角色描述必须完全一致。三个角色锚点（按风格自动选）：
- 现代/科学家 → `a small scientist figure with short black hair, round wire-frame glasses, light grey sweater, dark trousers, neutral expression, age 30`
- 国潮/古代 → `Character bible (FIVE ANCHORS): oval face + sharp jawline + 大眼双睑 sharp winged eyeliner + swordsman brows + cupid's bow lips + 高髻 + cloth ribbon + Han-Chinese historical hanfu`
- 戴敦邦派（chinese_lianhuanhua_classic）→ `Dai Dunbang-style: square jaw + phoenix-eye 丹凤眼 / triangular-eye 三角眼 + sword-brow 剑眉 + 朝代蓄须 + 朝代高髻/幞头/乌纱`

### 4. 七要素结构铁律（v0.2.3）

每页 visual 必须按 7 段组织：

| # | 段名 | 必填内容 |
|---|---|---|
| 1 | SUBJECT | 主角 + 陪伴角色 + 物件（名词短语列举） |
| 2 | ACTION | 反应动词（yanking / slashing / biting），禁用静态"stands/looks" |
| 3 | CAMERA | shot size + angle + lens + DoF 四件套 |
| 4 | PLACEMENT | 主体在画面位置（rule of thirds / asymmetric） |
| 5 | DEPTH LAYERS | foreground / midground / background 三层显式 |
| 6 | LIGHTING | 光源 + 方向 + 色温 + 质感 |
| 7 | MOOD/PALETTE | 情绪基调 + 配色 |

### 5. 视觉概念具象化铁律

抽象概念必须转成**具体可见的视觉元素**：
- ❌ "showing the concept of attention" → 太空
- ✅ "three glowing dots floating in air, connected by golden threads to the character" → 视觉可读

### 6. AI 出图现代写实锚点防范 (v0.2.4)

**症状**：做"国画 / 工笔 / 水墨 / 连环画 / 古风条漫"等非写实风格图时，凡 prompt 里出现 candle / lantern / desk / porcelain rest / modern Chinese minimalism / cinematic studio lighting 等"现代写实"物件词，模型自动走"现代写实油画 / 3D 渲染 / 摄影"风。

**修复**：
1. 把"painted illustration"声明放 SUBJECT 第一句：`CRITICAL — The entire frame is rendered as a classical Chinese lianhuanhua painted illustration, NOT a photograph, NOT a 3D render...`
2. 把人物描述成 `brush-painted figure on rice paper, NOT a photorealistic person`
3. 在视觉描述里**避免** candle / lantern / desk / porcelain rest / modern Chinese minimalism / cinematic studio lighting 等词
4. 把"volumetric light"改成"painted warm wash"

**踩坑验证**：张巡守睢阳 v0.2.4 chinese_lianhuanhua_classic 风格 — p1-p9（战场 / 粮仓 / 城墙）自动到位，p10-p11（书房 + 学者）反复跑偏现代写实风，重写 visual 加 v2 fix 后到位。

### 7. 公众号 IP 白名单 + 编码

- 第一次跑前提示用户加公网 IP 到 mp.weixin.qq.com → IP 白名单（errcode 40164）
- `requests.post` 必须 `ensure_ascii=False`，否则中文变 `\uXXXX` 字面量

### 8. 文风铁律（v0.3.18 定版 · 文字内容的硬约束）

> 这一节是 Mavis 审阅 layout_preview 时**必查**的。完整版 + 改写对照表见
> `references/style_guide.md` §2.5。

**8.1 术语翻译（看不懂的唯一根因）**

- 任何术语首次出现，必须 `术语（大白话解释）` 或 `术语，意思就是……`
- **一页最多 1 个术语**需要解释 —— 密度上限 = 1
- 解释用**读者生活里的类比**，不是同义替换
- 专有名词免解释：人名 / 地名 / 朝代 / 事件名 / 官职
- 禁用裸术语：上兵 / 伐谋 / 伐交 / 庙算 / 奇正 / 势 / 全胜 / 釜底抽薪 / 合纵连横 / 欲擒故纵 / 以全争于天下 / 兵家极意 / 存乎一心 …

**8.2 正文三拍结构（100-150 字）**

| 拍 | 字数 | 职责 |
|---|---|---|
| 讲事 | 40-50 字 | 这一页发生了什么（时间/地点/人物/动作） |
| **说破** | **40-60 字** | 把"**为什么**"用人话说出来 —— **最容易丢、最关键** |
| 落点 | 20-30 字 | 一句判断，**不重复画面** |

**8.3 白话 / 文言严格分层（三者不可混用）**

| 字段 | 语体 | 位置 |
|---|---|---|
| `body` | **现代白话（信达雅）** | 图下正文 |
| `dialogue` | **文言原文，逐字出原著** | 叠在图片下缘蒙版 |
| `punchline` | **白话金句** 10-22 字 | 「定格瞬间」卡 |

**8.4 分寸禁写**

- ❌ hedging：「（或…）」「（实际为…）」「（一说…）」 → preflight **阻塞**
- ❌ 现代口水词：极限测试 / 活体武器 / 情绪价值 / 内卷 / 破防 / 降维打击 → warn
- ❌ 复述画面已表达的内容 —— 图为主、文字为脚注
- ❌ 元叙事：「远川研究所式的视角告诉我们」—— 直接写内容，不点名引用源
- ❌ 说教：「总而言之 / 综上所述 / 我们应该…」

**8.5 排版（v0.3.8 定版）**

正文**一句一段、无首行缩进**，段边界由段间距标明。
排版层自动实现（`article._split_paragraphs()`，引号感知切分），Mavis 不需要手动干预。

## 文件结构

```
knowledge-comic/
├── SKILL.md                  ← 你正在读的（v0.3.24）
├── references/
│   ├── handraw_styles.md     ← 5 个锁定风格完整定义 + 推荐矩阵
│   ├── templates.md          ← 3 个排版模板详情 + v0.3.8 排版铁律
│   ├── user-review.md        ← Mavis 对话流 + 分镜意图 vs 实际画面对照表模板
│   ├── workflow.md           ← 端到端流程图 + 调试指南
│   └── style_guide.md        ← 作者风格 + **文风铁律 §2.5**（术语翻译 / 三拍结构 / 白话文言分层）
├── scripts/
│   ├── run.py                ← 主入口：step_* API + CLI 兼容
│   ├── run_tests.py          ← **v0.3.24** 一次跑完全部测试（唯一入口，见下）
│   ├── check_drift.py        ← **v0.3.24** 真源 ↔ dev 镜像一致性校验（--sync 可同步）
│   ├── canon.py              ← 一致性约束注入（v0.3.24 起已接入 run.py）
│   ├── check_alignment.py    ← 视觉文字对齐审查（step_gen_images 自动跑）
│   ├── image_review.py       ← 图片 rerender 标记工具
│   ├── publish_existing.py   ← 重发草稿（图片复用）
│   ├── tests/                ← 正式测试（全部不烧 API 额度；用 run_tests.py 跑）
│   │   ├── test_smoke_v029.py         ← v0.2.9 默认值 + keywords 字段
│   │   ├── test_gender_v030.py        ← v0.3.0 性别分支 8 项
│   │   ├── test_regression_v032.py    ← v0.3.2 修复回归 22 项
│   │   ├── test_preflight_v0315.py    ← v0.3.15 preflight 93 项
│   │   ├── test_visual_qa_v0315.py     ← v0.3.15 visual_qa 41 项
│   │   ├── test_v0322.py              ← v0.3.22 四项不可降级约束
│   │   ├── test_prompt_v0324.py       ← **v0.3.24** prompt 瘦身 + JSON 示例合法性
│   │   ├── test_thresholds_v0324.py   ← **v0.3.24** 检查层阈值不漂移
│   │   └── test_live_smoke.py         ← 真 LLM 冒烟（默认 skip，`--live` 才跑）
│   └── core/                 ← 核心模块（planner/image_gen/article/publisher/prompts/config/
│                               preflight/visual_qa/review_page/story_script/thresholds）
├── _archive/                 ← 一次性调试脚本归档（v0.3.24 起 diagnose_*.py 也在此）
├── data/                     ← 生成的图 + 中间产物（git ignore）
│   └── canon.md              ← 一致性约束（v0.3.24 起为**空模板**，不注入任何内容）
├── .env.example
└── README.md
```

## v0.3.24 三条自检命令（改完必跑）

```bash
# 1) 全量测试（8 个文件一条命令；原来 pytest 会 INTERNALERROR 退出码 3）
python scripts/run_tests.py

# 2) 真源 ↔ dev 镜像一致性（改完 core/*.py 后跑；有漂移退出码 1）
python scripts/check_drift.py
python scripts/check_drift.py --sync    # 同步到 D 盘镜像并复校

# 3) Lint（v0.3.24 从 62 条清到 0；配置见 ruff.toml）
ruff check scripts/
```

**为什么测试要用 `run_tests.py` 而不是 pytest**：`scripts/tests/test_*.py` 是 standalone
脚本（顶层 `assert` + 结尾 `sys.exit(0)`），pytest 收集时撞上 `SystemExit` 会
INTERNALERROR 整个 session 崩掉。`run_tests.py` 用子进程逐个跑并汇总，
不改动已验证的断言。

## 关键 pitfall

| 坑 | 怎么避 |
|---|---|
| 公众号乱码 `\u4e00` | `requests.post` 必须 `ensure_ascii=False`（`publisher.py` 已封装） |
| 图里出现中文/年份/数字 | `prompts.py:ZERO_TEXT_BOOST` 强制 "NO text/numbers/digits/letters" + planner system prompt 严禁具体年份 |
| 角色"换人" | planner system prompt 强制同款角色锚点（5-tuple bible） |
| 大头贴（人物面部占满画面） | 七要素铁律强制 SUBJECT + CAMERA/PLACEMENT + DEPTH LAYERS + 角色面部 < 1/3 画面 |
| 风格跑偏到现代写实 | v0.2.4 §6 现代写实锚点防范（"painted illustration"声明放 SUBJECT 第一句） |
| 书房+学者+灯具 = 3D 写实 | 砍掉 "candle/lantern/desk/porcelain" + 加 "brush-painted figure" 描述 |
| Agnes 队列 503 | `core/image_gen.py` 自动 retry with 退避 |
| Agnes prompt > 10000 字符失败 | `build_image_prompt` > 9800 自动砍 scene_description |
| WeChat IP 白名单 | 第一次跑前提示用户加白名单；errcode 40164 报错时明确指出 |
| LLM 没配置 | `core/planner.py` 自动 fallback 到 mock storyboard（角色一致版） |
| **Mavis 对话接不到 subprocess stdin** | v0.2 已重构：去掉所有 `subprocess.run([sys.executable, review.py])`，Mavis 直接调 step API |
| `recommended_template` 字段丢失 | v0.2.4 修复：`Storyboard.recommended_template` 字段 + `to_dict()` 返回 + `_load_storyboard` 读 |

## v0.2.6 核心变化（2026-09-22，视觉文字对齐 + 风格/人物一致性再加固）

1. **视觉文字对齐审查自动跑**（v0.2.5 漏的：planner visual 写"单骑闯营"但图里两人都在马上）
   - 新增 `scripts/check_alignment.py`：检查 caption + body 里的关键人物 / 动作是否在 visual 描述里被提及
   - `step_gen_images` 跑完自动调，HIGH/MEDIUM 风险页打印到日志
   - Mavis 必读审查输出，复审对应页

2. **build_image_prompt 自动剥 cinematic 词**（v0.2.5 漏的：planner LLM 在 visual 里写 "Wide shot (35mm, low angle, deep focus)"）
   - 中国画风格时自动 strip + 替换（wide shot → Expansive composition）
   - 未来跑 chinese_lianhuanhua_classic / cn_xuanfeng / guochao_manhua **永远**不会被 cinematic 镜头术语覆盖

3. **step_plan 自动检测人物故事 + 强制 i2i**（v0.2.5 漏的：用户没传 characters 时 planner LLM 可能漏提取）
   - `_is_character_story()` 启发式检测 topic（已知历史人物名 + 典故/故事/生平关键词）
   - 检测到人物故事但 LLM 没提取 characters → 打印 WARNING
   - 未来 run 时只会出现 2 种结果：i2i 启用 + warning

## v0.2.5 核心变化（2026-09-22，中国画风格分流 + 人物一致性 i2i）

1. **中国画风格分流到专属 booster**（根上解决"风格跑偏到现代写实"）
   - `chinese_lianhuanhua_classic` / `cn_xuanfeng` / `guochao_manhua` 三个中国画风格自动用 `CHINESE_PAINTING_BOOST`（散点透视/留白/平面色块/白描+朱砂勾线），跳过 `CAMERA_LANGUAGE_KIT` + `DEPTH_LAYERS_BOOST` + `CINEMATIC_FRAMEWORK_BOOST` 三套西方镜头语言 booster
   - prompt 头部加 `STRICT STYLE` 强约束（painted illustration on rice paper）
   - 影响：未来跑这 3 个风格不会再被 cinematic 拉偏到油画/电影截图/3D 渲染

2. **人物故事 i2i 接入**（根上解决"角色换脸"）
   - 借鉴 baoyu-comic v3.0 模式：planner 提取 characters → 自动跑 4 视图参考图（front/3-4/side/back）→ 每页 i2i 跑
   - Agnes i2i API: `agnes-image-2.0-flash` + `tags=["img2img"]` + `extra_body.image` (data: URI)
   - Agnes 硬限制：最多 6 张 input images → 自动按 front > 3-4 > side > back 优先级截断
   - 用户怎么用：`step_plan(..., characters=[{name, role, visual_signature}, ...])` 或不传（planner LLM 自动提取）

3. **代码改动文件**
   - `scripts/core/prompts.py`：新增 `CHINESE_PAINTING_BOOST` + `CHINESE_STYLE_PREFIX` + `TRADITIONAL_CN_STYLES` + `build_image_prompt` 分流
   - `scripts/core/image_gen.py`：重写 `_call_agnes` 支持 i2i，新增 `generate_character_references()`，`generate_pages` 接受 character_refs
   - `scripts/core/planner.py`：`Storyboard.characters` 字段 + LLM 输出格式加 `characters` 数组
   - `scripts/run.py`：`step_plan` 接受 `characters`，`step_gen_images` 默认 `auto_char_refs=True` 跑角色图 + i2i

## v0.2.9 核心变化（2026-09-23，正文精简 + 关键词高亮 + 多人物连环画 + 现代审美脸默认）

用户多次反馈后沉淀的默认约定（未来直接实现，不需用户重复调整）：

1. **正文长度：100-150 字/页硬上限**
   - 之前：planner 写 ≥80 字 → 实际输出 200-300 字/页（用户嫌"文字太重"）
   - 现在：planner system prompt 严格"100-150 字" + 强调"图为主、文字为脚注，只补画面没说的事"
   - 应用到 `scripts/core/planner.py` 第 4 铁律 + JSON schema

2. **关键词朱砂红高亮（per-page keywords）**
   - 之前：`_HIGHLIGHT_KEYWORDS` 全局列表硬编码（张巡守睢阳人名），其它项目高亮不到
   - 现在：`StoryPage.keywords: list[str]` 字段（每页 5-8 个），c 模板自动渲染 `<span style="color:#9b2332;font-weight:600;">{kw}</span>`
   - 改名：`CHARACTER_CN_LIANHUANHUA_ANCESTOR`（古典戴敦邦脸）保留；要纯古典脸可显式传 `character_anchor=CHARACTER_CN_LIANHUANHUA_ANCESTOR` 覆盖
   - 应用到：`scripts/core/planner.py` StoryPage 字段 + JSON schema、`scripts/core/article.py::_highlight_keywords` 接 `extra_keywords` 参数、`scripts/core/prompts.py` 新增 `CHARACTER_CN_LIANHUANHUA_MODERN` 默认锚点

3. **连环画多人物铁律**
   - 之前：planner 写"1 主角 + 1-2 次要人物"，模型跑出"主角 + 琵琶乐师 + 匈奴人"等套话场景
   - 现在：连环画风格默认每页 **3+ 主人物 + 2-3 远景配角 + 多道具 + 满画幅构图**（戴敦邦/顾炳鑫/贺友直派）
   - 应用到：`scripts/core/planner.py` 新增"连环画多人物铁律"段落

4. **chinese_lianhuanhua_classic 默认 = 戴敦邦体裁 + 现代审美脸**
   - 之前：默认是 `CHARACTER_CN_LIANHUANHUA_ANCESTOR`（方颌丹凤眼剑眉朝代蓄须）→ 太古典
   - 现在：默认是 `CHARACTER_CN_LIANHUANHUA_MODERN`（桃花腮 + 花钿 + 步摇簪花 + 柳叶眉 + 樱桃小口）→ 现代读者也能欣赏的古典美人
   - 应用到：`scripts/core/prompts.py` `CHARACTER_ANCHORS["chinese_lianhuanhua_classic"]`

## v0.3.0 核心变化（2026-09-24，性别分支 + 角色一致性 + 画面 caption 匹配 + 零文字强化）

**根因**：用户连续 3 次反馈"男主角被画成女子 + 画面和文字不符 + 摄像机偏少连环画要求" → 已知用户反复要求,**未来不会再出别的漫画时搞错**。

1. **性别分支（chinese_lianhuanhua_classic 专用）—— 防止男主角被性转成女子脸**
   - **根因**：v0.2.9 默认 anchor 是为女性主角优化的（桃花腮+花钿+步摇+柳叶眉+樱桃小口）。当主题是男性主角（张巡/郭子仪/文天祥），planner visual 写"Zhang Xun, 40+ male general"，anchor 强制女性化 → 模型脸部女性化 + 服饰中性 → 完全性转成女子。
   - **修复**：拆 anchor 为三部分：
     - `CHARACTER_CN_LIANHUANHUA_FACE` — 中性脸部特征（任何性别共用）
     - `CHARACTER_CN_LIANHUANHUA_GENDER_FEMALE` — 女性妆发分支（桃花腮+花钿+步摇+柳叶眉+樱桃小口）
     - `CHARACTER_CN_LIANHUANHUA_GENDER_MALE` — 男性妆发分支（玉冠/幞头/束发 + 直眉/剑眉 + 无桃花腮 + 玉簪/金簪 + 朝代配饰 + 短须或无须）
   - **planner 强制**：每页 visual 第二行必须写 `[GENDER:male|female|mixed]` tag
   - **`build_image_prompt(gender="auto")`** 自动从 `[GENDER:xx]` tag / 中文代词 / 英文代词 / 已知中国名字（Zhang Xun, Wang Zhaojun 等）检测 → 拼装对应 gender 子块
   - `CHARACTER_CN_LIANHUANHUA_ANCESTOR` 古典戴敦邦脸保留（要纯古典脸可显式传 `character_anchor=CHARACTER_CN_LIANHUANHUA_ANCESTOR` 覆盖）
   - 应用到：`scripts/core/prompts.py` 拆 anchor + `_resolve_cn_lianhuanhua_anchor()` helper + `build_image_prompt(gender=)` + `image_gen.generate_one(gender=)` + `planner.py` 性别标记铁律段

2. **角色视觉签名锁定铁律**（v0.3.0 新增）
   - **根因**：planner LLM 早期不写 [GENDER:xx] + anchor 默认女性化 → 男主角跨页被性转（p4/p6/p7/p8 张巡在不同页面分别是"白色道袍女子脸"+"明显女子"+"白色道袍女子脸"+"白色道袍女子脸"，与刚重画的 p3/p5/p9/p10 "棕色官员袍 + 蓄短须男性"不一致），读者会认为是"换了人"或"穿越了"。
   - **铁律**：同一主角在**所有页面**的核心视觉签名（服饰+面部+身体）必须保持一致。
   - 应用到：`scripts/core/planner.py` 新增"角色视觉签名锁定铁律"段

3. **画面与 caption 严格匹配铁律**（v0.3.0 新增）
   - **根因**：planner LLM 默认忽略 caption 内容直接套场景模板 → 视觉与文字脱节（caption"砍断一根指头"画面只放桌上没动作；caption"36 将尽死"画面只 2 人对峙；caption"城破火光"画面是单人大留白）。
   - **铁律**：每页 visual 的 ACTION 段必须严格包含 caption 中的核心动作/事件的具象对应物。
   - 应用到：`scripts/core/planner.py` 新增"画面与 caption 严格匹配铁律"段

4. **零文字铁律强化**（v0.3.0 升级）
   - **根因**：每次重画都发现画面会出现"可读字符"——袍上花纹被读成篆字、地图被画上汉字、玉佩上刻字。模型默认会给"中国风装饰"加字符。
   - **强化**：每页 visual 末尾必须明确写 `STRICT NO TEXT — plain fabric robes with NO characters/symbols/inscriptions, map shows ONLY abstract terrain WITHOUT any writing, armor is PLAIN unadorned, no characters on blade.`
   - 应用到：`scripts/core/planner.py` 强化"零文字铁律"段

5. **代码改动文件**
   - `scripts/core/prompts.py`：拆 `CHARACTER_CN_LIANHUANHUA_FACE` / `_GENDER_FEMALE` / `_GENDER_MALE`，加 `_resolve_cn_lianhuanhua_anchor()`，改 `build_image_prompt(gender=)`
   - `scripts/core/image_gen.py`：`generate_one(gender=)` 传给 `build_image_prompt`
   - `scripts/core/planner.py`：加 [GENDER:xx] 标记铁律 + 角色视觉签名锁定铁律 + 画面 caption 匹配铁律 + 零文字铁律强化
   - `scripts/_smoke_v03.py`：8 项验证测试（中性别分支 + 自动检测 + mixed 处理）

## 变更记录

- **0.3.25**（2026-10-08）：live 验证抓出的静默降级。① **【真故障】** LLM 返回**合法 JSON**（`finish_reason=stop`、括号闭合、16K 字符、`json.loads` 直解成功）却被旧解析层判「non-JSON」—— 根因是旧实现**手写大括号计数、不认字符串字面量**，visual/正文里一个不平衡的 `{`/`}` 或 JSON 尾部多余文字都会整段失败；`temperature=0.7` 所以是偶发的，看起来像"跑通了"。改用 stdlib `JSONDecoder.raw_decode` + 4 层尝试，报错带尝试记录与 `finish_reason`。② **【更严重】** 解析失败会**静默降级**到 mock，而 mock 没有 `keywords`/`[GENDER]`，等于把朱砂高亮与性别锚点整条链路废掉，拖到审阅阶段才炸 30 个 error。现在拆成两类：没配 key = 合法离线模式照旧降级；配了 key 但调用/解析失败 = **默认当场抛错**，`allow_mock_fallback=True` 才降级（已透传到 `step_plan`）。③ 修 v0.3.24 重编号后遗留的 8 处过期「铁律 N」交叉引用。④ 新增 `test_json_extract_v0324.py`（24 项）、`test_fallback_v0324.py`（11 项）、`test_drift_v0324.py`。测试 11/11，lint 0
- **0.3.24**（2026-10-08）：可观察性 + 结构性瘦身。① **【阻塞级】** planner prompt 里的"严格 JSON"示例本身非法（`{"enum": [...]}` 教 LLM 输出嵌套对象 → `CHAR_GENDER_MISSING` 阻塞 → 一张图不跑；`characters` 是两段对象拼接；`sources` 未转义引号），且 v0.3.22 的测试把这个 bug 锁成了规范，已一并改写；② 跑图接 `progress_cb`（`image_gen` 早有该形参，`run.py` 两处都没传，3-6 分钟零输出），角色参考图同步补齐；③ 新增 `run_tests.py`（`pytest scripts/tests` 是 INTERNALERROR rc=3，standalone 脚本只能手敲）；④ 新增 `core/thresholds.py` 单一真源，收敛 6 处已实证漂移（body 150 warn vs error、keywords<3 preflight 漏检、punchline 实按 30 但文案写 22…）；⑤ system prompt 22,064 → 14,578（历史）/ 13,297（非历史），朝代速查表改按风格条件注入；⑥ canon 约束在主流程一直是死的（只有 `run_plain.py` 调），接线前先把黑死病专属数据的 `data/canon.md` 存为 `canon.blackdeath.md`、主文件换空模板；⑦ 新增 `check_drift.py` 自动化真源↔镜像校验（实测镜像已漂移 6 处）；⑧ lint 从 62 条清到 0（新增 `ruff.toml`），修 F601 重复 dict key，归档 3 个脚本
- **0.3.23**（2026-09-30）：两个可移植性 bug —— ① Windows GBK 崩溃：报告标记 🔴/🟡 改纯文本 `[阻塞]`/`[建议]` + `run.py` 加 `_safe_stdout()` 安全网（**只在阻塞分支触发，体检通过时不崩，所以极易漏测**；Mavis 里因宿主重定向 stdout 测不出来）；② `玉璧` 假阳性：从 `ANACHRONIC_MARKERS` 移除（玉璧是春秋战国正统礼器，蔺相如完璧归赵即战国故事），原事故真正穿帮的是「金质发冠 + 繁复华丽丝绸」；③ 附带修 `test_preflight_v0315.py:271` 编码损坏字符（GBK 下 print 抛异常 → 逻辑全过但 rc=1）
- **0.3.22**（2026-09-29）：性别锚点工程化收尾 —— JSON schema `gender` 改 `enum:["male","female"]`；`KNOWN_GENDER` 兜底表**停止兜底**（`CHAR_GENDER_MISSING` 转阻塞，planner 必须自己填）；MUST-SHOW fallback 复用 `_assemble` 不再 `assembled[:9790]` 硬切（否则砍掉 ZERO_TEXT_BOOST）；连环画强锚不再锚现代室内物；`preflight` / `visual_qa` 落盘 JSON 报告（`data/<job>/preflight_report.json` / `visual_qa_report.json`）
- **0.3.21**（2026-09-30）：prompt 拼装唯一化 —— 原先主路径和超限截断路径有**两份几乎相同的拼装代码**，改一处漏另一处；统一为 `_assemble()`
- **0.3.20**（2026-09-29）：性别解析收敛为单一真源 `resolve_gender()`，page 级和 char 级都走它；原默认 `female` 改掉（男性主题被默认成女性）；preflight 修两个真实缺陷
- **0.3.19**（2026-09-29）：角色签名指纹 —— `visual_signature` 变了必须重画 4 视图参考图，不复用旧的
- **0.3.18**（2026-09-30）：图文关联专项 —— planner 加「术语翻译成人话」铁律 + 正文三拍结构（讲事/说破/落点）+ `CONCEPT:` 段（画概念不画场景）；`prompts.py` 把 MUST-SHOW 块提到最终 prompt **第 6 字符**（原第 4703/9700 ≈ 48%，模型高权重区拿不到概念）；`check_alignment` 加 `check_concept()`；模板 c 段数上限 `max_paras=3` + 均衡合并（`max_len` 只管单句超长，4 个 20-50 字短句会原样切 4 段）+ 去掉史料脚注逐字插空格（`" ".join(src)` 把《孙子兵法》渲染成《 孙 子 兵 法 》，无法检索/复制）；`preflight` 黑名单补 `concept`/`headwear`/`negative`/`avoid`/`wardrobe`（v0.3.17 建的 `_SEVEN_ELEMENT_LABELS` 漏了 v0.3.18 新增的 `CONCEPT:`，被 `_ACTOR_LINE_RE` 当成角色段 → GENDER_PARTIAL 永久误报阻塞）。负面提示词在本管线基本无效：顽固偏差（明代乌纱帽、斗笠）要**改正面描述 + 塞进 CONCEPT 段**才压得住。概念页/大场面页必须 `auto_char_refs=False`，i2i 角色参考图会压制 CONCEPT 里的场景
- **0.3.17**（2026-09-29）：朝代服饰考据铁律 — `characters[].era` 必填 / `CN_DYNASTY_COSTUME_GUIDE` 进 planner prompt（春秋/秦汉/魏晋/隋唐/宋元/明清 6 段）/ 新铁律 7.4 / 同步 dev 源。根因：卧薪尝胆勾践被写"圆领袍+武冠+幞头"三朝错配
- **0.3.8**（2026-09-28）：排版结构化定版 —— 正文一句一段（最长块 124→33 字）/ 去首行缩进 / 修引号被劈开 / 定格瞬间不再与正文重复。规范写入 references/templates.md，作为历史经典故事类默认
- **0.3.7**（2026-09-28）：分镜速记全中文 + 取消截断 + 兼容 LLM 两种七要素写法（60 条要素 98% 中文）
- **0.3.5/0.3.6**（2026-09-28）：Checkpoint 1 收敛为单一产物 —— layout_preview.html 同时展示排版 + 分镜意图
- **0.3.3**（2026-09-28）：苏武牧羊真实端到端测试暴露 2 个 bug — 分类器增加史事动作词兜底层（覆盖名单外人名）/ 修复 keywords 在 LLM 解析层被静默丢弃（朱砂红高亮曾整条失效）
- **0.3.2**（2026-09-28）：全量代码审核修复 7 个 bug — P0 风格推荐对真实题材失效（改加权信号分类器）/ LLM 无 timeout 挂死 / num_pages 两处被丢弃 / mock 历史风格画出现代科学家 / 跑图失败写 0 字节污染下游 / step_rewrite_visual 返回错页；另整理 tests/ + 归档 70 个一次性脚本 + 同步 src/core
- **0.3.1**（2026-09-24）：`step_publish_draft` 加 `thumb_page` 参数（封面选页，不再固定用第 1 张）
- **0.3.0**（2026-09-24）：性别分支 + 角色视觉签名锁定 + 画面 caption 匹配 + 零文字强化
- **0.2.9**（2026-09-23）：正文精简 100-150 字 + 关键词高亮 + 连环画多人物铁律 + 现代审美脸默认
- **0.2.6**（2026-09-22）：视觉文字对齐审查 + cinematic 词自动剥离 + 人物故事自动检测
- **0.2.5**（2026-09-22）：中国画风格分流 + 人物一致性 i2i
- **0.2.4**（2026-09-21）：戴敦邦派连环画定版
  - 新增第 5 风格 `chinese_lianhuanhua_classic`（戴敦邦派工笔重彩连环画），历史典故第一推荐
  - 新增 `CHARACTER_CN_LIANHUANHUA_ANCESTOR` 锚点（5-tuple 戴敦邦派脸：方颌 + 丹凤/三角眼 + 剑眉 + 朝代蓄须 + 朝代高髻/幞头）
  - `RECOMMEND_MATRIX` 历史/文学/古风/武侠/宏大类第一优先改 `chinese_lianhuanhua_classic`
  - `build_image_prompt` > 9800 字符截断保护（保 style + 七要素套话，砍 scene_description）
  - 修 `recommended_template` 字段丢失 bug（`Storyboard.recommended_template` + `to_dict()` 返回 + `_load_storyboard` 读）
  - SKILL.md / references 升 v0.2.4
- **0.2.3**（2026-09-21）：七要素铁律
  - planner system prompt 显式七要素结构（SUBJECT / ACTION / CAMERA / PLACEMENT / DEPTH LAYERS / LIGHTING / MOOD）
  - planner 加镜头分配铁律（12 页版："开-推-特-退"节奏）
  - prompts.py 加 `CAMERA_LANGUAGE_KIT`（6 shot × 6 angle × 5 lens × 3 DoF）
  - prompts.py 加 `DEPTH_LAYERS_BOOST`（三层景深硬约束）
  - prompts.py 加 `CINEMATIC_FRAMEWORK_BOOST`（七要素结构铁律）
  - prompts.py 加 `EXPRESSION_VOCAB`（8 件套：neutral / rage_scream / sobbing_silence / grim_resolve / awed_stillness / sneering_scorn / tender_grief / fierce_command）
- **0.2.2**（2026-09-21）：新增第 4 风格 `guochao_manhua`（国潮古风条漫）—— 历史典故类第一推荐；Mavis 对话流必附"分镜意图 vs 实际画面"对照表
- **0.2.0**（2026-09-20）：砍 8 风格→3 风格，砍 5 模板→3 模板，去 subprocess 改对话流，加零文字/角色一致性/视觉具象化三重硬约束
- 0.1.1（2026-09-20）：新增 `e` 模板（典雅知识风，深蓝灰配色版，基于 `c` 模板结构）
- 0.1.0（2026-09-18）：初始版本，4 模板 + 8 风格
