# 执行 · 回归 fixture 书

## 步骤

1. **定落位**：确认 `scripts/check-release-manifest.mjs`、`scripts/check-doc-budget.sh`、`scripts/check-shared-files.sh` 的扫描范围，选一个不会被这三者误判的目录。倾向 `tests/fixtures/quality-gates-book/`。
2. **抄权威模板**：细纲字段以 `skills/story-write/references/workflow-setup.md`「细纲（全书每章）」为准（`check-outline-contract.js:22` 注释指明这是权威模板）。必须覆盖 `FIELDS` 全部 16 项 + 四个小节（内容概括 / 情节安排 / 人物关系和出场顺序 / 情节细化）+ 五段式 + 四列情节点表。
3. **写 5 章细纲**，`目标情绪` 序列设计为：

   | 章 | 目标情绪 | 用途 |
   |---|---|---|
   | 1 | 打脸 | 正常 |
   | 2 | 家国 | 连排起点 |
   | 3 | 家国 | 连排 2 |
   | 4 | 家国 | 连排 3 → 触发 3 章阈值 |
   | 5 | 家国 | 连排 4 → 触发 4 章阈值 |

   这样同一份 fixture 能同时观察 3 章与 4 章两个阈值的行为。
4. **写 5 章短正文**：满足骨架与标题门禁即可。若 `fanqie_length` 的 2200–2800 阻碍 fixture，**不要改 fixture 去凑字数**——记录该冲突并在子任务 1/2 的测试里走 `check` 而非 `promote`，或为测试提供专用入口。
5. **初始化追踪状态**：走 `tracking_commit.py init`，不手写 `_tracking-state.json`。确认 `imported_through_chapter = 0`。
6. **加缺字段变体**：复制第 3 章细纲，删掉 `目标情绪` / `结尾拍ID/类型` / `期待ID/类型` / `读者验收预期` 四行，存为 blocking 用例。
7. **写 README**：说明这本书是什么、验哪几项、为什么不能用 demo（引用父任务 `design.md` 的实测基线）。

## 验证命令

```bash
for n in 1 2 3 4 5; do node skills/story-write/scripts/check-outline-contract.js --json --project tests/fixtures/quality-gates-book --chapter $n > /tmp/f.json; python -c "import json;d=json.load(open('/tmp/f.json',encoding='utf-8'));print($n, d['ok'], [c['id'] for c in d['checks'] if not c['ok']])"; done
```

期望：5 章全部 `True []`。

## 回滚

纯新增文件，删目录即可。
