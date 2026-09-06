# workflow-revision.md：日常修改与结构修订

修改、回炉或重写已采用章时使用。章节和范围能从上下文确定就执行；只在缺必要信息时询问。先交候选，作者采用后才替换正稿。

## 定位与分类

递归定位 `正文/` 中章号唯一的文件，兼容卷目录和补零章号。读取整章、相关前后章、细纲与角色档案；运行 `tracking_commit.py check` 验证唯一 state 和派生视图。缺 state 的旧书先路由 `story-import`，不能手写替代追踪。

| 修改 | 普通模式 | 阅读范围 |
|---|---|---|
| 台词、措辞、必要解释 | `wording` | 原稿、新稿、实际差异、相邻已采用章 |
| 压重复、调篇幅、不改变故事事实 | `rhythm` | 同上，核对保留的关系与回报 |
| 改事件、知识、资源、关系结果或后续义务 | `facts` | 前一章及全部已采用后文，逐章判定受影响/不受影响，重算当前追踪 |

末章还绑定下一章细纲（如有）。分类由阅读证据支持，脚本不声称能自动证明事实未变。发现越出措辞/节奏范围时重新准备 facts 候选。存在 `.story-quality/HEAD.json` 时转本文件最后一节，普通入口拒绝绕过研究 HEAD。

## 一次针对性编辑

先用 `{PYTHON} {本 skill 根}/scripts/storyctl.py wordcount measure --file {正稿}` 记录实际字数。按用户范围找最影响理解、人物表现或兴趣的 1～2 处：重复验收/收费、旁白与对白重复归纳、关键选择迟迟不到等。不凭心理词、对白标签、段落长度启动全文重写。

完整新稿写到书根 `候选/`；有效心理、停顿和生活互动不因词形一律改成动作。未改善则保留原文并重新诊断，不反复清洗。专业事实按需研究。普通长篇仍使用 fanqie-long-v2 的 2200～2800 字；显著增减报告原因，不自动补写或删除重要结果。超出当前档位的篇幅要求先明确交付限制。

## 准备与只读预检

本 skill 的 `scripts/revision-commit.py` 与新章 `candidate-commit.py promote` 分开，不给新章采用偷偷加覆盖行为。

```text
{PYTHON} {本 skill 根}/scripts/revision-commit.py prepare --project {书目录} --chapter {N} --candidate {完整新稿} --kind wording --summary "本次阅读问题"
```

返回 operation 和 `候选/_修订/{operation}/`，保存原始字节、新稿、差异、摘要和未填写的 review-template.json。准备不改正文或追踪，不生成通过意见。

阅读者核对原稿、新稿、实际差异及模板所列上下文，另存阅读结果：填写真实 reviewer、`reader_type=model|human`、status、原稿/新稿可定位锚点、逐文件上下文判断和 findings。措辞/节奏须明确 `facts_unchanged=true`。blocking 未解决不能 pass；模型不能冒充真人。hash 沿用本次模板，改稿须重新准备，不能刷新旧意见伪装重读。

```text
{PYTHON} {本 skill 根}/scripts/revision-commit.py check --project {书目录} --operation {operation} --review {实际阅读结果.json}
```

check 只读，验证字数、标题、确定性扫描、作者禁令、原始 state、正文集合与阅读绑定。语境/密度 advisory 不自动阻断，没有阅读结果就是未评估。

facts 的 check/accept 还需 `--transaction {修订追踪事务.json}`。按 [tracking-transaction.md](tracking-transaction.md) 使用 `mode=revision` 和准备时的 `expected_state_revision`：

- 根据新旧正文重算本章增量；伏笔、时间、角色快照和 metrics 提交截至最后已采用章 M 的当前有效结果，不能把旧章修订误写成现在退役。
- 后文还引用被删除事实时先处理正文冲突，不能删除追踪掩盖；扩大检查范围不自动授权改写后文。
- 保留 `imported_through_chapter`；导入范围内修订只新增覆盖记录。
- 不提交旧 wordcount 记录；采用时移除该章旧测量，避免过期摘要继续有效。

## 采用、恢复与撤销待办

展示候选、修改目的、阅读结果和事实影响。有作者明确采用授权就执行，否则等待选择。新版不更好可保留原稿。

```text
{PYTHON} {本 skill 根}/scripts/revision-commit.py accept --project {书目录} --operation {operation} --review {实际阅读结果.json} --author-approval "作者实际采用指令"
```

不得编造批准原话。facts 追加同一份 transaction。运行器复用项目锁及 tracking 规范化/渲染逻辑：先保存可恢复日志，再写正文和派生视图，最后写唯一 `_tracking-state.json`。纯文字修订保留经复核的事实并递增 state_revision，事实修订重算事务；不建立第二个事实权威。

旧阅读凭证、候选绑定和受影响测量因正文或 state 摘要变化而过期，回执列出失效项；不能复用旧 PASS。研究证书由研究生命周期管理。

```text
{PYTHON} {本 skill 根}/scripts/revision-commit.py recover --project {书目录} --operation {operation}
```

中断后原稿仍保存。recover 检查各文件处于事务前或预期后版本，拒绝覆盖第三方修改，可幂等重跑。未完成修订阻止其他采用与追踪写入。若仍为 prepared 且全部正式文件未变，可取消待办，保留证据重新准备：

```text
{PYTHON} {本 skill 根}/scripts/revision-commit.py abort --project {书目录} --operation {operation} --reason "候选需重新准备"
```

采用后想恢复原文：用保存的 original.md 重新 prepare，按最新上下文复核采用。不倒退 state_revision，也不让旧凭证重新生效；备份禁止放入 `正文/` 污染章号发现。

## 显式研究生命周期

仅已有研究 HEAD 或用户明确要求研究协议时，按 [quality-lifecycle.md](quality-lifecycle.md) 执行：先 `quality_lifecycle.py check` 定位父 revision，再 stage `--kind revision`，保留 finding、影响区和授权。该模式的六视角、盲 A/B、cohort、写后抽取和 certify/accept 不被普通入口弱化。

接受第 X 章后，X..M 旧研究证书和 reader chain 按原协议失效；X+1..M 顺序 replay，重放不授权改文。正确性通过但强度不足时用显式 strength_reopen，不伪造 defect。未满足实际证据要求就保留 pending，模型意见不能写成真人认可。
