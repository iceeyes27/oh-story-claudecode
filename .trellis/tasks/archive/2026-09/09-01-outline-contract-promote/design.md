# 设计 · 读者体验契约接进采用链

## 现状锚点

```
candidate-commit.py
  :36-49   RC_IDS / TOOL 常量区（SKELETON_TOOL, OUTLINE_COPY_TOOL, TITLE_TOOL,
           FIRST_MENTION_TOOL, ARC_LEDGER_TOOL, SCAN_SCRIPTS）
  :219-229 scan_gate()
  :430-494 validate_binding(...)  ← 纯校验，promote 在其之后才搬文件
  :765     promote_chapter(project, chapter, *, skip_scan=False)
  :864-880 argparse 子命令：promote / recover / reject / list
```

`check-outline-contract.js` 的 CLI：

```
node check-outline-contract.js --json [--require-p1] --project <书目录> --chapter N
```

输出 JSON：`{schema_version, verifier, file, ok, checks:[{id, ok, severity, evidence, expected, references, repair}]}`，exit 1 表示有 blocking。

> Windows 注意：该脚本 JSON 里含 Windows 绝对路径。**不要用管道接 python 解析**（控制台代码页会破坏 UTF-8），落盘再读。

## 决策

### A · 新增 `OUTLINE_CONTRACT_TOOL` 常量，进 TOOL 区

与 `SKELETON_TOOL` / `OUTLINE_COPY_TOOL` 并列，指向 `Path(__file__).resolve().parent / "check-outline-contract.js"`。

注意：`check-outline-contract.js` 目前有两份（`story-write/scripts/` 与 `story-import/scripts/`），**不在 `shared-assets.json` 里**。本任务不改这个现状，但要在实现说明里记一笔——若二者已漂移，先对齐再接线。

### B · 不用 exit code，用 JSON 分级

`run_node(... , "细纲契约检查")` 后**不**直接 `require(returncode == 0)`。原因：脚本对 `plotpoint-table` 等也给 blocking，直接用 exit code 会把本批不想阻断的项一起阻断。

改为：

```python
report = parse_node_json(result, "细纲契约检查", {0, 1})   # 复用 :349 的既有 helper
blocking_ids = {c["id"] for c in report["checks"] if not c["ok"]}
```

然后按下面两张表裁决。`parse_node_json` 已存在（`validate_rc01` 在用），沿用即可。

### C · 严重度表（本批）

| check id | 新写章 | 历史章 |
|---|---|---|
| `outline.readable` | blocking | blocking |
| `outline.required-fields` | **blocking，但只看 `INTENT_FIELDS` 缺失** | advisory |
| `outline.reader-contract` | advisory | advisory |
| `outline.plotpoint-table` | advisory | advisory |
| 其余 | advisory | advisory |

「只看 `INTENT_FIELDS` 缺失」的实现：`outline.required-fields` 的 `evidence` 是「缺字段：A、B、C」形式的字符串。**不要解析这段中文文案**——脆弱。改为在 Python 侧独立读细纲文件，对 `INTENT_FIELDS` 五项各做一次在场性判定（字段行存在且冒号后有非占位内容）。脚本的 finding 仅作 advisory 证据一并打印。

> 若实现时发现 `check-outline-contract.js` 支持按 check id 过滤或输出结构化 `missing` 数组，优先用结构化数据，避免 Python 侧重复实现字段解析。**先读脚本再定**。

### D · 分级判定：共享 helper

```python
def chapter_is_new(state: dict, chapter: int) -> bool:
    return chapter > int(state.get("imported_through_chapter", 0))
```

放在 `candidate-commit.py` 顶层（子任务 2、4 复用）。`state` 在 `validate_binding` 里已可得（:456 `sha256_file(project.resolve() / TRACKING_STATE)` 附近已加载）。

### E · `check` 子命令

```
sub.add_parser("check")  →  --project (必填) --chapter (必填) [--json]
```

实现：

```python
def check_chapter(project, chapter) -> dict:
    # 与 promote_chapter 前半段完全相同的加载路径
    # 调 validate_binding(...)，捕获 CandidateError 转成结构化结果
    # 不调 tracking.merge_transaction 的落盘、不移动候选、不写 receipt
```

**关键约束**：`validate_binding` 内部已有 `tracking.normalize_transaction` + `merge_transaction` 的**预演**（:499-500），那是纯内存演算、不落盘，可以保留——它正是「promote 会不会失败」的最强预测。要确认的是 `project_lock` / `assert_no_unfinished_adoption` 是否会写盘；若会，`check` 走只读路径。

不复制校验逻辑。若 `validate_binding` 里混有副作用，先把副作用提出去，再让两个入口共用。

### F · 出骨架前的本章检查

骨架生成流程在 `long-mode.md` Phase 4 与 `check-chapter-skeleton.js` 一线。本任务只需在 `long-mode.md` 与 `AGENTS.md` 写明「出骨架前跑 `check-outline-contract.js --project ... --chapter N`」，**不新增脚本**。真正的阻断由 `check` / `promote` 兜底。

### G · 文档修订

- `artifact-protocols.md:274`：「既有项目的旧细纲不因此阻断写正文」→ 改为「`imported_through_chapter` 及之前的章不因此阻断；其后的新写章，`INTENT_FIELDS` 缺失即阻断采用」。
- `AGENTS.md`：新增一条，明确 `check`（写完自检）与 `promote`（作者采用）的分工。

## 未决

1. `check-outline-contract.js` 是否已能结构化输出缺失字段列表（决定 C 节走哪条路）。
2. `story-write` 与 `story-import` 两份 `check-outline-contract.js` 是否已漂移。
3. `project_lock` 在只读路径下的行为。

以上三条**必须在动手前先读代码确认**，不要凭推断实现。
