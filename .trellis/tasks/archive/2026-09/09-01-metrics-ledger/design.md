# 设计 · 数值台账与写前注入

## 触点清单（`tracking_commit.py`，4 份副本经脚本同步）

| 行 | 内容 | 是否要改 |
|---|---|---|
| :31-38 | `TRACKING_SCHEMA_VERSION = 4`、`DELTA_MAX_BYTES = 3072`、`CONTEXT_MAX_BYTES = 12288` | 版本**倾向不改** |
| :40-47 | `CONTEXT_HEADINGS` 七元组 | **不改** |
| :644-686 | `render_context()` | 改：`## 当前位置` 加一条子弹 |
| :684 | `require(headings == CONTEXT_HEADINGS, ...)` | **不改**，且必须仍通过 |
| :689-704 | `normalize_delta()` 的 `require_known_keys` | 加 `metrics` |
| :841 | state root `require_known_keys` | 加 `metrics` |
| :847 | `require(root.get("schema_version") == TRACKING_SCHEMA_VERSION, ...)` | 不改（若不升版） |
| :895 / :947 | state 构造处 | 加 `metrics` 缺省 |
| :972 | 事务 `INPUT_SCHEMA_VERSION` 校验 | 视 R7.5(a) 决定 |

`candidate-commit.py`：`validate_binding` 内已有 `tracking.normalize_transaction` + `merge_transaction` 预演（:499-500），R7.5(b) 的拒绝逻辑挂在这里最自然。

## 核心张力：schema 4 兼容 vs 事务必填

R7.1 要「旧 state 无 `metrics` 键也能跑」，R7.5(a) 要「事务缺 `metrics` 被拒收」。二者不冲突，前提是**分清两个对象**：

| 对象 | 规则 |
|---|---|
| `state["metrics"]`（持久状态） | **可缺**。`root.get("metrics", {})` 读取，旧书零迁移 |
| 事务 payload 的 `metrics`（新提交） | **必填**。空表也要显式 `{}`，缺键即 `require` 失败 |

这样 `TRACKING_SCHEMA_VERSION` 可以保持 4：state 的形状是**向后兼容的扩展**（新增可选键），不是破坏性变更。`test-tracking-commit.py:193` 的 `assertEqual(state["schema_version"], 4)` 不需要改。

**但要验证**：`require_known_keys` 是否为严格白名单（未知键报错）。若是，旧 state 不含 `metrics` 没问题，而**新 state 含 `metrics` 会被旧副本拒绝** —— 所以 4 份副本必须同步落地，不能分批。这也是 `sync-shared-assets.py` 存在的理由。

若调研发现 `require_known_keys` 的语义使得兼容不可行，**再升 schema 5**，并接受连带成本（4 份副本版本常量 + `test-tracking-commit.py:193` + 迁移路径）。此决策必须在动手前敲定并记入本文件。

## metrics 数据形状（草案）

```json
"metrics": {
  "抖手粉丝": {"value": "100万", "as_of_chapter": 11, "source_phrase": "粉丝突破100万"},
  "《如愿》播放": {"value": "1亿", "as_of_chapter": 20, "source_phrase": "点击破亿"},
  "华国国运": {"value": "+30000", "as_of_chapter": 20, "source_phrase": "国运+20000"},
  "任务·老兵的愿望": {"value": "已结算", "as_of_chapter": 20, "source_phrase": "超额完成"}
}
```

- 键 = 名目，用**原文措辞**（R7.3）
- `source_phrase` 保留正文原句片段，供 R7.5(b) 的结算句式比对与人工审计
- `as_of_chapter` 让「哪一章定的这个数」可追溯

## 渲染（R7.2）

`render_context()` 的 `## 当前位置` 段，在现有 4 条子弹后追加：

```
关键数值：抖手粉丝 100万｜《如愿》播放 1亿｜华国国运 +30000｜任务·老兵的愿望 已结算
```

- metrics 为空时**不输出**该子弹（旧书上下文一字不变）
- 受 `CONTEXT_MAX_BYTES = 12288` 约束：条目数超上限时按 `as_of_chapter` 倒序截断，并在子弹末尾标注「…（另 N 项见台账）」
- `headings` 校验不受影响——只加子弹不加 `##`

## 回写拒绝（R7.5b）

结算句式表（封闭，脚本读文件）：`叮`、`任务完成`、`任务结算`、`粉丝突破`、`国运+`、`奖励发放` 等。

判定：正文命中任一句式 ∧ `next_state["metrics"] == state["metrics"]` → `require` 失败，报错文本点名命中的句式与位置。

误报预案：允许在事务里显式声明 `metrics_unchanged_reason`，用于「正文提到系统播报但本章确实没有数值变化」的情况。**不要**做成静默豁免。

## 三本账收口（R7.6）

- `设定/世界观/金手指.md`：保留「机制」「写作约束（防金手指崩坏）」「任务史（历史记录）」；**删除或标注为历史快照**的当前值表述。
- `设定/题材定位.md`：数值摘要标注「派生自追踪 metrics，可能过期」。
- `AGENTS.md` 的「公理点门禁」：该节针对另一本书。本任务不删，但需加一句说明 metrics 与公理点台账的关系（倾向：公理点是 metrics 的特化，新项目用 metrics）。

## 写前注入（R7.7）

不新开块。数字通过 `上下文.md` 的 `## 当前位置` 子弹自然进入 prompt——日更本来就整份读 `上下文.md`。`long-mode.md` 只需在「状态筛选」一步加半句话说明「关键数值在 `## 当前位置`」。

## 未决（动手前必须确认）

已在实现前确认：

1. `require_known_keys` 是严格白名单；schema 保持 4，state 可缺 `metrics`，事务必须显式提交。
2. metrics 不属于 `delta`，而是与 `character_snapshots` 同级的全量当前快照。
3. 记录采用 `{value, as_of_chapter, source_phrase}`；state 最多保存 100 项，上下文按事实章倒序显示 12 项并标注隐藏数量。
4. 来源短语必须能在正文定位；数字允许正文直接值，或由前值加本章增量得到当前值。
5. 结算句式表为共享文件；误报通过非空 `metrics_unchanged_reason` 显式说明，不静默跳过。
