#!/usr/bin/env python3
"""Build scene context from verified adopted prose; select prerequisites explicitly."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location('context_core', Path(__file__).with_name('novel.py'))
n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(n)


def approved_source(root, path, chapter, scene):
    """Reject future prose, drift and obsolete scene drafts from closed chapters."""
    name = n.rel(root, n.inside(root, path))
    data = n.rows(root)
    match = n.SCENE.fullmatch(name)
    if match:
        ch, sc = int(match[1]), int(match[2])
        n.require(ch == chapter and sc < scene, '场景原文只能来自本章当前场景之前')
        n.require(data.get((ch, 0), {}).get('status') != '已通過', '已收尾章节必须使用最新正式正文')
        n.verify_adopted(root, ch, sc, data)
    else:
        match = n.CHAPTER.fullmatch(name)
        n.require(match is not None, '前文只接受已采用场景或正式章节')
        ch = int(match[1])
        n.require(ch < chapter, '前文不能包含当前章之后的正文')
        if (ch, 0) in data:
            n.verify_adopted(root, ch, 0, data)
        else:
            entries = n.load(root/'導入/清單.json') if (root/'導入/清單.json').exists() else {}
            entry = entries.get(str(ch), {})
            n.require(entry.get('text') == n.digest(n.read(root/name))
                      and bool(n.read(root/name)), '正式章节尚未确认导入或版本已变')
            source = n.inside(root, entry.get('source', ''))
            n.require(n.rel(root, source).startswith('導入/原稿/')
                      and entry.get('source_hash') == n.digest(n.read(source)), '导入原稿身份已变，供给待核')
    n.revision_identity(root, name, data)
    return name


def excerpt(root, item, chapter, scene, direct=False):
    name = approved_source(root, item['path'], chapter, scene)
    raw = n.read(root/name)
    lines = raw.decode('utf-8').splitlines(keepends=True)
    start, end = item.get('start_line', 1), item.get('end_line', len(lines))
    n.require(type(start) is int and type(end) is int and 1 <= start <= end <= len(lines),
              '原文范围必须是有效的连续行号')
    n.require(direct or bool(str(item.get('reason', '')).strip()), '必要前因必须说明选择依据')
    selected = ''.join(lines[start-1:end])
    return {'path': name, 'start_line': start, 'end_line': end,
            'source_hash': n.digest(raw), 'excerpt_hash': n.digest(selected.encode('utf-8')),
            'reason': '叙事顺序的直接前场' if direct else item['reason'], 'text': selected}


def current_fact_sources(root, chapter, scene):
    """Read only the current adopted delivery for each preceding scene."""
    result = []
    data = n.rows(root)
    for sc in range(1, scene):
        n.verify_adopted(root, chapter, sc, data)
        identity = data[(chapter, sc)]['meta'].get('delivery')
        n.require(identity, '已采用场景缺少交付身份，章内事实供给待核')
        journal_path = n.inside(root, f'審閱/採用/{n.ident(identity)}/journal.json')
        journal = n.load(journal_path)
        n.require(journal['status'] == 'complete', '事实增量对应的交付尚未采用')
        targets = [c for c in journal['changes'] if c['target'] == n.scene_path(chapter, sc)]
        n.require(len(targets) == 1 and targets[0]['after_hash'] == data[(chapter, sc)]['meta']['text'],
                  '事实增量不是当前已采用场景的交付')
        delivery = journal.get('delivery')
        n.require(delivery, '旧交付缺少明确交付身份，供给待核；不能按文件顺序猜测事实来源')
        n.require(delivery and journal['watches'].get(delivery) == n.digest(n.read(root/delivery)),
                  '事实增量交付已变，供给待核')
        body = n.text(n.inside(root, delivery))
        # Facts stay in the writer view, outside the blind source-prose view.
        heading = next((line for line in body.splitlines() if line.startswith('## ')
                        and any(word in line for word in ('事实增量', '追踪与登记变更', '追蹤與登記變更'))), None)
        n.require(heading is not None, '交付缺少章内事实增量，供给待核')
        section = body.split(heading, 1)[1].split('\n## ', 1)[0].strip()
        n.require(section, '章内事实增量为空，供给待核；无新增事实也须明确记录')
        result.append({'scene': sc, 'delivery_id': identity, 'path': delivery,
                       'hash': n.digest(n.read(root/delivery)), 'text': section})
    return result


def build(root, specification):
    n.require(set(specification) <= {'chapter', 'scene', 'prerequisites', 'prerequisite_audit'},
              '未知的上下文字段，供给待核')
    audit = specification.get('prerequisite_audit', {})
    n.require(isinstance(specification.get('prerequisites'), list)
              and isinstance(audit, dict) and audit.get('status') == 'checked'
              and audit.get('unresolved') == [], '必要前因尚未明确核对或仍有未决项，供给待核')
    chapter, scene = specification['chapter'], specification['scene']
    n.require(type(chapter) is int and type(scene) is int and chapter > 0 and scene > 0,
              '上下文必须指向一个具体场景')
    n.eligible(root, chapter, scene)
    items = []
    fallback = None
    if scene > 1:
        items.append(excerpt(root, {'path': n.scene_path(chapter, scene-1)}, chapter, scene, True))
    elif chapter > 1:
        items.append(excerpt(root, {'path': n.scene_path(chapter-1, 0)}, chapter, scene, True))
        fallback = '跨章场景边界未登记，保守提供最新正式前章全文'
    for item in specification.get('prerequisites', []):
        selected = excerpt(root, item, chapter, scene)
        if not any((x['path'], x['start_line'], x['end_line']) ==
                   (selected['path'], selected['start_line'], selected['end_line']) for x in items):
            items.append(selected)
    facts = current_fact_sources(root, chapter, scene) if scene > 1 else []
    blind = '\n\n'.join(f'<!-- source:{x["path"]}:{x["start_line"]}-{x["end_line"]} -->\n{x["text"]}'
                        for x in items)
    writer = blind + '\n\n## 仅供写手和事实审阅者的累积事实\n\n' + '\n\n'.join(
        f'场景{x["scene"]:02d}，当前交付{x["delivery_id"]}\n{x["text"]}' for x in facts)
    dependencies = {n.STATE, *[x['path'] for x in items], *[x['path'] for x in facts],
                    *[f'審閱/採用/{x["delivery_id"]}/journal.json' for x in facts]}
    for item in items:
        identity = n.revision_identity(root, item['path'])
        if identity['kind'] == 'import':
            dependencies.update({'導入/清單.json', identity['source']})
        else:
            dependencies.add(f'審閱/採用/{identity["delivery"]}/journal.json')
    dependencies = sorted(dependencies)
    manifest = {'version': 1, 'chapter': chapter, 'scene': scene,
                'prose_ranges': [{k: v for k, v in x.items() if k != 'text'} for x in items],
                'fact_sources': [{k: v for k, v in x.items() if k != 'text'} for x in facts],
                'fallback': fallback, 'dependencies': dependencies,
                'input_hashes': {p: n.digest(n.read(root/p)) for p in dependencies},
                'blind_hash': n.digest(blind.encode('utf-8')), 'writer_hash': n.digest(writer.encode('utf-8'))}
    return manifest, blind, writer


def write_packet(root, specification, output):
    dest = n.inside(root, output)
    name = n.rel(root, dest)
    n.require(name.startswith('審閱/') and '/採用/' not in name and name.endswith('.json'),
              '上下文包必须写入审阅工作目录的 JSON 文件')
    n.check(root, name)
    blind_path, writer_path = dest.with_suffix('.blind.md'), dest.with_suffix('.writer.md')
    n.check(root, n.rel(root, blind_path)); n.check(root, n.rel(root, writer_path))
    n.require(not any(path.exists() for path in (dest, blind_path, writer_path)),
              '上下文产物已存在，请使用新的版本路径；不会覆盖既有文件')
    manifest, blind, writer = build(root, specification)
    manifest['blind_path'], manifest['writer_path'] = n.rel(root, blind_path), n.rel(root, writer_path)
    n.atomic(blind_path, blind.encode('utf-8')); n.atomic(writer_path, writer.encode('utf-8'))
    n.atomic(dest, n.dump(manifest))
    return manifest


def main():
    parser = argparse.ArgumentParser(description='生成当前场景的同源原文上下文包；必要前因由协调器按证据选择。')
    parser.add_argument('spec'); parser.add_argument('--root', default='.')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    try:
        with n.locked(root):
            manifest = write_packet(root, n.load(n.inside(root, args.spec)), args.output)
        print(json.dumps({'manifest': args.output, 'blind': manifest['blind_path'],
                          'writer': manifest['writer_path']}, ensure_ascii=False))
        return 0
    except (n.Invalid, OSError, ValueError, KeyError, TypeError) as exc:
        print('【上下文供给待核】'+str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
