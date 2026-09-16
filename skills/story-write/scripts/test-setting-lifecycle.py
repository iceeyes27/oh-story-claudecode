"""Readiness gates and unresolved debts, using isolated book fixtures."""
import importlib.util
import json
import hashlib
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent

def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

volume = load('volume_setting_tests', 'volume-audit.py')
writer = load('writer_setting_tests', 'build_writer_prompt.py')
candidate = load('candidate_setting_tests', 'candidate-commit.py')

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.book = Path(self.temp.name)
        for name in ('设定', '追踪', '大纲'):
            (self.book/name).mkdir()
        (self.book/'设定/规则.md').write_text('# 录音\n能当面回放。', encoding='utf-8')
        (self.book/'设定/_设定登记.md').write_text('''| 编号 | 类型 | 来源 | 一句话 | 窗口 | 目标 | 摘录 |
|---|---|---|---|---|---|---|
| SET-001 | payoff | 设定/规则.md | 录音 | 第1章 | 当面回放改变选择 | 能当面回放 |
| SET-002 | recurring | 设定/规则.md | 习惯 | 每1–2章 | 记得习惯 | 能当面回放 |
''', encoding='utf-8')
        self.state = {'last_committed_chapter':3,'setting_payoff':{'enabled':True,'schema_version':1,'since_chapter':1},'setting_payoffs':{}}
        self.write_state()

    def tearDown(self):
        self.temp.cleanup()

    def write_state(self):
        (self.book/'追踪/_tracking-state.json').write_text(json.dumps(self.state),encoding='utf-8')

    def findings(self, start=1, end=3):
        return {f['code'] for f in volume.setting_payoff_due_findings(self.book,start,end,{'volume':1})}

    def record(self, result, sid='SET-001', chapter=1):
        self.state['setting_payoffs'].setdefault(sid,{'records':[]})['records'].append({'result':result,'chapter':chapter})
        self.write_state()

    def test_partial_untriggered_and_unpaid_remain_due(self):
        for result in ('部分兑现','条件未触发','未兑现'):
            with self.subTest(result=result):
                self.record(result)
                self.assertIn('Setting_Payoff_Due',self.findings())

    def test_complete_closes_obligation(self):
        self.record('已兑现')
        self.assertNotIn('Setting_Payoff_Due',self.findings())

    def test_prior_volume_debt_survives(self):
        self.record('部分兑现')
        self.assertIn('Setting_Payoff_Due',self.findings(2,3))

    def test_explicit_future_reschedule(self):
        p=self.book/'设定/_设定登记.md'
        p.write_text(p.read_text().replace('第1章','第5章'),encoding='utf-8')
        self.assertNotIn('Setting_Payoff_Due',self.findings())

    def test_recurring_boundary_and_no_false_reset(self):
        self.record('已兑现','SET-002',1)
        self.assertNotIn('Setting_Payoff_Recurring_Overdue',self.findings())
        self.record('条件未触发','SET-002',3)
        self.state['last_committed_chapter']=4;self.write_state()
        self.assertIn('Setting_Payoff_Recurring_Overdue',self.findings(2,4))

    def test_future_evidence_cannot_clear_old_audit(self):
        self.record('已兑现',chapter=4)
        self.state['last_committed_chapter']=4;self.write_state()
        self.assertIn('Setting_Payoff_Due',self.findings())

    def test_volume_target_cannot_escape_audit(self):
        p=self.book/'设定/_设定登记.md'
        p.write_text(p.read_text().replace('第1章','卷一'),encoding='utf-8')
        self.assertIn('Setting_Payoff_Due',self.findings())

    def test_final_candidate_is_audited_against_projection(self):
        p=self.book/'设定/_设定登记.md'
        p.write_text(p.read_text().replace('第1章','第4章'),encoding='utf-8')
        projected=json.loads(json.dumps(self.state))
        projected['last_committed_chapter']=4
        result=volume.setting_payoff_due_findings(self.book,1,4,{'volume':1},projected)
        self.assertTrue(any(f['code']=='Setting_Payoff_Due' for f in result))
        projected['setting_payoffs']['SET-001']={'records':[{'chapter':4,'result':'已兑现'}]}
        result=volume.setting_payoff_due_findings(self.book,1,4,{'volume':1},projected)
        self.assertFalse(any(f['code']=='Setting_Payoff_Due' for f in result))
        self.assertEqual(json.loads((self.book/'追踪/_tracking-state.json').read_text()),self.state)

    def ready_candidate(self):
        (self.book/'大纲/细纲_第4章.md').write_text(
            '#### 设定兑现\n| 编号 | 关系 | 目标 | 备注 |\n|---|---|---|---|\n'
            '| SET-001 | 兑现 | 录音使对方退还押金 | |\n',encoding='utf-8')
        hashes={str(p.relative_to(self.book)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.book/'设定').rglob('*.md')}
        review={'schema':'setting-readiness/v1','reviewer':'fixture','sources':hashes,
                'checks':[{'id':i,'status':'ready','reason':'Fixture defines the relevant rule and expected event'}
                          for i in ('rules','resources','characters','information','progression','closure')],'issues':[]}
        (self.book/'设定/_设定审查.json').write_text(json.dumps(review),encoding='utf-8')
        prose=self.book/'candidate.md';prose.write_text('录音响起，他退还了押金。',encoding='utf-8')
        item={'id':'SET-001','registry_sha256':hashes['设定/_设定登记.md'],'relation':'兑现',
              'evidence':[{'anchor':'他退还了押金'}],'review':{'result':'已兑现','reviewer':'fixture','note':'录音改变对方选择'}}
        return prose,{'setting_payoffs':[item]}

    def test_candidate_gate_evidence_and_partial_reason(self):
        prose,binding=self.ready_candidate()
        changes=candidate.setting_payoff_gate(self.book,4,prose,binding,{'delta':{}},self.state)
        self.assertEqual(changes[0]['result'],'已兑现')
        binding['setting_payoffs'][0]['evidence'][0]['anchor']='未出现的假证据'
        with self.assertRaises(candidate.CandidateError):
            candidate.setting_payoff_gate(self.book,4,prose,binding,{'delta':{}},self.state)
        binding['setting_payoffs'][0]['evidence'][0]['anchor']='他退还了押金'
        binding['setting_payoffs'][0]['review']={'result':'部分兑现','reviewer':'fixture','note':''}
        with self.assertRaisesRegex(candidate.CandidateError,'原因'):
            candidate.setting_payoff_gate(self.book,4,prose,binding,{'delta':{}},self.state)

    def test_volume_adoption_gate_uses_current_candidate(self):
        (self.book / "正文").mkdir()
        for chapter in range(1, 4):
            (self.book / "正文" / f"第{chapter}章.md").write_text("此前已采用正文。", encoding="utf-8")
        (self.book/'大纲/卷纲_第1卷.md').write_text(
            '# 卷纲·第一卷\n章节范围：第 1–4 章\n## 核心矛盾\n主矛盾：活下去\n下一卷新周期规划',encoding='utf-8')
        p=self.book/'设定/_设定登记.md'
        p.write_text(p.read_text().replace('第1章','第4章'),encoding='utf-8')
        prose=self.book/'第004章_回放.md';prose.write_text('录音响起，他退还押金。',encoding='utf-8')
        projected=json.loads(json.dumps(self.state));projected['last_committed_chapter']=4
        projected['setting_payoffs']['SET-001']={'records':[{'chapter':4,'result':'部分兑现'}]}
        with self.assertRaisesRegex(candidate.CandidateError,'通用 volume_gate'):
            candidate.volume_gate(self.book,4,prose,{'volume_gate':{'approved_by_author':True,'reason':'延期'}},projected)
        projected['setting_payoffs']['SET-001']['records'][0]['result']='已兑现'
        receipt=candidate.volume_gate(self.book,4,prose,{},projected)
        self.assertEqual(receipt['volume'],1)
        self.assertEqual(json.loads((self.book/'追踪/_tracking-state.json').read_text()),self.state)

    def test_in_progress_keeps_real_volume_payoff_boundary(self):
        (self.book / "大纲/卷纲_第1卷.md").write_text("章节范围：第1–3章\n## 核心矛盾\n活下去。", encoding="utf-8")
        (self.book / "正文").mkdir()
        for chapter in range(1, 4):
            (self.book / "正文" / f"第{chapter}章.md").write_text("已采用正文。", encoding="utf-8")
        registry = self.book / "设定/_设定登记.md"
        registry.write_text(registry.read_text().replace("第1章", "第3章"), encoding="utf-8")
        self.state["last_committed_chapter"] = 3
        self.write_state()
        result = volume.audit_volume(self.book, 1, through_chapter=1)
        self.assertIn("Setting_Payoff_Due", {f["code"] for f in result["findings"]})
        registry.write_text(registry.read_text().replace("第3章", "卷一"), encoding="utf-8")
        self.state["last_committed_chapter"] = 1
        self.write_state()
        result = volume.audit_volume(self.book, 1, through_chapter=1)
        self.assertNotIn("Setting_Payoff_Due", {f["code"] for f in result["findings"]})
        self.assertEqual(result["metrics"]["future_chapters"], [2, 3])

    def test_candidate_rechecks_source_freshness(self):
        prose,binding=self.ready_candidate()
        (self.book/'设定/规则.md').write_text('# 录音\n能当面回放。新增例外。',encoding='utf-8')
        with self.assertRaisesRegex(candidate.CandidateError,'过期'):
            candidate.setting_payoff_gate(self.book,4,prose,binding,{'delta':{}},self.state)

    def test_new_book_cannot_silently_disable_registered_flow(self):
        prose,binding=self.ready_candidate()
        self.state['last_committed_chapter']=0
        self.state['setting_payoff']['enabled']=False;self.write_state()
        with self.assertRaisesRegex(ValueError,'新书'):
            writer.setting_payoff_block(self.book,1)
        with self.assertRaisesRegex(candidate.CandidateError,'新书'):
            candidate.setting_payoff_gate(self.book,1,prose,{}, {'delta':{}},self.state)

    def test_new_init_defaults_on_and_import_defaults_off(self):
        doc={'schema_version':1,'book_title':'测试','last_chapter':0,
             'context':{'position':{'volume':'第一卷','volume_start_chapter':1,'story_time':'清晨','scene':'柜台'},
                        'long_term_constraints':[], 'active_character_names':[], 'continuity_risks':[],
                        'recent_chapters':[], 'next_chapter_commitments':[]},
             'character_snapshots':{},'foreshadow':[],'timeline_events':[]}
        self.assertTrue(candidate.tracking.normalize_initial_document(doc)['setting_payoff']['enabled'])
        doc['last_chapter']=3
        self.assertFalse(candidate.tracking.normalize_initial_document(doc)['setting_payoff']['enabled'])

    def test_writer_refuses_missing_review(self):
        (self.book/'大纲/细纲_第4章.md').write_text('#### 设定兑现\n无\n',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'审查记录'):
            writer.setting_payoff_block(self.book,4)

    def test_writer_refuses_deleted_registry_when_enabled(self):
        (self.book/'设定/_设定登记.md').unlink()
        with self.assertRaises(ValueError):
            writer.setting_payoff_block(self.book,4)

    def test_audit_refuses_deleted_registry_when_enabled(self):
        (self.book/'设定/_设定登记.md').unlink()
        self.assertIn('Setting_Payoff_Registry',self.findings())

if __name__ == '__main__':
    unittest.main()
