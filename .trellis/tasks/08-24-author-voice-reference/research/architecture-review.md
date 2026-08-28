# 两轮架构审查共识

## 结论

三名只读审查者从可维护性、边界条件和回归风险独立检查，并在交叉复核后形成一致意见：

- 保持分域唯一权威，不建立统一可编辑设定库。
- 先修 Windows Python 探测、adapter 哈希和陈旧候选事务。
- tracking 只补 `reader_contracts` 与 `knowledge_facts`，不补 `storylines`。
- 单章上下文必须由确定性工具生成，并携带 revision、来源与缺项。
- 采用影响预览必须绑定 revision 与候选正文摘要。
- 控制台只展示派生数据；AI 数值评分不作为自动门禁。
- 作者声纹只从已采用正文采样，保护 `设定/文风.md` 作者区域。

## 已验证证据

- Dashboard 候选测试在 Windows 为 2 项失败，候选 Python 工具自身 14/14 通过；问题位于解释器探测边界。
- adapter 检查为 96/97，失败为 `claude/_shared` 源哈希过期。
- `candidate-commit.py` 会改写 `expected_state_revision`，底层 `tracking_commit.py` 原本会拒绝陈旧事务。
- 当前七栏续写状态卡有界，但完整上下文仍主要由 Agent 指令组装。
- 当前人物 `knowledge` 为自由文本，读者期待债缺少动态 ID 与证据状态。

## 验收重点

- 陈旧事务拒绝必须发生在移动正文之前，并证明所有文件零变化。
- 候选事务生成后正文被修改必须拒绝采用。
- 新状态字段只描述正式正文已经产生的事实，不复制未来大纲。
- Dashboard 测试必须穿过 UI/API/Python 真实链路，不能只 mock action。
