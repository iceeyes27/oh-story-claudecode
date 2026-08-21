# 候选系统 · 技术设计

## 一、设计取舍：候选态放在哪

| 方案 | 机制 | 结论 |
|---|---|---|
| A 候选目录约定 | 正文写 `正文/候选/`，promote 脚本移入 `正文/` | **采用**。纯文件约定，全平台（含 generic）可用，与 narralume「production/candidate 物理分离」一致 |
| B frontmatter 状态位 | 正文写正稿路径 + `status: candidate` 标记 | 否。污染正稿文件，所有读者/守卫都要判标记，易漏 |
| C hook 强制暂存 | PreToolUse hook 改写路径 | 否作主机制。依赖平台 hook，generic Web AI 直接失效；违反 C1 |

**决定**：以方案 A 为主机制（SKILL + 文件约定 + promote 脚本），hook 仅作路径覆盖的兜底增强（扩展项）。

## 二、数据流

```
候选模式写作（单章 / 逐章确认日更）
  narrative-writer ──写──▶ 正文/候选/第XXX章_章名.md
                     └暂存▶ 正文/候选/第XXX章_追踪事务.json   (tracking 事务 JSON，不 commit)
  主会话 ──写后同轮──▶ AI句式/去味/退化扫描（作用于候选文件）blocking 清零
  ▲ 此时 正文/ 与 _tracking-state.json 均未变

作者审批
  「采用第X章 / 全部采用」
    scripts/candidate-commit.py promote --chapter X
      1. 校验候选文件 + 暂存事务存在、扫描已过
      2. 原子移动 候选/第XXX章_*.md ──▶ 正文/第XXX章_*.md
      3. tracking_commit.py commit（回放暂存事务 JSON）→ 原子替换 _tracking-state.json
      4. flow-state update（current_chapter/next_action）
      5. 归档或清除暂存事务 JSON
  「重写第X章 更XX」/「弃用第X章」
    scripts/candidate-commit.py reject --chapter X
      → 候选/第XXX章_*.md + 事务 JSON 移入 候选/_历史/第XXX章_{ts}.md
      → 正文/ 与追踪不动；重写则 narrative-writer 重新产出候选
```

关键不变式：
- **追踪只在 promote 时推进**——`_tracking-state.json` 永远只反映已采用正文。
- **候选自带待提交事务**——promote = move + replay，天然幂等/可重跑，复用既有原子事务模型（C3）。
- 候选章之间不互相依赖 promote：单章候选模式下，下一章须等本章采用后才写（审批门 = 天然的串行门），因此不存在「候选章读不到前章追踪」的问题。

## 三、组件契约

### 3.1 目录约定
```
{书名}/正文/
├── 第001章_章名.md              # 正稿（已采用）
├── 候选/
│   ├── 第002章_章名.md          # 待批准正文
│   ├── 第002章_追踪事务.json    # 待回放的 tracking 事务
│   └── _历史/
│       └── 第002章_20260821-1530.md  # 被替换/弃用的候选
```

### 3.2 新增脚本 `skills/story-write/scripts/candidate-commit.py`
- `promote --project <dir> --chapter <N>`：执行数据流第 2-5 步；`--all` 批量按章号升序 promote。
- `reject --project <dir> --chapter <N> [--rewrite]`：归档候选；`--rewrite` 时保留意图供重写。
- `list --project <dir>`：列出候选目录待审项（供 SKILL / dashboard 消费）。
- 失败语义与 `tracking_commit.py` 对齐：move 失败不推进追踪；tracking commit 失败保留候选与事务 JSON，直接重跑同一 promote。
- 探测 python 顺序 `python3/python/py`，跨平台字符与路径处理沿用现有脚本约定。

### 3.3 narrative-writer 契约变更（agents_version bump）
- prompt 新增可选参数 `candidate_mode: true` 与 `output_dir`（默认 `正文/`，候选模式传 `正文/候选/`）。
- 候选模式下：正文写 `output_dir`，并把本章 tracking 事务 JSON 写到同目录 `第XXX章_追踪事务.json`，**不调用 tracking_commit**。
- 非候选模式：行为逐字节不变（C4）。

### 3.4 story-write SKILL.md 变更
- 模式路由表新增「候选/逐章确认/先给我看」→ 候选模式；裸调用诊断在「已有正文+追踪」时新增「候选中：第X章待审」状态展示。
- Phase 4 单章流程 step 7/12 分支：候选模式写候选路径、step 12 改为「暂存事务不 commit」。
- Phase 5「写后同轮清零」明确覆盖候选文件；新增「审批门」话术（采用/重写/弃用命令）。
- 新增 references 小节或 `references/candidate-workflow.md` 承载候选完整流程，避免 SKILL.md 膨胀（现已 1019 行）。

## 四、边界与兼容

- **日更纯批量**（R7/C4）：路由到 `workflow-daily.md` 时默认直写不变；候选批量为扩展项，设计预留 `candidate-commit.py promote --all` 接口但 MVP 不接日更。
- **跨平台**（C1）：核心全靠文件约定 + 主会话脚本调用，Claude Code / OpenCode / Codex / ZCode / OpenClaw / Reasonix / generic 一致可用。hook 路径覆盖候选目录列为扩展（需改 `story_hook_core.js` + 六端 parity 锁 + 各端 wrapper）。
- **部署契约**（C2）：narrative-writer 变更 → bump `agents_version` 25→26；story-setup 打包新脚本；更新各端 parity 清单与 `current-contract.json`；README/CHANGELOG 记「重跑 /story-setup 新开会话」。

## 五、回滚

- 候选功能是纯增量 opt-in：不开启候选模式时代码路径与现状一致（AC5 回归保证）。
- 回滚 = 移除候选路由 + 脚本 + agents_version 回退；已产生的 `正文/候选/` 目录不影响正稿与追踪，可手动清理。
