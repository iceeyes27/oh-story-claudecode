# 设计

- Bash 目标解析继续以 `story_hook_core.js` 为主实现，Claude 通过 CLI 桥接全部目标。
- 前置守卫覆盖 Bash；成功与失败写后事件使用同一检查器，并输出事件对应的 `additionalContext`。
- 无 Node 前置兼容仅覆盖 PRD 声明的直接写入形式，以同一测试夹具校验行为。
- 生成模板和平台副本只通过既有同步路径更新。
