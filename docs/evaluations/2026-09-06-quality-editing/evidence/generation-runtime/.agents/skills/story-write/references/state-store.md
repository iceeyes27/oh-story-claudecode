# state-store.md：结构化状态库（实验性旁路）

Markdown 追踪文件回答不了两类问题：**「第 N 章那一刻的世界状态是什么」**（追踪文件只有当前值，历史被覆盖）和**「全书有没有机器可查的状态矛盾」**（死亡角色复活、伏笔未埋先收）。状态库用按章分片的 JSONL 事件流补这两个能力。

**定位：旁路，不替代**。`追踪/伏笔.md`、`追踪/角色状态.md` 仍是权威追踪文件，流程照旧；状态库是它们的机器可查影子。稳定性审计（grep 正文那套）也不依赖它。状态库缺失或滞后不阻塞任何流程。

## 存储：分片 JSONL（单文件不膨胀）

```
追踪/状态库/
  事件_第001-050章.jsonl
  事件_第051-100章.jsonl
  ...
```

每行一个 JSON 事件，**按 50 章一片自动分文件**——500 章的书也只是 10 个小文件，每片约几百行，git diff 是逐行追加、人可读。不要手工挑文件写：`add` 命令按 `ch` 自动路由到正确分片（放错分片 `check` 会报 `Shard_Mismatch`）。

## 事件格式（三种）

```jsonl
{"ch":12,"type":"状态","entity":"林岚","field":"位置","value":"营业厅"}
{"ch":30,"type":"状态","entity":"陈叔","field":"存活","value":"死亡"}
{"ch":12,"type":"认知","entity":"林岚","learns":"账单被人动过"}
{"ch":12,"type":"伏笔","op":"埋设","id":"F001","desc":"陌生号码警告","due":30}
{"ch":30,"type":"伏笔","op":"回收","id":"F001"}
```

- **状态**：实体某字段的新值（位置/身体/能力/持有/关系:某人/**存活**……字段名自定，同名字段后值覆盖前值）。`存活` 是特殊字段：值为 `死亡` 后该实体再有事件即矛盾（先写复活事件才能解除）。
- **认知**：实体在第 ch 章获知某信息。回答"角色 A 到第 N 章为止知道什么"——认知边界审查的数据源。
- **伏笔**：`op` ∈ 埋设/推进/回收/废弃；埋设必带 `desc`，`due`（预计回收章）可选但建议写——超期未收会被 `check` 提醒。
- 可选 `note` 字段放备注。值全用**可 grep 的具体词**（同 character-invariants.md 选词规则）。

## 写入时机

每章过完漂移门控、更新追踪文件的同一时刻，把本章 State Delta 里的条目翻译成事件写入（一条 Delta 一般对应 1-2 个事件）：

```bash
node .agents/skills/story-write/scripts/state-query.js add '{"ch":12,"type":"状态","entity":"林岚","field":"位置","value":"营业厅"}'
```

只录**会被后文引用的硬状态**（生死、位置跃迁、能力获得、关键持有物、关系定性、关键信息获知、伏笔操作），不录情绪、氛围、一次性细节——那些是散文性上下文，留在 Markdown 里。每章通常 2-5 条，多了说明录得太细。

## 查询

```bash
node .agents/skills/story-write/scripts/state-query.js snapshot 47                # 第 47 章时点的全量快照
node .agents/skills/story-write/scripts/state-query.js snapshot 47 --entity 林岚  # 单实体：状态+已知信息
node .agents/skills/story-write/scripts/state-query.js foreshadow 47              # 第 47 章时点活跃伏笔（含超期标记）
node .agents/skills/story-write/scripts/state-query.js log --entity 陈叔          # 实体全事件时间线
node .agents/skills/story-write/scripts/state-query.js check                      # 全库矛盾检测，FAIL 退出码 1
```

用法场景：

1. **回炉老章节**：改第 47 章前先 `snapshot 47`，拿到当时的世界状态和角色认知边界，而不是被"当前值"误导（第 90 章陈叔已死，不代表第 47 章他死了）。
2. **写新章前**：`snapshot {N-1} --entity {本章出场角色}` 作为交接包的补充数据源。
3. **批量验收时**：`check` 与 `stability-audit.js` 并跑；`check` 管事件流自洽（时间线矛盾），审计管正文与承诺字面一致，互不重叠。

## 矛盾检测规则

| code | 级别 | 判定 |
|------|------|------|
| `Dead_Entity_Active` | error | 实体 `存活=死亡` 后仍有状态/认知事件 |
| `Foreshadow_Not_Planted` | error | 伏笔未埋设就推进/回收/废弃 |
| `Foreshadow_Double_Plant` | error | 同 id 未关闭就再次埋设 |
| `Foreshadow_After_Close` | error | 已回收/废弃后又操作（含重复回收） |
| `Shard_Mismatch` / `JSON_Invalid` / `Event_Invalid` | error | 分片错位 / 坏行 / 缺必填字段 |
| `Foreshadow_Overdue` | warning | 活跃伏笔已过预计回收章 |
| `Knowledge_Duplicate` | warning | 同实体重复获知同一信息 |

error 阻塞（退出码 1），修复方式通常是补写遗漏事件或修正错误事件行；warning 只提醒不阻塞。

## 与 Markdown 追踪文件不一致时

以正文为准 → 修 Markdown 追踪文件 → 再补/改状态库事件。状态库的事件行可以直接编辑（它是文本），改历史事件后重跑 `check` 确认自洽。
