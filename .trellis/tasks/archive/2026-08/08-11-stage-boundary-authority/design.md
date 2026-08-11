# 设计

- `_progress.md` schema v3 是唯一持久化边界状态，来源指纹用于识别原文变化。
- skill-local 校验器只校验和读取现有表，不在 Stage 1/2/6 重建章节。
- 旧 schema 和无效状态统一返回 Stage 0 重建。
