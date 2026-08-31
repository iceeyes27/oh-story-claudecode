# 单章深审与逻辑原子验收

配套冷参考：[顺序读者链、事件与图谱](reader-chain-and-graph.md)、[清晰度与文风优先级](prose-policy.md)、[盲评与纵向验收](evaluation-protocol.md)。启用绝对强度、重开、checkpoint 或 P1 实验时再读 [P1 强度、重开与纵向验收](quality-p1.md)。

本协议是正文写作与旧章修订的提交权威。目标不是“多打几个分”，而是让每章在交付前同时做到：当前行动看得懂、因果与事实成立、情绪和追读价值不退步、问题已逐条处置、正文与追踪状态同一代际生效。

## 三道门

1. **正确性门（硬底线）**：因果链、既有事实、当前人物在做什么与为什么做、悬念是否合法，四项都必须 PASS。所谓“悬念合法”是指被隐藏的信息不妨碍理解当前行动，且确有细纲允许的开放问题/回收边界；不能用“以后会解释”掩盖当下逻辑断裂。任何改进分数都不能抵消正确性失败。
2. **改进选择门**：只在正确性通过后比较追读力、情绪交付、人物声线、记忆点、题材契约。零缺陷不等于比上一版好；修后变差就保留上一版。
3. **强度门（P1，版本化启用）**：判断本章是否交付与章节定位相符的正向阅读价值。`SHADOW` 只记录；只有 held-out calibration、真人验证、误伤 controls 和完整重开出口通过后才可 `ENFORCE`。强度平庸不伪造 finding，转不可变 reopen case；证据不足转补采或人工复核。

S1-S4 沿用 `story-review` 既有含义，不改严重度。每条 finding 另有处置状态：

- `FIXED_VERIFIED`：已修且由独立终验确认。
- `PRESERVED_WITH_FUNCTION`：原写法有可指认的叙事功能，并在盲评中不劣于改写版。
- `FALSE_POSITIVE`：有证据说明不成立。
- `OVERRIDDEN`：仅 S3/S4 可由作者明确批准保留；S1/S2 不能靠 override 穿过正确性门。

“清零”指所有 finding 都有合法处置，不是删光省略、留白、短句或其他 S3 风格特征。

## 文件与提交点

```text
{书项目}/
├── 草稿/待验收/                         # 完整、可读候选稿；不算正文
├── .story-quality/
│   ├── HEAD.json                       # 唯一逻辑提交点
│   ├── generations/{generation}/       # manifest + 追踪快照 + review/reader/event 自包含质量树
│   ├── revisions/chapter-NNNNNN/       # 每一版正文与 parent/finding/影响区元数据
│   ├── reviews/                        # 六视角证书冷存档
│   ├── readers/                        # hash-linked 顺序读者状态
│   ├── events/                         # 写后完整观察与权威事件
│   ├── outline-revisions/              # 旧/新大纲与作者审批
│   ├── policies/ 与 calibration/        # 版本化强度策略与校准
│   ├── reopen-cases/ 与 outline-variants/ # 不可变 L1/L2/L3 搜索历史
│   └── checkpoints/                    # advisory 累计检查点
├── 正文/                               # HEAD 的单一接受版本投影
└── 追踪/                               # HEAD 的追踪快照投影
```

`正文/` 每章只能有一个接受版。旧稿、修订候选和失败版不得塞回 `正文/`；它们都在不可变修订库里。`正文/` 与 `追踪/` 可由 HEAD 重建；`check` 拒绝多余/缺失/篡改文件。`stage / certify / accept / replay / graph / hot-context` 都先确认投影与 HEAD 同代，旧投影不能继续产生新证书。崩溃或投影损坏后执行 `rebuild`，移出的额外文件保存在 `.story-quality/recovered-projections/`。投影根及每个写入目标的任一 symlink 组件都会被拒绝，不能借目录链接把重建写到项目外。

所有写操作使用操作系统文件锁；锁文件长期存在，只表示锁入口，不靠 PID 文本猜“陈旧锁”并删除，因此两个并发 writer 不会因删除/重建锁文件而同时进入临界区。

首次启用：

先按 `python3` → `python` → `py -3` 探测可用解释器；下文统一记作 `{PYTHON}`，不得假定 Windows 存在可用的 `python3`。

```bash
{PYTHON} scripts/quality_lifecycle.py init --project {项目根}
{PYTHON} scripts/quality_lifecycle.py check --project {项目根}
```

旧项目已有正文时，`init` 只做 `legacy_import`，并把第 1 章起标为待审；必须顺序 replay 后才能新写，不能把导入等同于质量验收。

## 每章事务

1. narrative-writer 把完整可读稿写到 `草稿/待验收/第NNN章_章名.md`，不写 `正文/`。
2. 准备同章 tracking JSON。新章用 `mode=append`；旧章用 `mode=revision`。
3. `stage` 把候选正文、细纲 hash、tracking 输入固化为 pending generation。旧章修订必须记录 finding IDs、影响区和 `local/structural/full`；结构/全文重写还要作者授权。
4. 缺陷 evaluator、修复者、整体 selector、最终 validator 四者全部隔离；六视角、两个 reader 和 judge 也各有唯一 run ID。P1 还把策略与 Reader v3 schema hash 固化进 pending。
5. 运行六视角深审，形成 `story-quality-review/v1` 包；每个视角绑定候选 revision、输入 fingerprint、实际读取单元和证据摘要，复审后六项都 PASS 才有资格接受。每条 finding 必须给正文证据锚和 `gate_impacts`；`causality / facts / present_action / mystery_legitimacy` 由对应视角 verdict 与未解决 finding **重新派生**，调用方填写的 `correctness_gate` 不能自报放行。
6. 修订必须逐一把 stage 时的 `finding_ids` 独立终验为 `FIXED_VERIFIED`，再盲化 A/B：隐藏新旧和顺序；任一改进维度变差、tie 或旧版胜即不可 accept，证书登记 `FIX_FAILED`。判断为“修复失败，重新诊断”，不能回写成 false positive。
7. writer 隔离的 extractor 在正文完成后做完整抽取。全部观察进冷库；明确/强暗示且可能影响后文的事实、信息来源、知识五态、关系、人物弧、承诺、开放问题、规则、例外进 occurred 事件账本。证书中的权威事件与本章 tracking timeline 必须双向一一覆盖；漏抽、重复绑定或多出任意一边都失败。行动前提还要追溯到前章或本章更早的 knowledge event；未来计划只能留大纲。
8. 至少两名独立顺序读者只读“接受正文 1..N-1 + 当前不可变候选 N”，输入绑定逐章 revision hash，不看细纲、作者真相和追踪答案；独立 judge 再用细纲 oracle 对比 `must_know / may_believe / must_not_know / open_ids`。P1 的决策 persona 至少两份独立证据，结构化位置、情绪与期待由程序重算强度状态。
9. `certify` 先确认 live 投影等于 HEAD，从接受 generation 的 tracking 快照验事件 ID，并核对 stage 时的 transaction digest；它只生成证书，不改正文。`accept` 先重算证书 packet hash，再用同一 pending/transaction/candidate/base generation 重跑完整证书绑定和事件双向覆盖，然后在临时代际里重跑字数、确定性质量与 tracking 事务。旧章 revision 还会在切 HEAD 前预读、校验并准备 checkpoint/benchmark 索引失效内容；索引损坏时整次 accept 在旧 HEAD 停止。全部通过后先落不可变 generation，再原子切 HEAD，最后重建投影。
10. `check` 通过，才可以汇报本章完成或开始下一章。

命令骨架：

```bash
{PYTHON} scripts/quality_lifecycle.py stage \
  --project {项目根} --chapter {N} \
  --candidate 草稿/待验收/第NNN章_章名.md \
  --tracking-input 草稿/第NNN章_tracking.json --kind draft

{PYTHON} scripts/quality_lifecycle.py certify \
  --project {项目根} --pending {pending_id} --input 草稿/第NNN章_review.json

{PYTHON} scripts/quality_lifecycle.py accept \
  --project {项目根} --pending {pending_id}

{PYTHON} scripts/quality_lifecycle.py check --project {项目根}

# 仅恢复 HEAD 投影，不改变接受历史
{PYTHON} scripts/quality_lifecycle.py rebuild --project {项目根}
```

显式 P0/P1 对照不是先写完再补凭证。两臂都要在落笔前冻结故事包、创作包、作者/writer/model、逐章可见上下文、reference/agent、预算和停止规则；P1 额外冻结细纲/reader oracle 与逐场因果拍。所有压缩、确定性扫描和定向修复先完成，最后才关闭：

```bash
{PYTHON} scripts/quality_lifecycle.py open-treatment-run \
  --project {项目根} --input 草稿/第NNN章_treatment-open.json

{PYTHON} scripts/quality_lifecycle.py close-treatment-run \
  --project {项目根} --run {treatment_run_id} \
  --input 草稿/第NNN章_treatment-close.json \
  --pass-a-body 草稿/待验收/第NNN章_plain-direct.md \
  --pass-b-body 草稿/待验收/第NNN章_voice-restore.md

# P0-control：一个创作候选，可附带已记录的确定性局部修复链
{PYTHON} scripts/quality_lifecycle.py close-treatment-run \
  --project {项目根} --run {p0_treatment_run_id} \
  --input 草稿/第NNN章_p0-close.json \
  --single-body 草稿/待验收/第NNN章_single-draft.md \
  --single-original-body 草稿/treatment/第NNN章_single-original.md \
  [--single-repair-body 草稿/treatment/第NNN章_single-repair-001.md]
```

P0/P1 每个生成步骤只允许一次创作尝试，正文不得超过冻结的 `max_visible_chars`；P0 每次局部修复逐稿存档，P1 A/B 分别绑定互异 writer run，B 必须绑定实际 A hash，writer/evaluator/selector 全互斥。随后 `stage --metadata` 必须带同一个 `treatment_run_id`；脚本只允许 P0 唯一稿或 P1 盲选胜出稿进入 pending。certificate 绑定完整 pending；accept 重新加载 closed run 并核对正文、章节、base、细纲和 start/close 边界。15 章 `workflow_run` 再从 run starts 重算 common-control、预算、版本、细纲与最终 accepted manifest。receipt 固定为 `SHADOW / non_enforced`：它证明工程边界可重算，不代表已经过真人校准，也不能单独开启生产 `ENFORCE`。

修订 `stage` 的 `--metadata` 至少含：

```json
{
  "finding_ids": ["LOGIC-003"],
  "impact_regions": ["场景2：人物决定到后果"],
  "repair_scope": "local",
  "author_authorization": null
}
```

默认只修 finding 及其直接因果上游/下游。相同 finding 再次出现时，review 包必须填写 `repair.rediagnosis`，不得自动升级全文重写。

P1 `strength_reopen` 不走 finding 修复：metadata 改为绑定 `revision_intent / reopen_case_id / reopen_arm_id / strength_certificate_sha256 / impact_regions / repair_scope`。L2 的边界授权和 L3 的逐案作者授权都不可省略，详见 `quality-p1.md`。

## 六个视角

| 视角 | 只回答什么 |
|---|---|
| `story-logic` | 动机、原因→行动→结果→后果、世界规则、风险是否成立 |
| `character-arc` | 性格/关系变化是否有触发、人物选择是否属于本人、弧线是否前进或有意义地抗拒 |
| `reader-comprehension` | 当前段落能否理解；指代、省略、视角、场景转换与信息先后是否让人迷路 |
| `reader-retention` | 第一处摩擦/弃读点、最强续读点、章尾期待、目标情绪是否收到、累计疲劳 |
| `prose-style` | AI 极简、省略过度、模板句、说明书对话、节奏与本书/题材声线；不得把一种句法偏好当通则 |
| `continuity` | 前文事实、知识来源、时间线、关系、伏笔与规则是否冲突 |

多 agent 输出仍按严重度合并、显式保留分歧，不做平均分。一个 LLM 的主观“我不想读”不能单独否决：只有一名 reader 非 pass 时顶层仍派生为 pass；至少两名非 pass 才派生 review；retention block 还必须有至少两名 cohort reader 对同一 `retention_issue_id` 独立同向，并各给可定位证据。

## 修订、失效与回放

接受第 K 章的新 revision 时，系统会把旧 K..M 的读者链、质量证书、事实/知识/关系/弧线重放结果和累计证书登记为失效。新 K 的本轮证书恢复为 fresh；K+1..M 必须从前往后 `replay`，不得跳章。

若重放发现旧 tracking 缺少 occurred 事件，replay 输入可附按章排序的 `tracking_transactions`（仅 `mode=revision`）；系统在临时快照中逐章应用该章 transaction，随后立刻验该章 packet，不会先把未来章事务全部灌入快照。全局事件 ID 归属首次发生章，后章变化必须新建事件 ID；检测到后章回写旧 ID 就停止并要求规范化。没有双向对账的关系/人物弧事件不能进入图谱。

每个 staged/certified policy hash 都必须有 `.story-quality/policies/{hash}.json` 不可变实体。新 `ENFORCE` 的启用章之前继续生成并保存 P0-compatible SHADOW policy；旧 v1 证书缺 policy hash 时，首次 replay 会补存兼容 policy 实体。这样后续再次修订旧章、第二次 replay 也不会因只剩 hash 而失去可解析策略。

失效只表示“需要重验”，不授权改正文。后续已接受正文保持只读；只有重放确认的新问题才能创建新的 revision candidate。

回滚也不是把文件倒回去：用 `rollback` 把某个已知旧 revision 作为新 pending generation，重新提供 revision tracking 事务和证书；accept 后仍产生新的 generation，历史不被抹掉。

## 累积失败与改纲

先把失败定位为 `prose_delivery / chapter_design / multi_chapter_structure / core_contract`。若确属大纲问题，保存旧/新 plan、作者批准、最早分歧章，执行 `record-outline-revision`，再从最早分歧章重建。禁止事后改目标，把已经失败的正文重新贴成 PASS。

累计 checkpoint 在第 3、5 章及后续每 5 章运行，始终 `advisory_only`。它可以发出重开/改纲建议，但不污染 correctness，不自动覆盖锁定大纲。旧章修订会使受影响 checkpoint、悬念债和结构 benchmark 失效并随新代际重算。
