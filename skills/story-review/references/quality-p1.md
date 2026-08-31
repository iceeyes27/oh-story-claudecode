# P1 强度、重开与纵向验收

本参考只在启用绝对强度、累计 checkpoint、多臂重开、结构对标或 P1 实验时加载。P0 的正确性、不可变代际、finding 修复与 blind A/B 仍以 [quality-lifecycle.md](quality-lifecycle.md) 为权威；本文件只增加正向交付，不降低任何 P0 底线。

## 1. 准确诊断与启用顺序

P0 已有正确性门和相对改进选择，不是纯缺陷扫描。P1 补的是“这章是否交付了与章节定位相符的正向阅读价值”的绝对强度契约。

严格顺序：

1. Reader Evidence v3、persona、policy/calibration 版本和中性实验契约；
2. persona 与累计 checkpoint 容器；
3. 临时项目 reference calibration 与误伤 controls，只跑 `SHADOW`；
4. L1/L2/L3 最小重开闭环仍在 `SHADOW` 验证；
5. 用 development 故事包形成并冻结阈值；若黄金三章属于基础 P1，只能在此阶段用 development 数据决定预算并冻结进完整 treatment；
6. held-out 只验收上一步冻结的完整 treatment，不得重调；真人验证、误伤 controls 和重开出口都通过，才允许生产 `ENFORCE`；held-out 后新增黄金三章或其他 treatment 组件必须升为 P1.1 并重新走 held-out；
7. 自动细纲搜索保持 instrument-only，结构对标保持 diagnostic/nonblocking；长周期验收、knowledge 和悬念债可在不改变 treatment 的前提下逐步接入；
8. 补完跨阶段去重与功效审计后，再由多个全新 held-out 故事包复现，才可声称系统层提升。

完结书前 15 章只可作为 `reference_instrument`：必须复制到临时项目，标记 `causal_baseline: false`、`production_thresholds: false`。它不能充当 P0 因果对照，也不得修改真实书。

完成状态拆开报告，不能互相冒充：

- **工程闭环完成**：模板/解析/门/receipt/回放能在隔离项目确定性重算，测试与共享副本一致；这是一项可关闭的工程目标。
- **探索性实验完成**：至少一个新故事包的配对盲读跑通，只能报告该包结果，不得产品放行。
- **系统层实验声称**：跨阶段去重/功效审计完成，且多个预注册 held-out 新故事包复现后才成立。它是后续研究目标，不反向阻塞工程闭环关闭。

## 2. 版本化策略

`quality_lifecycle.py init` 默认安装 `p0-compat-shadow-v2`。策略保存为不可变 `.story-quality/policies/{sha256}.json`，`POLICY.json` 只指向当前策略；每个 pending 又固化完整策略及 hash，后续切策略不能改写已 staged 证据。

```text
strength_mode: SHADOW | ENFORCE
strength_status: PASS | FLAT | INSUFFICIENT_EVIDENCE

selection_status:
  ACCEPT_CANDIDATE
  REOPEN_REQUIRED
  EVIDENCE_REQUIRED
  FIX_FAILED
  REJECTED
```

- `SHADOW` 仍计算和保存真实 `strength_status`，但不改变 P0 accept。
- `ENFORCE + PASS` 才能进入正常选择。
- `ENFORCE + FLAT` 派生 `REOPEN_REQUIRED`。
- `ENFORCE + INSUFFICIENT_EVIDENCE` 派生 `EVIDENCE_REQUIRED`；必须补足独立证据或交作者人工复核，不得默认放行、也不得冒充 `FLAT`。
- `PASSED_BUT_FLAT` 只是人类可读标签，不是持久状态。

生产 `ENFORCE` 要引用 `held_out_validation` calibration；校准必须至少含多故事包、真人验证、低压/余波/有意多解/安静转场 controls，并证明 L1/L2/L3 有合法出口。布尔声明本身不是证据：故事包正文/细纲原文、真人原始观察、四类 control 读者结果、项目真实 CASE 树历史和阈值推导都先用 `record-evidence-bundle` 保存为不可变 artifact；生命周期 receipt 给出不可由输入覆盖的接收时间，calibration 只能引用这些 hash。真人导入必须携带原始观察对象及其重算 hash，calibration 的逐章 observations 必须逐项来自同一导入包。

阈值不再读取原始观测中的 `minimum_*`，也不对所有指标一律取 `min()`。统一使用 `directional-reader-story-quantiles-v1`：先把同一 reader×story 的 15 章重复观察折叠为一个单元，再按每项预注册的方向和分位数计算 story 内估计，最后等权汇总故事包。正向下限取 min 会放松读下去/情绪/置信要求，风险触发阈值取极值又可能把门收得过紧；两者都不是校准。development 产出并冻结 `threshold_spec + thresholds`，held-out 只能接受或拒绝；任何改算法、方向、分位数、persona 或预算都必须升版本并换新的 held-out 数据。

仓库没有非 synthetic 真人数据时，准确状态只能是 `UNCALIBRATED / SHADOW`。fixture、LLM 代理、完结书 reference instrument 和一次隔离 smoke 均不得被表述成真人校准。

```bash
{PYTHON} scripts/quality_lifecycle.py record-evidence-bundle --project {项目根} --input evidence.json
{PYTHON} scripts/quality_lifecycle.py record-calibration --project {项目根} --input calibration.json
{PYTHON} scripts/quality_lifecycle.py configure-policy --project {项目根} --input policy.json
```

`configure-policy` 会逐项核对 policy 的 thresholds、function rules、persona profiles 与 calibration 完全一致；`ENFORCE` 只能从下一未写章或更晚的章号启用。启用点之前的旧章继续使用 P0-compatible `SHADOW`，旧证书 replay 使用证书原先绑定的 policy hash，不能被新阈值追溯改写。

## 3. Reader Evidence v3

persona 是可组合证据维度，不是三个互斥标签：

- `genre_familiarity: low | medium | high`
- `reading_history: fresh | sequential | full_prefix`
- `evidence_type: llm_proxy | human`

persona profile 必须以 `persona_profile_sha256` 绑定。任何拥有否决或重开权的 persona 至少两份独立同向证据；策略可按 persona 限定允许的 evidence type。LLM 只作逐章代理，正式 P0/P1 终验必须由 held-out 真人完成。

v2 只保留为历史 `reference_instrument / SHADOW` 输入；`ENFORCE` 必须使用 v3。每名 reader 在文本观察外增加：

```json
{
  "reader_schema": "story-reader-evidence/v3",
  "persona_id": "core-reader",
  "persona_profile": {
    "genre_familiarity": "high",
    "reading_history": "sequential"
  },
  "persona_profile_sha256": "...",
  "evidence_type": "llm_proxy",
  "measurements": {
    "first_friction": {
      "present": true,
      "scene_id": "scene-1",
      "scene_index": 1,
      "start_offset": 120,
      "visible_ratio": 0.08,
      "kind": "comprehension",
      "severity": 3,
      "recovered": false,
      "quit_intent": true,
      "evidence_anchor": "..."
    },
    "strongest_read_on": {
      "scene_id": "scene-3",
      "scene_index": 3,
      "start_offset": 1480,
      "end_offset": 1600,
      "function": "choice-consequence",
      "intensity": 4,
      "confidence": 0.8,
      "evidence_anchor": "..."
    },
    "end_expectation": {
      "expectation_ids": ["EX-01-003"],
      "hypothesis_ids": ["H-A"],
      "confidence": 0.8,
      "free_text": "..."
    },
    "target_emotion": {
      "target_id": "EMO-01-003",
      "observed_emotion": "期待",
      "intensity": 4,
      "confidence": 0.8,
      "received": true
    },
    "cumulative_fatigue": {"level": 1, "delta": 0, "reason": "..."},
    "cumulative_confusion": {"level": 2, "delta": 1, "reason": "当前目标连续两章不清楚"},
    "mystery_fatigue": {"level": 1, "delta": 1, "reason": "新增谜团没有当前行动锚"},
    "first_quit_chapter": 4,
    "continued_by_choice": true,
    "continued_for_study": false
  }
}
```

正文 offset 和 ratio 由冻结候选重算。`first_quit_chapter` 一经出现不得后移或抹去；自然弃读后继续完成研究任务时必须标 `continued_for_study=true`、`continued_by_choice=false`，不能把实验强制阅读洗成自然留存。checkpoint 从已接受 reader hash 链派生首次弃章、累计混乱、谜语疲劳与总体疲劳，调用方不能另交一份更好看的累计表。不得把自由文本、单一布尔值或字符串相似度直接接进硬门。

### 3.1 P1 写作 treatment，而非“更多门”

用 `C` 表示同一冻结创作包：题材/角色/细纲目标、writer/model 身份、可见上下文、字数预算和停止规则一致。

- `P0-control = C + single draft`：只生成一个创作候选；允许与 P1 相同的确定性 correctness 修复，但必须记录唯一 generation attempt、finding、before/after body hash 和修复次数，不得另写备用稿或隐藏重采样。
- `P1-treatment = C + causal preflight + plain_direct A + constrained voice_restore B + blind selection`。

P1 的因果预检必须逐行绑定 `scene_catalog`，明确人物目标、已知依据、原因/触发、行动/选择和可见结果；缺项直接回到细纲，不在正文里用解释性旁白补洞。Pass A 是简单平直但可发表的完整正文；Pass B 只恢复人物声线、潜台词与节奏，不得改变因果拍、事实、事件顺序、POV 和 reader oracle。A 必须单独通过 `causal_spine / current_action_clear / scene_grounded / pov_stable / characters_distinct`，同时不得有 `explanation_bloat / voice_loss`；B 另由隔离 evaluator 检查，再隐藏标签盲选。B 不合格或不胜就保留 A。

P0/P1 都在正文落笔前 `open-treatment-run`，逐章冻结故事/创作包、作者/writer/model、可见上下文、reference/agent、预算和停止规则；P1 额外冻结细纲/oracle 与因果拍。P1 显式调用两个 narrative-writer：A 使用 `quality_treatment_mode=P1/pass=A`，B 使用 `quality_treatment_mode=P1/pass=B` 并绑定实际 A hash 和五项 invariants；A/B writer run 互异，且与两名 evaluator、selector 全部隔离。P0 使用 `P0/single_draft`。两种 treatment 每步都只允许一次创作尝试，并执行冻结字数上限；压缩、扫描和定向修复全部在关闭前完成。`close-treatment-run` 冻结 P0 原稿及逐次修复版本，或 P1 A/B 正文与盲选；关闭后需再改就换新 run。certificate 绑定 pending，accept 重新加载 run 后才写入代际。题材兴趣单独记录，不进入正文胜负。receipt 固定 `SHADOW / non_enforced`，不是 agent launcher，也防不了同一主体蓄意造假；作用是防误接、复制粘贴和事后改口径。

## 4. 章节强度契约

新细纲增加单行、机器可读的 `P1质量契约`：

```text
- P1质量契约：{"chapter_function":"推进","target_emotion_id":"EMO-01-003","required_deliveries":["choice-consequence"],"allowed_expectation_ids":["EX-01-003"],"allowed_hypothesis_ids":["H-A","H-B"],"intentional_ambiguity":false,"scene_catalog":[{"scene_id":"scene-1","scene_index":1},{"scene_id":"scene-2","scene_index":2}]}
```

强度服从 `chapter_function`，不是四项统一 AND：低压章可以靠关系回收、恢复、信息增量或转场交付；余波章不强迫强悬念；有意多解允许不同 hypothesis，只要仍落在 `allowed_hypothesis_ids`，并识别到允许的 expectation function。

`scene_catalog` 由冻结细纲的“情节点序列表”确定性生成：第 N 行固定映射 `scene-N / scene_index=N`，数量与顺序必须完全一致；增删或重排情节点后重算，不得照抄模板固定场景。旧纲未启用 P1 时，outline checker 默认兼容；显式 P1 流程使用 `--require-p1`，字段存在即完整校验。reader 的摩擦点和最强续读点必须引用这张表，不能让两个实际区域都自报 `scene_index=1` 伪造“±1 场景”共识。`first_friction` 的正文前 15% 只是校准观测。只有同 persona 至少两名 reader 同向报告“早期、严重、未恢复、确有弃读意图”，才形成强度风险；生产性压力不等于坏摩擦。

## 5. 不可变重开

平庸不是 finding。新增：

```text
revision_intent:
  defect_repair
  strength_reopen
  rollback
```

`defect_repair` 继续逐条绑定并终验 finding。`strength_reopen` 绑定原 FLAT 证书、reopen case 和选中 arm，finding IDs 必须为空；不得把平庸伪装成缺陷。

- L1：证据能定位到局部区域时，单臂局部重写。
- L2：细纲不变，2–3 个等预算、同停止规则的正文臂；任何场景取舍、信息顺序等搜索必须事前取得边界明确的作者授权或预授权。
- L3：2–3 个不可变细纲变体，各有正文；章节切分、事件顺序、POV 等逐案取得作者授权。胜出 outline 先走 `record-outline-revision`，再成为 live 细纲，之后才可 stage 正文。

所有 arm、outline、选择器输入、随机顺序和失败结果都保留。每个 arm 都要由相互隔离的 writer、evaluator 和 reader runs 复算独立 strength gate；reader 原始 JSON、正文与派生 gate 都复制到 case 的不可变 artifact 树，resolve 时从这些存档重新读取、验 hash、重算，不依赖已经删除的输入文件。selector 输入同时绑定正文/细纲 hash 与该强度证书。选臂后还需另一组 held-out reader import；其每名读者必须盲看全部 arm，原始观察逐项绑定 arm hash，并由多数结果派生 winner/all-flat，才可把 PASS 臂交给最终章级 review。任何 reserved run ID 都不得在最终六视角、judge 或 validator 中复用。

只有“P0 已过且 strength=FLAT”能开重开 case。`SHADOW` 可以完整演练重开，但 request 必须显式 `simulation_only: true`，证据必须标记 synthetic，产物永远不能推进 accepted HEAD。生产 case 则必须来自 `ENFORCE + REOPEN_REQUIRED`，使用非 synthetic 真人终验。L1 全败只提出 L2；L2 全败只提出 L3；L3 request 必须绑定这个 all-flat L2 parent，不能直跳。L3 全败登记设计问题，不自动覆盖锁定大纲。

```bash
{PYTHON} scripts/quality_lifecycle.py open-reopen --project {项目根} --input request.json
{PYTHON} scripts/quality_lifecycle.py record-reopen-arm --project {项目根} --case {case} --input arm.json --body {正文} [--outline {细纲}]
{PYTHON} scripts/quality_lifecycle.py resolve-reopen --project {项目根} --case {case} --input decision.json
```

## 6. 累计 checkpoint

调度为 `{3, 5} ∪ {10, 15, 20...}`。checkpoint 绑定 generation、1..N revision 序列、reader state hashes 与独立 run IDs；它是 `advisory_only`，不污染 correctness，也不复用会阻断写作的 semantic stale。

旧章修订仍会把受影响 checkpoint、悬念债和结构 benchmark 标记 stale，随后按新 generation 重算。alert 只能给 `reopen_recommendation / outline_review_recommendation / observe`，不能自动改纲。

长期附件的判定：

- 人物：比较“选择 + 理由链”是否体现稳定内核，同时明确允许合理意外；不追求最大可预测性。
- 记忆：分自由召回、提示召回、最近两章近因；不强求精确台词。
- 情绪：比较计划与实测的送达和转折，不要求机械复刻；意外但更好的效果交 selector。
- 悬念债：从 accepted `open_question` 事件派生，状态为 open/payoff/paused/superseded；`planned_payoff_chapter` 可未知，`age` 动态计算。

## 7. Knowledge 五态

保留历史 `knowledge_source`，新增 `kind: knowledge`，不重解释旧事件。tracking timeline 与质量事件同时记录：

```json
{
  "character": "甲",
  "fact_id": "FACT-door",
  "state": "knows|believes|suspects|misbelieves|denies",
  "source": "乙当面告知",
  "source_chapter": 3,
  "source_order": 1,
  "occurrence_order": 2
}
```

`knowledge_prerequisites` 只管硬规则：被用作行动前提的信息，必须追溯到更早的 knowledge event。合法来源可以是前章，也可以是本章更早场景；来源在行动之后或缺失即 correctness 失败。tracking fingerprint 同时绑定 kind、章内 order 与 knowledge 数据。

## 8. 细纲搜索、结构对标和黄金三章

`record-outline-search` 只接受 2–3 个 hash 绑定的结构变体；输入必须显式 `instrument_only: true`。代理 evaluator 必须与生成隔离，只能 shortlist。当前 recorder 尚未绑定 CASE、base generation、live outline revision 与最终正文，因此不能充当 L3 出口或写作硬门；要阻断必须另立完整 provenance 工程。

`record-structural-benchmark` 只比较题材和结构位置归一化后的事件密度、信息释放、章尾类型分布、情绪强度、对话/叙述比。必须声明 `diagnostic_only: true`、`blocking: false`，且句子、具体桥段、专名比较全部关闭。

`record-golden-three-plan` 当前明确是 `plan_only: true / execution_ready: false`：只登记由 development calibration 推出的臂数、预算、停止规则和 preregistration，不证明生成、selector、held-out treatment 绑定或执行闭环。真正接入前不得硬编码“3 个细纲 × 2 个正文 = 6 臂”；若它属于基础 P1，须另补执行 provenance 并在 held-out 前冻结，held-out 后新增则升为 P1.1 重新验证。

## 9. 实验 v2 与正式结论

`check-experiment` 同时兼容 v1 和 v2。v1 只返回 `historical_shadow_only / BLOCKED_LEGACY_SCHEMA`，即使 candidate 获胜也永不构成放行证据。v2 可中性保存 P1 胜、P0 胜或 tie，但当前 `product_release_pass` 恒为 false，`check-system-experiment.system_pass` 也恒为 false：跨阶段 participant/content 去重与可重算功效审计尚未完整实现，schema 的最小人数不能冒充产品放行。winner 和多包结果只作研究信号。

真正 P0/P1 双臂必须共享同一冻结创作包、作者/writer/model 身份、逐章可见上下文和 `shared_max_visible_chars`，只改变上文定义的 workflow treatment；两臂都必须引用 `workflow_run` evidence，逐章输出 hash、预算、停止规则和 treatment 由生命周期 receipt 冻结，legacy/reference 原文不能冒充 P0 因果臂。预注册不是实验 JSON 内的事后字段：必须在 workflow receipt 与真人导入之前，用 `record-experiment-preregistration` 单独落盘。它固定故事包证据、精确样本量、禁止事后扩样、命名纳排规则、分配算法与随机种子承诺、两臂顺序配平、多臂预算、共同字数上限、停止规则、主要终点、主分析及重复阅读污染处理。实验再按 preregistration hash 引用；`artifacts_frozen_at` 与 `observations_completed_at` 必须分别等于真实 workflow/human-import 接收时间且不得在未来，实际纳入/排除 reader 必须完整对账。正式 reader 行只能引用已记录的 `human_reader_import`，其盲序、逐章观察、偏好和理由必须与原始导入完全相同。

`accepted_lifecycle workflow_run` 会从 15 个实际关闭的同 treatment run 重算输出、时间、停止规则、treatment version、实际预算、逐章细纲、common-control 与身份摘要，并与故事包及最终 accepted manifest 交叉核对；实验 arm provenance 只能引用该 receipt。P0 逐章引用 `single_draft`，P1 引用 A/B 胜出稿。外部自报、只关闭未接受稿或关闭后改正文都会被拒绝。P0/P1 同级边界仍固定 SHADOW，不等于真人收益证据。

```bash
{PYTHON} scripts/quality_lifecycle.py record-experiment-preregistration --project {项目根} --input preregistration.json
{PYTHON} scripts/quality_lifecycle.py check-experiment --project {项目根} --input experiment-v2.json
{PYTHON} scripts/quality_lifecycle.py check-system-experiment --project {项目根} --input system-experiment.json
```

严格多数按全部已纳入 reader 计算，tie/弃权不能从分母删除；效果报告以 reader 为独立单位给偏好率和预注册置信界限。小 persona 组（例如每组 n=4）的 3/4 或 4/4 反向偏好只能触发复审，不能直接硬判 P1 失败：在真实等价、独立且 p=0.5 的简化假设下，单个 n=4 组出现至少 3 票同向的概率是 5/16，三个组至少一组触发约 67%，硬否决会被噪声频繁触发。若要作否决，必须预先做功效/误报设计并扩大样本。

单一故事只能证明该作品。先在两个隔离临时项目用同一冻结创作包各跑 P0/P1 10–15 章，作者按整臂随机顺序自然阅读；首次弃读、逻辑断裂、累计混乱、谜语疲劳、说明膨胀和 voice loss 只作 development no-go，不入样本、阈值或胜负。修完 no-go 后冻结新 treatment/故事包版本，并在生成真人 pilot 新双臂、接触真人之前预注册；作者自读双臂不得直接转作 pilot。至少两名真人的探索性 pilot 只能验证流程、明显问题和访谈信号，必须报告 underpowered，不能声称 treatment 有收益。

held-out calibration 已机器拒绝复用 development 的故事包 ID、创作包、正文/细纲 hash、reader ID、blind code 和原始观察 hash。需要对外声称时，还必须补齐 pilot/held-out/formal 全阶段登记与功效审计；在此之前 formal 只能保存描述性结果，不能产生 release/system pass。完成该工程后，formal 才能使用全新故事包与真人，并按预注册端点的功效设计决定样本。
