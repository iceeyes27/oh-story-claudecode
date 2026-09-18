# 阅读与编辑过程记录

行为协议与机器凭证分开：本记录只检查实际返回报告、版本、调用顺序声明与重要意见处置完整性，不证明模型阅读充分、身份真实或审美正确。只读审核只在会话返回结果，不要求写文件。生产采用使用以下固定结构，禁止自动补造原始报告。

候选 `candidate_binding.schema_version=4` 增加 `review_process:{path,sha256}`，指向书目录内 JSON。既有 editor receipt 与 rc/arc 键集合不变。过程 `schema_version=1,policy_version=review-quality-v2`。

```json
{
  "schema_version": 1,
  "policy_version": "review-quality-v2",
  "chapter": 1,
  "writer_run_id": "实际写手身份，与编辑凭证一致",
  "candidate_path": "候选/第1章_门.md",
  "candidate_sha256": "文件摘要",
  "prose_files": [{"path":"候选/第1章_门.md","sha256":"文件摘要","text":"实际读取正文完整文本"}],
  "reports": {
    "editor": {"path":"审核/编辑.json","sha256":"报告摘要"},
    "natural": {"path":"审核/自然首读.json","sha256":"报告摘要"},
    "diagnostic": {"path":"审核/回查.json","sha256":"报告摘要"}
  },
  "change": {"kind":"none","reason":"首次读者版本"},
  "dispositions": []
}
```

`prose_files` 是编辑和读者凭证实际输入文件的并集；各文件摘要一致，text 保存 UTF-8 原始文本（含原始换行/BOM），摘要以 UTF-8 字节计算。报告与正文版本不可覆盖，改稿使用新路径。冻结文本使旧阅读证据在正文修改后仍可定位，不要求旧稿仍在原路径。

三份报告均含：`role`（editor/natural/diagnostic）、`chapter`、`candidate_sha256`、实际 `run_id`、`reviewer_run_id`、编排实际 `started_order/completed_order`、`findings` 数组、`observations` 对象。序号来自真实任务分派/返回次序，不编造模型时间；编辑完成后才派首读，首读返回后才派诊断任务。三个 run_id 不同，读者两个任务保持同一阅读身份，编辑独立。诊断报告另存 `natural_report_sha256`，对应冻结自然报告。

每项 observation 为 `{assessment,evidence:[{path,anchor}]}`，必须含本次候选原句。编辑 observation 键精确为 `accuracy/clarity/naturalness/continuity`；自然阅读精确为 `understanding/engagement/confusion/skimming/reward_expectation`；诊断 observation 键精确为 `events/causes/turns/presence_space/objects/quantities_practice/repetition`，对应七问；不适用项写具体依据。自然报告另含 `reading_kind:first_read|targeted_recheck`。rc-02/03 或修订 reader receipt 的 run_id、阅读身份、reading_kind 对应当前诊断任务与自然报告。

报告 finding 为 `{id,important,impact,evidence:[{path,anchor}]}`，空数组合法。重要原始意见以 `报告run_id/问题id` 为全局标识；处置行 `{finding_id,decision,reason,evidence:[{path,anchor}]}` 必须精确覆盖本次与前版保留的重要意见。decision 为 `accepted/partial/rejected/pending/deferred`。处置不是解决；现有编辑硬伤门不受此记录放宽，不以趣味偏好阻止采用。

读者已参与后修改正文，`change.kind=minor|substantial` 并保存 `previous:{path,sha256}`，只指向前一次冻结过程。信息次序、理解、动机、场景节奏、兑现变化用 substantial，须新身份 first_read；意义不变的小改允许原身份 targeted_recheck（沿用首读凭证要求），或新身份 first_read。编辑阶段修改且尚无读者参与，用 none 并说明基准；不能凭此隐藏已发生读者意见。

当前过程核验前版引用、报告身份与摘要、重要意见 ID；历史链最多 64 版，仅遍历冻结写手、编辑和读者身份及版本，拒绝循环、A→B→A 冒充新首读，以及旧写手或编辑换角色充当新读者，不递归审美裁定、不读旧候选当前内容。新读者只收到正文，旧报告仅给协调器对照。

纯只读 API：`review_process.validate(project, chapter, candidate, reference, *, editor, readers, moved_to=None)`；返回 VERIFIED 或抛 `ReviewProcessError`。候选 check、锁内 promote、慢检查后、恢复前均调用。新采用 journal v3 保存引用和结果；旧 v1/v2 已启动事务需明确限定授权按旧协议恢复，报告 `process_status=NOT_EVALUATED`，不补签。旧未启动候选须真实完成新流程后升级 v4。
