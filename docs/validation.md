# novel-kit 改進與驗證記錄

日期：2026-09-23。基線：32ba46e0。這是獨立 novel-kit 分支上的改進，不涉及主線合併。

## 已落實

- 候選／正式正文分離，場景與章節分別採用；整章採用時同步全書追蹤。
- prepare 保存候選、依據、交付與採用前版本；來源變更後舊交付不能採用。
- Markdown 保持場景狀態入口；採用日誌只保存快照及恢復進度。
- 文字與情節修訂均建立任務，最後追蹤同步採用後才完成；已採用場景變更會使同章後續已採用場景待復核。
- 中斷採用可重跑或回退；外部手改不覆寫。作業鎖由系統釋放，不因程序中斷留下持續佔用的鎖。
- 按檔案提交；原有暫存不動；提交失敗不偽稱已提交。
- Write/Edit 共用關卡，驗證细綱確認版本、合法狀態、前序採用與修訂任務；既有檔案不再無條件放行。
- 導入登記含來源位置、摘要／詳細覆蓋及版本；正文存在不再等同導入已確認。
- README、五個技能、相關代理與模板已統一流程。嚴重分歧、關鍵待核與審閱缺席保留；每輪盲讀新上下文；不固定每章場景數。

## 驗證

`python3 -m unittest discover -s tests -v`：36 項通過。全部使用臨時書稿與臨時 Git 倉庫，沒有採用或改動真實小說。

覆蓋：草案細綱、非法／重複狀態、跳場景、跨章待審、已有檔案、版本漂移、重新交付、章節待審不發佈、修訂全流程、同章依賴失效、手改保留、缺席審閱、導入重複／缺章、中斷恢復、回退、無 Git、原有暫存、提交失敗，以及 Hook 的 Write/Edit 與錯誤 JSON。

Python 編譯與 `git diff --check` 通過。五個技能和七個代理的 YAML 已解析，名稱、必要欄位與 Hook 設定檢查通過。

通用 `skill-creator/quick_validate.py`：new-book 通過，另外四個因既有 `argument-hint` 被拒絕。這是通用 Agent Skills 校驗範圍與 Claude Code 欄位的差異，未刪除有效欄位以求通用校驗全綠。[Claude Code 官方欄位說明](https://code.claude.com/docs/en/skills#frontmatter-reference) 明確支援 argument-hint。

Hook 設定以 [Claude Code 官方 Hook 契約](https://code.claude.com/docs/en/hooks) 核對；測試驗證 Python 入口的輸入、拒絕碼及設定，並非 Claude Code 端到端實測。

## 邊界與下一階段

- 尚未驗證 Windows、Claude Code 子代理環境和真實會話；不宣稱全平台相容。
- Shell／外部編輯器不在 Write/Edit Hook 範圍；版本核對能發現漂移，不能證明真人授權。
- 導入切分、文字比對與語義抽取仍由協調器依技能執行。現在有確認清單與按章續做規則，尚未加入通用自動切章器或大書檢索系統。
- 變更已有写作內容的細綱會被擋住，未加入自動細綱遷移；不能靠改摘要跳過已有內容的相容性審查。未開始的章節可以重新確認。
- 跨章因果依賴仍需原文搜尋與作者決定，腳本只負責版本與任務，不宣稱懂故事。
- 尚未進行真實章節的對照試用、作者盲讀或審閱費用比較。工程測試通過不能替代文風與閱讀品質驗收。

本輪完成安全與採用機制、流程口徑統一，並補入導入登記。原方案中的完整長篇導入自動化和真實寫作試用不列為完成。

## 2026-09-24 Windows 可用性修復

基線：81abcc1。範圍：文字 I/O 編碼、Hook 輸入輸出、Hook 啟動器、無 Python 時的嚴格回退。

### 問題（中文 Windows 實測）

- `novel.py` 13 處 `read_text()` 未指定編碼，預設 GBK 下 36 項測試 22 項失敗；`PYTHONUTF8=1` 下全過。
- Hook 以 locale 解碼 stdin，UTF-8 路徑成亂碼後前綴比對全部落空：寫 `正文/第001章.md`、未確認細綱的 `草稿/…/場景01.md` 均被放行（退出 0）。
- `settings.json` 用 `python3`；本機 `python3` 是 Microsoft Store 佔位程式（退出 49），Claude Code 視為非阻斷錯誤而放行。

### 修改

- `novel.py` 以 `text()`／`load()` 統一 UTF-8 讀取；`tests/test_encoding.py` 以 AST 檢查 `novel.py`、`scene_gate.py`、`tests/*.py`，未指定 encoding 的 `read_text`／`write_text`／文字模式 `open`／`subprocess(text=True)` 即失敗，UTF-8 系統上也能擋回歸。
- `scene_gate.py` 以位元組讀 stdin、嚴格 UTF-8 解碼，stderr 直接寫 UTF-8 位元組；任何例外都退出 2。
- 新增 `.claude/scripts/py.sh`：依序探測 `python3` → `python` → `py -3`，以版本檢查排除佔位程式，設 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8` 後執行；都不可用退出 127。技能與 adoption 流程命令改經此啟動器。
- 新增 `.claude/hooks/scene_gate.sh`，`settings.json` 改為 `bash "$CLAUDE_PROJECT_DIR/.claude/hooks/scene_gate.sh"`。0／2 原樣返回，其他非零一律 2；127（無 Python）時以純 bash（`LC_ALL=C`，bash 3.2 語法）判定：`正文/`、`草稿/`、`導入/原稿/` 攔截並提示安裝 Python，書稿外與其他路徑放行，取不到路徑、含 `..` 或含 `\uXXXX` 等無法還原的跳脫一律攔截。

### 驗證

環境：Windows 11 Pro 10.0.26200、Git Bash（GNU bash 5.2）、Python 3.13.3（`python`）、`python3` 為 Store 佔位程式（退出 49）、系統編碼 cp936；另以 WSL Ubuntu 22.04（Python 3.12.3、bash 5.2.21）跑同一套測試。

| 命令 | 結果 |
|---|---|
| Windows 預設編碼（未設 PYTHONUTF8）`python -m unittest discover -s tests -v` | 48 項通過（原 36 + 新 12） |
| 修改前同一命令 | 原 36 項中 22 項失敗；新增 12 項中 11 項失敗 |
| WSL `python3 -m unittest discover -s tests`（C.UTF-8 與 `LC_ALL=C`） | 均 48 項通過 |
| WSL 以原 `scene_gate.py` 跑 `tests/test_hook_encoding.py` | 2 項失敗（GBK stdin 下亂碼放行／錯誤放行），確認測試在 Linux 也能重現 |
| `python -m py_compile …`、`bash -n`、`sh -n`、`git diff --check` | 通過 |

經 `settings.json` 實際命令（`CLAUDE_PROJECT_DIR` 以 `pwd -W` 模擬，`python3` 為佔位程式）：Write `正文/第001章.md` → 2；無細綱的 `草稿/第001章/場景01.md` → 2；`設定/設定.md` → 0；Edit 以反斜線 Windows 路徑寫 `正文\第001章.md` → 2。

模擬無 Python（`PATH=/nonexistent`）：`正文/…`、`草稿/…`、`導入/原稿/…` → 2 且 stderr 提示安裝 Python 3.9+；`設定/設定.md`、書稿外路徑 → 0；缺 `file_path` → 2。

經啟動器每次 Hook 約 0.6 秒（直接呼叫 Python 約 0.2 秒），差額是佔位程式與版本探測。

### 複查後修正

獨立複查（只讀）另發現三項，已修正並補測試：

- `scene_gate.sh` 以內建 `read` 逐位元組讀 stdin，3 MB 內容需 8.4 秒；內容大到觸發 Hook 逾時就會被放行。改為有 `cat` 時整塊讀取（PATH 無 `cat` 才退回 `read`；Windows 的 MSYS 環境不一定有 `/dev/stdin`，不採用 `$(</dev/stdin)`）。3 MB 實測約 0.9 秒，`正文` → 2、`設定` → 0。
- 無 Python 回退的路徑漏洞：`\\?\` 裝置前綴、路徑段尾的點或空白（Windows 會去掉，`正文.\` 仍寫進 `正文`）、磁碟相對路徑 `D:正文\…` 曾被放行。現在前綴會先去掉再判定，後兩者一律攔截；Python 關卡本來就攔截這些情況。
- `import-book` 技能一處「語义」改為「語義」。

修正後 Windows 預設編碼 48 項通過。

### 未驗證範圍

- 未在 macOS 實機執行；回退分支刻意只用 bash 3.2 語法，但未以 bash 3.2 實測。
- 未在 Claude Code 真實會話中觸發 Hook（留待 maturity-gate 子任務）；Claude Code 在 Windows 經 Git Bash 執行 Hook 的前提依官方文件與 main 分支現行做法。
- 無 Python 回退只做字串判定，不解析符號連結；書稿外路徑回退放行、Python 關卡仍拒絕，兩者由 hook-scope 子任務統一。
- `novel.py` CLI 的 stdout／stderr 仍依 locale；經 `py.sh` 啟動時為 UTF-8，直接以 `python` 執行時不保證。

## 2026-09-24 Hook 範圍（hook-scope）

基線：ec67d6b。範圍：書稿外路徑放行、工具專屬檔禁寫、寫檔工具名擴充、無 Python 回退同步。

### 問題

- 書稿外的絕對路徑經 `inside()` 拋錯，Hook 退出 2，誤擋 Claude Code 的記憶、計劃等書稿外寫入；無 Python 回退卻放行，兩條路徑不一致。
- `追蹤/場景狀態.md`、`審閱/採用/`、`審閱/修訂/*/任務.json`、`導入/清單.json` 只應由 `novel.py` 寫入，但 Write/Edit 可直接改動。
- matcher 只有 `Write|Edit`，NotebookEdit（路徑欄位是 `notebook_path`）與舊版 MultiEdit 不經關卡。

### 修改

- `novel.py` 新增 `outside(root, name)`：只有絕對路徑，且字面路徑、`Path.resolve()` 後的真實路徑、各既有上層目錄的檔案身分（`st_dev`／`st_ino`）都不在書稿內才算書稿外；`check()` 遇到即放行。實測 `resolve()` 對 `\\?\C:\…` 與 `\\localhost\C$\…` 不會還原成盤符路徑，只比對字面與真實路徑會被這兩種寫法繞回書稿；因此 UNC／裝置路徑與書稿不同磁碟時一律不算書稿外，身分比對再補上 macOS 大小寫別名等 `resolve()` 看不出的情況。相對路徑與 `D:foo` 不算書稿外，仍由 `inside()` 拒絕。
- `TOOL_OWNED`（`re.I`）命中即拒絕並指向 adoption 流程。`novel.py` 自身經 `atomic()` 寫這些檔，不經 `check()`。另拒絕含冒號（`::$DATA`）或段尾點／空白的路徑：這些檔尚不存在時 `resolve()` 保留原樣，Windows 卻寫進同名檔，會繞過 `TOOL_OWNED`。
- `settings.json` matcher 改為 `Write|Edit|MultiEdit|NotebookEdit`；`scene_gate.py` 同步工具集合，路徑取 `file_path`，沒有則取 `notebook_path`。
- `scene_gate.sh` 回退：工具名同步；`notebook_path` 備援；工具專屬檔 glob 陣列（比對不加引號）；前綴與 glob 比對全程 `nocasematch`；拒絕冒號與 UNC；字面在書稿外時以 `[[ -ef ]]` 逐層核對既有上層目錄，連結繞回書稿即攔截。
- README（安裝段標明 Windows 必須裝 Git Bash、Hook 段）、`adoption.md`「Hook 邊界」、`CLAUDE.md` 與 `import-book` 的 Hook 名稱同步。

### 驗證

環境：Windows 11 Pro 10.0.26200、Git Bash（GNU bash 5.3.15）、Python 3.13.3（`python`）、`python3` 為 Store 佔位程式（退出 49）、系統編碼 cp936，未設 `PYTHONUTF8`。

| 命令 | 結果 |
|---|---|
| `python -m unittest discover -s tests -v` | 56 項通過（原 48 + 新 8），無略過 |
| 實作前同一命令（先寫測試） | 13 項失敗／錯誤 |
| 變異：去掉回退的 `-ef` 身分核對 | 符號連結繞回書稿的用例失敗（0 ≠ 2），還原後通過 |
| `python -m py_compile .claude/scripts/novel.py .claude/hooks/scene_gate.py`、`bash -n .claude/hooks/scene_gate.sh`、`git diff --check` | 通過 |

新測試覆蓋：書稿外絕對路徑 → 0（Python、經 settings 的佔位 `python3`、無 Python 三條路徑）；四類工具專屬檔含 `.MD`／`.JSON` 大小寫變體 → 2；MultiEdit 與以 `notebook_path` 寫 `正文/` 的 NotebookEdit → 2，`notebook_path` 缺失 → 2；`設定/設定.md`、`審閱/修訂/fix/候選.md` → 0；符號連結、`\\?\`、`\\.\`、`\\localhost\C$`、大寫路徑繞回書稿 → 拒絕；`::$DATA`、段尾點 → 拒絕；原有 `正文/`、`草稿/` 規則不變。

經 `settings.json` 實際命令手工驗收（`CLAUDE_PROJECT_DIR="$(pwd -W)"`，printf 原始 UTF-8 JSON）：書稿外 `C:/Users/…/.claude/projects/…/memory/MEMORY.md` → 0；`追蹤/場景狀態.md` → 2；`追蹤/場景狀態.MD`（Edit）→ 2；`正文/第001章.md`（Write、MultiEdit）→ 2；NotebookEdit `正文/第001章.ipynb` → 2；`導入/清單.json` → 2；`設定/設定.md` → 0。每次約 0.6 秒，與修改前相同；無 Python 回退約 0.24 秒。

Claude Code 真實會話（本機 Claude Code 桌面版，已裝 Git Bash，工作區即 novel-kit 書稿）：Write 書稿外暫存檔成功；Edit `追蹤/場景狀態.md` 被 Hook 攔截，提示「此檔由 novel.py 維護」。修改前同一會話 Write 書稿外暫存檔被攔截（「路徑必須位於專案內」）。

### 未驗證範圍

- **Windows 未裝 Git Bash 時 Hook 失效**：依[官方 Hook 文件](https://code.claude.com/docs/en/hooks)，command hook 的 `shell` 預設 `"bash"`，Windows 未裝 Git Bash 時預設改為 `"powershell"`；`bash …` 在 PowerShell 找不到，以非 2 退出，Claude Code 視為非阻斷錯誤而放行寫入。Hook 內部無法修復。評估過在 settings 顯式寫 `"shell": "bash"`：文件只說它是預設值，未說明 Git Bash 缺席時會怎樣，無法證明能轉成攔截，故未加入，留待在無 Git Bash 的 Windows 以真實會話驗證（連同 PowerShell 端退出 2 的可行寫法）。目前以 README 標明 Git Bash 為 Windows 必需依賴。
- 真實會話只驗了 Write／Edit；NotebookEdit 與 MultiEdit 只以 Hook 輸入模擬驗證。
- 未在 macOS／Linux 實機跑本輪測試；macOS 大小寫別名只靠身分比對邏輯推論，未實測。
- UNC 書稿（書稿本身在網路共用上）未實測；無 Python 回退會把 `//server` 合併成單斜線再比對，身分核對在這種情況下不生效。
- 身分比對依賴檔案系統提供穩定的 `st_ino`；不穩定的檔案系統上可能把書稿外路徑誤判為書稿內而攔截（偏嚴，不會放行），未實測。
