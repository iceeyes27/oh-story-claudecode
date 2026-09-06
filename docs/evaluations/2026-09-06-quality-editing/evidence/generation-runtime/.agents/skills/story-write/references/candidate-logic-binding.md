# 候选逻辑证据绑定

`candidate_binding.schema_version` 必须为 `2`，`quality_profile` 为 `fanqie-long-v2`。`logic_checks` 使用对象键，禁止数组和未知 ID。

## 每章必需项

- `rc-01`：共享 `check-first-mention.js --json` 的确定性结果。
- `rc-02`：只读正文回答“本章前因能否指到已发布正文”。
- `rc-03`：只读正文回答“关键转折所需信息是否已经交代”。

只有第 15 章增加：

- `arc-01`：连读已采用 1～14 章与候选 15 章后生成完整 ledger。
- `arc-02`：共享 `arc-ledger.js --json --window=15` 的确定性结果。

第 3、5、10、14、16 章和第 15 章以后不因章号倍数触发 arc 采用门。

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

`rc-01` 另存确定性 JSON 的 `result_sha256`。第 15 章 `arc-01` 另存 `ledger` 与 `ledger_sha256`；`arc-02` 绑定同一 `ledger_sha256`、确定性结果 `result_sha256`、候选摘要及运行证据。

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
