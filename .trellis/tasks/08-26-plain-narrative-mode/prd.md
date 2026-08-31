# 平直叙事档位与标题门禁分档（子任务 · P2）

> 父任务：[08-26-narrative-logic-overhaul](../08-26-narrative-logic-overhaul/prd.md)
> 对应反馈：**"写作水平低就不要故弄玄虚，简单平直地写未尝不好"**。这是硬门禁强制的问题，不是模型自由发挥。

## Goal

两件事：
1. 章节标题门禁按平台/题材分档，字数硬上限降为 advisory，让市场上有效的说明性标题不再被判 blocking。
2. 新增 `叙事复杂度` 三档（平直 / 常规 / 复杂），把"简单平直地写"变成一个受支持的一等档位。

## 为什么

父任务 PRD Background 3 已核实：
- `check-chapter-titles.js` 强制 2～6 字、最长 7 字、只允许硬质物证/数字/实体。对 demo 书前 20 章实跑为 13 条 blocking、涉及 11 章。
- 文风配置只有"对标文风 / `设定/文风.md`"两条路，没有叙事复杂度维度。"平直"在当前系统里不是可选项，反而被"每章必须钩子 + 禁止提前释放 + 章尾卡关键信息 + 元信息隔离"合力推向故弄玄虚。

## Requirements

### R1 标题门禁分档

- `check-chapter-titles.js` 增加平台/题材档位参数（如 `--profile=fanqie-male` / `--profile=terse`）。
- **保留**判得对的规则：禁 AI 偏正修饰从句（`[状语/动作]+的+[名词]`）、禁散文并列句、禁完整叙事句/设问口号——这些是真 AI 味。
- **放宽**：2～6 字硬上限在非 terse 档改为 advisory（超长提示但不 blocking）；允许口语化说明性标题（如《军报记者来采访了！》）。terse 档保留原严格标准供偏好极简的作者选用。
- 默认 `fanqie` 档要保证 demo 前 20 章从 13 条 blocking 降到 0；单纯超长、普通市场问句和相邻通用角色词重合降为 advisory。`terse` 保持原 13 条严格结果。
- 更新回归测试 `scripts/test-chapter-titles.js`：分档用例 + demo 书基线断言。

### R2 叙事复杂度三档

- 在文风体系引入 `叙事复杂度: 平直 | 常规 | 复杂` 声明。新建书默认 `平直`；既有书缺少字段时映射为 `常规`。
- `平直` 档语义：单线时序、不倒叙、同时未解释悬念 ≤ 2、章尾钩子允许**明写下一步**而非卡关键信息；每句求清楚不求余韵。
- `常规`/`复杂` = 现有行为（复杂档允许多线、埋更多悬念）。
- 写作流程（`long-mode.md` Phase 4 写前准备、narrative-writer prompt）读取该档，平直档下：
  - "每章必须钩子/章尾卡关键信息"从硬要求降为可选（父任务 AC4）。
  - 元信息隔离规则保留（那条是对的），但允许平实的承接过渡。
- 热路径预算：`long-mode.md` 余量仅 1277 字。档位说明主体放冷路径（新 `references/narrative-complexity.md` 或 `writing-craft.md`），`long-mode.md` 只加最短分支引用。撑爆则显式调 `doc-budget.json` 并记录理由。

### R3 契约与部署同步

- 标题门禁分档若改默认行为，检查 `check-chapter-titles.js` 的既有调用点（`long-mode.md:256`「写前预检与写后验证」、composite manifest 的 `ai-10-chapter-title`）是否需传档位。
- 新档位不得破坏 `check-current-skill-contracts.py`、`static-check.sh`。

## Acceptance Criteria

- [x] AC1：`node .agents/skills/_shared/scripts/check-chapter-titles.js --dir "demo/长篇/让你管账号，你高燃混剪炸全网/正文"` 在默认 `fanqie` 档下 blocking 数为 0；`terse` 档保持 13 条严格结果。
- [x] AC2：AI 偏正修饰从句/设问口号标题在任何档位仍被拦（构造用例断言）。
- [x] AC3：`叙事复杂度=平直` 可声明并被写作流程读取；该档下章尾卡关键信息不再是硬要求。
- [x] AC4：`node scripts/test-chapter-titles.js` 全绿（含分档与 demo 基线用例）。
- [x] AC5：`bash scripts/check-doc-budget.sh`、`bash scripts/static-check.sh`、`python scripts/check-current-skill-contracts.py` 通过。

## Out of Scope

- 不改 `check-ai-patterns.js` 正文规则。
- 不删除 terse 档（保留给偏好极简的作者）。
- 不改短篇标题规则。

## 依赖与顺序

- **有回归风险，动既有 blocking 门禁**。父任务要求以 demo 书为基线，故本任务排在两个 P0 之后。与 first-mention-protection 无冲突可并行，但建议 P0 验证过"弃书能被捕获"后再放宽门禁，避免同期两处大改难归因。
