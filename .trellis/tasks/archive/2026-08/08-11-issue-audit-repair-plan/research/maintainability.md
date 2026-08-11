# 可维护性初审

- R1：Claude 的 Bash 前后置检查复用现有 `story_hook_core.js` 目标抽取；Shell 只保留无 Node 兼容，覆盖重定向、追加、`tee`、`cp`、`mv`，并同步 matcher 与部署测试。
- R2：Stage 6 删除 Grep、正则调整和重新切片分支，只读取 `_progress.md` 章节边界表；静态检查器拒绝 Stage 6 自行识别边界。
- R3：新增 `story-review` 自有 findings 状态工具，固定项目内路径、版本化 JSON、原子写入和批次生命周期；full/lean 由主会话写，solo 与显式只读模式只读。
- R4-R6：新增 `story-scan/scripts/scan-contract.js`，统一参数校验、100 字简介截断、同一时刻生成文件日期与带时区抓取时间、字段质量报告；平台脚本只保留采集和页面切换。
- R7-R8：书目录深度和忽略目录由单一 JSON 契约供 JS/Python 使用；Codex 的 `target_cli` 使用逗号分词后的精确 token 判断。修改仅限统一 Skill 和权威模板，派生副本经既有同步脚本生成并补本地回归。

初审结论：`APPROVE`。
