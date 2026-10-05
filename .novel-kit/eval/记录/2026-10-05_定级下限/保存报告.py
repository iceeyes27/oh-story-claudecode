"""Extract a copy-editor subagent's final hand-back report from its transcript; record model, reads, hash."""
import hashlib, json, pathlib, sys
src, dest = sys.argv[1], pathlib.Path(sys.argv[2])
report, model, reads = None, None, []
for line in open(src, encoding='utf-8'):
    m = json.loads(line).get('message')
    if not isinstance(m, dict):
        continue
    model = m.get('model') or model
    for c in m.get('content') or []:
        if not isinstance(c, dict) or c.get('type') != 'tool_use':
            continue
        inp = c.get('input') or {}
        if c.get('name') in ('Read', 'Glob', 'Grep'):
            reads.append(c['name'] + ':' + str(inp.get('file_path') or inp.get('pattern') or inp.get('path')))
            continue
        texts = [v for v in inp.values() if isinstance(v, str) and len(v) > 200]
        if texts:
            report = max(texts, key=len)
if not report:
    sys.exit('no report: ' + src)
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(report.rstrip() + '\n', encoding='utf-8')
meta = {'model': model, 'tool_calls': reads, 'report_sha256': hashlib.sha256(dest.read_bytes()).hexdigest()}
dest.with_suffix('.meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
outside = [r for r in reads if '2026-10-05_定级下限/输入' not in r]
print(dest.name, model, len(report), 'reads', len(reads), 'OUTSIDE' if outside else 'ok', outside)
