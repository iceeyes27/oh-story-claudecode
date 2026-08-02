---
name: fanqie-chapter-publish
description: "Upload a local chapter markdown file to Fanqie writer backend, normalize body formatting, save draft, and submit for immediate or scheduled release. Use when the user asks to 上传番茄、发布章节、定时发布、同步本地章节到番茄、修改番茄草稿、处理 Fanqie 章节排版，especially for projects whose chapter files live under `正文/.../第NN章_标题.md` and the target chapter changes from call to call."
---
# Fanqie Chapter Publish

把本地章节稿同步到番茄作家后台，并把容易踩坑的排版、AI 选项、定时发布分支一起处理掉。

## Platform Notes

- 所有脚本命令统一写 `python`。Windows 上 `python3` 往往是 Microsoft Store 的空壳存根，会静默失败；macOS/Linux 如果只有 `python3`，替换命令名即可。
- 脚本已强制 UTF-8 输出。不要另外用 `chcp` 或改 `PYTHONIOENCODING`。
- `agent-browser` 需要全局安装（`npm install -g agent-browser`）；命令找不到时先装再继续，不要改用其他浏览器方案。

## Invocation Contract

调用这个 skill 时，不要默认“上一章”或“刚才那章”。

用户请求里至少要包含以下信息之一：
- 明确的章节文件路径
- 明确的章节号，例如 `第52章`
- 明确的番茄章节管理 URL

如果用户只说“发一章”“把这章传上去”，先从上下文或当前项目里补齐目标章节；补不齐时，先让用户备注章节号或文件路径，再继续。

如果只有章节号，先运行：

```bash
python {SKILL_DIR}/scripts/locate_fanqie_chapter.py "第52章" --root "<project-root>"
```

- `status=unique` 时直接取返回的 `path`
- `status=multiple` 时把候选列表给用户确认
- `status=not_found` 时不要猜，直接让用户补路径或章号

## Default Release Policy

- 用户只说“发布”“上传番茄”这类动作时，默认先尝试立即发布。
- 如果平台因为当日上传字数限制、前序章节未消化、或其他发布配额限制导致当天不能立即发布，就改成排到最早可发布的下一天；如果第二天仍不合法，就继续顺延，直到得到合法时间。
- 如果一次要发多章，按章节顺序处理，并尽可能把所有章节排到当前条件下最早的连续可发布时间；不要把后章排到前章之前，也不要无故留空档。
如果想把“找章、抽正文、抓排期、算建议时间”一次性做完，直接运行：

```bash
python {SKILL_DIR}/scripts/prepare_fanqie_publish.py \
  --chapter-no "第52章" \
  --project-root "<project-root>" \
  --queue-file /tmp/fanqie-chapter-manage.txt \
  --chapter-manage-url "<fanqie-url>"
```

它会返回：
- 目标章节文件
- 章号、纯标题、正文段数、正文字符数
- 当前待发布/审核中排期
- 建议定时时间
- 一组按顺序执行的清单

## Fast Path

浏览器登录态已经就绪时，优先使用这条单脚本路径，速度明显快于多轮 `snapshot` / `eval` / 手动点控：

```bash
python {SKILL_DIR}/scripts/publish_fanqie_fast.py \
  --chapter-manage-url "<fanqie-url>" \
  --project-root "<project-root>" \
  第52章 第53章
```

特点：
- 直接连接已登录的 CDP Chrome
- 直接打开 `publish/?enter_from=newchapter`，跳过章节列表里的低效点击
- 一次脚本完成正文注入、存草稿、过错别字提示、选择基础检测、设置 `AI=否`、排期与验收
- 多章发布时，先读取当前待发布队列，再按顺序生成最快可发计划

只有在 fast path 失败，或页面结构变化导致脚本无法继续时，再退回下面的分步浏览器流程。
## Workflow

0. 发布前字数体检（推荐，尤其批量发布时）。
   先用批量脚本扫一遍目标章节，确认没有 <1000 字符的章节，避免逐个到发布台才被平台拦下。脚本按与发布脚本一致的口径统计字符数（去标题、去空行），门槛默认 1000：

   ```bash
   python {SKILL_DIR}/scripts/check_chapter_chars.py --root "<project-root>" --from <起章> --to <止章>
   ```

   - 脚本输出每章字符数，标记 <1000 的，结尾汇总不足数量；有不足时退出码非 0。
   - 任一章节不足 1000 字符，**不要**进入发布流程，先回本 skill 上游补写（见 story-write 的「平台发布底线」），达标后再发布。

1. 找章节源文件。
   优先用用户给的文件路径；如果用户只给章节号，就在当前项目里找 `正文/**/第0*NN章*.md`。
   如果用户同时给了番茄后台章节管理 URL，直接复用；没有的话，优先使用当前已打开的番茄作品后台页。

   常用检索：

   ```bash
   rg --files . | rg "正文/.*/第0*52章"
   ```

   更稳的做法是直接用定位脚本，而不是手搓 grep 结果。

2. 先把正文整理成番茄可直接粘贴的格式。
   运行：

   ```bash
   python {SKILL_DIR}/scripts/extract_fanqie_chapter.py "<chapter-file>"
   ```

   这个脚本会：
   - 从文件名或一级标题提取章号和标题
   - 删除开头的 Markdown 章标题
   - 去掉所有空白段，只保留连续正文段落
   - 输出 `chapter_no`、`title`、`display_title`、`body`

   发布页里：
   - `章节序号` 填 `chapter_no`
   - `标题` 只填 `title`
   - 不要把 `display_title` 整串再塞进标题框

3. 复用 Chrome 登录态进入番茄后台。
   无副作用探测：

   ```bash
   node {SKILL_DIR}/../browser-cdp/scripts/setup-cdp-chrome.js 9222 --detect-only
   ```

   - `CDP_STATUS=ready` 时直接继续
   - `needs-setup` 且 Chrome 未运行时，再启动 CDP Chrome
   - 如果 Chrome 正在运行且需要重启，先征得用户同意

4. 打开番茄章节管理或当前编辑页。
   常用命令：

   ```bash
   agent-browser --cdp 9222 open "<chapter-manage-url>"
   agent-browser --cdp 9222 snapshot -i
   agent-browser --cdp 9222 eval 'window.location.href'
   ```

5. 创建或更新章节草稿。
   - 从章节管理页点 `新建章节`，或进入已有草稿编辑页
   - 正文写入优先用一条管道命令完成（比逐段 `type`/`insertText` 快且不会产生大空行）：

     ```bash
     python {SKILL_DIR}/scripts/extract_fanqie_chapter.py "<chapter-file>" --eval-js \
       | agent-browser --cdp 9222 eval --stdin
     ```

     这条命令会把正文按段落写成连续 `<p>...</p>` 注入 `.ProseMirror`，并返回
     `{"ok": true, "paragraph_count": N, "char_count": M}`。
     把返回的 `paragraph_count`/`char_count` 与本地提取脚本输出比对，一致才继续。
     返回 `ok: false` 说明当前页不是编辑页，先确认页面再重试。
   - 如果注入后编辑器内容被 ProseMirror 回滚（读回段数为 0 或明显不符），再退回逐段写入方案，且不要保留空白段
   - 写入后用 `snapshot -i` 或 `eval` 复核：
     - 章号正确
     - 标题正确
     - 正文首尾和段距正常
   - 提交前先 `存草稿`

6. 发布前强制检查这两条硬规则，任一条不通过立即终止发布、退回补写，绝不尝试进入发布设置。
   - **字数门槛（平台绝对底线）**：提取正文后读取 `char_count`，必须 `≥ 1000`。番茄平台不允许 <1000 字符的章节进入发布设置——`char_count < 1000` 时直接报错退出，明确告知「第N章仅M字符，不足番茄平台最低 1000 字符，无法进入发布设置」，并退回让用户补写，**不要**尝试发布。
     - 多章发布时逐章校验；只要有一篇不足 1000，整体停下，列出所有不足章节及各自缺口，不继续发布任何一章。
     - 这条规则独立于写作侧的字数目标，是发布侧的绝对下限，任何情况下不得跳过。
   - `是否使用AI`：默认必须选 `否`
     只有用户明确要求改成 `是` 时才允许例外
   - 如果正文里还有临时修改，先同步回本地文件，保证本地稿和后台稿一致

7. 选择立即发布还是定时发布。
   优先立即发布；但番茄后台经常会拦住这一类情况：
   - 前面还有 `待发布` / `定时待发布` 的章节
   - 页面提示 `否则在前面定时章节发布前本章不进审`
   - 当日上传字数或发布配额已满，导致当天不能继续发

   这时改走定时发布：
   - 打开 `定时发布`
   - 单章时，直接排到当前约束下最早可发布的时间；如果当天不合法，就顺延到第二天，再不合法继续顺延
   - 多章时，按章节顺序依次排到最早可发布时点，尽量连续，不主动留空档
   - 默认沿用现有作品节奏
   - 如果当前作品明显是每天 `09:01` 连发，就顺延到下一个可用日期同一时间
   - 如果页面提示 `请选择半小时以后的时间进行发布`，至少推迟到合法时间
   - 定时时间一旦修改，必须再次读回输入框确认

   推荐先从章节管理页抓一版现有排期，再算建议时间。

   先抓页面文本：

   ```bash
   agent-browser --cdp 9222 eval 'document.body.innerText' > /tmp/fanqie-chapter-manage.txt
   ```

   再提取当前队列里的 `待发布/审核中` 时间：

   ```bash
   python {SKILL_DIR}/scripts/extract_fanqie_queue.py \
     /tmp/fanqie-chapter-manage.txt \
     --field times > /tmp/fanqie-scheduled-times.txt
   ```

   再算建议时间：

   ```bash
   python {SKILL_DIR}/scripts/next_fanqie_schedule.py \
     --scheduled-file /tmp/fanqie-scheduled-times.txt \
     --preferred-time "09:01"
   ```

   这个脚本会返回：
   - `scheduled_for`
   - `date`
   - `time`
   - `min_valid_time`

   用法建议：
   - 优先从章节管理页自动提取待发布/审核中时间
   - 如果自动提取结果明显不对，再手动补 `--scheduled "YYYY-MM-DD HH:MM"`
   - 再把脚本给出的 `date`、`time` 填回页面
   - 如果页面组件回滚，改用它自己的日历/时间面板去点

8. 完成提交后回到章节管理页验收。
   至少确认：
   - 行里出现新章节标题
   - `审核状态` 变成 `审核中`、`待发布` 或用户期望的其他状态
   - `发布时间` 显示为目标时间
   - 章节名称、章号、用户本次要求的目标章节一致

## Reliable Browser Tactics

- `agent-browser` 的元素引用会变化，优先按当前 `snapshot -i` 结果现取现用。
- 某些按钮看起来点到了但页面没推进，可以改用：

  ```bash
  cat <<'EOF' | agent-browser --cdp 9222 eval --stdin
  (() => {
    const btn = [...document.querySelectorAll('button')].find(
      b => (b.innerText || '').includes('确认发布')
    );
    btn?.click();
  })()
  EOF
  ```

- 日期/时间组件经常忽略直接赋值：
  - 如果 `set value` 后又回滚，改用页面自己的日历/时间面板去点
  - 每次改完都再读回 `input[placeholder="请选择日期"]` 和 `input[placeholder="请选择时间"]`

## Verification Checklist

- 本地文件已存在且提取脚本成功输出正文
- 标题框里是纯标题，不带 `第NN章`
- 编辑器里没有异常大空行
- `是否使用AI=否`
- 正文字符数 `≥ 1000`（番茄平台发布门槛）；不足则本次发布未进入发布设置、已被拦截
- 若立即发布被前置章节阻塞，已切到定时发布
- 提交后章节管理页能看到该章及对应状态

## Resources

### scripts/

- `extract_fanqie_chapter.py`
  从本地 Markdown 章节提取番茄发布所需的章号、标题和压平空行后的正文。
  `--eval-js` 直接产出可管道给 `agent-browser eval --stdin` 的正文注入脚本，写入后自动回读段数字数。
- `locate_fanqie_chapter.py`
  根据 `第NN章` 在项目根下唯一定位本地正文文件；找不到或重名时返回结构化结果。
- `next_fanqie_schedule.py`
  根据已有排期、日更节奏和最小提前时间，计算下一个更稳妥的定时发布时间。
- `extract_fanqie_queue.py`
  从番茄章节管理页文本里提取 `待发布/审核中` 章节的当前排期时间，供定时推荐脚本直接复用。
- `prepare_fanqie_publish.py`
  把定位章节、提取正文、读取当前排期、计算建议发布时间和执行清单合并成一次输出。
