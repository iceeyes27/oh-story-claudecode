# 读者视角理解力检查 · 技术设计

## 1. 目录形态

新 skill 自包含（static-check 要求：`name`=目录名、有 `description`、references 从 SKILL.md 可达、禁跨 skill 引用）：

```
skills/reader-comprehension-scan/
├── SKILL.md                      # 三问连读法 + 脚本用法 + 结论边界
├── scripts/
│   └── test-first-mention.js     # 直接测试共享实现（node 原生 assert）
└── references/
    └── reading-protocol.md       # 三问通读法的分批子代理 prompt（从 SKILL.md 链接可达）
```

确定性实现唯一位于 `skills/_shared/scripts/check-first-mention.js`；平台入口由 adapter 生成器维护。

## 2. check-first-mention.js 判据

纯规则提取中文人名/机构名不可靠，故**限定到可机械判定的子集**，定位为 advisory：

- **候选专名**：① 书名号/引号包裹的具名实体（`《…》`「…」`『…』`）；② 全书重复出现 ≥3 次的 2–4 字连续中文 token，过滤停用词表（的/了/他/她/说/看…）与章节工程词。
- **首现定位**：候选按章号升序找第一次出现的 `章节:行号`。
- **交代锚点**：首现所在段落（或相邻 1 段）内是否含解释信号——判断句（`是/为/叫/名为/称/名叫`）、同位结构、职务/身份词（`长/师/官/主任/记者/团/队/公司/门/阁…`）、来历动词（`出身/来自/毕业/曾…`）。
- **finding**：候选首现处无任何锚点 → `未交代即使用`(advisory)。升 blocking 仅当该候选在**首现之后 ≥2 章**再次被当已知前提出现（复用频率+跨章 span 近似），且首现零锚点——即"读者被要求记住一个从没解释过的东西"。
- 输出：文本摘要 + `--json`；退出码 0 无 blocking / 1 有 blocking / 2 参数错误。与仓库既有脚本（check-chapter-boundary.js）风格一致。

## 3. 输入隔离（R1 立身之本）

脚本只 `walk` 传入的 `<书目录>/正文`，绝不读 `设定/大纲/追踪/对标`。SKILL.md 的三问子代理 prompt 显式声明"只喂正文文件、不注入设定/大纲/追踪"，并在 reading-protocol.md 固化。

## 4. 三问连读法（语义层）

reading-protocol.md 给分批子代理 prompt（参考 dialogue-naturalness-scan 第 3 层分批纪律，默认 5 章/批，禁单代理通读全书）。每章逐问：
1. 谁在做什么（正文本身能否说清）
2. 前因在正文哪一章明写过（指不到具体章=悬空）
3. 读者此刻信息够不够理解本章关键转折

输出 `章节 + 断点描述 + 读者此刻缺的信息`，分「确认断点 / 边界待定」。

## 5. manifest 接入（延后到父任务统一编排）

本设计**不在本子任务内改 manifest**。原因：`composite-check-contract.test.js` 硬编码 `stages.length===8`、`stageCount===8`、`allItems().length===103`、`expectedStages` 顺序，`.trellis/spec/skills/validation.md` 硬编码 `103 个必检项`/`8/8, 103/103`，`story/SKILL.md` 硬编码 `8/8, M/M`。新增 stage 要同步这 4 处计数。qa-budget-rebalance 会改 count 的另一侧。两者**同一批一次性改**，避免 count 反复。故本子任务只交付可独立调用的 skill+脚本，登记进 `platform-skill-set.json`；接 manifest 记为父任务集成步骤。

## 6. 兼容与回退

- 纯新增目录 + 一个 `platform-skill-set.json` 条目 + adapters 重新生成。回退 = 删目录、还原 skill set、repair adapters。
- 不改任何既有 stage / 脚本 / 门禁，零回归面。
