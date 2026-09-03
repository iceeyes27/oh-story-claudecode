# 技术设计

## 权威边界

```text
设定/ + 大纲/ + 已采用正文/
          │
          ├─ context-package（只读组装）
候选正文 + 候选追踪事务
          │  preview: revision + digest + semantic diff
          ▼
作者采用 ── candidate-commit ── tracking_commit
                                  │
                                  ▼
                        _tracking-state.json
                                  │
                         确定性派生 Markdown/API
```

所有写入继续通过既有事务工具。Dashboard、上下文工具和控制台只读取并投影权威数据。

## 可靠性设计

### Python 探测

将“进程成功启动”与“解释器可用”分开：先用 `--version` 探测候选命令，只有 exit 0 才用于业务脚本。业务脚本的非零退出属于业务结果，不能再切换解释器重跑。

### 候选绑定

候选追踪事务增加：

- `expected_state_revision`：生成事务时的状态修订；
- `candidate_digest`：规范化读取候选正文原始字节后计算 SHA-256。

`promote` 在扫描和移动正文之前验证两项。状态修订变化返回专用陈旧错误；摘要变化返回候选已改变错误。工具不自动重写事务。

## Tracking schema

在唯一 state 中增加：

- `reader_contracts[]`：`id`、`summary`、`owner`、`established_chapter`、`due_chapter`、`status`、`evidence_chapters`；
- `knowledge_facts[]`：`id`、`character`、`timeline_event_id`、`learned_chapter`、`source`、`confidentiality`、`status`。

逐章事务通过 `delta.reader_contract_changes` 与 `delta.knowledge_fact_changes` 做 `upsert/delete`。验证集中在 `tracking_commit.py`，Dashboard 不重写 schema。旧 state 缺少两字段时按空数组读取，并在下一次成功事务中写出当前 schema。

## 单章上下文包

新增 `chapter_context.py`，复用追踪 state 的解析与项目路径边界。输出固定 JSON：

- identity：项目、章号、`state_revision`；
- sources：路径、类型、摘要；
- fixed：定位、静态设定、文风；
- dynamic：近三章、角色、伏笔、承诺、知情事实；
- chapter：细纲、上一章、禁止事项；
- diagnostics：缺失、截断、容量。

默认只返回当前章相关对象；超限时按优先级截断并记录 diagnostics，不读取整本正文替代。

## Dashboard

服务端提供：

- 候选列表内嵌 `impactSummary`；
- 项目状态只读 API，直接从 tracking state 和派生文件生成；
- action 请求携带客户端看到的 revision 与 digest，服务端再次验证。

前端增加影响区和状态区，不提供编辑按钮。API 解析集中在服务端，前端只渲染稳定 DTO。

## 作者声纹

新增确定性 `author_voice_profile.py`：

1. 只发现 `正文/` 下的正式章节，排除特殊目录和符号链接逃逸；
2. 提取可复现统计与短证据定位，不复制长段正文；
3. 在 `设定/文风.md` 的固定标记间更新机器分析；
4. 标记缺失或损坏时拒绝写入，作者区域保持原字节；
5. 相同样本重复运行不产生差异。

工程工具只回答“声纹资料是否从合法样本安全、稳定地产生”，不自行声称更吸引读者。效果证据使用独立 treatment：冻结剧情包、模型、上下文、预算和停止规则，只切换声纹提示；缺少非 synthetic 真人输入时状态固定为 `PENDING_HUMAN_EVIDENCE`。

## 旧书吸引力实验

在 `quality_lifecycle.py` 增加独立于 `story-quality-longitudinal/v2` 的旧书修订协议。它不复用生成 treatment 的被试内双臂读取：

- A/B 各提交同一连续 15 章，章号和未修订正文摘要必须一致；
- `revised_chapters` 在读者接触文本前冻结，B 只允许这些章与 A 不同；
- `assignment = between_subject`，每名 reader 只读取一个盲码 arm；
- `primary_endpoint = first_quit_chapter` 固定；其他阅读观察为 secondary；
- `pilot` 只返回 `UNDERPOWERED_PILOT`，不得选 winner；`powered` 必须提交功效设计和预注册判定规则；
- 输入与结果使用不可变摘要绑定，真人数据不得由 synthetic/LLM 记录冒充。

局部修订是否可采用仍由 revision 生命周期判断；旧书实验只研究修订对目标读者阅读行为的影响，两者不能互相替代。

## 证据等级

- 单章 revision 证书：修订正确性。
- 单书 pilot：流程可行与方差估计。
- 单书 powered：该作品上的效果证据。
- 多个全新 held-out 故事包及功效审计：系统层效果证据。

## 兼容与恢复

- 所有 schema 扩展向后兼容旧 state；不提供反向降级写入。
- 候选拒绝发生在移动前，失败无需恢复正文。
- Dashboard 新区块在缺 state 时显示不可用原因，不创建文件。
- 作者声纹更新失败时不替换 `文风.md`。
