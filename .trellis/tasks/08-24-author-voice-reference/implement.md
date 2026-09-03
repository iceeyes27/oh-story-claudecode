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

- [x] 实现正式正文发现、统计分析和受保护标记区更新。
- [x] 接入 `story-write`，确保不读取候选、骨架、对标和归档。
- [x] 增加作者区域保护、幂等、空样本和损坏标记测试。

## 6. 分层效果协议

- [x] 为旧书局部修订新增独立的被试间 15 章实验 schema 与 CLI 校验，不改现有 P1 生成实验语义。
- [x] 复用现有摘要、预注册和真人 evidence 校验 helper，禁止再写一套宽松解析。
- [x] 覆盖同 reader 跨 arm、未声明章节变化、主要终点漂移、pilot 冒充结论、powered 缺功效字段等负例。
- [x] 为声纹 treatment 增加相同创作条件冻结与 `PENDING_HUMAN_EVIDENCE` 状态契约；不得生成 synthetic 真人结果。
- [x] 更新 `evaluation-protocol.md`，明确修订正确性、旧书吸引力和声纹效果三种证据不可互换。

## 7. 验证

- [x] 运行相关 Python/Node 单测和 Dashboard 测试。
- [x] 运行 `bash scripts/static-check.sh`、共享资产、当前契约、统一 Skill 漂移和 adapter 检查。
- [x] 运行 `npm test`；结果为 30/33 PASS、0 FAIL，Dashboard Chromium、Codex CLI、OpenCode CLI 因本机缺依赖记为环境阻断。
- [x] 运行 `git diff --check`，只审查本任务文件，不纳入无关工作区改动。
- [x] 更新 `.trellis/spec/skills/` 中的作者声纹与分层效果实验契约。

## 回退点

- 可靠性修复、schema、上下文、Dashboard、声纹各自保持独立可验证；任一后续阶段失败不撤销已经通过的前置修复。
- 不使用 reset、stash 或批量覆盖；所有修改限定到本任务路径。
