# 首次交代保护区（子任务 · P1）

> 父任务：[08-26-narrative-logic-overhaul](../08-26-narrative-logic-overhaul/prd.md)
> 对应反馈：**叙事混乱**。当前三条规则叠加把因果连接组织当 AI 味删掉了。

## Goal

设立"首次交代保护区"：一个信息**首次**成为剧情前提时，正文必须有一次落地交代，去 AI 味的删除优先与 Gate G 不得删除它，只能改写表达。第二次以后的重复解释才算 AI 腔可删。同时把"删除优先"的执行顺序从"先删后改"改成"先查信息首现完整性，再删"。

## 为什么

父任务 PRD Background 2 已核实三处叠加：
- `skills/story-deslop/SKILL.md:239`「删除优先判断（**先于各 Gate**）」：能删就删。
- Gate G 删作者解释；`long-mode.md:348` narrative-writer prompt 明写「作者解释总结…优先删掉」。
- `dialogue-mastery.md:157`「前因后果不能靠任何角色整段讲解」。

旁白不能解释、角色不能解释、能删就删——因果链没有文本落点。问题不在"该不该删 AI 腔解释"，而在**没有区分"首次必要交代"与"第二次冗余复述"**，一刀切删掉了前者。

## Requirements

### R1 首次交代定义与保护

- 定义：某信息（人物动机、关系、能力来历、事件因果）在正文中**首次**成为后续情节的前提时，对它的那一次交代 = 首次交代。
- 保护规则：首次交代属于既有"保护规则优先级"（`story-deslop/SKILL.md:282` 已列伏笔/钩子/角色特征/因果锚点等不可删）里**因果锚点**的显式细化。Gate A-G 与删除优先**不得删除首次交代，只能改写表达方式**（把作者旁白解释改成角色可感知的事件/动作/物件/对话，但保留信息本身）。
- 第二次及以后对同一信息的解释性复述，仍按 Gate C/D 合并去重、按删除优先可删。

### R2 删除优先执行顺序调整

- `story-deslop/SKILL.md`「删除优先判断（先于各 Gate）」增加前置步：删任何标记项前，先判它是否承载某信息的**首次交代**；是 → 不进删除通道，转 Gate 改写（改表达不改信息）；否 → 按现有删除优先流程。
- narrative-writer 的去 AI 味 prompt（`story-deslop/SKILL.md:236`、`long-mode.md:348`）同步补这条：解释总结先判是否首次因果交代，首次的落回场内动作/对话/物件而非删除。

### R3 dialogue「不当科普嘴」的边界收窄

- `dialogue-mastery.md:157`「前因后果不能靠任何角色整段讲解」改为：禁止的是**整段无压力的科普独白**；角色在压力下交代必要因果（首次、且推动当前冲突）允许保留，只要求拆散、带情绪、落到具体，不要求删除因果本身。

### R4 与 anti-ai-writing 模式目录一致

- `skills/_shared/references/anti-ai-writing.md` 的"模式 8（解释腔/上帝视角）"补充：解释腔的判定要先过首次交代闸——首次因果交代不是解释腔。
- 注意热路径预算：`anti-ai-writing.md` 14110/14800（余 690）、`story-deslop` 是冷路径 SKILL 但 narrative-writer 模板 15695/16500（余 805）。改动要么等量换出旧文，要么显式调 budget。优先精炼表达不净增。

## Acceptance Criteria

- [ ] AC1：`story-deslop/SKILL.md` 删除优先段落含"先判首次交代"前置步；narrative-writer 去味 prompt 同步。
- [ ] AC2：`dialogue-mastery.md` 科普嘴规则收窄为"无压力整段独白"，明确首次必要因果可保留改写。
- [ ] AC3：`anti-ai-writing.md` 模式 8 含首次交代闸。
- [ ] AC4：`bash scripts/check-doc-budget.sh` 通过（未撑爆或已显式调 budget 记录理由）。
- [ ] AC5：`bash scripts/static-check.sh`、`python scripts/check-current-skill-contracts.py` 通过。
- [ ] AC6：对一个"首次交代被误删导致后文突兀"的样例，按新规则该交代被保留改写而非删除（人工走查 + 若有 deslop 相关测试则补例）。

## Out of Scope

- 不新增确定性脚本（首次交代判定是语义的，靠文档规则 + agent prompt；纯脚本易误杀）。本条与父任务 R2"新增门禁需脚本+语义两层"的例外：本任务是**规则边界调整**不是新增门禁，故只动文档规则。
- 不改 Gate A-F 的其它规则。
- 不放松对第二次以后冗余复述的清理力度。

## 依赖与顺序

- 与 [08-26-outline-causal-fields](../08-26-outline-causal-fields/prd.md) 互补（一个在细纲阶段建因果，一个在去味阶段保因果），但相互独立，可并行。
