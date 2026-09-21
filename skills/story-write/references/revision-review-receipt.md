# 普通修订的独立审核记录

`revision-commit.py prepare` 生成 `ordinary-revision/v3` 冻结提案。新旧正文、差异与事实连续性仍用既有 review-template 字段；另外填写 `editor_review`、`reader_review` 和 `review_process`，不能用看过旧稿、后文或细纲的连续性复核代替正文盲读。

`review_process: {path, sha256}` 引用 [review-process.md](review-process.md) 的真实过程记录。自然首读先实际返回，再派发核查任务；重要意见须有处置。实质理解、动机、信息次序或场景节奏修改需要新读者；不改变意义的小改可定向复核。过程校验只验证记录完整与版本绑定，不决定文学优劣。

## 编辑

`editor_review` 严格沿用 [editor-review-receipt.md](editor-review-receipt.md)。当前文件绑定本次 候选修订目录内的 candidate Markdown 文件（路径形如：候选/_修订/{operation}/candidate.md），并绑定实际读取的此前正文；编辑先完整理解，再核查句段。已批准的豁免与自查来源分别记录，不生成独立 PASS。

## 读者

`reader_review` 的字段为：

- `reader_review.schema_version = 1`、`source: independent`、`status: PASS`：仅实际独立审读完成且没有未解决的关键理解问题时填写；未执行保留 null/待审，check 不会通过。
- `run_id`、`reviewer_run_id`：本次实际执行和审读者身份；审读者不能是编辑或写手。
- `chapter`、`candidate_path`：本次章号与冻结候选相对路径；初读记录同样保留这两个字段，定向复核只能引用同章旧版。
- `reading_kind: first_read | targeted_recheck`。初读不看旧稿、差异、后文或修改意图；定向复核保留初读，不能当作新读者首次理解。
- 定向复核追加 `first_read_run_id`、`first_read_candidate_sha256`、`first_read: {path, sha256}`。引用实际保留的首次阅读 JSON；其 run_id、reader 身份、旧稿摘要及 first_read 类型都须一致。不要为通过检查补造历史记录。
- `candidate_sha256`：本次冻结新稿摘要。
- `prose_files: [{path, sha256}]`：当前冻结新稿与实际阅读的此前正文，含存在时的最近前章。不得混入正式正文里的旧版当前章、后文、其他候选或设计材料。
- `observations` 恰好包含 `understanding`、`friction`、`reward`、`read_on`。每项都有非空 `assessment` 及 `evidence: [{path, anchor}]`，至少一条出自当前候选；其他证据只能出自上述已读正文。没有摩擦也明确说明依据，不为凑问题改文。
- `findings`：真实问题数组，可空；每项含 `id/path/anchor/impact/severity/critical`。原句须定位到已读文件；`severity` 为 advisory、blocking 或 uncertain。blocking 及关键问题不得签 PASS；非关键项必须明确 `critical: false`，并在意见中说明限制。

读者用自己的话复述事件、理由与转折，再说明阅读摩擦、所得和续读期待。模型代理与真人来源如实披露，摘要和身份声明不能证明理解已经发生。

## 版本与恢复

check 只读；accept 在项目锁内检查、耗时扫描后重新验证全部审核输入，然后保存采用日志。recover 重新验证日志绑定的审核结果和正文版本，不跳过审核。改稿必须重新 prepare，并重新审核，不能只刷新旧结果里的 hash。

旧版未启动的 v1/v2 修订提案须重新 prepare/补审；已经进入旧事务的恢复保留原事实与版本校验，v1 报告 `legacy_editor_status: NOT_EVALUATED`，v1/v2 均报告 `review_process_status: NOT_EVALUATED`，不补造新协议通过。已采用正文不因协议升级被追溯标错。
