# 技术设计

## 边界

`.agents/skills/` 是唯一编辑源；生成目录由同步工具更新。Dashboard、候选恢复协议和 `quality_lifecycle.py` 均不改。

## 首次交代保护

在去 AI 味删除判断前增加语义分支：首次说明动机、关系、能力来历或因果链时，保留信息并改写表达；前文已经成立的重复解释仍走原删除规则。规则同步到 deslop、narrative-writer、对话规则和共享 anti-ai 参考，并用“首次保留、重复可删”契约测试固定。

## 共享读者逻辑实现

`check-first-mention.js`、`arc-ledger.js` 的实现只进入 `_shared/scripts`。业务 skill、测试、复合检查与候选采用直接调用共享实现，避免同名副本被共享资产检查判为漂移，也避免业务 skill 互相导入。

## candidate_binding v2

`logic_checks` 按 filter ID 索引，不接受未知或重复 ID。语义 receipt 至少含 `run_id`、`status`、`findings`、非空且可在正文定位的 `evidence`、`candidate_sha256`、`prose_files[{path,sha256}]` 和基于排序文件清单计算的 `prose_set_sha256`。第 15 章的 `arc-01` 还携带 ledger；`arc-02` 作者批准必须绑定当前复验结果摘要。

Promote 顺序：验证 v2 与逐文件摘要 → 构造已采用正文加候选的临时读者视图 → 重跑 rc-01 → 第 15 章重跑 arc-02 → 执行既有标题、篇幅、细纲、AI 扫描、追踪 dry-run 与采用事务。采用日志固化读者视图；`prepared`/`prose_moved` 恢复在移动正文或回放追踪前重验原始事务、逐文件摘要和集合摘要。多候选只允许逐章采用，兼容 `--all` 在多章时于任何写入前拒绝。

## 适用预算

manifest filter 增加 `appliesWhen` 元数据。契约层按场景计算适用 required 集；纯中文正文排除英文、Markdown、对外文案专属项，阶段和完整 108 项目录不删除。测试保存明确适用 ID 清单，断言逻辑分子为 13、比例至少 25%。

## 平直叙事与标题档位

叙事复杂度主体写入冷路径 `narrative-complexity.md`。新书模板写 `平直`，旧书字段缺失解释为 `常规`。标题脚本默认 `fanqie`，另提供 `terse`：两档都阻断 AI 摘要、口号式设问和近似复读；`fanqie` 对单纯超长、普通问句、通用角色词重合只提示。

## 兼容策略

- v1 binding 不猜测升级，明确要求重建候选。
- `--no-scan` 只跳过原 AI 扫描。
- 旧书缺叙事复杂度字段时行为不变。
- `terse` 保存旧标题严格结果。
