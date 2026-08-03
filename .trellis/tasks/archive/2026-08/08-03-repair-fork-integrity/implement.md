# Repair fork integrity — Implementation plan

1. 将 Trellis 规范从通用初始化模板替换为本仓库的 Skill、共享资产和校验约定。
2. 修复公开元数据、README 引用、私有路径、Python 调用示例与 `deslop-register` 的共享资源定位。
3. 修复 `story-deslop` 的跨 Skill 文件引用，并为 Trellis 文档的项目工件引用建立窄范围静态检查规则与回归测试。
4. 修复共享文件检查对 `trellis-meta` 分层 `overview.md` 的误报。
5. 删除确认为空的旧目录，清理失效 worktree 登记与已合入本地分支。
6. 执行任务 PRD 中的全部验证并记录结果。
