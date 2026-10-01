# 平台與 Agent 相容性

共用流程使用 Python 3.9+ 與 UTF-8，不依賴 Node.js、第三方 Python 套件或特定模型。Git 只用於選擇性的版本提交。這份工具組需要 Agent 具備本地檔案與命令能力；只有聊天介面的工具只能提供文字，不能代為登記或採用。

## 作業系統

| 平台 | 命令 | 寫入 Hook 啟動 | 本輪驗證 |
|---|---|---|---|
| macOS | `./novel` 或 `sh novel` | 系統 bash → Python | Python 3.9.6、bash 3.2 實機測試 |
| Windows PowerShell / CMD | `.\novel.cmd` | 系統 PowerShell → cmd 啟動器 → Python | 原生測試與 CI 已加入；本輪未取得 Windows 實機結果 |

macOS 啟動器依序探測 python3、python、py -3；Windows 依序探測 py -3、python、python3，跳過不可用或版本過舊的命令。啟動器固定 UTF-8；Windows 無需 Git Bash。也可使用本機已確認可用的 Python 呼叫 `novel.py`。

`.gitattributes` 固定 shell 腳本 LF、Windows batch CRLF。Windows Hook 的 PowerShell 啟動參數使用固定程式的 UTF-16LE 編碼，避免中文、空白與單引號路徑被外層 shell 重解釋；沒有改動 ExecutionPolicy，Hook JSON 載荷仍走 stdin。

## Agent 入口

| Agent | 規則與技能 | 獨立角色 | 前置寫入保護 |
|---|---|---|---|
| Claude Code | `CLAUDE.md` 引入 `AGENTS.md`；產生 `.claude/skills/` | 產生 `.claude/agents/*.md` | `.claude/settings.local.json`，Write/Edit/MultiEdit/NotebookEdit |
| Codex | `AGENTS.md`；原生 `.agents/skills/` | 產生 `.codex/agents/*.toml` | `.codex/hooks.json`，apply_patch 與相容寫檔事件；需要宿主信任 |
| 其他本地 Agent | 明確要求讀 `AGENTS.md` 和對應 `.agents/skills/<名稱>/SKILL.md` | 依其子代理功能載入 `.novel-kit/roles/` | 未實作工具專用 Hook；寫前由協調器執行 check |

模型設定由宿主繼承，不把 Claude 模型名稱寫進共用規則或 Codex 角色。無並行能力時可依序使用獨立上下文。沒有獨立子代理時不宣稱完成盲讀；缺席項仍記錄，作者明確裁決後才可採用。不能把在同一會話切換角色視為独立審閱。

通用 Agent 啟動提示：

> 請先讀取本資料夾的 AGENTS.md，按我的小說需求載入 .agents/skills/ 中對應技能。先回報你是否能讀寫本地檔案、執行 novel 命令及啟動獨立子代理；缺少能力時依規則降級，不假稱完成審閱或採用。

這是檔案與流程協定相容，不是宣稱每個 Agent 都已實測或都支持同一種 Hook、指令或權限模型。

## 安裝、更新與自檢

macOS：

```sh
./novel setup --agent all
./novel setup --agent all --check
./novel doctor --agent all
```

Windows：

```powershell
.\novel.cmd setup --agent all
.\novel.cmd setup --agent all --check
.\novel.cmd doctor --agent all
```

`--agent` 可選 all、claude、codex、generic。在沒有 Git 的書稿中也能安裝與執行。從子目錄使用絕對路徑呼叫 novel 時，根目錄依 novel.py 所在位置決定，不把子目錄誤認為書稿根。

修改只做在以下來源：

- `AGENTS.md`：共用協調規則。
- `.agents/skills/`：5 個工作流技能。
- `.novel-kit/roles/`：7 個角色規則。
- `.novel-kit/workflows/`、`.novel-kit/scripts/`、`.novel-kit/hooks/`：流程、狀態工具、Hook。

setup 產生普通檔案，沒有符號連結或 Windows 開發者模式依賴。適配檔與已記錄版本不一致時拒絕覆寫；check 只報差異。檢視差異後才用 `setup --replace`，原內容先保存到 `.novel-kit/adapter-backups/`。其他設定、其他工具的 Hook 與未列入的檔案保留。個人角色設定如需修改，會被視為自訂衝突，不會靜默抹掉。

`.claude/settings.local.json`、`.codex/hooks.json` 與 `.novel-kit/adapters.json` 含本機路徑或部署狀態，已忽略，不提交。新 checkout、搬動目錄、换機或切換作業系統時重新 setup。產生的角色與技能可提交；來源變更後需同步並 check。舊 `.claude/scripts/`、`.claude/hooks/` 和工作流路徑只作轉接，核心沒有第二份實作。

doctor 直接執行產生的 Hook 啟動命令，送入允許／拒絕載荷，不寫測試正文。它驗證配置、啟動器與關卡，不能知道宿主會話是否已讀到技能、信任 Hook 或真的隔離了子代理。

## 保護邊界

- 已啟用的 Hook 使用共用 check：拒絕直接修改正式正文、工具專屬狀態與採用日誌、既有導入原稿；草稿需要已確認細綱及合法場景順序。
- Codex apply_patch 檢查整份補丁的新增、修改、刪除及移動兩端。任何一個目標不合格就拒絕整次呼叫；相對路徑按 tool cwd 解讀。
- 狀態工具在每次交付／採用時核對版本，所有 Agent 共用相同的追蹤、修訂、回退及提交限制。
- Shell 寫入、外部編輯器、其他 MCP 寫檔與未匹配工具未自動攔截。check 與版本核對不能證明真人授權，也不是作業系統級隔離。
- Codex 未信任或不支持本配置的版本會跳過 Hook；必須在 `/hooks` 核對本地來源與信任狀態。Claude Code 也需要宿主載入並信任相應專案。未啟用時如實標為流程保護，不宣稱前置攔截。
- 找不到 Python：Windows Hook 與 macOS 的 apply_patch 一律拒絕匹配的寫入；macOS 單檔工具走保守路徑回退。若宿主連啟動器都無法執行，內部退出碼轉換不會發生；先修復 doctor，不能把 Hook 啟動失敗當成保護正常。

## 介面依據與版本差異

2026-09-24 核對的官方文件：

- [Codex 本地技能](https://learn.chatgpt.com/docs/build-skills)：專案使用 `.agents/skills`。
- [Codex AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)：共用指令入口。
- [Codex 子代理](https://learn.chatgpt.com/docs/agent-configuration/subagents)：本地 TOML 角色，未指定模型時繼承宿主設定。
- [Codex Hooks](https://learn.chatgpt.com/docs/hooks)：專案 hooks.json、commandWindows、apply_patch 的 tool_input.command 與信任流程。
- [Claude Code Hooks](https://code.claude.com/docs/en/hooks)：exec form 的 command/args、退出 2 與 Windows 啟動行為。

本實作依上述介面，沒有推測一個未驗證的最低 Agent 版本。舊版若不支持 exec form、自訂子代理或 Hooks，需升級或明確使用通用流程模式。完整宿主驗收需在每個目標 Agent 內另外執行。
