# 盲评、正向样本与纵向验收

## 角色隔离

- defect evaluator 只找问题和证据。
- repairer 只按批准范围产候选，不能选自己的版本。
- holistic selector 在隐藏新旧标签、随机顺序后比较整体阅读效果。
- final validator 检查选择结果、未解决问题、tracking/reader/event 完整性。

身份名称不是执行证据。四个角色、六个视角、每个 benchmark evaluator、对话测试、每名 reader 与 judge 的 `run_id` 在同一证书内全局唯一；视角和终验还要绑定候选 revision、输入 fingerprint、实际读取单元和证据摘要。发现复用就整包失败，不能把一次输出复制成多方意见。

修订版若输给旧版，记录“修复失败/需重新诊断”；tie 保留旧版。不能为了让流程通过，把失败改写成 false positive。

## 多版本

预先标记的关键章或结构性修复至少生成两个真正不同的 candidate；baseline 与 candidate 都提交 `{body, body_sha256}` 不可变正文产物，脚本重算 hash。两臂至少两个、数量相等且互斥；修订时 baseline 必含已接受 parent，candidate 必含当前 staged revision。普通局部修复不强制多写版本。

## 正向样本

只比较结构功能和读者效果，不复刻原句、桥段或专名。每个测试包同时有：

- development：用于形成方法；
- held-out：方法确定后才看；
- controls：本来就好的正常表达，防止误伤；
- mutants：只改坏一个目标特征的反例，检验 evaluator 是否真能识别。

四组样本的正文、hash 和 oracle 由部署包中的 `scripts/positive-benchmark-fixtures.json` 冻结；review 包必须绑定 fixture version 与整文件 hash，不得自带 `expected`。每条评测只把 `artifact_sha256 + fixture_version + evaluator_protocol` 绑进输入 fingerprint，先产出 observed/finding IDs/证据摘要，再由验收器与冻结 oracle 对账；不把答案放进 evaluator 输入。四组数据 hash 互斥，执行 dataset hash 由完整运行对象重算。

## 对话声线

只抽有角色声线信息的台词，连同人物 voice card 和必要前情盲测。每条样本保存 `line_text + line_sha256`，且 `line_text` 必须等于验收器从当前不可变候选检出的一条声线台词行；“候选中任意子串”、标题或叙述行都不算台词样本。整次测试绑定样本 fingerprint 并使用独立 run ID。候选没有声线台词才可豁免。speaker-swap 用来诊断混淆点，不设全书统一识别率门槛；修复不能给每人硬塞口头禅。

## 15 章纵向 A/B

P1 使用 `story-quality-longitudinal/v2` 时再读 [P1 强度、重开与纵向验收](quality-p1.md)。v2 把本节 v1 的“候选必须胜”验收器拆为中性实验校验和产品放行判定：P0 胜或 tie 也必须合法留存；pilot 胜出不能放行；正式系统结论还需多个独立 held-out 故事包复现。

v2 在任何正文冻结和读者观察之前，先单独记录不可变 preregistration。正式实验固定非 synthetic 故事包来源、精确 reader 数、禁止事后扩样、命名纳排规则、P0/P1 预算与停止规则；P0/P1 各有一份不可变 workflow-run receipt，逐章绑定真实输出；每位 reader 的盲序、两臂逐章 observation、最终偏好和理由都原样进入 human-import artifact。运行时必须用 `--project` 解析生命周期接收时间、预注册、workflow、真人导入与故事包证据，不能只相信实验 JSON 内重复粘贴的字段，也不能用未来时间伪装事前登记。系统层同样必须在任一包 workflow 冻结前，先冻结精确故事包集合和每包 preregistration hash，不能在看到结果后追加或挑包。

工程闭环完成不以“脚本全绿”冒充小说质量终证，也不反过来被正式研究的高成本锁死。探索阶段先让一个全新故事包跑通负结果可保存的配对盲读；正式阶段才冻结基线与候选各连续 15 章并隐藏来源。每名真人都从第 1 章累计盲读两臂到第 15 章，两臂阅读顺序独立随机并留 nonce；每臂分别记录每章第一摩擦点、最强续读点、章尾预期、目标情绪、累计混乱、谜语疲劳、自然首次弃章和总体疲劳，读完两臂后才给最终偏好。自然弃读后因研究要求继续，必须标记 study continuation，不能算留存。只读一个版本的人不能声称对两臂形成偏好。LLM reader-retention 只作代理证据。

v1 实验 JSON 用 `quality_lifecycle.py check-experiment --input ...` 验结构。v2 则用 `quality_lifecycle.py check-experiment --project {项目根} --input ...`：两臂各提交 15 个 `{chapter, body, revision}` 正文产物，revision 由 body 重算，顺序严格为 1..15，两臂互斥，arm hash 绑定章节与 revision；真人 ID/盲码唯一；每人提交包含两臂的 `arm_order`、独立随机 nonce、两套 1-15 章逐章记录、最终偏好与理由；allocation hash 与预注册精确样本量一致，所有排除都引用预注册 rule ID 并留证据。全部观察完成后才提交 baseline/candidate 盲标映射。outcome fingerprint 绑定两臂 hash、每位读者的两臂逐章观察/偏好/理由 hash、揭盲映射和决策规则；winner 必须对全部纳入 reader 做严格多数推导，2:1:1 仍是 tie，独立 judge 只能解释结果，不能把基线多数改写成 candidate 胜。`llm_retention_role: proxy_only`。正式实验至少四名 held-out 真人；n=4 persona 子组的 3/4 反向偏好只触发复审，不作硬否决。不能因 token 或费用在已经预注册后偷偷减少读者数、章节跨度或 held-out/control/mutant；资源不足时应停在探索性结论，而不是降格冒充 formal。

最终比较至少报告：

- 正确性门失败数（任何一项都不能被均分掩盖）；
- 首个显著摩擦/弃读章；
- 15 章累计偏好与理由；
- 情绪兑现、人物声线、记忆点、题材契约的相对胜负；
- 修订回滚率、相同 finding 重现率、误报保护情况。
