# 平台与 Agent 兼容性

共享核心使用 Python 3.9+ 和 UTF-8，无 Node.js 或第三方 Python 依赖；Git 可选。本地 Agent 需读写文件和执行命令，纯聊天接口只能给规划和候选，不能宣称登记或采用。

## 系统与入口

| 平台 | 命令 | Hook 启动 | 验证边界 |
|---|---|---|---|
| macOS | ./novel 或 sh novel | 系统 bash 调用 Python | 本地测试结果见 validation |
| Windows PowerShell/CMD | .\novel.cmd | PowerShell 经 cmd 启动 Python | 原生检查只在 Windows 执行，其他系统略过 |

macOS 探测 python3、python、py -3，Windows 探测 py -3、python、python3；跳过不可用或低于3.9者，固定 UTF-8。无需 Git Bash。也可由已验证 Python 调用 novel.py。gitattributes 固定 shell LF、batch CRLF；Windows Hook 的固定程序以 UTF-16LE 编码参数启动，不改变 ExecutionPolicy，JSON 载荷经 stdin。

| Agent | 规则技能 | 独立角色 | 前置保护 |
|---|---|---|---|
| Claude Code | CLAUDE.md 引入 AGENTS.md，生成 .claude/skills | 生成 .claude/agents | settings.local.json，Write/Edit/MultiEdit/NotebookEdit |
| Codex | AGENTS.md，原生 .agents/skills | 生成 .codex/agents TOML | hooks.json，apply_patch 和兼容写事件，需宿主信任 |
| 其他本地 Agent | 明确读取 AGENTS.md 和技能 | 按其能力载入 .novel-kit/roles | 无专用 Hook，协调器写前 check |

Claude setup --models quality 默认为写手和 copy-editor opus，其余 sonnet；inherit 不指定模型，选择记录在 adapters.json。Codex 与通用 Agent 继承宿主设定。无并行可顺序开独立上下文，无独立能力须报告缺席；同会话切换角色不算独立盲读。

通用入口可说：“先读取本目录 AGENTS.md，按需求载入技能；说明本地读写、执行 novel、独立子代理是否可用，缺失时如实交付。”文件协议相容不代表每个宿主都已实测。

## 配置与维护

依实际宿主选 claude/codex/generic，确实同时使用才选 all：

```sh
./novel setup --agent codex
./novel setup --agent codex --check
./novel doctor --agent codex
```

Windows 换为 .\novel.cmd。根目录由入口 novel.py 所在位置确定。修改来源为 AGENTS.md、六个 .agents/skills、七个 .novel-kit/roles，以及 workflows/scripts/hooks；适配生成，不手改。

setup 生成普通文件，无链接或 Windows 开发者模式要求。自定义适配与记录不符会拒绝覆盖，check 只报差异；检查后 setup --replace 先备份。保留无关设置、Hook 和文件。含本机路径的 settings.local.json、hooks.json、adapters.json 不提交，移动目录或系统后重跑。生成角色技能可提交；旧转接路径没有第二份核心实现。

只读源码检查可执行 setup --agent all --models quality --check-sources，核对确定性生成副本，无需首次部署被忽略的本机配置。CI 在生成前先做此核对，防止自动生成掩盖仓库中旧副本。

doctor 执行 Hook 启动命令送允许/拒绝载荷，验证配置和关卡；不能知道宿主是否实际载入技能、信任 Hook、隔离子代理。真实会话验收需逐宿主执行。

## 保护范围

- 已启用 Hook 拒绝直接修改正式正文、工具专属状态和 journal、已有原稿备份；草稿检查细纲确认、顺序和当前版本。
- apply_patch 检查整份新增、修改、删除和移动两端，任一不合格拒绝整次；相对路径按 tool cwd 解析。
- 开读冻结与 prepare/accept 核对实际输入版本；交付全文与待采用源核对，旧审阅不能套给新文字。
- 路径身份检查包含字面、真实路径和既有祖先身份；短名、junction、符号链接、前缀与大小写别名回到书稿仍检查。非法路径、数据流和末尾点空白拒绝。
- **无有效 Python 时，Write/Edit/MultiEdit/NotebookEdit/apply_patch 五类匹配写入全部拒绝**，含设定和书稿外路径；只读工具可用。先修运行环境并 doctor，不用字符串回退猜测路径身份。
- Shell、外部编辑器、其他 MCP 写入和未匹配工具未自动拦截。Hook 和版本核对不是系统隔离，不证明作者身份或真人授权。
- 宿主未加载/未信任或不支持配置时，保护仅是流程约定；每次候选写前 check，采用仍走工具，不能宣称前置拦截已启用。

## 接口依据

以下是2026-09-24核对时采用的官方接口依据，保留为历史记录，不将其当成本轮宿主实测：

- [Codex 技能](https://learn.chatgpt.com/docs/build-skills)
- [Codex AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- [Codex 子代理](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [Codex Hooks](https://learn.chatgpt.com/docs/hooks)
- [Claude Code Hooks](https://code.claude.com/docs/en/hooks)

不推测最低 Agent 版本。旧版缺 exec form、子代理或 Hook 时升级或明确使用通用流程。源码测试、配置自检和真实会话是不同验证范围，逐项记录。
