# 质量回归样本

用真实书稿段落量测审阅与修正 prompt 的效果。每次修改 `.novel-kit/roles/`、`.novel-kit/standards/` 或 `review-loop.md` 的质量规则后，照本协议重跑，与上一次记录比对。

样本取自作者的书稿 `iceeyes27/wozaiyuenan`（提交 `a401925d`），只作评测用，不是本工具的写作范本。书稿修订后不回头更新样本，以保持可比性。样本原文保持书稿原样，不改字形。

## 目录

```
样本/<ID>/正文.md     审阅对象，只含正文
样本/<ID>/前文.md     可选，前文或相关前章摘录（以“……”分隔不连续段）
答案/<ID>.json        应抓问题、预期严重度、不应报的保护项
文风样本.md           书稿的文风样本，评测时代替 `設定/文風樣本.md`
记录/<日期>_<标签>/   每次执行的原始报告与汇总
```

| 组 | 层 | 用途 |
|---|---|---|
| A | L1 语文正确 | 病句、搭配、指代、标点 |
| B | L2 段落与衔接 | 动作缺失、时空跳转、主语切换 |
| C | L3 上下文事实 | 附前文，测跨章矛盾 |
| D | L4 自然度 | 套话密度，含应受保护的角色声线 |
| K | 对照 | 作者认可的段落；除答案列出的项目外，S1/S2 一律算误报 |

## 盲读隔离

评测者只能读：角色档、角色档引用的规格档、指定的 `正文.md`／`前文.md` 与 `文风样本.md`。**不得读 `答案/`、`记录/` 或其他样本。** 每个样本、每次执行都用新的独立上下文。

## 执行

以独立子代理执行，提示固定如下（`<角色>`、`<ID>`、`<输出>` 代换）：

> 你在做 novel-kit 质量回归评测。先完整读 `.novel-kit/roles/<角色>.md`，严格照它的规则与回报格式工作，并读它引用的流程或规格档。审阅对象：`.novel-kit/eval/样本/<ID>/正文.md`；前文：`.novel-kit/eval/样本/<ID>/前文.md`（无则略）。角色档提到的 `設定/文風樣本.md` 一律改用 `.novel-kit/eval/文风样本.md`；本评测没有 `正文/`、`設定/`、`追蹤/` 可读或搜索，只用指定的前文。除上述文件外，不得读 `.novel-kit/eval/` 下任何文件。这里没有细纲、设定或追踪，不要去找。报告用简体中文，引用原文保持原样。把完整报告写入 `<输出>`，不修改其他文件。回复只列问题：`严重度 | 类别 | 证据前 20 字`。

修正测试：把答案中预期 S1/S2 的应抓问题按 review-loop 问题格式交给 `scene-writer` 修正模式，输出到记录目录的副本；再用新的 copy-editor 盲读复审修后副本。

## 指标

| 指标 | 计算 |
|---|---|
| 检出率 | 被报出（任何严重度）的应抓问题 ÷ 应抓总数 |
| 定级达标率 | 预期 S1/S2 且被报为 S1/S2 的问题 ÷ 预期 S1/S2 总数 |
| 误报 | K 组答案外的 S1/S2 数 ＋ 被报成问题的保护项数 |
| 修正后新增错误 | 修后复审新出现、原文没有的 L1/L2 问题数 |
| 保护项被误改 | 修正时被改动的保护项数 |

LLM 输出不固定：copy-editor 每样本跑两次，逐次报告检出率、定级达标率和误报，并报告两次一致率。两次中任一次报出及取较严定级的并集指标作为补充保留，不能用它代替单次稳定性。

## 冻结与验收边界

每次运行先保存只读输入清单：样本和前文哈希、角色和规格哈希、审阅提示、实际提供的原文范围、模型标识（宿主未提供时如实注明）、上下文是否独立、执行日期及输出路径。源文件变化后另开版本，不覆盖历史报告或原文。修后复审只给修后正文、相同原文前因、规格与文风，不给原问题、答案或先前意见。

现有样本是调参回归集，部分错误与规格示例同型；它能验证已知问题的回归，不能单独证明其他作品表现。新规则冻结后，再选择未参与规则设计的保留样本；保留样本不得作为继续改规则的同时测试集，调参后需另换保留集。短样本之外还需完整场景、非相邻前因、物件中途转交、转线、旧稿与新正式稿差异、缺前文与有意留白等覆盖。

检测、定级、修复效果分别评分；保护项与新错误另列。评分必须注明是协调器或模型对照、还是作者亲自核验，不把“人工比对”用于模型评分。样本答案与审阅意见冲突时保留双方证据供作者裁决。L5“好看”、完整场景的阅读体验及正文采用仍由作者和读者决定，不设置模型自动通过门槛。

工程测试仅验证格式和版本机制。质量验收需具备冻结清单、原始审阅、修正副本、独立修后盲读和可核对汇总；缺任何一项就明确列为未完成，不能宣称规则已经提升质量。

`tests/test_eval_samples.py` 只检查样本与答案格式、证据原文是否存在，不调用模型。

`记录/2026-10-01_基准/` 的原始报告生成于简体规则生效前，按原样保留作证据。

## 持久证据工具

`.novel-kit/scripts/eval_evidence.py` 使用 Python 3.9 标准库，不调用模型，不搜索关键词判定检出。协调器先冻结实际输入，再安排独立审阅，最后按原始报告填写逐问题判分表。

```text
python3 .novel-kit/scripts/eval_evidence.py freeze --spec 配置.json --dest 新证据目录
python3 .novel-kit/scripts/eval_evidence.py verify 新证据目录
python3 .novel-kit/scripts/eval_evidence.py verify 新证据目录 --require-outputs
python3 .novel-kit/scripts/eval_evidence.py score 新证据目录 --judgments 逐项判分.json --name 本次评分
```

`freeze` 只创建不存在的新目录，不覆盖任何历史。每份输入保存完整源路径、完整源 SHA-256、实际提供的行范围与范围内容 SHA-256；`inputs/` 副本、`manifest.json` 和 `freeze-spec.json` 为只读文件。角色档引用的每份规格、流程及文风也必须列入实际 `context`，不能只声明角色档。文件相对路径按配置文件所在目录解释；行号从 1 开始，两端都包含，省略 `range` 表示全文。模型未提供时记录 `unknown`。冻结时间由工具记录，不把它冒充实际执行日期或已启动任务的开读时间。

配置最小示例（实际执行两次时声明两条运行，各用新上下文和不同输出路径）：

```json
{
  "schema_version": 1,
  "scope": "review_only",
  "inputs": [
    {"id": "body", "path": "样本/A01/正文.md", "kind": "prose"},
    {"id": "role", "path": "../roles/copy-editor.md", "kind": "role"},
    {"id": "language", "path": "../standards/语文规格.md", "kind": "standard"},
    {"id": "review-loop", "path": "../workflows/review-loop.md", "kind": "standard"},
    {"id": "style", "path": "文风样本.md", "kind": "style"},
    {"id": "answer", "path": "答案/A01.json", "kind": "answer", "audience": "coordinator"}
  ],
  "runs": [
    {
      "id": "A01-ce-1", "sample": "A01", "role": "copy-editor", "attempt": 1,
      "phase": "review", "context": ["body", "role", "language", "review-loop", "style"],
      "prompt": "此处填本次实际使用的完整提示，逐项列明允许读取的冻结副本。",
      "independent_context": true,
      "output": "outputs/A01_copy-editor_1.md"
    }
  ]
}
```

输入和运行 `id` 只能使用字母、数字、点、下划线或连字符；`audience` 默认 `reviewer`，答案必须为 `coordinator`，不能进入运行 `context`。评测者只能拿自己 `context` 中声明的副本和提示，不能读取含答案信息的整份清单。`phase` 为 `review`、`repair` 或 `repair_review`；`independent_context` 必须显式填 `true`、`false` 或 `"unknown"`。`scope` 默认 `full`，要求审阅、修正副本及独立修后盲读证据；明确只测审阅的回归集或保留集用 `review_only`，该范围的数据完整不代表完成全部质量验收。

判分表不是小说流程状态，由协调器另填；质量判断来源必须如实标成 `model_comparison`。每个应抓问题都填一行，包括未检出项。`detected` 为布尔值；检出时填报告中的严重度和原文摘录，未检出时 `severity` 为 `null`。`reason` 解释对照判断，工具不替协调器判断匹配；非空 `evidence` 必须确实出现在对应原始报告。缺行或 `null` 判断均列为缺失，不计算完整率。`execution_date` 填实际执行日期，宿主未给模型标识仍可保留未知。

```json
{
  "schema_version": 1,
  "quality_judgment_source": "model_comparison",
  "runs": [
    {
      "run_id": "A01-ce-1", "execution_date": "2026-10-03",
      "issues": [
        {"issue_id": "A01-1", "detected": true, "severity": "S3", "evidence": "报告里的原文摘录", "reason": "该项确实指出相同问题。"},
        {"issue_id": "A01-2", "detected": false, "severity": null, "evidence": "", "reason": "逐项核对后未见此问题。"},
        {"issue_id": "A01-3", "detected": false, "severity": null, "evidence": "", "reason": "逐项核对后未见此问题。"}
      ],
      "protected": [
        {"protected_id": "A01-protected-1", "reported": false, "evidence": "", "reason": "该口语未被列为问题。"}
      ],
      "extra_findings": []
    }
  ],
  "repairs": []
}
```

保护项没有自带编号时，按冻结答案的顺序编号为 `<样本>-protected-1` 等。答案外问题填 `extra_findings`，每项含稳定 `id`、`severity`、`evidence`、`reason` 和显式布尔 `false_positive`；无额外问题也须填 `[]`。K 组答案外 S1/S2 与任何严重度的保护项误报单列，其他样本由协调器明确判断的误报另列。补充并集按稳定编号合并，同一额外问题在两次报告中的编号须相同。

`full` 的 `repairs` 每项含 `sample`、声明的 `repair_run_id`、`review_run_id`、`execution_date`，以及以下显式表：

- `issues`：原答案中预期 S1/S2 的每项填 `issue_id`、`resolved`、`evidence`、`reason`；证据引用独立修后报告。
- `protected`：每项填 `protected_id`、`changed`、`evidence`、`reason`，记录保护项是否误改。
- `new_errors`：无新增时填 `[]`；每项填稳定 `id`、`layer`（L1/L2）、`severity`、`evidence`、`reason`。

工具输出 `scores/<名称>.json`、同名简体汇总和只读逐项判分副本，不覆盖同名文件。JSON 保留逐次、逐角色次数、两次一致率、补充并集、修正结果、缺失清单和原始输出哈希。检出一致率按应抓问题的两次布尔判断比较，包含两次都未报；严重度一致率比较具体 S1–S4 或两次都未报；正向重合率为两次都检出除以至少一次检出。分母为零时显示“不适用”，不会报 100%。修正结果、新增错误和保护项误改单列。

`verify` 核对源和快照漂移、输出是否位于声明范围，并核对已经评分的原始输出和逐项判分副本哈希。未完成执行的输出单列；加 `--require-outputs` 时缺输出也返回失败。源、快照或已评分原始报告变化后另开版本，不能重新冻结旧记录并声称它是开读前冻结。`score` 的 `evidence_complete` 仅说明声明范围的数据完整，`quality_acceptance` 始终为 `not_determined`，不会自动给出“质量通过”。

只读权限用于防止意外改写，不是签名认证。当前 `verify` 信任清单内记录的哈希和上下文声明，不能证明模型实际只读了声明输入，也未把清单各字段与配置重新推导交叉绑定；独立上下文和实际可读范围仍需宿主执行证据。旧报告的历史冻结缺失不能由本工具事后补成开读前冻结。

## 有界执行和恢复

实际模型运行使用 [可恢复的评测执行器](执行器说明.md) `.novel-kit/scripts/eval_runner.py`，每项独立会话，按小批次执行并设置单项超时和批次总预算。先核对冻结输入，逐项保存实际提示、开读记录、原始事件、退出状态和报告哈希；中断后只恢复凭据完整且版本一致的结果。未知已有报告保留待核，不覆盖或盲目重跑。

指定角色必须在本会话直接完成单项评测，不再委派。命令行请求关闭多代理不等于宿主实际没有代理调用；执行器还检查真实事件，发现嵌套代理或线程委派时不得登记完成。若为修正执行行为追加控制指令，应先保存新的完整提示版本，原质量规则和冻结正文保持不变，评分汇总注明提示差异，不能冒称逐字执行原提示。

旧修正稿的再次盲读不能代替当前规则的修正能力测试。当前写手修正完成后，先冻结实际候选，再把该纯正文及同范围前文交给新的独立编辑；答案、修正意见及旧报告不进入盲读。若替换历史评测任务，登记原任务与替代任务的对应关系，不把被替换任务计成已经执行。
