# 候选逻辑证据绑定

`candidate_binding.schema_version` 必须为 `2`，`quality_profile` 为 `fanqie-long-v2`。`logic_checks` 使用对象键，禁止数组和未知 ID。

## 每章必需项

- `rc-01`：共享 `check-first-mention.js --json` 的确定性结果。
- `rc-02`：只读正文回答“本章前因能否指到已发布正文”。
- `rc-03`：只读正文回答“关键转折所需信息是否已经交代”。

## 每 15 章增加（滚动 arc 连读）

章号是 15 的整数倍时（15、30、45…）必须增加：

- `arc-01`：连读第 `N-14`～`N` 章后生成完整 ledger（最后一章是当前候选，其余是已采用正文）。
- `arc-02`：共享 `arc-ledger.js --json --start=N-14 --window=15` 的确定性结果。

窗口是**刚写完的这 15 章**，不是累计到第 N 章。第 15 章的窗口是 1～15，与旧行为完全一致；第 30 章的窗口是 16～30，第 45 章是 31～45，互不重叠。这样判的是「读者从上一个体检点读到这里，悬念收支和主线推进如何」——用累计口径的话，任何长线伏笔都会让 `netOpen` 单调增长，门会退化成每次必报。

窗口前埋下的环仍会登记，所以本窗口闭掉一个 30 章前的旧环算作正常闭环、按真实跨度计入平均延迟，不报「引用不存在的 open」；这些旧环不计入本窗口的 `openCount`，未闭的数量单列为 `carriedPending`，只作伏笔债务参考，不参与阈值裁决。

其余章号（第 3、5、10、14、16、29 章等）不触发 arc 采用门；这些章的 `logic_checks` 出现 `arc-01`/`arc-02` 属于非法键集。

触发章还要求 `正文/` 完整包含第 1～`N-1` 章：ledger 是连读产物，缺章就不是连读。

第 3/5 章及单元结尾的建议性连读、每章趣味反馈见 `reader-first-writing.md`。这些反馈不增加 `logic_checks` ID，不以缺失或主观偏好阻断采用；实际未运行时明确报告未评估，不能用本文件的 hash 检查代替阅读效果证据。

## 语义 receipt

`rc-01/02/03` 与 `arc-01` 都必须包含：

```json
{
  "run_id": "本次审阅唯一值",
  "status": "pass",
  "findings": [],
  "evidence": [{"path": "正文或候选的项目相对路径", "anchor": "可定位证据"}],
  "candidate_sha256": "候选正文摘要",
  "prose_files": [{"path": "实际读取的项目相对路径", "sha256": "文件摘要"}],
  "prose_set_sha256": "按规范化路径排序后的文件集合摘要"
}
```

`prose_files` 必须逐个列出实际读取的已采用正文、当前候选及存在时的 `正文/_已知实体.txt`，不能只保存报告摘要。`prose_set_sha256` 对每行 `path + NUL + sha256` 按路径排序后以换行连接，再计算 SHA-256。`evidence` 必须非空；每项 `path` 必须属于 `prose_files`，`anchor` 必须是对应正文中可直接定位的非空原文。

`rc-01` 另存确定性 JSON 的 `result_sha256`。触发章的 `arc-01` 另存 `ledger` 与 `ledger_sha256`，`ledger.chapters` 按章号严格递增，窗口段必须整段覆盖第 `N-14`～`N` 章，不得出现第 `N` 章之后的章；本窗口若闭掉更早埋的环，把那个环的开启章一并列进来即可（窗口前的章只用于登记 open，不计入本窗口收支）。`arc-02` 绑定同一 `ledger_sha256`、确定性结果 `result_sha256`、候选摘要及运行证据。

> `arc-ledger.js` 的报告新增 `start`/`end`/`carriedPending` 三个字段，所以 `result_sha256` 的取值与滚动窗口上线前不同。上线前准备、尚未采用的第 15 章候选需要重跑 `arc-02` 并重新绑定，不能沿用旧摘要。

## Arc 作者批准

`arc-02` 复验为 blocking 时默认拒绝采用。作者明确批准后，receipt 使用 `status: blocking-approved`，并增加：

```json
{
  "override": {
    "approved_by_author": true,
    "result_sha256": "当前 arc-02 结果摘要",
    "reason": "作者给出的具体理由"
  }
}
```

候选、已采用正文或 ledger 任一变化都会使批准失效。
