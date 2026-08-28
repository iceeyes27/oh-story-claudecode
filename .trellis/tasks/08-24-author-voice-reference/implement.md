# 实施计划

## 1. 可靠性基线

- [ ] 修复 Dashboard Python 解释器探测并补 Windows 9009 回归。
- [ ] 运行 adapter generator 修复过期哈希，确认全通过。
- [ ] 移除候选采用的 revision 自动刷新，引入候选摘要绑定。
- [ ] 反转旧 stale-refresh 测试，补全零副作用断言和 Dashboard 状态码。

## 2. Tracking schema

- [ ] 增加 `reader_contracts` / `knowledge_facts` 校验、合并和派生视图。
- [ ] 扩展 init / append / revision / check 与旧状态兼容。
- [ ] 更新协议文档、候选事务与行为/契约测试。

## 3. 确定性上下文

- [ ] 实现 `chapter_context.py` 及 JSON/错误契约。
- [ ] 接入 `story-write` 长篇流程和部署资产。
- [ ] 增加路径、缺项、容量、筛选与 revision 测试。

## 4. Dashboard

- [ ] 服务端解析候选影响与只读项目状态。
- [ ] 前端增加影响预览和状态视图。
- [ ] action 绑定 revision/digest，补 API 与真实临时项目 E2E。

## 5. 作者声纹

- [ ] 实现正式正文发现、统计分析和受保护标记区更新。
- [ ] 接入 `story-write`，确保不读取候选、骨架、对标和归档。
- [ ] 增加作者区域保护、幂等、空样本和损坏标记测试。

## 6. 验证

- [ ] 运行相关 Python/Node 单测和 Dashboard 测试。
- [ ] 运行 `bash scripts/static-check.sh`、共享资产、当前契约、统一 Skill 漂移和 adapter 检查。
- [ ] 运行 `npm test`；浏览器不可用时明确记录未验证范围。
- [ ] 运行 `git diff --check`，只审查本任务文件，不纳入无关工作区改动。
- [ ] 更新 `.trellis/spec/skills/` 中的候选、追踪和上下文契约。

## 回退点

- 可靠性修复、schema、上下文、Dashboard、声纹各自保持独立可验证；任一后续阶段失败不撤销已经通过的前置修复。
- 不使用 reset、stash 或批量覆盖；所有修改限定到本任务路径。
