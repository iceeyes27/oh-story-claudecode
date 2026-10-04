"""Regression cases for recovery and review identity, using disposable books only."""
import base64
import copy
import json
from unittest.mock import patch
import unittest

import test_workflow as workflow

n = workflow.n


class Recovery(unittest.TestCase):
    setUp = workflow.Workflow.setUp
    write = workflow.Workflow.write
    plan = workflow.Workflow.plan
    ready = workflow.Workflow.ready
    scene_delivery = workflow.Workflow.scene_delivery
    adopt_scene = workflow.Workflow.adopt_scene
    chapter_delivery = workflow.Workflow.chapter_delivery
    adopted_chapter = workflow.Workflow.adopted_chapter
    revision_delivery = workflow.Workflow.revision_delivery
    git = workflow.Workflow.git
    init_git = workflow.Workflow.init_git
    prepare = workflow.Workflow.prepare

    def test_unstarted_existing_file_cannot_be_revision_target(self):
        self.ready(); self.write(n.scene_path(1, 2), '预先存在的文本')
        with self.assertRaises(n.Invalid):
            n.revision_start(self.root, 'bypass', [n.scene_path(1, 2)])
        self.assertFalse(n.task_path(self.root, 'bypass').exists())

    def test_unregistered_chapter_cannot_be_revision_target(self):
        target = n.scene_path(1, 0); self.write(target, '没有导入身份的正文')
        with self.assertRaises(n.Invalid): n.revision_start(self.root, 'bypass', [target])

    def test_commit_brackets_are_literal(self):
        self.init_git()
        wanted = '審閱/报告[1].md'; unwanted = '審閱/报告1.md'
        self.write(wanted, '列明的文件'); self.write(unwanted, '不能混入的文件')
        n.safe_commit(self.root, [wanted], 'literal scope')
        self.assertEqual(self.git('-c', 'core.quotePath=false', 'show', '--format=', '--name-only').decode().strip(), wanted)
        self.assertFalse(self.git('diff', '--cached', '--name-only'))

    def test_simplified_outline_and_conflicting_status(self):
        self.write('大綱/細綱/第001章.md', '- 状态：已确认\n## 场景01 标题\n')
        n.confirm_plan(self.root, 1)
        self.assertIn((1, 1), n.rows(self.root))
        self.write('大綱/細綱/第001章.md', '- 状态：已确认\n- 狀態：草案\n## 场景01 标题\n')
        with self.assertRaises(n.Invalid): n.outline(self.root, 1)

    def test_prepare_requires_review_start(self):
        self.ready(); s = self.scene_delivery()
        with self.assertRaises(n.Invalid): n.prepare(self.root, s)
        self.assertFalse((self.root/'審閱/採用/s1').exists())

    def full_delivery(self, s):
        result = '逐场景审阅说明\n\n'
        for f in s['files']:
            result += '<!-- novel-candidate:' + f['source'] + ' -->\n'
            result += (self.root/f['source']).read_text(encoding='utf-8')
            result += '\n<!-- /novel-candidate -->\n'
        self.write(s['delivery'], result)

    def test_review_freeze_rejects_changed_candidate_before_prepare(self):
        self.ready(); s = self.scene_delivery(); self.full_delivery(s)
        n.review_start(self.root, s)
        self.write(s['files'][0]['source'], '审阅开始后偷偷换稿')
        with self.assertRaises(n.Invalid): n.prepare(self.root, s)
        self.assertEqual(n.load(self.root/'審閱/採用/s1/journal.json')['status'], 'reviewing')

    def test_review_freeze_rejects_changed_context_or_spec(self):
        self.ready(); s = self.scene_delivery(); self.write('設定/設定.md', '规则 A')
        s['context'] = ['設定/設定.md']; self.full_delivery(s); n.review_start(self.root, s)
        self.write('設定/設定.md', '规则 B')
        with self.assertRaises(n.Invalid): n.prepare(self.root, s)
        self.write('設定/設定.md', '规则 A'); altered = copy.deepcopy(s); altered['context'] = []
        with self.assertRaises(n.Invalid): n.prepare(self.root, altered)

    def test_delivery_full_text_must_equal_frozen_candidate(self):
        self.ready(); s = self.scene_delivery(); n.review_start(self.root, s)
        with self.assertRaises(n.Invalid): n.prepare(self.root, s)
        self.full_delivery(s); n.prepare(self.root, s); n.accept(self.root, s['id'], '通过')

    def test_withdraw_preserves_candidate_and_unblocks_predecessor_revision(self):
        self.ready(); self.adopt_scene(); s = self.scene_delivery(2)
        self.full_delivery(s); n.review_start(self.root, s); n.prepare(self.root, s)
        candidate = (self.root/n.scene_path(1, 2)).read_bytes()
        self.write(n.scene_path(1, 1), '作者手改前场')
        n.withdraw(self.root, 1, 2, '修订前场后重新审阅', '作者授权撤回')
        self.assertEqual((self.root/n.scene_path(1, 2)).read_bytes(), candidate)
        self.assertEqual(n.rows(self.root)[1, 2]['status'], '未開始')
        with self.assertRaises(n.Invalid): n.accept(self.root, 's2', '通过')
        n.revision_start(self.root, 'fix', [n.scene_path(1, 1)])
        with self.assertRaises(n.Invalid): n.begin(self.root, 1, 2)

    def test_withdraw_without_journal_and_interruption_resumes(self):
        self.ready(); n.begin(self.root, 1, 1); self.write(n.scene_path(1, 1), '保留的草稿')
        before = (self.root/n.STATE).read_bytes(); real = n.atomic
        def stop(path, data):
            if path == self.root/n.STATE: raise OSError('interrupted withdrawal')
            real(path, data)
        with patch.object(n, 'atomic', stop):
            with self.assertRaises(OSError): n.withdraw(self.root, 1, 1, '作者改计划', '作者授权')
        self.assertEqual((self.root/n.STATE).read_bytes(), before)
        with self.assertRaises(n.Invalid): n.begin(self.root, 1, 1)
        n.withdraw(self.root, 1, 1, '作者改计划', '作者授权')
        self.assertEqual(n.rows(self.root)[1, 1]['status'], '未開始')
        self.assertEqual(n.text(self.root/n.scene_path(1, 1)), '保留的草稿')

    def test_rebind_keeps_adopted_identity_and_registers_new_scenes(self):
        self.ready(); self.adopt_scene(); adopted = n.rows(self.root)[1, 1]['meta']['text']
        self.plan(scenes=3)
        n.rebind_plan(self.root, 1, '作者确认新细纲且复核已采用前场不受影响', '作者授权重绑')
        self.assertEqual(n.rows(self.root)[1, 1]['meta']['text'], adopted)
        self.assertEqual(n.rows(self.root)[1, 3]['status'], '未開始')
        n.begin(self.root, 1, 2)

    def test_rebind_rejects_removing_started_scene_and_hand_edited_adoption(self):
        self.ready(); self.adopt_scene(1); self.adopt_scene(2)
        self.plan(scenes=1)
        with self.assertRaises(n.Invalid): n.rebind_plan(self.root, 1, '删除旧场', '作者授权')
        self.plan(scenes=2); self.write(n.scene_path(1, 1), '手改但未复核')
        with self.assertRaises(n.Invalid): n.rebind_plan(self.root, 1, '新细纲', '作者授权')

    def test_revision_extend_requires_identity_but_accepts_author_hand_edit(self):
        self.ready(scenes=3); self.adopt_scene(1); self.adopt_scene(2)
        self.write(n.scene_path(1, 1), '作者手改已采用前场')
        n.revision_start(self.root, 'fix', [n.scene_path(1, 1)])
        self.write(n.scene_path(1, 3), '未开始但存在')
        before = n.task_path(self.root, 'fix').read_bytes()
        with self.assertRaises(n.Invalid): n.revision_extend(self.root, 'fix', [n.scene_path(1, 3)])
        self.assertEqual(n.task_path(self.root, 'fix').read_bytes(), before)
        self.write(n.scene_path(1, 2), '作者手改已采用后场')
        n.revision_extend(self.root, 'fix', [n.scene_path(1, 2)])
        self.assertEqual(len(n.load(n.task_path(self.root, 'fix'))['targets']), 2)

    def test_revision_updates_delivery_identity_and_preserves_old_history(self):
        self.ready(); self.adopt_scene(); target = n.scene_path(1, 1)
        old = (self.root/'審閱/採用/s1/journal.json').read_bytes()
        n.revision_start(self.root, 'fix', [target])
        self.prepare(self.revision_delivery(target)); n.accept(self.root, 'r1', '通过')
        self.assertEqual(n.rows(self.root)[1, 1]['meta']['delivery'], 'r1')
        self.assertEqual((self.root/'審閱/採用/s1/journal.json').read_bytes(), old)
        self.assertEqual(n.revision_identity(self.root, target)['delivery'], 'r1')

    def test_old_prepared_journal_cannot_authorize_first_adoption(self):
        self.ready(); self.prepare(self.scene_delivery())
        path = self.root/'審閱/採用/s1/journal.json'; journal = n.load(path)
        journal['version'] = 1; journal.pop('binding'); n.atomic(path, n.dump(journal))
        with self.assertRaises(n.Invalid): n.accept(self.root, 's1', '通过')
        n.withdraw(self.root, 1, 1, '旧交付重新审阅', '作者授权')
        self.assertEqual(n.load(path)['status'], 'withdrawn')

    def test_old_applying_journal_can_only_resume_existing_adoption(self):
        self.adopted_chapter(); target = n.scene_path(1, 0)
        n.revision_start(self.root, 'fix', [target]); self.prepare(self.revision_delivery())
        real = n.atomic
        def stop(path, data):
            if path.name == '任務.json': raise OSError('interrupted existing adoption')
            real(path, data)
        with patch.object(n, 'atomic', stop):
            with self.assertRaises(OSError): n.accept(self.root, 'r1', '通过')
        path = self.root/'審閱/採用/r1/journal.json'; journal = n.load(path)
        journal['version'] = 1; n.atomic(path, n.dump(journal))
        self.assertEqual(n.accept(self.root, 'r1', '恢复原采用'), 'complete')

    def test_review_start_crash_resumes_without_refreezing_changed_input(self):
        self.ready(); s = self.scene_delivery(); self.full_delivery(s)
        real = n.atomic
        def stop(path, data):
            if path == self.root/n.STATE: raise OSError('interrupted review start')
            real(path, data)
        with patch.object(n, 'atomic', stop):
            with self.assertRaises(OSError): n.review_start(self.root, s)
        self.assertEqual(n.rows(self.root)[1, 1]['status'], '撰寫中')
        n.review_start(self.root, s)
        self.assertEqual(n.rows(self.root)[1, 1]['status'], '自動審閱中')
        self.write(s['files'][0]['source'], '重新开读前外部更改')
        with self.assertRaises(n.Invalid): n.review_start(self.root, s)

    def test_review_snapshot_preserves_trailing_newlines_and_exact_delivery(self):
        self.ready(); s = self.scene_delivery(); self.write(s['files'][0]['source'], '第一段\n\n第二段\n')
        self.full_delivery(s); n.review_start(self.root, s)
        journal = n.load(self.root/'審閱/採用/s1/journal.json')
        self.assertEqual(base64.b64decode(journal['review_candidates'][s['files'][0]['source']]), '第一段\n\n第二段\n'.encode())
        altered = n.text(self.root/s['delivery']).replace('第二段\n\n<!--', '第二段\n<!--')
        self.write(s['delivery'], altered)
        with self.assertRaises(n.Invalid): n.prepare(self.root, s)
        self.full_delivery(s); n.prepare(self.root, s); n.accept(self.root, 's1', '通过')

    def test_context_ranges_cannot_change_while_sources_stay_same(self):
        self.ready(); s = self.scene_delivery(); self.write('設定/設定.md', '第一行\n第二行\n')
        s['context'] = ['設定/設定.md']
        s['context_ranges'] = [{'path': '設定/設定.md', 'start_line': 1, 'end_line': 1, 'reason': '当前行动依据'}]
        self.full_delivery(s); n.review_start(self.root, s)
        altered = copy.deepcopy(s); altered['context_ranges'][0]['end_line'] = 2
        with self.assertRaises(n.Invalid): n.prepare(self.root, altered)

    def test_withdraw_rejects_adopted_and_requires_reason_authorization(self):
        self.ready(); self.adopt_scene()
        with self.assertRaises(n.Invalid): n.withdraw(self.root, 1, 1, '不能撤回已采用', '作者授权')
        n.begin(self.root, 1, 2)
        for reason, approval in [('', '作者授权'), ('撤回', '')]:
            with self.assertRaises(n.Invalid): n.withdraw(self.root, 1, 2, reason, approval)
        self.assertEqual(n.rows(self.root)[1, 2]['status'], '撰寫中')

    def test_withdrawn_started_scene_cannot_be_deleted_by_rebinding(self):
        self.ready(); self.adopt_scene(); n.begin(self.root, 1, 2)
        self.write(n.scene_path(1, 2), '保留旧候选')
        n.withdraw(self.root, 1, 2, '改变计划', '作者授权'); self.plan(scenes=1)
        with self.assertRaises(n.Invalid): n.rebind_plan(self.root, 1, '删除开始过的场景', '作者授权')

    def test_rebinding_has_legal_path_after_revision_finish(self):
        self.ready(); self.adopt_scene(); self.plan(scenes=3)
        target = n.scene_path(1, 1); n.revision_start(self.root, 'fix', [target])
        self.prepare(self.revision_delivery(target)); n.accept(self.root, 'r1', '通过')
        with self.assertRaises(n.Invalid): n.rebind_plan(self.root, 1, '修订未结案', '作者授权')
        self.write('審閱/追踪候选.md', '修订后的章内事实已同步')
        finish = {'id': 'finish', 'kind': 'revision-finish', 'revision': 'fix', 'delivery': '審閱/finish.md',
                  'files': [{'source': '審閱/追踪候选.md', 'target': '追蹤/追蹤.md'}],
                  'review': {'mode': '文字', 'completed': sorted(n.REVIEWERS['文字']), 'unresolved': []}}
        self.prepare(finish); n.accept(self.root, 'finish', '通过')
        n.rebind_plan(self.root, 1, '新细纲经作者确认，已采用前场影响已复核', '作者授权')
        n.begin(self.root, 1, 2)

    def test_rebinding_completed_chapter_retains_historical_scene_identity(self):
        self.adopted_chapter(); self.plan(scenes=1)
        # Same numbered scenes, with a revised explanatory outline section.
        self.write('大綱/細綱/第001章.md', '- 状态：已确认\n## 场景01 标题\n复核通过的新说明\n')
        n.rebind_plan(self.root, 1, '只改说明，已完成影响复核', '作者授权')
        self.assertEqual(n.rows(self.root)[1, 1]['status'], '已通過')
        self.assertEqual(n.rows(self.root)[1, 0]['status'], '已通過')

    def test_review_freezes_adoption_identity_journal(self):
        self.ready(); self.adopt_scene(); target = n.scene_path(1, 1)
        n.revision_start(self.root, 'fix', [target]); s = self.revision_delivery(target)
        self.full_delivery(s); n.review_start(self.root, s)
        path = self.root/'審閱/採用/s1/journal.json'; prior = n.load(path)
        prior['status'] = 'cancelled'; n.atomic(path, n.dump(prior))
        with self.assertRaises(n.Invalid): n.prepare(self.root, s)

    def packet(self, source):
        self.write('審閱/packet.blind.md', '审阅正文的必要前因')
        self.write('審閱/packet.writer.md', '审阅正文及事实说明')
        dependencies = [n.STATE, source]
        packet = {'version': 1, 'prose_ranges': [], 'dependencies': dependencies,
                  'input_hashes': {x: n.digest(n.read(self.root/x)) for x in dependencies},
                  'blind_path': '審閱/packet.blind.md', 'writer_path': '審閱/packet.writer.md',
                  'blind_hash': n.digest(n.read(self.root/'審閱/packet.blind.md')),
                  'writer_hash': n.digest(n.read(self.root/'審閱/packet.writer.md'))}
        self.write('審閱/packet.json', json.dumps(packet, ensure_ascii=False))
        return packet

    def test_packet_dependencies_are_automatically_frozen_and_must_be_current(self):
        self.ready(); s = self.scene_delivery(); self.write('審閱/必要前因.md', '源文件 A')
        self.packet('審閱/必要前因.md'); s['context'] = ['審閱/packet.json']; self.full_delivery(s)
        self.write('審閱/必要前因.md', '源文件 B')
        with self.assertRaises(n.Invalid): n.review_start(self.root, s)
        self.write('審閱/必要前因.md', '源文件 A'); n.review_start(self.root, s)
        journal = n.load(self.root/'審閱/採用/s1/journal.json')
        self.assertIn('審閱/必要前因.md', journal['frozen'])
        self.assertIn('審閱/packet.blind.md', journal['frozen'])
        self.write('審閱/必要前因.md', '开读后源文件 C')
        with self.assertRaises(n.Invalid): n.prepare(self.root, s)

    def test_packet_blind_writer_tampering_rejected_before_review_start(self):
        self.ready(); s = self.scene_delivery(); self.write('審閱/必要前因.md', '实际原文')
        self.packet('審閱/必要前因.md'); s['context'] = ['審閱/packet.json']
        self.write('審閱/packet.blind.md', '被换成另一段')
        with self.assertRaises(n.Invalid): n.review_start(self.root, s)
        self.assertFalse((self.root/'審閱/採用/s1/journal.json').exists())

    def test_prepare_does_not_publish_state_or_author_text_on_mismatched_delivery(self):
        self.ready(); s = self.scene_delivery(); n.review_start(self.root, s)
        before = (self.root/n.STATE).read_bytes(); prose = n.read(self.root/n.scene_path(1, 1))
        with self.assertRaises(n.Invalid): n.prepare(self.root, s)
        self.assertEqual((self.root/n.STATE).read_bytes(), before)
        self.assertEqual(n.read(self.root/n.scene_path(1, 1)), prose)

    def test_simplified_state_output_and_legacy_state_input_normalize(self):
        self.ready(); content = n.text(self.root/n.STATE)
        self.assertIn('场景01 | 未开始', content)
        legacy = content.replace('场景', '場景').replace('未开始', '未開始')
        self.write(n.STATE, legacy)
        self.assertEqual(n.rows(self.root)[1, 1]['status'], '未開始')
        n.begin(self.root, 1, 1)
        self.assertIn('场景01 | 撰写中', n.text(self.root/n.STATE))


if __name__ == '__main__': unittest.main()
