# 版本交付、採用與恢復

協調器處理本流程；寫手只寫指定候選，審閱者只讀。Python 3.9+ 為必要依賴。以下命令在書稿根目錄執行；作者不必手填 JSON，由協調器依實際檔案產生。

命令一律經 `bash .claude/scripts/py.sh` 啟動：它依序找 `python3`、`python`、`py -3` 中可用的 Python 3.9+（排除 Windows 的 Microsoft Store 佔位程式），並以 UTF-8 讀寫。不要直接寫 `python3 …`；Windows 上它常是佔位程式。

## 檔案的用途

- `追蹤/場景狀態.md` 是場景工作狀態的唯一入口，四欄保留；備註由工具保存細綱與正文版本，不手改。
- `草稿/第NNN章/場景MM.md` 是場景候選。場景採用後凍結；整章採用前，後續場景讀已採用場景和交付中的章內事實增量。
- `草稿/第NNN章/整章候選.md` 是收尾候選；正式章節只在採用後出現在 `正文/`。
- `審閱/修訂/<id>/` 保存修訂候選、影響分析與任務。`任務.json` 是修訂任務狀態，不複製場景狀態表。
- `審閱/採用/<id>/journal.json` 保存不可手改的交付快照、原版本和恢復進度。它不是第二份可編輯正文。交付 ID 用英數、底線或連字號，例如 `ch001-sc01-v1`。

## 確認細綱與開始

作者確認細綱後，把細綱的狀態改為單值 `- 狀態：已確認`，場景標題使用 `## 場景01 標題`，由 01 連續編號。然後：

```sh
bash .claude/scripts/py.sh .claude/scripts/novel.py confirm-plan 1
bash .claude/scripts/py.sh .claude/scripts/novel.py begin 1 1
```

工具登記所有場景及收尾，凍結細綱版本。尚未開始任何場景時，可以修改細綱後再次確認；已有寫作內容時不得直接改確認摘要來繞過復核。收尾使用 `begin 1 0`。

待審後作者要求修改，先執行 `reopen 1 1`（收尾為 `reopen 1 0`），旧交付立即失效。已採用內容走 `/revise`；整章採用後只修訂正式章節，不再修改留存的場景草稿。

## 凍結交付

完成審閱與交付 Markdown 後，建立一次性交付規格，例如 `審閱/第001章/場景01_v1.json`：

```json
{
  "id": "ch001-sc01-v1",
  "kind": "scene",
  "chapter": 1,
  "scene": 1,
  "delivery": "審閱/第001章/場景01_交付.md",
  "files": [
    {"source": "草稿/第001章/場景01.md", "target": "草稿/第001章/場景01.md"}
  ],
  "context": ["設定/文風樣本.md", "追蹤/追蹤.md"],
  "review": {
    "mode": "完整",
    "completed": ["copy-editor", "consistency-checker", "character-reviewer", "prose-reviewer", "structure-reviewer"],
    "unresolved": []
  }
}
```

`context` 列出實際影響本次審閱的設定、角色卡、原文等檔案；工具另綁定細綱、同章前序場景和上一章。`completed` 只能列真正完成的審閱者。`unresolved` 列未解決 S1/S2、嚴重分歧和需要作者裁決的覆蓋缺口；S3/S4 仍放交付檔，不必全部當阻塞項。

```sh
bash .claude/scripts/py.sh .claude/scripts/novel.py prepare 審閱/第001章/場景01_v1.json
```

工具保存精確快照並將場景改成待審。先完成交付檔再 prepare；之後改正文、交付檔、細綱或輸入都需重新交付。新版本使用新 ID，不能覆寫舊 journal。

收尾用 `kind: chapter`、`scene: 0`、`mode: 章節`，正文檔案映射為 `草稿/第001章/整章候選.md` → `正文/第001章.md`。同時交付本章追蹤、兌現登記等更新：各自先寫候選，再加入 `files`。所有目標的修改前內容都會凍結。

場景交付只能採用該場景，章內事實增量保留於交付檔；整章採用才更新全書追蹤。收尾重新檢查兑现，證據使用正式章節位置與候選版本，不能沿用已被順稿刪掉的場景原句。

## 作者採用

僅在作者已明確採用該交付版本後執行：

```sh
bash .claude/scripts/py.sh .claude/scripts/novel.py accept ch001-sc01-v1 --approval '作者回覆：通過'
```

一個待審交付時可由「通過」指向它；多個待審對象須先確定指的是哪份。命令參數是決策記錄，不能證明真人授權，協調器不得自行填入虛構回覆。

若缺少必要審閱或仍有未決嚴重問題，工具要求 `--override '作者針對哪些缺口作了什麼裁決'`。不能把含糊的「可以」擴張成知道所有缺口。作者採用不會把審閱缺席或原問題改寫成自動通過。

作者排除某項追蹤建議時，先依此產生新候選與新版交付，不採用包含被排除項目的快照。內容有變就重審受影響範圍。

## 修訂

文字修訂與情節修訂都先建立任務。情節影響分析與作者範圍決定先完成，再執行：

```sh
bash .claude/scripts/py.sh .claude/scripts/novel.py revision-start fix-ch001 正文/第001章.md
```

工具保存當前文本快照；對作者已手改的稿，這是「開始審閱時的作者稿」，不是「修改前稿」。修改前依據取上次採用 journal 的原文或已核實 Git 版本；找不到就報告基準缺失，不猜造差異，也不先 commit 全工作區。

逐章候選映射到任務目標，交付用 `kind: revision`、`revision: fix-ch001`。文字修訂用文字模式，情節修訂用完整模式。每次只採用一個正文；追蹤變更留到整個修訂收尾。

改動同章已採用場景時，後續已採用場景與收尾會標為待復核。按原文證據列影響範圍，經作者授權後用 `revision-extend <id> <paths...>` 納入。內容無須改的依賴也可用相同正文作候選，在復核後採用。跨章依賴需一致性審閱搜尋後續正文並列入任務，腳本不宣稱理解故事依賴。

全部目標採用後，再交付 `kind: revision-finish`、同一 `revision`，`files` 至少包含最終 `追蹤/追蹤.md`，另加所需設定、兑现登記。作者採用這份收尾後任務才完成。只通過最後一章不解除續寫阻塞。

未採用任何目標且原文未被手改時，可以 `revision-cancel <id>`；部分採用不能直接取消，須先完成事實同步或另外制定回復修訂。

## 中斷恢復與提交

- `accept` 中斷：以原 ID 重跑，先核對所有目標，再跳過已完成的檔案；已完成的採用不重做。
- 遇到外部手改：停止且保留現場。比較 journal 的前後快照和現有文字，與作者處理衝突，不能強制覆寫。
- 放棄中斷採用：`rollback <id> --reason '取消原因'`，僅在檔案仍是快照中的改前/改後版本時恢復；可重跑。已完成採用走修訂，不使用 rollback。
- prepare 後、待審狀態寫入前中斷：不會獲准採用。場景仍是撰寫中時，用新 ID 重新 prepare；保留舊快照供查核。

採用本身不依賴 Git。需要記錄版本時，只列本次實際檔案：

```sh
bash .claude/scripts/py.sh .claude/scripts/novel.py commit --message '第001章 場景01 通過' 草稿/第001章/場景01.md 追蹤/場景狀態.md 審閱/第001章/場景01_交付.md 審閱/第001章/場景01_v1.json 審閱/採用/ch001-sc01-v1/journal.json
```

禁止 `git add -A`。有任何原有暫存變更時，採用仍保留，但自動提交停止並說明；不要清掉、混入或替作者提交原有暫存。提交失敗不撤銷已採用正文，報告「已採用、未提交」。

## Hook 邊界

Write/Edit 在寫入草稿前共用 `check`；正式正文直接 Write/Edit 被阻止。導入的新正文由導入整理步驟寫入並確認清單。Shell、外部編輯器與其他工具不在 Hook 攔截範圍內；工具以版本比對發現漂移，不把 Hook 宣傳為授權驗證器。

設定依 [Claude Code 官方 Hook 文件](https://code.claude.com/docs/en/hooks) 使用 `Write|Edit` 和退出碼 2。Windows 需按當地 Python 命令調整設定；本版本尚未做 Windows 與 Claude Code 真實會話驗證。
