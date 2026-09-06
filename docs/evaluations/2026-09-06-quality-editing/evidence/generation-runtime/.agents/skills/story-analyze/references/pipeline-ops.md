# 管道运维参考

story-analyze long 拆解管道的运维工具文档：`_progress.md` 模板、错误处理、恢复机制操作步骤。

> 质量阈值（置信度 / 覆盖率 / 重叠率）见 [material-decomposition.md 质量阈值体系](material-decomposition.md)。

---

## _progress.md 模板

```markdown
# 深度拆解进度：{书名}
- 小说：{标题} | 总章数：{N} | 输出目录：{路径} | 开始：{日期}
- 最终状态：{pending/paused_after_stage1/completed/completed_with_errors}
- schema_version: 3
- source_path: 原文/原文.txt
- source_bytes: {原文 UTF-8 文件字节数}
- source_sha256: {原文文件 SHA-256，小写 64 位十六进制}
## 管道进度
| 阶段 | 状态 | 进度 | 备注 |
|------|------|------|------|
## 章节边界（Stage 0 章节边界子步骤产物，唯一权威）
| 章号 | 标题 | 起始行 | 字数 |
|------|------|--------|------|
## 分块进度
| 块 | 章节 | 状态 |
## 失败记录
| 类型 | 章节/阶段 | 错误信息 | 重试状态 |
|------|----------|---------|---------|
## 质量检查
| 检查项 | 阶段 | 结果 | 修正 |
## 角色合并
| 合并前 | 合并后 | 依据 | 确认 |
## 断点
- 最后处理：第{N}章 | 当前阶段 | 下一操作
```

**schema_version 说明**：

| 版本 | 含义 |
|------|------|
| 3 | 当前契约：含原文相对路径、字节数、SHA-256 与「章节边界」表。Stage 1/2/6 先校验来源指纹和边界，再以该表为唯一切片真值 |

缺少 `schema_version: 3`、任一来源字段或「章节边界」表时不得续跑；低于当前版本的进度不在消费阶段迁移，统一从 Stage 0 章节边界子步骤重跑并重建 `_progress.md` 后再恢复。

Stage 1、Stage 2、Stage 6 在读取切片前统一执行：

```bash
node skills/story-analyze/scripts/chapter-boundary.js validate 拆文库/{书名}/_progress.md
```

校验器验证 schema、来源路径/字节数/SHA-256、章号唯一连续、起始行严格递增和行号范围，并返回唯一可消费的 `source` 与 `chapters`。失败时停止当前 Stage，禁止自行调整规则或重建临时边界。

边界校验通过后，长篇管道初始化并验证 `_analysis-manifest.json`：

```bash
node skills/story-analyze/scripts/analysis-manifest.js init 拆文库/{书名}/_progress.md
node skills/story-analyze/scripts/analysis-manifest.js validate 拆文库/{书名}/_analysis-manifest.json
```

Stage 2 用 `begin-stage`、`record-chapter`、`resume`、`complete-stage` 记录真实执行历史；Stage 4c 用 `publish-relations` 生成不可变关系结果。完整命令与草稿格式见 [analysis-manifest.md](analysis-manifest.md)。

**最终状态值说明**：

| 状态值 | 含义 |
|--------|------|
| `pending` | 管道进行中，尚未跑完 |
| `paused_after_stage1` | Stage 1 停靠点暂停——Stage 0/1 已完成，已产出 `快速预览.md`，等待用户决定是否继续 Stage 2-6。续跑时跳过 Stage 0/1，从 Stage 2 开始 |
| `completed` | 全管道 Stage 0-6 完成 |
| `completed_with_errors` | 全管道完成，但有单章/单阶段失败（详见「失败记录」表，拆文报告中注明） |

---

## 剧情单元清单补建（存量书）

触发：用户说「补剧情单元清单」，或写作侧检索发现 `剧情/README.md` 无「剧情单元清单」表。

动作：读存量 `拆文库/{书名}/剧情/*.md`（或 `对标/{书名}/剧情/*.md`）各剧情单元表头的 标题 / 类型 / 桥段标签 / 章节范围 字段，按 output-templates.md「剧情单元清单」表模板机械重建 `剧情/README.md` 的清单表；项目 `对标/{书名}/` 视图存在时同步一份。不读原文、不重跑任何 Stage、不改剧情单元内容、不动 `节奏.md` / `情绪模块.md`。旧剧情单元「章节范围」行没有字数信息时，体量列只写「共{N}章」、字数记「未知」，不得编造。

写作侧消费点对无清单的书自动回退逐文件检索（见 story-write long 的 outline-structure-theory.md「对标节奏迁移」步骤 1），补建只是加速，不是阻塞项。

## 错误处理

| 场景 | 处理 |
|------|------|
| Stage 0 章节识别失败 | 提示确认格式；只在 Stage 0 修正规则并重建 schema v3 |
| schema/来源指纹/章节边界校验失败 | 停止 Stage 1/2/6；回到 Stage 0 重建，不临时迁移 |
| 分块中断 | 读 _progress.md 断点恢复 |
| 聚合质量不达标 | 孤立情节二次分类；阈值放宽至 0.5 |
| 角色合并冲突 | 记录待确认列表 |
| 分析清单、章节输出或关系结果指纹变化 | 停止当前操作；检查来源与对应产物，不手工修改清单 |
| Stage 2 有失败章节 | 默认继续重试；明确按部分失败策略进入 Stage 3 时使用 `complete-stage ... 2 --allow-failures` |
| 输出目录冲突 | 追加不覆盖；冲突标 `[重新分析]` |

---

## 恢复机制操作步骤

1. 管道启动时检查输出目录是否已有 `_progress.md`
2. 用 `chapter-boundary.js validate` 校验 `schema_version: 3`、来源指纹与「章节边界」表，再执行 `analysis-manifest.js init`（存量目录缺少清单时创建）和 `validate`，校验逐章输出与已发布结果；任一失败即停止并检查对应来源阶段
3. 读取断点信息；Stage 2 再执行 `analysis-manifest.js resume`，只恢复待处理与失败章节
4. **断点状态为 `paused_after_stage1`**（Stage 1 停靠点）→ 跳过 Stage 0/1，直接从 Stage 2 续跑逐章摘要，不重跑已完成的概要与黄金三章
5. 其他断点状态 → 从断点所在块的起始章节恢复，覆盖该块已有输出
