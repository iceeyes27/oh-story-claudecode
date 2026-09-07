# 修复 fcdcb2b 引入的两处回归

## Goal

`fcdcb2b`（`feat: improve reader-first writing and recoverable revisions`）在主干引入两处回归，使本机质量门禁从全绿变红。恢复 `quality-gate --profile release` 在 Windows 本机可通过，且不降低验证标准。

本 fork 无 CI（`upstream-integration.json` 把 `.github/workflows/` 列为 forbidden，"uses local verification"），本机是唯一验证信号。门禁红会连带阻断上游同步的 `validate` 阶段。

## 证据

同一台机器、同一 Python（D:\Python313）上的对照：

| 套件 | `21663ad`（fcdcb2b 之前） | `fcdcb2b` 及之后 |
|---|---|---|
| `scripts/test-candidate-commit.py` | 46 tests，OK | 78 tests，13 failures / 24 errors |
| `scripts/test-author-memory-commit.py` | OK | AssertionError |

## Requirements

### R1：修复 `revision-commit.py` 在 Windows 上读锁文件

**根因**：`skills/story-write/scripts/project_lock.py:18` 把项目锁放在 `追踪/.story-write.lock`。加锁方式两个平台语义不同：

- Windows：`msvcrt.locking(fd, LK_NBLCK, 1)` —— **强制锁**，其他句柄读该字节范围报 `PermissionError [Errno 13]`
- POSIX：`fcntl.flock(fd, LOCK_EX)` —— **劝告锁**，读取不受影响

`skills/story-write/scripts/revision-commit.py:181` 在持锁期间对 `追踪/` 做 `rglob("*")` 并 `read_bytes()` 每个文件，必然读到活动锁文件。因此该缺陷在 macOS/Linux 静默通过、在 Windows 必炸。

- 快照 `追踪/` 时必须排除项目锁文件，锁路径以 `project_lock.lock_path(project)` 为准，不硬编码文件名
- 排查同一仓库内是否存在其他"遍历 `追踪/` 读全部文件"的位置，一并处理
- 修复不得改变 `tracking_before` 对真实追踪文件的完整性语义

### R2：恢复 long-mode.md 的作者偏好注入契约

**根因**：`scripts/test-author-memory-commit.py:411` 要求 `skills/story-write/references/long-mode.md` 含字面片段 `作者偏好：{本章 query 命中的 prose_style/story_design 项}`。该片段原在 `21663ad:351` 的 narrative-writer spawn prompt 内，`fcdcb2b` 重写该段后只保留了散文表述"适用作者偏好"（现 `:304`），字面槽消失。

与 Windows 无关，任何平台都红。未被发现的原因：`narrative-gates` 只属于 `release` profile，而 `fcdcb2b` 的验证声明是 "all 15 affected checks"——`affected` 恰好 15 项且不含它。

- 需先判定 `fcdcb2b` 是有意移除该契约还是重写时遗漏
- 若契约仍应成立：在重写后的 prompt 形态里恢复一个机器可校验的字面槽，而不是把测试改松
- 若确属有意移除：更新测试契约，并说明作者偏好改由什么机制保证到达写作 agent
- 另两个契约文件（`short-mode.md`、`story-deslop/SKILL.md`）当前仍满足，不得回归

### R3：防止同类问题再次静默通过

`affected` profile 不含 `narrative-gates`，导致改动 `long-mode.md` 这类热路径文档时，其契约测试不会运行。需评估是否把 `narrative-gates`（或其中的文档契约子集）纳入 `affected`，并权衡运行时长。

## Constraints

- 不得为了让门禁变绿而放宽断言或跳过测试；R2 的裁决必须基于契约本身是否仍应成立
- 不得修改 `project_lock.py` 的加锁语义（跨平台锁行为是既定设计，问题在调用方）
- Windows 本机为验收环境；修复需同时在 POSIX 语义下成立

## Acceptance Criteria

- [ ] `python scripts/test-candidate-commit.py` 在 Windows 本机退出码 0
- [ ] `python scripts/test-author-memory-commit.py` 在 Windows 本机退出码 0
- [ ] `bash scripts/test-narrative-gates.sh` 退出码 0
- [ ] `node scripts/quality-gate.mjs --profile affected` 全项通过
- [ ] `node scripts/quality-gate.mjs --profile release` 全项通过（这是上游同步 `validate` 的实际门槛）
- [ ] R1 的修复有回归测试覆盖"持锁期间快照 `追踪/`"这一场景，且该测试在 POSIX 上也有意义
- [ ] R2 的裁决理由写入提交信息或 spec，不只是让断言通过

## 后续依赖

本任务完成后才恢复上游同步：`upstream/main` 的 `b446c365d398`（10 个 commit）需重新 `prepare`，并按已定策略执行——`tests/` 已在 `709b7af` 归类为 canonical；四个确定性检查器（check-degeneration / check-outline-copy / check-delivery-contract / anti-ai-writing）走 `adapt`（改 `skills/_shared/` 源后 `sync-shared-assets.py sync`）；短篇 `SKILL.md` 重构与 `workflow-design.md` 走 `reject`（fork 已用 mode 路由统一）。
