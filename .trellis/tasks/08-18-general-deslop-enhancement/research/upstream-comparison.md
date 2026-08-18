# 上游能力对比

## Source snapshot

- Repository: https://github.com/OUBIGFA/De-AI-Prompt-Enhancer-Writer-Booster-SKILL
- Branch: `main`
- Commit: `b050eefa88af3709ec24fc0b353740ccb151f563`
- Inspected: 2026-08-18

## Valuable capabilities

| Capability | Upstream evidence | Local gap | Planned adaptation |
| --- | --- | --- | --- |
| Progressive loading | `de-AI-writing/SKILL.md` routes rewrite, review and translation to the smallest reference set | General mode names external references but does not ship them | Add local lightweight index, detailed reference and translation guardrails |
| Top findings review | `ai-trace-index.md` and detector limit review to the most important 5-10 items | Current annotation mode limits count but lacks a distributed general-text taxonomy | Add general-text problem families with advisory semantics |
| Structure-preserving translation | `translation-guardrails.md` protects Markdown and information mapping | Current general mode excludes literal translation | Add an explicit translation branch under `mode=general` |

## Rejected imports

- `good-writing` author samples and style DNA: author-specific and inconsistent with the repository's genre/project style rules.
- Absolute lexical budgets and universal bans: high false-positive risk across chat, docs and technical writing.
- `scripts/style_audit.js`: hard-coded upstream directories and only a few shallow checks; it does not match this repository's validation architecture.
- Verbatim upstream files or prose: the inspected repository root does not expose a license file.

## Local boundaries

- Keep `skills/_shared/` focused on shared novel rules and scanners.
- Put general-only references under `skills/story-deslop/references/`.
- Keep the public Skill set unchanged.
- Validate locally; do not add CI files.
