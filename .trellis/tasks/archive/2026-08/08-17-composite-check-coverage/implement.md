# 实施计划

## 顺序

1. 读取并核对当前入口、七个业务 Skill、共享扫描器、平台公开清单和已有契约测试。
2. 新增复合检查机器可读清单，登记七阶段及全部内部过滤项和嵌套路由。
3. 更新 `skills/story/SKILL.md`，统一九层 AI 味说明、全量执行规则、覆盖报告字段和完成条件。
4. 扩展 `skills/story/tests/composite-check-contract.test.js`，加入清单结构、漏项、继续执行、阻断和触发词边界测试。
5. 修复 Claude `prose-after-event` 事件适配、静态共享路径、连续性时间边界和废弃 Skill 提示。
6. 将确定性契约测试加入 `package.json` 默认本地测试链路。
7. 运行静态检查、共享资产检查、公开 Skill 覆盖检查、Hook 回归、契约测试和 Dashboard 测试。
8. 使用 `git diff --check`、工作区状态和文件范围核对，确认没有正文、CI 或远端改动。

## 验证命令

```text
node --test skills/story/tests/composite-check-contract.test.js
npm run test:contracts
bash scripts/static-check.sh
python scripts/test-static-check.py
bash scripts/check-shared-files.sh
bash scripts/check-hook-regex-sync.sh
bash scripts/test-ai-patterns.sh
bash scripts/test-prose-backstop-hook.sh
bash scripts/test-story-continuity.sh
npm run test:dashboard
git diff --check
```

完整 `npm test` 仍需记录 Playwright 浏览器运行环境；浏览器未安装属于环境阻断，不与确定性契约测试混为一谈。

## 风险检查点

- 清单必须引用仓库现有公开 Skill，不得新增旧目录或跨业务 Skill 的运行时文件读取。
- Hook 适配必须保留无目标时静默、失败事件也检查和合法 JSON 输出。
- 入口文案、清单和测试必须使用同一阶段顺序和过滤器数量。
- 生成的 `.agents/skill-adapters.json` 不纳入源代码提交。
