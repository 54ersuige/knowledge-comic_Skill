# 版本变更史（CHANGELOG）

> 从 `SKILL.md` 抽出的完整版本考古记录，**按时间倒序**。
> 这些内容是写给维护者看的，不是执行规约 —— 执行时只需要读 `SKILL.md`。
> 保留原文，未做改写。

## 快速索引（版本 → 一句话）

- **0.3.28**（2026-10-08）：**输出质量三修**（真实 LLM + 真实出图实测驱动）。① **【阻塞级】** 裸词 `banner` 让中文历史战争题材 **12/12 页全阻塞**（"叛军的黑红旗帜"被判诱导画字）—— 与 v0.3.26 的 `inscriptions` 同源，第 3 次同类复发，已移出词表；② **`new_yorker` / `us_mid_century` 漂成照片写实**：根因是 `LIANHUANHUA_STYLE_LOCK` **被无条件拼进所有风格**（Risograph 与戴敦邦宣纸工笔互斥打架）+ 非中国风格无前置声明、不剥摄影词与中文速记 → 新增 `PRINT_ILLUSTRATION_STYLES` 三件套，实测 STYLE_DRIFT **90% 阻塞 → 40% 建议**；③ **七要素只落到 4 段**：§4.2 范例题只写了 5 段而 LLM 照抄 → 补齐后 **7/7 段**；正文平均 **89 → 100 字**，`BODY_SHORT` **3 页 → 0 页**
- **0.3.27**（2026-10-08）：**文档层重构 + 目录卫生**。① `SKILL.md` 1102 → 227 行（体积 -82%，每次触发少烧约 17K tokens）——三块互不相邻的版本史搬进本文件，**原文未改一字**；② 新增 `references/quality-gates.md`，判据**从代码取真值**（22 个 preflight code + 4 个 visual_qa code）而不是抄旧文档；③ `README.md` 整体停在 v0.2.4 且推荐两个已归档脚本 → 删除，安装说明并入 `SKILL.md` 的 `## Setup`；④ `scripts/review.py` 的 `set_page_field` / `dump_storyboard` 上收为 `run.py` 的 `step_set_page_field` / `step_dump_storyboard`（step 函数不该让 Mavis 去调旁路模块）；⑤ 新增 `scripts/check_docs.py` —— 校验文档 ↔ 代码一致性，应对本项目**第 4 次复发的文档漂移**；⑥ 清掉 434MB `data/` + 22MB `_archive/` + 7 个无人引用的外围脚本 + 根目录垃圾（`$null` / `_tmp_*.py` / `_msg2.txt`）；⑦ 修 `guide.py` 死引用、`preflight.py` 同名函数重复定义（347/393 行）、`style_guide.md` 的「总分≥90」死规格、`prompts.py` 把 5 风格写成 3 风格、`check_drift.py` 依赖不存在的 `AGENTS.md`；⑧ **测试夹具从 gitignore 的 `data/` 移进 `scripts/tests/fixtures/`** —— 原先那个测试只在"恰好跑过该 job 的机器"上能过，换设备必红
- **0.3.26**（2026-10-08）：两个 preflight 判据反转（零文字声明里的枚举被误判成"诱导画字"→ 12/12 页全阻塞；清代皇帝穿龙袍被判时代穿帮）+ 强制交付资产（**没发过的资产 = 没做完**）
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

---

## 详细版本记录

## v0.3.28 核心变化（2026-10-08，输出质量三修 —— 全部由实测驱动）

**背景**：v0.3.27 完成文档层重构后，用户要求「确保这个 skill 的输出效果」。
于是用**真实 LLM + 真实渲染 + 真实出图**跑了三轮，而不是 dry-run。
三个缺陷**全部是既有问题** —— `image_gen.py` 完全没被 v0.3.27 碰过，
`prompts.py` 只改了 docstring —— 但它们实打实影响成品。

### 1.【阻塞级】裸词 `banner` —— 历史战争题材一张图都跑不了

实测 kc_1791447274「张巡守睢阳」被自己的关卡拦在 p1：

```
[block] p1 TEXT_INVITING :: 画面描述含会诱导模型画字的词 ['banner']
```

而原文是 `black and red banners of the Yan army` —— **军旗 / 旌旗**，中文历史战争
题材的核心视觉元素。`TEXT_INVITING_WORDS` 里的裸词 `banner` 本意是拦"招牌 / 横幅"，
把军旗一起拦了。

**这与 v0.3.26 刚修的 `inscriptions` 是同一个失效模式**（关卡把合规写法当违规），
在本项目已是**第 3 次**同类复发（v0.3.15 NO_TEXT_MISSING → v0.3.26 inscriptions
→ 本次 banner）。修法：移出裸词，保留 `banner text` / `signboard` / `written` /
`characters on` 等真风险词。验证：该 job 由 `blocked=True` 变为 `0 blocks`。

### 2.【严重】`new_yorker` / `us_mid_century` 漂成照片写实

实测 kc_1791447361「峰终定律」出图是**一张照片**，visual_qa 报 `STYLE_DRIFT 90%` +
`TEXT_ON_IMAGE 85%`。排查确认根因**不是"没写风格"** —— dump 出来的 prompt 里
`Risograph print style on cream paper` / `Flat low-saturation color blocks` /
`NOT a photograph` 全都在。真问题是三条：

| 来源 | 证据 |
|---|---|
| **`LIANHUANHUA_STYLE_LOCK` 被无条件拼进所有风格** | new_yorker 的 prompt 里同时出现「Risograph 平面印刷」与「戴敦邦派宣纸工笔连环画」—— **两套互斥指令打架，模型退回最熟练的写实摄影**（主因） |
| 非中国风格**无前置风格声明、无 STRICT STYLE LOCK** | 只有中国画那支有 `CHINESE_STYLE_PREFIX` / `style_lock_repeat` |
| 非中国风格**不剥摄影词与中文速记** | 实测每页混入 **9 条** `// 中文速记`，正是 v0.3.9 记录过的"中文语义冲淡英文风格锁定"；`35mm lens` / `shallow_dof` 也一路进 prompt |

**修法**：把"非写实处理"抽成 `stylized = is_traditional_cn or is_print_illustration`，
新增 `PRINT_ILLUSTRATION_STYLES` + `PRINT_STYLE_PREFIX` + `PRINT_STYLE_LOCK`，
并把 `LIANHUANHUA_STYLE_LOCK` 收回给中国画风格。

**实测效果**（同一页 p1，真出图）：

| 配置 | visual_qa 判读 |
|---|---|
| v0.3.27（改前） | `STYLE_DRIFT 90%` **阻塞** —— 照片 |
| v0.3.28（改后） | 无漂移 —— 干净编辑插画 |
| 同上重跑一次 | `STYLE_DRIFT 40%` **建议**（左米色平涂 / 右暗部渐变的调性差异） |

**残留方差是真实的**：图像模型有 10-20% 固有漂移率（项目既有结论），本文 n=2~4，
只够说明"从阻塞级降到建议级"，不足以宣称消除。

**一次被实测否掉的改动**：为消掉 `CAMERA_LANGUAGE_KIT` 里
`shallow_dof (creamy bokeh)` 与 `PRINT_STYLE_LOCK` 的 "NO shallow depth-of-field"
字面矛盾，我曾给印刷风格换了一套精简取景说明 —— **真跑出来是回归**
（`STYLE_DRIFT 95%`，肉眼确认是"平面线稿人物贴在写实照片背景上"）。已回退，
并把这段实测写进 `build_image_prompt` 的注释，防止后人再"为整洁而换掉"。
教训：**kit 是构图词汇表，不是渲染指令**；真正压住写实的是前置 + 夹击那对声明。

### 3.【内容】七要素只落到 4 段 + 正文偏薄

- **七要素**：§4.2 的**范例题只写了 5 段**（漏 PLACEMENT / DEPTH LAYERS / LIGHTING），
  而 **LLM 会照抄范例** → 实测七段只落到四段。补齐范例后 **6/6 页 7/7 段**。
- **正文**：prompt 里只有上限有代码兜底（`_clamp_body`），下限纯靠提示。
  实测历史题材平均 89 字、3 页低于 `BODY_WARN_LO`。补上"不足 100 字 = 不合格"
  的硬要求后：**平均 89 → 100 字，`BODY_SHORT` 3 页 → 0 页**；同一份 storyboard
  跑 preflight 从 `1 block + 3 warns` 变为 **`0 block + 0 warn`**。

### 4. 其他

- `_CINEMATIC_TERM_PATTERNS` 补 `bokeh` 剥离规则（纯摄影概念，任何非写实风格
  都不该出现；此前只覆盖 `shallow_dof` / `deep_focus`）。
- 为容纳新增规则，§4.2 条目做了去冗余（范例已演示格式）——
  `PLANNER_SYSTEM_PROMPT` 保持 **13,967 字符**（预算 <14,000、压缩率 37%），
  `test_prompt_v0324.py` 的体积断言继续成立（**由我压缩去满足它，不是改测试**）。
- 新增 `scripts/tests/test_v0328.py`（双向用例：该放行 + 该拦同时成立）。
- **观察到的偶发问题（未修，留档）**：planner 返回的 JSON 偶发被判 `non-JSON`
  并抛错（6 次运行中 1 次）。`temperature=0.7`，与 v0.3.25 记录的同类偶发同源；
  当前行为是**大声抛错**（不是静默降级），重跑即可。补一次自动重试是后续可选优化。
- **一条被测试文档化的已知限制**：`_CONCEPT_RE` 的右边界靠"下一个换行处的要素标签"
  或字符串结尾；若 visual 写成**单行**，CONCEPT 会吞掉整段场景。真实 planner 输出
  是多行的，生产路径正常，故未改（改动它要承担 CONCEPT 抽取回归的风险）。

### 5. 验证

```
python scripts/run_tests.py     14/14 通过, 0 失败
ruff check scripts/             All checks passed!
python scripts/check_docs.py    7 份文档无悬空引用；step_* 全部存在
```

真实出图 3 张 + 真实 LLM 分镜 6 次（含 4 次 JSON 失败率探针）

## v0.3.27 核心变化（2026-10-08，文档层重构 + 目录卫生）

**背景**：用户反馈这个 skill「太乱太杂」，要做一次整体优化。全量审计后发现：
**功能代码是健康的**（13 个测试全绿、`ruff` 0 error），烂的是**文档层和目录卫生**。

### 1. 【最大单点损失】SKILL.md 1102 行，每次触发全量注入

85,402 字节 ≈ 25K tokens，**每次 `/knowledge-comic` 都全量进 context**，而其中约 2/3 是
版本考古。更糟的是版本史分散在**三个互不相邻的区块**（L11-241 / L278-643 / L968-1063），
把操作章节夹在中间。

这正是官方反模式 #6（主文件 > 500 行）与 #6.5（把 SKILL.md 写成 README/教程）的教科书案例。

**做法**：按二级标题程序化切分（不靠人肉数行号），把版本史无损搬进本文件，SKILL.md 只留
执行规约。**1102 → 227 行，85,402 → 15,617 字节（-82%）**。切分时抓到一个坑：
`## v0.3.24 三条自检命令（改完必跑）` 因标题以 `vX.Y.Z` 开头被误判成版本史 ——
**标题模式匹配必须有例外白名单**。

### 2. 【慢性病】文档反复指向不存在的东西

审计实测（本项目 CHANGELOG 里同类问题能数到 4 次）：

| 症状 | 证据 |
|---|---|
| `README.md` 整体停在 v0.2.4 | 且推荐 `diagnose_prompt.py` / `diagnose_terms.py` —— 已在 v0.3.24 归档 |
| `SKILL.md` 让 Mavis 调 `guide.show_intent()` | 该函数**从未存在**（`guide.py` 只有 `recommend` / `show_overview`） |
| `style_guide.md` 的「总分 ≥90 / 重试 2 次」 | 一整套**没有实现的**死规格，且声称"review.py 按本文档打分"（review.py 无打分逻辑） |
| `ruff.toml` / `check_drift.py` 以 `AGENTS.md` 为规矩来源 | skill 里根本没有 `AGENTS.md` |
| 风格数注释 | `prompts.py` docstring 写"锁定 3 个"，实际 5 个 |

**修法**：逐条改到与代码一致，并新增 `scripts/check_docs.py` 把这类漂移变成**可跑的检查**
—— 靠人工 review 已经漏了 4 次，不能再靠人工。同时确立一条约定：
**矩阵表以 `prompts.RECOMMEND_MATRIX` 为真源，reference 里的表是可读镜像**。

### 3. 【架构瑕疵】step 函数让 Mavis 去调旁路模块

`run.py:579` 的 docstring 写「改某页用 `review.set_page_field(...)`」，于是
`scripts/review.py` 成了 Checkpoint 1 唯一的分镜编辑入口 —— 但它不在主入口里。
同源问题在本项目已出现 3 次（v0.3.21 prompt 拼装双路径 / v0.3.24 阈值漂移 / 本次）。

**修法**：上收为 `run.py` 的 `step_set_page_field` / `step_dump_storyboard`，再删掉 `review.py`。
能力一点没丢，入口少了一个。

反过来 `scripts/image_review.py` 是**真死胡同**：它写的 `rerender.json` 全项目**无人读取**
（真正的重画机制是 `step_gen_images(regenerate_pages=[...])`），直接删。

### 4. 【测试不可复现】夹具躺在 gitignore 目录里

`test_preflight_v0315.py` 读 `data/kc_1790586703/storyboard.json` 做夹具 —— 而 `data/` 是
gitignore 的。**这个测试只在"恰好跑过那个 job 的机器"上能过**，换设备或清 `data/` 必红。
清理 `data/` 时它当场暴露（90/91 FAIL）。

**修法**：夹具移进 `scripts/tests/fixtures/kc_1790586703.storyboard.json`（内容一字未改），
测试只改路径定义，断言逻辑不动。**清理工作意外地暴露了一个潜伏已久的测试缺陷** ——
这也是"删之前先核依赖"的价值。

### 5. 目录卫生

| 清掉 | 体积 |
|---|---|
| `data/`（22 个历史 job 的成品图 + 参考图） | 434 MB |
| `_archive/`（70+ 一次性调试脚本） | 22 MB |
| 7 个无人引用/与主入口重叠的外围脚本 | — |
| 根目录 `$null` / `_tmp_*.py` ×6 / `_msg2.txt` + 3 类缓存目录 | — |

**保留** `data/canon.md` 与 `data/canon.blackdeath.md` —— 前者是 `canon.py:15` + `run.py:161`
真实调用的**活配置**（删了会静默关掉一致性约束注入）。

**教训**：删除前必须核"谁真的在用它"。本轮拦下两个误判 —— `data/canon.md`（活配置）与
`scripts/review.py`（唯一编辑入口）；同时揪出一个真死代码 `image_review.py`。
另外 `.gitignore` / `.gitattributes` 曾看着像乱码，实为 **PowerShell 5.1 用 GBK 读 UTF-8
的显示假象**，文件本身完全正常 —— 差点"修好"一个没坏的文件。

### 6. 验证

```
python scripts/run_tests.py     13/13 通过, 0 失败
ruff check scripts/             All checks passed!
python scripts/check_docs.py    7 份文档无悬空引用；step_* 全部存在
```

## v0.3.26 核心变化（2026-10-08，两个 preflight 判据反转 + 强制交付资产）

**背景**：用 skill 做「修建颐和园」（kc_1791440435，12 页戴敦邦派连环画）。
一次任务里连续撞出**三个同源问题**：关卡把合规写法当违规（判据反转），
以及资产没发到用户窗口（用户失去判断依据）。都是"看起来跑通了"。

### 1. 【真故障】零文字声明里的枚举被误判为「诱导画字」—— 12/12 页全阻塞

planner 每页的 visual 都以标准零文字声明结尾：
`STRICT NO TEXT ... NO characters/symbols/inscriptions ...`
`inscriptions` 在否定词 `NO` 的**枚举第三项**里，它本身就是声明的组成部分。

`_negated_before` 却要求否定词与被检词之间「只隔连接符」，撞上枚举项里的实词
`characters` 就判定否定作用域断裂 → 报阻塞。后果：最标准的合规写法反而
12/12 页被拦，一张图都跑不了。

**修法**：原判据保持不变，另加一条枚举规则 —— 识别 `否定词 + 词/词/词` 形态。
`no text here, a banner` 仍拦（词之间是普通实词，不是枚举）。

### 2. 【真故障】清代皇帝穿龙袍被判时代穿帮

`ANACHRONIC_MARKERS` 是为「春秋吴王被写成明清帝王」设计的**先秦词表**，
却对清代角色照样开火：乾隆签名写「戴双龙朝冠, 穿明黄色团龙袍」被判阻塞。
而这正是清代皇帝的**正统朝服** —— 照提示改成"素麻袍+发束高髻"，
等于把乾隆画成先秦布衣，比穿帮更糟。

**修法**：加时代门槛，有朝服制度的时代（清/明/元/宋/唐/汉…）跳过朝服类词表；
现代器物（沙发/机械钟）对任何古代角色仍照拦。

### 3. 【流程缺陷】资产没发给用户 —— 用户全程没看到一张图

12 页跑完，**一次都没把图发出去**。全程用了 3 轮 `ask_user`，每一步看似合规，
但用户从头到尾没看过产物，最后是在用户投诉"我没有效参与"之后才补发。

**根因**：用 `read` 工具看图 = 把图读进**模型自己**的上下文，用户窗口里什么都没有。
`read` 过 ≠ 用户看过。

**修法**：「用户主导」章节新增硬性条款 + 自查表 —— **没发过资产的步骤 = 没做完**。
详见下方「核心原则 §1」。

### 4. 新增 `test_preflight_v0326.py`（21 项双向用例）

只测正向会把判据放松过头而不自知 —— v0.3.26 第一版修复就发生过：
新增的枚举扫描走到窗口尽头时无条件放行，导致 `NO banner`、`(NOT calligraphy)`、
`无繁复纹样` 三条既有行为全部回归。是**先写的反向用例**把它抓出来的。

**测试原则**：正向（该放行）+ 反向（该拦）必须同时成立。


---

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


---

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


---

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


---

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


---

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


---

## v0.3.5 / v0.3.6 核心变化（2026-09-28，Checkpoint 1 收敛为一个产物）

用户连续三次纠正同一件事：**审阅分镜的唯一产物是 `layout_preview.html`，排版和分镜内容必须在同一个文件里**。

- v0.3.4 只给排版（看不出画面画什么）→ v0.3.5 又另开一个分镜脚本文件（用户要两边对照，反而是负担）→ **v0.3.6 合并为一个文件**
- 现在 `step_layout_preview(job_id)` 同时展示：成品排版 + 每页分镜意图（主体/动作/配角/背景/景别/情绪 + 关键词）
- 实现坑（都写在代码注释里）：分镜说明**不能**走 `page_image_urls` 通道（模板会 `_esc()` 把 URL 塞进 `<img src>`，整段 HTML 被转义成可见文本）；也**不能用 `<section>` 包裹**（会打乱模板的 section 配平导致整页塌掉）。正解是先用占位图渲染版式，再按 `data-page="N"` 注入说明块
- `step_story_script()` 降级为**图文对齐诊断**辅助工具：用户发现某页图文不符时调它，直接指出缺哪个动作/哪个人物


---

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


---

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


---

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


---

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


---

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


---

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


---

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


---

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

