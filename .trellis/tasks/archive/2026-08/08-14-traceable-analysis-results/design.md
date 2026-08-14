# 可追溯分析结果层设计

## 边界

新功能归属独立业务 Skill `skills/story-analyze/`，不读取其它业务 Skill 的脚本。唯一现有代码依赖是同目录的 `chapter-boundary.js`。

数据流：

```text
_progress.md
  -> chapter-boundary.js validate
  -> analysis-manifest.js init
  -> _analysis-manifest.json
       -> record-chapter / resume / complete-stage
       -> publish-relations
            -> _analysis/results/relationships-vNNNN.json
            -> manifest.result_sets + head_revision
```

## 文件契约

### `_analysis-manifest.json`

- `schema_version`: 当前为 1。
- `source`: 从章节边界校验器投影的路径、字节数、SHA-256、行数。
- `chapter_boundary_sha256`: 对规范化章节边界 JSON 计算的 SHA-256。
- `stages`: Stage 0..6 的 `pending/running/completed/completed_with_errors/failed`、开始/完成时间和最后错误。
- `stage2.chapters`: 每章的稳定输入指纹与追加式 `attempts[]`。
- `result_sets`: 已发布关系结果的修订元数据。
- `head_revision`: 最新发布修订，无结果时为 0。

清单只通过脚本的原子替换写入，同一路径的并发写入在写前后比较内容版本指纹；检测到外部更新时拒绝覆盖。

### `relationships-vNNNN.json`

- 顶层保存 schema、revision、source SHA-256、payload SHA-256、实体和关系。
- 实体使用稳定 ID；别名保留种类、置信度和主实体归属。
- 无向关系的端点按 ID 排序，有向关系保留输入顺序。
- 证据保存相对路径、开始/结束行、整文件 SHA-256 和区间 SHA-256。
- 发布后内容不允许原地修改；新分析产生新修订。

## CLI

```text
analysis-manifest.js init <_progress.md> [manifest]
analysis-manifest.js validate <manifest>
analysis-manifest.js begin-stage <manifest> <0..6>
analysis-manifest.js record-chapter <manifest> <chapter> success --output <path>
analysis-manifest.js record-chapter <manifest> <chapter> failed --error <message>
analysis-manifest.js resume <manifest>
analysis-manifest.js complete-stage <manifest> <0..6> [--allow-failures]
analysis-manifest.js fail-stage <manifest> <0..6> --error <message>
analysis-manifest.js publish-relations <manifest> <draft.json>
analysis-manifest.js release-claim <manifest> <targetRevision> --claim-id <id> --confirm-writer-stopped
```

CLI 默认输出 JSON，便于主会话和不同 Agent 运行时消费。错误使用稳定代码。

## 验证所有权

- `chapter-boundary.js` 仍是原文和章节边界的唯一校验器。
- `analysis-manifest.js` 是分析清单、Stage 2 尝试和关系结果的唯一解码/规范化器。
- Markdown 流程只调用 CLI，不自行解析或修改 JSON 字段。
- `scripts/current-contract.json` 保存 schema 版本，仓库检查器验证脚本和文档一致。
- 逐章记录只验证清单结构、来源和本章新输出，避免随章节数平方增长的旧文件读取；`resume`、`complete-stage`、发布和显式 `validate` 保持完整产物校验。

## 兼容与恢复

- 无清单的存量拆文库仍可读；进入相关 Stage 时执行 `init`。
- 原文或章节边界改变后，先按现有契约回到 Stage 0 重建 `_progress.md`，再将旧清单与结果目录移入书项目自己的存档位置或显式删除后重新初始化。脚本不自动删除旧记录。
- 发布关系结果失败时不写结果文件，也不更新清单。

## 取舍

- 使用 JSON 文件代替 SQLite：保持 Skill 可移植性，但不针对多进程高并发服务。
- 证据指向已产出的章节摘要/情节点：与当前 Stage 4c 数据源一致，不把关系提取改成从原文直读。
- 结果记录与人类可读的 `角色/角色关系.md` 并存；Markdown 仍是阅读和写作流程的主要产物。
