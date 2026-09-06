# 顺序读者链、事件账本与人物图谱

启用 Reader Evidence v2、persona、绝对强度、累计 checkpoint 或 knowledge 五态时，同时读取 [P1 强度、重开与纵向验收](quality-p1.md)。

## 顺序读者状态

长篇不能把整本书一次塞给模型。每名 reader 从第 1 章顺序推进，每章状态通过 `previous_hash` 串联，只保存读者此刻真正记得、忘了、相信、猜测、感受到和期待的内容。输入固定为接受正文 1..N-1 加当前不可变候选 N，`source_scope`、`input_fingerprint` 和 revision 序列必须一致；不能读取细纲、追踪、作者真相或后续答案。

每章每名 reader 必填：

- `remembered / forgotten / believes / guesses`
- `emotion / expectation`
- `first_friction`：本章第一处理解或耐心摩擦；没有也要明确写“无”。
- `strongest_read_on`：最强继续读的具体位置与原因。
- `end_expectation`：读完最后一行后预期下一章发生什么。
- `target_emotion_received`
- `cumulative_fatigue`：不是只看本章，而是判断相似刺激、解释、谜语化叙事是否累积过量。
- `run_id / retention_verdict / retention_issue_ids / retention_evidence`：证明独立执行及同向问题；run ID 在本章所有角色、视角、benchmark、reader 与 judge 中全局唯一，两个不同名字或复用一次执行都不等于两份证据。

相似章节连续三章只触发审查，不自动 block。只有“没有新增信息/关系/选择/升级，且读者 cohort 出现实质疲劳”才阻断。

顺序 reader 不得中途凭空加入；新 reader 必须 `fresh_replay`。每 15 章至少增加一名 fresh reader，从第 1 章分批重放到当前候选；`replayed_revision_hashes` 与每批 hash 必须匹配真实 revision，不能用占位字符串。

## 独立 judge

细纲为每章提供两类 ID 与读者 oracle：

- `ending_beat_id`：本章落点，类型只选 goal/conflict/choice/relationship/payoff/aftermath/open_question。
- `expectation_id`：本章继续阅读理由，同一组类型；不强迫未解谜题或强悬念。
- `must_know / may_believe / must_not_know / open_ids`。

reader 不看这些答案。judge 在 reader 输出完成后独立比较：该懂的是否懂、允许误判的是否落在边界内、不可提前知道的是否泄露、开放问题是否仍以正确形式存在。

## 完整冷抽取与有界热投影

每章接受前，writer 隔离 extractor 扫完整正文：

1. 所有观察先入 `posthoc_extraction.observations` 冷库，不因“当前看似不重要”丢失。
2. 明确或强暗示且可能影响未来的项目入 `authoritative_events`：fact、knowledge_source、knowledge、relation、arc、commitment、open_question、rule、exception。旧 `knowledge_source` 保留；新 `knowledge` 才承载 knows/believes/suspects/misbelieves/denies 五态。
3. 每个 event 记录正文证据、`occurrence_state: occurred`、`tracking_event_id` 与 `tracking_event_fingerprint`；后者是同章 tracking event 的 `id/story_time/objective_fact/reader_knowledge/reveal_status/reveal_chapter/characters/kind/occurrence_order/knowledge` 规范 JSON 的 SHA-256。ID、发生章、事实内容必须同时匹配，且 authoritative events 与本章 tracking facts 双向一一覆盖；漏抽、重复绑定或额外事件都失败。全局 tracking ID 归属首次发生章，后章变化新建 ID，不回写旧事件。大纲中的将来计划不得混入。
4. 写下一章时只用细纲 dependencies 查询有界热投影：

```bash
{PYTHON} scripts/quality_lifecycle.py hot-context \
  --project {项目根} --dependencies 草稿/第NNN章_dependencies.json
```

dependencies 只列本章直接需要的 `event_ids / characters / kinds`。writer 不读完整冷账本，也不直接读作者侧全部答案。
HEAD 有 stale 时 hot-context 拒绝输出；结果硬限 128 个事件/64 KiB，超限须收窄 dependencies。

## 人物关系与人物弧图谱

关系变化用 `kind: relation`，`data` 至少提供 `subject / object / relation / before / after / trigger`；人物弧用 `kind: arc`，`data` 至少提供 `character / dimension / before / after / trigger`。角色不是一张静态标签卡：每个变化必须有发生章、触发事件和前后状态。

```bash
{PYTHON} scripts/quality_lifecycle.py graph --project {项目根}
```

输出 `nodes / relations / character_arcs`，可供 Dashboard、Mermaid 或其他可视化消费。`graph` 在任何旧章修订造成 stale 时拒绝返回，必须顺序 replay 后再读，避免 Dashboard 展示旧关系。图谱是接受代际事件的投影，不另建一套可手改“真相”。关系没有变化时不强造变化；人物弧允许停滞、反复和抗拒，只要叙事知道这是一种状态而非遗忘。
