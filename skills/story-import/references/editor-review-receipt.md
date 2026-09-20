# 独立编辑采用凭证

`candidate_binding.schema_version=4` 新增 `editor_review`；`logic_checks` 键集合不变。凭证校验器为 候选采用运行器中的 editor_review 校验模块，只验证声明、文件版本与程序条件，不证明充分阅读，也不是身份防伪机制。

```json
{
  "schema_version": 1,
  "policy_version": "independent-editor-v1",
  "status": "PASS",
  "source": "independent",
  "writer_run_id": "实际写手调用标识",
  "reviewer_run_id": "实际独立编辑调用标识",
  "candidate_sha256": "候选文件SHA256",
  "context_files": [{"path": "候选/第1章_门.md", "sha256": "文件SHA256"}],
  "passes": [
    {"kind": "comprehension", "files": ["候选/第1章_门.md"], "assessment": "具体理解结论", "evidence": [{"path":"候选/第1章_门.md","anchor":"候选中实际原句"}]},
    {"kind": "sentence", "files": ["候选/第1章_门.md"], "assessment": "具体文字检查结论", "evidence": [{"path":"候选/第1章_门.md","anchor":"候选中实际原句"}]}
  ],
  "findings": [],
  "signoff": {"candidate_sha256": "候选文件SHA256", "limitations": []}
}
```

两遍均完整覆盖实际上下文文件；实际范围包含候选及最近已有前章，可按需加入更早正文。支持卷目录；不许后文、规划、隐藏目录或链接目录。修订候选允许项目内任意候选路径，章号由调用方提供。

每个问题字段为 `id/path/anchor/impact/severity/critical/disposition/reason`。`severity` 为 `blocking/advisory/uncertain`；`critical` 为布尔值；`disposition` 为 `resolved/retained/unresolved`。未解决硬伤或关键待核实问题不能签发。非关键待核实问题必须写入签发限制。未解决问题的原句必须出现在指定正文；已解决问题保留初审原句，另提供 `original_evidence:{path,sha256}` 绑定项目内初审正文快照并定位原句，不要求它继续出现在新稿。

无独立调用时 `source=self_check,status=NOT_EVALUATED`，不得以写手身份签独立通过。作者明确豁免可附 `waiver:{chapter,candidate_sha256,author_approval,reason}`，保持原来源及 `NOT_EVALUATED`，验证结果单独为 `WAIVED`。豁免仍核验候选、上下文、章号和原话原因，不能把豁免写成阅读发生。

`rc-02/rc-03` 另须保存 `source=independent`、`reviewer_run_id` 和 `reading_kind=first_read|targeted_recheck`；读者标识须不同于写手及编辑，两项可以由同一读者完成。定向复核另存 `first_read_run_id`、`first_read_candidate_sha256` 及 `first_read:{path,sha256}`，引用项目内保留的初读 JSON receipt。原记录必须为独立首读，调用标识、读者身份及原候选摘要与引用一致，不能宣称再次首读。原有 rc/arc 证据要求不变。

`check` 只读；`promote` 持项目锁重新验证，耗时检查后再次核验编辑全部上下文。`--no-scan` 仅影响既有扫描，不跳独立编辑及读者条件。采用日志 v3 保存编辑快照、审核过程引用和结果，恢复在正文移动前和追踪提交前核验原事务与快照、候选及上下文。

保留的首读记录须含 `findings` 数组、非空 `prose_files`（包含原候选摘要匹配项）以及非空阅读证据。候选首读使用 `evidence:[{path,anchor}]`；修订首读使用非空 `observations`，每项含 `assessment` 与 `evidence`。证据路径须属于所存正文清单。只核验历史记录自洽，不要求旧稿现在仍存在；这些条件仅拒绝没有阅读内容的引用，不证明记录真实或充分。

当前及历史读者 receipt 均保存 `chapter` 与 `candidate_path`。当前路径必须为本次候选；首读历史路径必须是同章 `候选/第N章*.md` 或 候选修订目录内的 candidate Markdown 文件（路径形如：候选/_修订/rN-20位摘要/candidate.md），并与历史 `prose_files` 同一项的路径及候选摘要同时匹配。不得引用同一读者在其他章的首读。共用函数签名为 `validate_first_read(project, receipt, *, chapter)`。

尚未启动采用的旧候选须实际补审升级 v4。旧日志 v1/v2 的 `prepared/prose_moved` 普通恢复返回 `migration_required`，不改现场。作者明确授权后使用：

```text
python scripts/candidate-commit.py recover --project <书目录> --chapter N --legacy-operation-id <日志中的ID> --journal-sha256 <当前日志SHA256> --author-approval <作者实际原话> --reason <恢复原因>
```

四个授权字段及单章范围缺一不可。锁内按对应旧版本事务完整核验正文、读者视图、追踪版本及摘要后恢复；授权审计另存 `legacy-authorization-*`，记 `process_status=NOT_EVALUATED`（v1 日志另记编辑未评估），不升级旧事务或生成通过凭证。`tracking_committed` 仅完成旧归档，`done` 不追溯。事实或摘要冲突不能由授权绕过。

审核过程须同时遵循 [review-process.md](review-process.md)，采用绑定 v4 和采用日志 v3；既有 rc/arc 键不变。旧未启动候选不得补造过程记录。
