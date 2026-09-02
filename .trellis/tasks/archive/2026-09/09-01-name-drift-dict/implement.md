# 执行 · 专名漂移词典

## 实现步骤

1. **词典文件**：`skills/_shared/references/real-world-names.md`（或 `.json`）。只收封闭平台/产品名。**脚本读文件**，不硬编码——`banned-words.md` 是反例。
2. **书级声明格式**：在 `设定/题材定位.md` 或 `设定/世界观/` 下加一个字段，形如：
   ```
   架空替换：抖音→抖手｜快手→（未用）
   保留真名：微博、知乎、东风、军报、火箭军
   ```
   格式最终形态在实现时定，要求可被脚本解析且作者能手写。
3. **写 `check-name-drift.js`**（`skills/_shared/scripts/`）：
   - 扫描范围：`正文/` + `大纲/细纲_*.md`
   - **豁免**：`设定/` 目录整体不扫，或只在含「化名/类/原型」等 gloss 标记的行豁免。倾向**整个 `设定/` 不扫 blocking**——最简单且不会自指。
   - 白名单：书级声明的「保留真名」清单
   - 人名距离 1：从 `追踪/角色状态/*.md` 与 `设定/角色/*.md` 运行时派生角色名集合，两两比较，只出 advisory
   - 输出 JSON，`--fail-on=blocking` 语义与 `check-ai-patterns.js` 对齐
4. **接进采用链**：`name_drift_gate()`，位置与 `causal_gate` 并列，按 `chapter_is_new` 分级。
5. **给 demo 加书级声明**，把 `微博 / 知乎 / 东风 / 军报 / 火箭军` 写进保留真名，作为回归 fixture 的一部分。
6. `python scripts/sync-shared-assets.py`

## 验证

```bash
node skills/_shared/scripts/check-name-drift.js "demo/长篇/让你管账号，你高燃混剪炸全网" --json
```

逐条核对 PRD 的验收表：`抖音` 命中 3 处（正文 11、正文 20、细纲 11）；`微博`/`东风`/`军报`/`火箭军`/`知乎` 零 blocking；`设定/` 下的 `抖音` 零 blocking。

## 回滚

单 commit revert；词典与书级声明为新增文件。

## 执行记录（2026-09-02）

- [x] 现实平台/产品词典与书级 `保留真名` 分离。
- [x] 正文卷目录递归发现，候选历史目录排除，设定目录不扫描。
- [x] 3～4 字角色名从角色设定、角色快照及追踪状态运行时派生；单字替换仅 advisory。
- [x] `candidate-commit check/promote` 对新章 blocking、历史章 advisory。
- [x] `node scripts/test-name-drift.js`、`python scripts/test-candidate-commit.py`、Skill adapter check 通过。
