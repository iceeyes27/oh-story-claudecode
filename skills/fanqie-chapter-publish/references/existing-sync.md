# Existing chapter synchronization

## Proven route and scope

Use the logged-in Chrome CDP session and browser-origin fetch. The September 8, 2026 run submitted chapters 1–54 of 《我在越南捞沉船》 and reread all 54 matching bodies, titles, AI=no, volume, status, and schedule. Chapter 55 returned -1019; 55–80 remained unchanged. This is evidence for the ordinary published-chapter endpoint, not for new publication or arbitrary future API schemas.

Canonical executable: `scripts/sync_fanqie_existing.py`. Reuses the existing chapter extractor and CDP transport. It has no stored cookies, account credentials, or hardcoded book/path. The new reusable wrapper is validated offline; the underlying endpoint and payload were validated live in that run. Adapt only on an actual interface failure.

## Fixed execution

1. Resolve the requested book, local prose directory, chapter range and platform volume ID. Use an existing report or the chapter manager metadata. Compare every requested chapter, including committed local revisions. Do not infer scope from Git dirty files. Existing chapter IDs are retained; never create replacement chapters.
2. Run the browser-cdp detect-only probe. Reuse a ready browser. If restart is necessary, reuse consent already given in the conversation; otherwise obtain it before closing a running browser. Never output raw resource URLs with tokens. If a page is blank, probe the chapter-list endpoint once: working API means continue, not repeatedly reload the UI. If authentication fails, request login; do not reset profiles speculatively.
3. Prepare into a fresh persistent directory under the book's reports. It extracts local text, enforces >=1000 characters, snapshots source hashes and platform data, and compares normalized paragraph text and full platform titles. Existing output directories cannot silently overwrite a plan.
4. Once comparison succeeds and publication is authorized, immediately run submit. One process runs the whole range; five chapters is a progress-report interval, not an invitation to rebuild a script or seek approval each batch. Observe incremental tool output, announce each five completed chapters or every 15 seconds. Keep a running process attached through its returned session ID; on user interruptions inspect that process and the event log first.
5. Run verify once at the end, including after quota rejection. Save the report directory; distinguish submitted, verified, audit_pending and remaining. Do not call audit_pending verified. Preserve local prose and avoid unrelated Git staging or pushes.

```bash
python3 .agents/skills/fanqie-chapter-publish/scripts/sync_fanqie_existing.py prepare \
  --book-id BOOK_ID --volume-id VOLUME_ID \
  --source-dir "BOOK/正文/VOLUME" --from 1 --to 80 \
  --out "BOOK/报告/番茄同步_DATE_RUN"
python3 .agents/skills/fanqie-chapter-publish/scripts/sync_fanqie_existing.py submit \
  --out "BOOK/报告/番茄同步_DATE_RUN"
python3 .agents/skills/fanqie-chapter-publish/scripts/sync_fanqie_existing.py verify \
  --out "BOOK/报告/番茄同步_DATE_RUN"
```

Use `python` on systems where appropriate. No need to run an additional standalone character scan: prepare enforces the publication floor before contacting chapter editors.

## Errors, timeouts and resumption

- Browser fetch: GET 10 s, POST 15 s. CDP socket 20 s; POSIX wall-clock guard 15/20 s. Windows uses the socket timeout plus browser AbortController; a caller should additionally bound the process if CDP emits events indefinitely. A tool wait should yield within 10–15 s so progress remains visible.
- Every submit writes and flushes `attempting` before the POST, then records its result. If interrupted between them, the chapter is ambiguous. Reread it: matching content can be marked verified, an audit-pending response is deferred, an unmatched attempted chapter must stop for investigation. Never retry a POST merely because its response timed out.
- `-1019`: stop all submissions in that run. The script refuses another submit with that quota event. After quota recovery, prepare a fresh plan for the remaining range using current local/platform content. Do not use scheduling to evade an existing-update limit.
- `-2014`: an individual article is under review. Continue independent chapters; defer readback. A dependency that requires that article waits until it is readable.
- `-3010`: inspect the rejected chapter against neighboring old platform bodies. Update a proven source chapter first only if already within scope; reread before retrying its dependent chapter. No speculative all-book overlap scan before ordinary updates.
- Auth failure, source-hash change, platform baseline change, or body/metadata mismatch: stop with the exact chapter. Refresh the affected comparison after resolving the cause.
- `.running` prevents two processes using one run directory. For a stale lock, inspect its recorded PID and actual process before removing just that lock. Never launch a second submission process to speed up one book.
- Special author-note, advertisement, preview, draft or timed-publication fields fail closed in this ordinary-published-chapter helper; use the established UI update path to preserve those fields. Platform content APIs use the full `第N章 标题`; the UI title input still uses only the pure title.

## Known book mapping (reconfirm against live returned rows)

《我在越南捞沉船》: book ID `7654938505423883326`; first volume ID `7654938509483969598`; local directory `我在越南捞沉船/正文/第1卷_会安·活下来`, chapters 1–80. September 8 continuation starts at chapter 55 according to the saved first-volume report. This is a dated checkpoint, not a permanent assumption about future progress.
