# 技术设计

## 1. 边界

`skills/story/references/composite-check-manifest.json` 负责声明复合检查的阶段和过滤器覆盖范围；`skills/story/SKILL.md` 负责面向 Agent 的路由和报告规则；`skills/story/tests/composite-check-contract.test.js` 负责静态契约和行为模拟。各业务 Skill 继续拥有自己的扫描实现，不把业务算法复制到入口。

## 2. 清单结构

每个阶段包含：

- `id`、`route`、`order`
- `filters[]`：`id`、`label`、`executor`、`scope`、`required`、`report`
- `dependencies[]`：必需公开 Skill 或共享资产

过滤器 ID 以可审计的稳定名称表示。清单覆盖结构审查、AI 味九层扫描、小说去味各 Gate 及污染检测、台词自然度、行业词动词化、通用去模板感和通用 AI 痕迹复核，同时登记保护区、白名单和跨章连续性等不会被文本正则替代的范围规则。

## 3. 执行与报告

入口先发现书名、正文目录和章节文件，计算清单中的必检项数量。阶段执行器按清单顺序运行，输出覆盖记录：

```text
filter_id | status | scope | findings | reason
```

`PASS` 表示已执行且无发现，`FAIL` 表示已执行且有发现，`BLOCKED` 表示无法执行，`SKIPPED` 仅用于清单明确允许且有原因的非适用项。`BLOCKED`、非法 `SKIPPED` 或缺失记录都会使复合检查保持未完成状态。

Reviewer agent 不可用时，使用 `story-review` 已定义的 solo rubric，并在报告中标明模式；这不减少清单中的过滤器。没有等价执行器时标记 `BLOCKED`。

## 4. 契约测试

测试直接读取清单，验证：

1. 阶段固定为七项且顺序正确。
2. 过滤器 ID 唯一，每项字段完整，执行者和依赖路径存在。
3. 所有嵌套路由属于公开 Skill 集合。
4. 模拟任一过滤器缺失时，完成判定失败。
5. 模拟前项发现问题时，后续阶段仍执行。
6. 模拟不可读输入时，结果包含阻断原因且没有完成标记。
7. 单项触发词和“检查更新”不会误走全量路线。
8. `story-deslop` 的 `batch-pollution-detector` 被计入嵌套依赖。

## 5. 运行链路修复

Claude 写作后钩子新增薄适配层：解析 Write/Edit/MultiEdit 的路径和 Bash 的命令字段，调用现有 `story_hook_core.js` 的 `extractProseTargets`、`resolveTarget`、`proseAfterWrite`，统一生成 Claude hook JSON。核心检查算法不复制。

连续性判定使用显式追踪状态或章节修订信息作为主依据，文件修改时间只作为辅助信号，避免测试依赖恰好一秒的睡眠。

## 6. 兼容性与回滚

清单为新增只读声明，不改变已有技能调用参数。报告规则只收紧完成标记，不会阻止单项检查输出。若运行时发现某个执行器与清单不一致，回滚范围为清单和入口契约，不回退已有共享扫描器。
