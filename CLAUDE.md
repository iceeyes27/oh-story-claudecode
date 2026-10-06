# novel-kit：Claude Code 入口

@AGENTS.md

先遵循共用 AGENTS.md。角色與技能由 `./novel setup --agent claude` 產生；Windows 使用 `.\novel.cmd setup --agent claude`。首次使用後執行 doctor，並在新會話核對本地 Hook 已載入。模型策略默认 quality（scene-writer、copy-editor 与 adjudicator 用 opus，其余角色用 sonnet）；需要全部继承会话时执行 `./novel setup --agent claude --models inherit`。
