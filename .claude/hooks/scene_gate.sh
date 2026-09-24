#!/usr/bin/env bash
# PreToolUse 寫檔工具（Write/Edit/MultiEdit/NotebookEdit）關卡的啟動器（嚴格語義）。
# Claude Code 只把退出 2 當攔截，其他非零都會放行寫入；
# 因此 Python 關卡的任何非預期結果一律映射為 2。
# 找不到 Python 時改用純 bash 判定：受保護路徑與工具專屬檔攔截，書稿外與其他路徑放行。

# 受保護前綴（相對書稿根目錄）。
protected=('正文/' '草稿/' '導入/原稿/')
# 只由 novel.py 寫入的檔案（glob 形式）。
owned=('追蹤/場景狀態.md' '審閱/採用/*' '審閱/修訂/*/任務.json' '導入/清單.json')

case $0 in
  *[\\/]*) here=${0%[\\/]*} ;;
  *) here=. ;;
esac

# stdin 存在變數中轉交（不 export，避免大內容觸發 E2BIG）。
# 優先用 cat 整塊讀取：內建 read 在管道上逐位元組讀，大內容可慢到觸發 Hook 逾時而被放行。
# PATH 沒有 cat 時才退回 read（/dev/stdin 在 Windows 的 MSYS 環境不一定存在，不可依賴）。
if command -v cat >/dev/null 2>&1; then
  input=$(cat)
else
  IFS= read -r -d '' input || true
fi
printf '%s' "$input" | "${BASH:-bash}" "$here/../scripts/py.sh" "$here/scene_gate.py"
code=$?
case $code in
  0 | 2) exit "$code" ;;
  127) ;;
  *)
    printf '【場景關卡】關卡程式異常結束（退出碼 %s），已攔截。\n' "$code" >&2
    exit 2
    ;;
esac

# ---- 無可用 Python：純 bash 回退，逐位元組處理 ----
LC_ALL=C
hint='請安裝 Python 3.9 以上，並確認 python3、python 或 py -3 可在 PATH 中執行。'

block() {
  printf '【場景關卡】找不到可用的 Python 3.9+，%s，已攔截。%s\n' "$1" "$hint" >&2
  exit 2
}

# 取出 JSON 字串欄位並還原跳脫；只接受 \\ \" \/，其他跳脫（含 \uXXXX）視為無法判定。
json_string() {
  local re="\"$1\"[[:space:]]*:[[:space:]]*\"(([^\"\\\\]|\\\\.)*)\""
  [[ $input =~ $re ]] || return 1
  local s=${BASH_REMATCH[1]} out='' c
  while [[ -n $s ]]; do
    c=${s:0:1}
    if [[ $c == '\' ]]; then
      case ${s:1:1} in
        '\' | '"' | '/') out+=${s:1:1} ;;
        *) return 1 ;;
      esac
      s=${s:2}
    else
      out+=$c
      s=${s:1}
    fi
  done
  REPLY=$out
}

# 反斜線轉斜線、/c/ → c:/、合併 // 與 ./（只用 bash 3.2 語法，macOS 可用）。
norm() {
  local p=${1//\\//}
  # \\?\ 與 \\.\ 裝置前綴：去掉後按一般路徑處理。
  [[ $p == '//?/'* || $p == '//./'* ]] && p=${p:4}
  if [[ $p =~ ^/([A-Za-z])(/|$) ]]; then p=${BASH_REMATCH[1]}:/${p:3}; fi
  while [[ $p == *//* ]]; do p=${p//\/\//\/}; done
  while [[ $p == */./* ]]; do p=${p//\/.\//\/}; done
  while [[ $p == ./* ]]; do p=${p:2}; done
  [[ $p == */. ]] && p=${p%/.}
  [[ $p == */ && $p != / && $p != ?:/ ]] && p=${p%/}
  REPLY=$p
}

tool_owned() {
  printf '【場景關卡】「%s」由 novel.py 維護，請改用對應命令（見 .claude/workflows/adoption.md），已攔截。\n' "$1" >&2
  exit 2
}

if json_string tool_name; then
  case $REPLY in Write | Edit | MultiEdit | NotebookEdit) ;; *) exit 0 ;; esac
fi

# NotebookEdit 的目標欄位是 notebook_path。
json_string file_path || json_string notebook_path || block '且無法從 Hook 輸入取得 file_path 或 notebook_path'
[[ -n $REPLY ]] || block '且路徑為空白'
raw=${REPLY//\\//}
norm "$REPLY"; target=$REPLY

root=$CLAUDE_PROJECT_DIR
if [[ -z $root ]] && json_string cwd; then root=$REPLY; fi
[[ -n $root ]] || root=$PWD
rawroot=${root//\\//}
norm "$root"; root=${REPLY%/}

case /$target/ in */../*) block '且路徑含 ..' ;; esac
# 磁碟相對路徑（D:正文\…）依各磁碟的當前目錄解析，無法判定。
[[ $target =~ ^[A-Za-z]:([^/]|$) ]] && block '且為磁碟相對路徑'
# Windows 會去掉路徑段尾的點與空白（正文.\、正文 \ 仍寫進正文），一律攔截。
trail='[. ](/|$)'
[[ $target =~ $trail ]] && block '且路徑段以點或空白結尾'
# 盤符以外的冒號（如 ::$DATA 資料流）在 Windows 會寫進同名檔。
[[ ${target#[A-Za-z]:} == *:* ]] && block '且路徑含冒號'
# UNC（\\server\share、\\?\UNC\…）可經 \\localhost\C$ 繞回本機磁碟；書稿不在 UNC 上時無法判定。
[[ $raw == //* && $raw != //[?.]/[A-Za-z]:* && $rawroot != //* ]] && block '且為 UNC 網路路徑'

# 比對全程不分大小寫：Windows 與 macOS 預設檔案系統如此；LC_ALL=C 下只影響 ASCII。
shopt -s nocasematch
if [[ $target == /* || $target =~ ^[A-Za-z]:/ ]]; then
  if [[ $target == "$root" ]]; then
    exit 0
  elif [[ $target == "$root"/* ]]; then
    rel=${target:${#root}+1}
  else
    # 字面在書稿外：再以 -ef（裝置＋inode）核對既有祖先，防符號連結、junction、8.3 短名繞回書稿。
    d=$target
    while :; do
      [[ $d -ef $root ]] && block "且「$target」經連結指向書稿"
      case $d in
        ?:/ | /) break ;;
        ?:/*/* | /*/*) d=${d%/*} ;;
        ?:/*) d=${d:0:3} ;;
        *) d=/ ;;
      esac
    done
    exit 0 # 書稿外的路徑不由本關卡管理
  fi
else
  rel=$target
fi

# 工具專屬檔（glob，比對時刻意不加引號）；對應 novel.py 的 TOOL_OWNED。
for pattern in "${owned[@]}"; do
  [[ $rel == $pattern ]] && tool_owned "$rel"
done
for prefix in "${protected[@]}"; do
  [[ $rel == "$prefix"* ]] && block "無法核對「$rel」"
done
exit 0
