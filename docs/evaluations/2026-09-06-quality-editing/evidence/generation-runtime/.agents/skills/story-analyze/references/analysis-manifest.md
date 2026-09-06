# 可追溯分析清单

`story-analyze long` 用 `_analysis-manifest.json` 记录来源指纹、Stage 状态、逐章尝试和关系结果修订。它补充 `_progress.md`，不替代章节边界表或人类可读进度。

## 文件位置

```text
拆文库/{书名}/
├── _progress.md
├── _analysis-manifest.json
└── _analysis/
    ├── relations-draft.json
    └── results/
        └── relationships-v0001.json
```

清单必须与 `_progress.md` 同目录。analysis schema 1 绑定 `_progress.md` schema v3 的原文路径、字节数、SHA-256 和章节边界摘要。

## Stage 0.5：初始化

```bash
node skills/story-analyze/scripts/analysis-manifest.js init 拆文库/{书名}/_progress.md
node skills/story-analyze/scripts/analysis-manifest.js validate 拆文库/{书名}/_analysis-manifest.json
```

相同输入重复初始化会保留已有历史。来源或章节边界变化时，校验失败并要求回到 Stage 0 重建；不得修改清单中的指纹绕过检查。

## Stage 2：逐章尝试与恢复

```bash
node skills/story-analyze/scripts/analysis-manifest.js begin-stage 拆文库/{书名}/_analysis-manifest.json 2
node skills/story-analyze/scripts/analysis-manifest.js resume 拆文库/{书名}/_analysis-manifest.json
```

`resume` 返回 `pending_chapters`、`failed_chapters` 和 `completed_chapters`。只处理前两组。

每章最终结果确定后立即记录：

```bash
node skills/story-analyze/scripts/analysis-manifest.js record-chapter 拆文库/{书名}/_analysis-manifest.json {N} success --output 章节/第{N}章_摘要.md
node skills/story-analyze/scripts/analysis-manifest.js record-chapter 拆文库/{书名}/_analysis-manifest.json {N} failed --error "{错误摘要}"
```

成功尝试只接受对应的 `章节/第{N}章_摘要.md`，并保存文件 SHA-256；失败尝试保留错误摘要。全部章节成功时执行：

```bash
node skills/story-analyze/scripts/analysis-manifest.js complete-stage 拆文库/{书名}/_analysis-manifest.json 2
```

仍有失败章节但按现有部分失败策略继续 Stage 3 时，必须显式执行：

```bash
node skills/story-analyze/scripts/analysis-manifest.js complete-stage 拆文库/{书名}/_analysis-manifest.json 2 --allow-failures
```

此时状态为 `completed_with_errors`。后续可再次 `begin-stage 2`，只重试 `resume` 返回的失败章节。

## Stage 4c：发布关系结果

开始 Stage 4 后，将结构化草稿写入 `_analysis/relations-draft.json`：

```json
{
  "entities": [
    {
      "id": "character-xu-qian",
      "name": "许七安",
      "type": "protagonist",
      "confidence": 0.99,
      "aliases": [
        { "name": "宁宴", "kind": "nickname", "confidence": 0.95 }
      ]
    },
    {
      "id": "character-li-miaozhen",
      "name": "李妙真",
      "type": "supporting",
      "confidence": 0.97,
      "aliases": []
    }
  ],
  "relationships": [
    {
      "source": "character-xu-qian",
      "target": "character-li-miaozhen",
      "type": "ally",
      "direction": "undirected",
      "sentiment": "信任",
      "description": "共同处理案件后形成合作关系。",
      "confidence": 0.9,
      "evidence": [
        { "path": "章节/第20章_摘要.md", "chapter": 20, "start_line": 18, "end_line": 21 }
      ]
    }
  ]
}
```

发布命令：

```bash
node skills/story-analyze/scripts/analysis-manifest.js begin-stage 拆文库/{书名}/_analysis-manifest.json 4
node skills/story-analyze/scripts/analysis-manifest.js publish-relations 拆文库/{书名}/_analysis-manifest.json 拆文库/{书名}/_analysis/relations-draft.json
```

发布结果写入 `_analysis/results/relationships-vNNNN.json`。相同规范化内容重复发布返回已有修订，不创建新文件。

规则：

- 只有 `proper_name`、`nickname` 且置信度不低于 `0.85` 的别名可解析为关系端点。
- `descriptor`、`title` 只保留为别名信息，不参与端点解析。
- 无向关系按实体 ID 排序；有向关系保持 `source_to_target`。
- 每条关系至少一条证据；证据必须指向同章已成功登记的 `章节/第{N}章_摘要.md`，行号为 1-based 闭区间。
- 自环、未知实体、重复实体引用、重复关系、非法置信度和证据变化都会拒绝发布。
- 首个关系结果发布后，已成功且可能被结果引用的章节摘要不可替换或改为失败；此前失败的章节仍可恢复成功，再发布新关系修订。

## 中断处理

所有命令先验证来源、清单和已发布结果。进程异常终止可能留下 `.analysis-manifest-cas-{revision}` 申领文件；仅在确认对应写入进程已经停止后释放：

```bash
node skills/story-analyze/scripts/analysis-manifest.js release-claim 拆文库/{书名}/_analysis-manifest.json {nextRevision} --claim-id {claimId} --confirm-writer-stopped
```

不要手工改 `_analysis-manifest.json`、已发布关系结果或申领文件。
