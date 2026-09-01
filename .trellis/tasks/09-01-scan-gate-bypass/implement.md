# 执行 · 堵住语言门禁绕过口

## 步骤

1. **读现状**：`skills/story-write/scripts/candidate-commit.py` 的 :41（`EXEMPTION`）、:219-229（`scan_gate`）、:430/:492（`validate_binding` 里的 `skip_scan` 与 `EXEMPTION.search(head)`）、:765/:855/:889（CLI 到 `promote_chapter` 的传递链）。
2. **搜历史用途**：`grep -rn "去味：跳过\|去味:跳过" skills/ demo/ AGENTS.md` —— 确认没有文档或 demo 依赖这个豁免；有则先记录再决定。
3. **删豁免**：移除 `EXEMPTION` 常量与 :492 的 `EXEMPTION.search(head)` 分支；`head` 变量若无其他用途一并清理。
4. **给 `--no-scan` 加理由**：
   - argparse 层：`promote` 子命令增加 `--reason`；`--no-scan` 存在而 `--reason` 缺失或为空白 → 报错退出（沿用现有 `CandidateError` / `require` 风格）。
   - 传递链：`promote_chapter(..., skip_scan, scan_skip_reason)` → 写入回执结构。
   - 回执落点：查 `promote_chapter` 现有返回结构与 receipt 写盘位置，加字段；**不要新开文件**。
5. **修 AGENTS.md**：:65 与 :73 两行。`check-axiom-rewards.js` 所在的「公理点升级门禁」整节对无台账项目本就不适用，改为「存在 `追踪/公理点.md` 时手工对账」并删掉命令行；`check-chapter-length.js` 那行改为指向 `candidate-commit.py` 的字数校验（`wordcount_core.fanqie_length` 已是权威），并删除与之冲突的「<2000 blocking」第三套标准表述。
6. **同步副本**：`python scripts/sync-shared-assets.py`（`candidate-commit.py` → `skills/story/scripts/`）。

## 验证命令

```bash
python scripts/sync-shared-assets.py && bash scripts/check-shared-files.sh && python scripts/test-candidate-commit.py && grep -rn "check-axiom-rewards\|check-chapter-length" AGENTS.md; echo "exit=$?"
```

手工验证豁免已失效：在一份候选正文首行插入 `去味：跳过`，跑 `check`/`promote`，确认 `scan_gate` 仍执行。

## 回滚

单 commit，`git revert` 即可。无 schema 变更、无数据迁移。
