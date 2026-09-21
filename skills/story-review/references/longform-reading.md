# 长篇累计连读协议

本协议管理持续写作中的读者体验复核，不替代逐章 rc、十五章 arc、普通 full/lean/solo 审查或作者采用。设计卡的变化是假设，正文连读才是阅读证据；不凭文学分数阻断采用，不强制改写。

## 启用与检查点

- 新开书默认在 Phase 3 完成单元规划及第 0 章追踪初始化后、首章生成前启用（`last_committed_chapter=0` 且无正式正文）；不得在空项目阶段提前 init。旧书没有策略即未启用，不自动迁移、不把历史漏记录算通过。旧书须由作者明确选择起始章节；中途启用后的首个单元末仍读整个单元，但不追罚此前未审检查点。
- 单元结束必做，必读本单元全部已采用正文；每到全十五章整数倍另审最近十五章。两种检查点重合时只组织一次，必读范围取两者并集，不能用十五章窗口缩短整个单元的阅读范围。
- 既有 arc 可在采用前读当前候选；累计检查复用这次阅读必须满足本协议的独立性、完整范围及相同文本版本，候选采用后再核对。版本不一致不能沿用旧结论。
- 只有最终选定的已采用正文参与历史比较，候选或未写设计不能冒充真实阅读。正式正文缺失时报告缺读，不拿追踪摘要补齐。
- 已采用范围必须有连续的单元归属与正式正文。追踪中合法的 `chapter_gaps` 是明确未写的跳号，运行器以 `excluded` 单列章号和原因，不计入已读；无声明的空档、非法缺口或缺口内存在正文仍阻断。历史缺口沿用追踪权威，不为通过审读临时编写缺口声明。


## 独立顺序阅读

1. 父流程确认审读者未参与该段创作/规划，给正文路径、章号、必读范围及本协议，不给设定、大纲、追踪、设计卡、作者意图或预设问题答案。记录实际审读者与模型代理/真人来源。上下文已受规划或后文污染时换独立审读者，不靠“忘掉”指令恢复盲审。
2. 审读者按章序完整阅读必读正文，每章先记录当时理解、阅读摩擦和期待再读下一章；不得提前看后文解释早先困惑。理解疑点按 [前文回查协议](reading-protocol.md) 只向前查。
3. 当前范围初读记录固定后，再与此前相似单元正文比较。选择依据可由父流程记录，但不给读者设计差异或“应当觉得重复”的结论。比较材料必须覆盖困境、解法、兑现及必要上下文；审读者可以请求扩大范围。摘句不足以判断时扩读完整旧单元，或记比较证据不足。
4. 可分段递送以控制上下文，但同一顺序审读者应保持正文形成的阅读记录。并行五章理解报告的拼接不等于累计连读；中途换读者须重读必需范围，不能只靠他人摘要取得已审结论。不可用、超时或缺读保留待审原因，父流程不以自评代替独立阅读。
5. 读者交回结果后，父流程才对照设计假设、汇总问题并安排处置；父流程的作者视角说明与盲读原结果分开，不能改写读者判断来达成一致。

## 阅读问题与证据

- 理解：用自己的话说清谁在做什么、为什么、风险及转折前提；附当前原句与前文落点。前文未命中按已核查范围表述，尚未查证记待核实。
- 跳读与重复：第一处想跳读在哪里，哪些步骤、解释、交锋或回报反复出现？是否有新的认识、选择、关系后果或有意义的回声？只换敌人、地点、数值不是充分差异，重复本身也不是缺陷。
- 关系印象：人物关系、声口与相处给出了什么感受？指出有用的心理直写、安静场景、生活细节及值得保留的表达，不强制关系每单元升级。
- 满足与期待：本轮实际获得了什么、还想看什么，压力、呼吸与余波是否有作用？不给统一情绪强度、套路间隔或字数比例评分。

记录应包含：要求范围与实际精读文件、检索及打开的回查范围、旧单元比较依据、文本版本/摘要、原始行号与原句、独立性及来源、未读部分、确认问题/待核实/无问题、处置及理由。哈希只能绑定版本，不能证明阅读发生；必须同时有实际阅读结果和可定位证据。没有损失可以无 finding，不为填表制造问题。

## 处置与后续回应

每个问题保留可追踪的身份及原始证据，处置可为保留、改正文、改设计或下单元处理；指出由谁按何种授权处理，审读者只读不改。改已采用稿仍遵守作者边界。设计不同却读感重复时，不以卡片字段齐全反驳阅读证据。

下单元处理的问题在下一次检查必须回应：已处理须有新正文或设计复核依据；未处理可说明理由继续延期，保留原问题及下一回应点，不能无回应消失。设计上的处理不等于读者已感受到改善。读者初读完成后再核对这些旧问题，避免预设答案污染盲读。

## 状态归属与完成边界

实际入口是 `{本 skill 根}/scripts/review-state.js longform`，分派到同目录 `longform-review.js`。状态文件为 `{书目录}/.story-review/longform-v1.json`，`schema_version=1`、`policy_version=longform-reading-v1`；检查点身份由运行器返回（当前为 `chapter-{N}`）。接口可调用不代表所有编排入口已完成集成验收，禁止手写状态伪造完成。

- 沿用 `.story-review/` 归属，由 `review-state.js` 管理独立命名/版本的长篇检查记录及收据，不覆盖普通 `latest.json`，不新增故事事实账本。flow-state 只派生显示与引用，不保存另一份可变审查真相。复用原子写与并发保护，明确 schema/policy 版本、起始章节及稳定检查点身份；读写接口及返回值见下节。
- flow-state detect/update、单元收口与写前组装必须消费同一个检查点计算/验证入口。当前章仍按原规则由作者采用；到期进入 `pending_reading`，下一章正文生成前需有效已审记录或明确继续授权，规划可继续。不能写 `done` 或手填 PASS 绕过。
- 待审 `pending` → 已审 `reviewed`；正文、比较证据版本、单元边界或要求范围变化 → `stale`，需补审。未运行、失败或缺少必读正文保留待审；完整读完但主观不确定/比较证据不足可以据实记已审，不能把未读必需范围包装成证据不足而完成。
- 已审不等于所有问题解决，也不等于作者认可。临时继续授权保持待审，记录适用范围并在下一检查点回收，不自动滚动延长。明确豁免具体检查点记 `waived` 及原因，不算已审；同一有效授权不重复索要。
- 不向 `logic_checks` 增加文学判断 ID，不用模型分数拒绝采用；必读范围与版本核验是流程完整性要求。作者暂时继续和具体豁免不能伪装为阅读已经发生。
- 用户明确只读时不写任何收据或状态，报告本次结果未持久化；不得为落盘借用普通 full/lean 模式。普通 solo 降级不能补足独立连读，允许的状态动作须由已授权父流程通过实际接口执行。

## 实际接口与最小操作例

以下从仓库根执行，`{书目录}`、`{REV}`、`{N}` 和输入文件路径均替换为实际值。每个写命令传当前返回的 `state_revision` 作为 `--expected-revision`；冲突时停止并重读状态，不能盲目自增或覆盖。`status/gate` 只读，不需要 CAS；其余下列命令会写长篇状态，明确只读任务不得调用。

新书仅在 Phase 3 的单元已规划、追踪初始化到 0 且没有正式正文后调用；旧书使用第二条，二选一，不对已有策略重复初始化：

```text
node {本 skill 根}/scripts/review-state.js longform init --book "{书目录}" --expected-revision 0 --new-book
node {本 skill 根}/scripts/review-state.js longform init --book "{书目录}" --expected-revision 0 --start-chapter {起始章} --author-approval "{作者实际启用指令}"
node {本 skill 根}/scripts/review-state.js longform status --book "{书目录}"
node {本 skill 根}/scripts/review-state.js longform gate --book "{书目录}" --chapter {下一已采用章号}
node {本 skill 根}/scripts/review-state.js longform gate --book "{书目录}" --complete
```

`--chapter` 必须等于 `last_committed_chapter + 1`，不是任意未来章。`gate` 按 `can_generate` 决定退出码，`--complete` 改看 `can_complete`；0 为允许、1 为未满足、2 为接口/数据错误。`status` 成功退出 0 只代表查询成功，仍须读其状态。未启用返回 `not_enabled`，不等于已审；临时授权可使 `can_generate=true`，但 `can_complete` 仍为 false。所有到期未决检查点均需处理，缺正文/重复章不能用继续授权掩盖。

### 1. 开始独立阅读

父流程从 status 的 `checkpoints` 取实际到期 ID，准备 start JSON；以下是结构示例，身份和路径必须真实。`creative_participants` 非空且含该段写作/规划参与者的 ID/会话标识；读者的 ID 与 session_id 均不能与其中任一项相同。

```json
{
  "checkpoint_id": "chapter-15",
  "reader": {"id": "实际读者ID", "session_id": "实际独立会话ID", "reader_type": "model"},
  "independent": true,
  "creative_participants": ["实际写手ID", "实际规划会话ID"],
  "reading_order": "chronological_then_comparison",
  "prose_only": true,
  "comparison": {"reason": "实际选择依据；若从第1章开始则无更早单元", "paths": []}
}
```

`reader_type` 可为 model/human。比较路径是书目录相对路径，须为必读范围首章之前的正式正文；排序由运行器处理。不从第1章开始却无比较文件时，必须明确 `comparison.insufficient_evidence=true` 并说明原因，不能默认比较已完成。需新增/扩大比较文件时重新 start，不手改既有 run。

```text
node {本 skill 根}/scripts/review-state.js longform start --book "{书目录}" --expected-revision {REV} --input "{start.json}"
```

返回 `state_revision`、`run_id`、`required_files`、`comparison_files`。父流程只向读者递送正文，不把状态内的规划边界来源、旧问题或设计结论混入盲读。

### 2. 逐文件递送与阅读

按 `required_files` 顺序，再按 `comparison_files` 顺序，每次提供 JSON `{"run_id":"实际run_id","path":"正文/实际文件.md"}`：

```text
node {本 skill 根}/scripts/review-state.js longform read --book "{书目录}" --expected-revision {REV} --input "{read.json}"
```

返回完整 `text` 和新 revision，实际交给同一独立读者；每章先保存当时理解再递送后章。read 只证明文件被递送，不证明读懂；finish 还需要实际阅读意见。`read` 不接受任意回查路径；B 的向前疑点检索另按回查协议记录，不能改变 read 顺序或把外部回查引文冒充已递送的 finish 证据。若必要上下文不能纳入本次比较范围，报告限制并重新组织审读，不编造 read 成功记录。

### 3. 完成、失败与授权

```text
node {本 skill 根}/scripts/review-state.js longform finish --book "{书目录}" --expected-revision {REV} --input "{finish.json}"
node {本 skill 根}/scripts/review-state.js longform fail --book "{书目录}" --expected-revision {REV} --input "{fail.json}"
node {本 skill 根}/scripts/review-state.js longform authorize --book "{书目录}" --expected-revision {REV} --input "{authorization.json}"
```

finish JSON 使用真实 `run_id`，且包含：

- `observations` 恰好有 `understanding`、`fatigue`、`relationships`、`reward_expectation` 四键；每项含非空 `assessment` 和非空 `evidence` 数组。证据项为 `{"path":"已递送正文相对路径","line":1,"quote":"该行起真实原句"}`，一基行号，原句须与对应行起始内容匹配。无问题也写实际判断与支持证据，不能把示例复制成反馈。
- `findings` 数组，可空；每项含唯一 `id`、`disposition`、非空 `reason` 与 `evidence`。处置仅为 `retain|revise_prose|revise_design|next_unit`。
- `responses` 数组，可空；此前已审收据中仍待下单元处理的每个问题必须且仅回应一次，每项含 `finding_id`、上述 disposition 和非空 reason。初读后由父流程从长篇记录核对旧问题，处理依据随理由记录；延期用 next_unit 并说明下一回应点，不伪造已经改善。

必读及已选比较文件须全部完成 read；版本变化须重开阅读。finish 校验通过才生成 reviewed 记录与绑定收据。失败 JSON 为 `{"run_id":"实际run_id","reason":"实际失败原因"}`，将 run 标 failed，保留待审，不能拿 fail 清除问题。

授权 JSON 含 `checkpoint_id`、`kind`（continue/waive）、`author_approval`（实际原话）和 `reason`。continue 另需 `through_chapter`，从当前已采用章+1开始，终点不能超过下一个已规划检查点；没有下个检查点时先规划边界，不能编造无期限授权。waive 仅豁免指定检查点，记 waived 不记 reviewed。授权绑定当前要求版本，变化后由 gate 重算，不自行延长旧授权。

完成或授权后重跑 gate；父流程依据返回值进入下一章或保留 pending_reading，不靠命令退出 0 宣布文学问题已解决。

## 验证边界

协议走查见 [longform-reading-scenarios.md](longform-reading-scenarios.md)。先验证范围、独立性、状态与授权，再判断阅读意见是否有正文依据；工程通过、模型阅读结果、作者反馈分别报告。十五章、三个单元和一次跨卷仅为最小集成试跑；长期效果还需相似单元再次出现及处理后的反馈，不拿旧实验顶替当前版本验收。
