"""Scene source selection, current facts and blind-view isolation."""
import importlib.util
from pathlib import Path
import unittest

import test_workflow as fixtures

n = fixtures.n

spec = importlib.util.spec_from_file_location('packets', Path(__file__).resolve().parents[1]/'.novel-kit/scripts/context_packets.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)


class ContextPackets(unittest.TestCase):
    setUp = fixtures.Workflow.setUp
    write = fixtures.Workflow.write
    plan = fixtures.Workflow.plan
    ready = fixtures.Workflow.ready
    prepare = fixtures.Workflow.prepare
    scene_delivery = fixtures.Workflow.scene_delivery
    adopt_scene = fixtures.Workflow.adopt_scene
    chapter_delivery = fixtures.Workflow.chapter_delivery
    adopted_chapter = fixtures.Workflow.adopted_chapter
    def context_spec(self, scene, chapter=1, prerequisites=None):
        return {'chapter': chapter, 'scene': scene, 'prerequisites': prerequisites or [],
                'prerequisite_audit': {'status': 'checked', 'unresolved': []}}
    def adopted(self, sc):
        s = self.scene_delivery(sc)
        self.write(s['delivery'], '## 章内事实增量\n当前只有一把钥匙。\n')
        if hasattr(n, 'review_start'):
            source = s['files'][0]['source']
            self.write(s['delivery'], '<!-- novel-candidate:'+source+' -->\n'+n.text(self.root/source)
                       +'\n<!-- /novel-candidate -->\n## 章内事实增量\n当前只有一把钥匙。\n')
            n.review_start(self.root, s)
        n.prepare(self.root, s); n.accept(self.root, s['id'], '测试模拟通过')
        if not hasattr(n, 'review_start'):
            journal_path = self.root/f'審閱/採用/{s["id"]}/journal.json'
            journal = n.load(journal_path); journal['delivery'] = s['delivery']
            self.write(str(journal_path.relative_to(self.root)), n.dump(journal))

    def test_same_source_prose_and_facts_are_isolated(self):
        self.ready(scenes=3); self.adopted(1); self.adopted(2)
        manifest, blind, writer = p.build(self.root, self.context_spec(3))
        self.assertIn('場景 2 正文', blind)
        self.assertNotIn('場景 1 正文', blind)
        self.assertNotIn('钥匙', blind)
        self.assertIn('钥匙', writer)
        self.assertEqual(len(manifest['fact_sources']), 2)
        self.assertEqual(manifest['prose_ranges'][0]['path'], n.scene_path(1, 2))

    def test_nonadjacent_cause_requires_adopted_original_and_reason(self):
        self.ready(scenes=3); self.adopted(1); self.adopted(2)
        specification = self.context_spec(3, prerequisites=[{'path': n.scene_path(1, 1), 'reason': '钥匙转交发生在这里'}])
        _, blind, _ = p.build(self.root, specification)
        self.assertIn('場景 1 正文', blind)
        self.assertNotIn('钥匙转交', blind)
        specification['prerequisites'][0].pop('reason')
        with self.assertRaises(p.n.Invalid): p.build(self.root, specification)

    def test_future_prose_and_drift_are_denied(self):
        self.ready(scenes=3); self.adopted(1)
        self.write(n.scene_path(1, 3), '未来揭晓')
        with self.assertRaises(p.n.Invalid):
            p.build(self.root, self.context_spec(2, prerequisites=[{'path': n.scene_path(1, 3), 'reason': '未来'}]))
        self.write(n.scene_path(1, 1), '作者未复核的手改')
        with self.assertRaises(p.n.Invalid): p.build(self.root, self.context_spec(2))

    def test_crosschapter_uses_latest_formal_and_fullchapter_fallback(self):
        self.adopted_chapter(); self.plan(ch=2, scenes=1); n.confirm_plan(self.root, 2)
        manifest, blind, _ = p.build(self.root, self.context_spec(1, chapter=2))
        self.assertIn('已採用整章', blind)
        self.assertTrue(manifest['fallback'])
        with self.assertRaises(p.n.Invalid):
            p.build(self.root, self.context_spec(1, chapter=2, prerequisites=[{'path': n.scene_path(1, 1), 'reason': '旧场景'}]))

    def test_changed_fact_delivery_stops_supply(self):
        self.ready(scenes=2); self.adopted(1)
        self.write('審閱/s1.md', '篡改的旧事实')
        with self.assertRaises(p.n.Invalid): p.build(self.root, self.context_spec(2))

    def test_outputs_have_explicit_ranges_and_hashes(self):
        self.ready(scenes=2); self.adopted(1)
        result = p.write_packet(self.root, self.context_spec(2), '審閱/context.json')
        self.assertEqual(result['blind_hash'], n.digest(n.read(self.root/result['blind_path'])))
        self.assertEqual(result['writer_hash'], n.digest(n.read(self.root/result['writer_path'])))
        self.assertIn(n.STATE, result['input_hashes'])
        with self.assertRaises(p.n.Invalid): p.write_packet(self.root, self.context_spec(2), n.STATE)

    def test_unknown_legacy_fact_identity_is_not_guessed(self):
        self.ready(scenes=2); self.adopted(1)
        journal_path = self.root/'審閱/採用/s1/journal.json'
        journal = n.load(journal_path); journal.pop('delivery')
        self.write(str(journal_path.relative_to(self.root)), n.dump(journal))
        with self.assertRaises(p.n.Invalid): p.build(self.root, self.context_spec(2))

    def test_unresolved_prerequisites_and_companion_collision_do_not_write(self):
        self.ready(scenes=2); self.adopted(1)
        specification = self.context_spec(2)
        specification['prerequisite_audit']['unresolved'] = ['钥匙的转交原文尚未定位']
        with self.assertRaises(p.n.Invalid): p.build(self.root, specification)
        with self.assertRaises(p.n.Invalid): p.build(self.root, {'chapter': 1, 'scene': 2})
        self.write('審閱/context.writer.md', '作者的已有笔记')
        with self.assertRaises(p.n.Invalid):
            p.write_packet(self.root, self.context_spec(2), '審閱/context.json')
        self.assertEqual(n.text(self.root/'審閱/context.writer.md'), '作者的已有笔记')
        self.assertFalse((self.root/'審閱/context.json').exists())
        self.assertFalse((self.root/'審閱/context.blind.md').exists())

    def test_import_backup_and_manifest_are_bound(self):
        self.write('導入/原稿/book.md', '不可修改的导入原文')
        self.write('正文/第001章.md', '已确认的正式前章')
        n.confirm_import(self.root, [{'chapter': 1, 'source': '導入/原稿/book.md',
                                     'coverage': '詳細', 'location': '第一章'}])
        self.plan(ch=2, scenes=1); n.confirm_plan(self.root, 2)
        manifest, _, _ = p.build(self.root, self.context_spec(1, chapter=2))
        self.assertIn('導入/清單.json', manifest['input_hashes'])
        self.assertIn('導入/原稿/book.md', manifest['input_hashes'])
        self.write('導入/原稿/book.md', '被外部改变的备份')
        with self.assertRaises(p.n.Invalid): p.build(self.root, self.context_spec(1, chapter=2))

    def test_empty_fact_section_is_pending_supply(self):
        self.ready(scenes=2); self.adopted(1)
        journal_path = self.root/'審閱/採用/s1/journal.json'
        journal = n.load(journal_path)
        self.write(journal['delivery'], '## 章内事实增量\n\n## 审阅\n无问题')
        journal['watches'][journal['delivery']] = n.digest(n.read(self.root/journal['delivery']))
        self.write(str(journal_path.relative_to(self.root)), n.dump(journal))
        with self.assertRaises(p.n.Invalid): p.build(self.root, self.context_spec(2))


if __name__ == '__main__':
    unittest.main()
