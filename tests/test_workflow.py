import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / '.claude/scripts/novel.py'
spec = importlib.util.spec_from_file_location('novel', SCRIPT)
n = importlib.util.module_from_spec(spec); spec.loader.exec_module(n)
HOOK = SCRIPT.parents[1] / 'hooks/scene_gate.py'


class Workflow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='novel-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.write(n.STATE, n.table({}))

    def write(self, path, content):
        p = self.root / path; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content if isinstance(content, bytes) else content.encode('utf-8'))
        return p

    def plan(self, ch=1, scenes=2, confirmed=True):
        return self.write(f'大綱/細綱/第{ch:03d}章.md', '- 狀態：' + ('已確認' if confirmed else '草案') + '\n' + ''.join(f'## 場景{s:02d} 標題\n' for s in range(1, scenes+1)))

    def ready(self, scenes=2):
        self.plan(scenes=scenes); n.confirm_plan(self.root, 1)

    def scene_delivery(self, sc=1, name=None):
        name = name or f's{sc}'
        n.begin(self.root, 1, sc)
        source = n.scene_path(1, sc); self.write(source, f'场景 {sc} 正文')
        self.write(f'審閱/{name}.md', '完整候選與審閱結果')
        return {'id': name, 'kind': 'scene', 'chapter': 1, 'scene': sc,
                'delivery': f'審閱/{name}.md', 'files': [{'source': source, 'target': source}],
                'review': {'mode': '完整', 'completed': sorted(n.REVIEWERS['完整']), 'unresolved': []}}

    def adopt_scene(self, sc=1):
        s = self.scene_delivery(sc); n.prepare(self.root, s); n.accept(self.root, s['id'], '通過')

    def adopted_chapter(self):
        self.ready(scenes=1); self.adopt_scene()
        n.begin(self.root, 1, 0)
        self.write('草稿/第001章/整章候選.md', '已採用整章')
        self.write('審閱/closure.md', '收尾交付')
        s = {'id': 'closure', 'kind': 'chapter', 'chapter': 1, 'delivery': '審閱/closure.md',
             'files': [{'source': '草稿/第001章/整章候選.md', 'target': n.scene_path(1, 0)}],
             'review': {'mode': '章節', 'completed': sorted(n.REVIEWERS['章節']), 'unresolved': []}}
        n.prepare(self.root, s); n.accept(self.root, 'closure', '通過')

    def revision_delivery(self, target=None, name='r1'):
        target = target or n.scene_path(1, 0)
        self.write('審閱/修訂/fix/候選.md', '新的修订正文')
        self.write(f'審閱/{name}.md', '修改對照')
        return {'id': name, 'kind': 'revision', 'revision': 'fix', 'delivery': f'審閱/{name}.md',
                'files': [{'source': '審閱/修訂/fix/候選.md', 'target': target}],
                'review': {'mode': '文字', 'completed': sorted(n.REVIEWERS['文字']), 'unresolved': []}}

    def test_draft_outline_rejected(self):
        self.plan(confirmed=False)
        with self.assertRaises(n.Invalid): n.confirm_plan(self.root, 1)

    def test_unknown_and_duplicate_rows_rejected(self):
        self.ready()
        text = (self.root / n.STATE).read_text(encoding='utf-8')
        self.write(n.STATE, text.replace('未開始', '未知', 1))
        with self.assertRaises(n.Invalid): n.rows(self.root)
        self.write(n.STATE, text + next(x for x in text.splitlines() if '場景01' in x) + '\n')
        with self.assertRaises(n.Invalid): n.rows(self.root)

    def test_outline_changed_after_confirmation(self):
        self.ready(); self.plan(scenes=3)
        with self.assertRaises(n.Invalid): n.begin(self.root, 1, 1)

    def test_skip_scene_and_existing_file_do_not_bypass(self):
        self.ready(); self.write(n.scene_path(1, 2), '預先存在')
        with self.assertRaises(n.Invalid): n.check(self.root, n.scene_path(1, 2))

    def test_pending_delivery_blocks_other_scene(self):
        self.ready(); n.prepare(self.root, self.scene_delivery())
        with self.assertRaises(n.Invalid): n.begin(self.root, 1, 2)
        with self.assertRaises(n.Invalid): n.check(self.root, n.scene_path(1, 1))

    def test_reopen_invalidates_old_delivery(self):
        self.ready(); n.prepare(self.root, self.scene_delivery())
        n.begin(self.root, 1, 1, reopen=True)
        with self.assertRaises(n.Invalid): n.accept(self.root, 's1', '通過')

    def test_changed_candidate_cannot_use_old_review(self):
        self.ready(); n.prepare(self.root, self.scene_delivery())
        self.write(n.scene_path(1, 1), '作者新改')
        with self.assertRaises(n.Invalid): n.accept(self.root, 's1', '通過')
        self.assertEqual(n.rows(self.root)[1,1]['status'], '待審')

    def test_changed_delivery_is_stale(self):
        self.ready(); n.prepare(self.root, self.scene_delivery())
        self.write('審閱/s1.md', '換了交付內容')
        with self.assertRaises(n.Invalid): n.accept(self.root, 's1', '通過')

    def test_adopted_predecessor_edit_blocks_next(self):
        self.ready(); self.adopt_scene(); self.write(n.scene_path(1, 1), '已採用後手改')
        with self.assertRaises(n.Invalid): n.begin(self.root, 1, 2)

    def test_missing_review_and_severe_issue_need_explicit_decision(self):
        self.ready(); s = self.scene_delivery(); s['review']['completed'] = ['copy-editor']; s['review']['unresolved'] = ['CC-1 S1']
        n.prepare(self.root, s)
        with self.assertRaises(n.Invalid): n.accept(self.root, 's1', '通過')
        n.accept(self.root, 's1', '作者明確採用此版本', '作者知道缺席及 CC-1，決定保留')
        j = json.loads((self.root/'審閱/採用/s1/journal.json').read_text(encoding='utf-8'))
        self.assertTrue(j['missing_reviewers']); self.assertEqual(j['review']['unresolved'], ['CC-1 S1'])

    def test_new_scene_cannot_silently_use_text_mode(self):
        self.ready(); s = self.scene_delivery(); s['review']['mode']='文字'
        with self.assertRaises(n.Invalid): n.prepare(self.root, s)

    def test_scene_adoption_does_not_update_global_tracking(self):
        self.ready(); s = self.scene_delivery(); self.write('審閱/追蹤候選.md', '追蹤')
        s['files'].append({'source':'審閱/追蹤候選.md','target':'追蹤/追蹤.md'})
        with self.assertRaises(n.Invalid): n.prepare(self.root, s)

    def test_chapter_is_not_published_before_acceptance(self):
        self.ready(scenes=1); self.adopt_scene(); n.begin(self.root,1,0)
        self.write('草稿/第001章/整章候選.md', '候选')
        self.assertFalse((self.root/n.scene_path(1,0)).exists())
        self.plan(ch=2)
        with self.assertRaises(n.Invalid): n.confirm_plan(self.root, 2)

    def test_chapter_acceptance_allows_next_plan(self):
        self.adopted_chapter(); self.plan(ch=2); n.confirm_plan(self.root,2)
        n.begin(self.root,2,1)

    def test_revision_candidate_preserves_official_text(self):
        self.adopted_chapter(); target=n.scene_path(1,0)
        n.revision_start(self.root,'fix',[target]); n.prepare(self.root,self.revision_delivery())
        self.assertEqual((self.root/target).read_text(encoding='utf-8'), '已採用整章')
        self.plan(ch=2)
        with self.assertRaises(n.Invalid): n.confirm_plan(self.root,2)

    def test_last_revision_adoption_still_blocks_until_finalize(self):
        self.adopted_chapter(); target=n.scene_path(1,0)
        n.revision_start(self.root,'fix',[target]); n.prepare(self.root,self.revision_delivery()); n.accept(self.root,'r1','通過')
        with self.assertRaises(n.Invalid): n.no_revision(self.root)
        self.write('審閱/修訂/fix/追蹤候選.md', '更新後追蹤'); self.write('審閱/end.md', '最終追蹤與登記')
        s={'id':'end','kind':'revision-finish','revision':'fix','delivery':'審閱/end.md',
           'files':[{'source':'審閱/修訂/fix/追蹤候選.md','target':'追蹤/追蹤.md'}],
           'review':{'mode':'文字','completed':sorted(n.REVIEWERS['文字']),'unresolved':[]}}
        n.prepare(self.root,s); n.accept(self.root,'end','通過'); n.no_revision(self.root)

    def test_revision_invalidates_adopted_dependent_scenes(self):
        self.ready(); self.adopt_scene(1); self.adopt_scene(2)
        n.revision_start(self.root,'fix',[n.scene_path(1,1)])
        n.prepare(self.root,self.revision_delivery(n.scene_path(1,1))); n.accept(self.root,'r1','通過')
        self.assertEqual(n.rows(self.root)[1,2]['status'],'待復核')
        n.revision_extend(self.root,'fix',[n.scene_path(1,2)])
        self.assertEqual(len(json.loads(n.task_path(self.root,'fix').read_text(encoding='utf-8'))['targets']),2)

    def test_cancel_preserves_prose_and_cannot_cancel_partial_adoption(self):
        self.adopted_chapter(); n.revision_start(self.root,'fix',[n.scene_path(1,0)])
        n.revision_cancel(self.root,'fix'); n.no_revision(self.root)
        n.revision_start(self.root,'fix2',[n.scene_path(1,0)])
        s=self.revision_delivery(); s['revision']='fix2'; n.prepare(self.root,s); n.accept(self.root,'r1','通過')
        with self.assertRaises(n.Invalid): n.revision_cancel(self.root,'fix2')

    def test_hand_edit_after_revision_start_is_preserved(self):
        self.adopted_chapter(); target=n.scene_path(1,0); n.revision_start(self.root,'fix',[target])
        self.write(target,'作者手改')
        with self.assertRaises(n.Invalid): n.prepare(self.root,self.revision_delivery())
        self.assertEqual((self.root/target).read_text(encoding='utf-8'),'作者手改')

    def test_interruption_resumes_without_overwriting_external_edits(self):
        self.adopted_chapter(); n.revision_start(self.root,'fix',[n.scene_path(1,0)])
        n.prepare(self.root,self.revision_delivery())
        real=n.atomic
        def stop_at_task(path,data):
            if path.name=='任務.json': raise OSError('simulated crash')
            real(path,data)
        with patch.object(n,'atomic',stop_at_task):
            with self.assertRaises(OSError): n.accept(self.root,'r1','通過')
        self.assertEqual((self.root/n.scene_path(1,0)).read_text(encoding='utf-8'),'新的修订正文')
        with self.assertRaises(n.Invalid): n.idle(self.root)
        n.accept(self.root,'r1','通過')
        self.assertEqual(n.accept(self.root,'r1','通過'),'already-complete')
        n.idle(self.root)

    def test_interrupted_adoption_stops_on_external_edit(self):
        self.adopted_chapter(); n.revision_start(self.root,'fix',[n.scene_path(1,0)]); n.prepare(self.root,self.revision_delivery())
        real=n.atomic
        def stop(path,data):
            if path.name=='任務.json': raise OSError('crash')
            real(path,data)
        with patch.object(n,'atomic',stop):
            with self.assertRaises(OSError): n.accept(self.root,'r1','通過')
        self.write(n.scene_path(1,0),'中斷後作者又改')
        with self.assertRaises(n.Invalid): n.accept(self.root,'r1','通過')
        self.assertEqual((self.root/n.scene_path(1,0)).read_text(encoding='utf-8'),'中斷後作者又改')

    def test_existing_chapter_without_confirmed_import_is_insufficient(self):
        self.write(n.scene_path(1,0),'導入章'); self.plan(ch=2)
        with self.assertRaises(n.Invalid): n.confirm_plan(self.root,2)
        self.write('導入/原稿/book.txt','導入章')
        n.confirm_import(self.root,[{'chapter':1,'source':'導入/原稿/book.txt','location':'第1章全文','coverage':'詳細'}])
        n.confirm_plan(self.root,2)

    def test_import_duplicate_and_changed_chapter(self):
        self.write(n.scene_path(1,0),'導入章'); self.write('導入/原稿/book.txt','導入章')
        m=[{'chapter':1,'source':'導入/原稿/book.txt','location':'第1章','coverage':'摘要'}]
        n.confirm_import(self.root,m)
        with self.assertRaises(n.Invalid): n.confirm_import(self.root,m)
        self.write(n.scene_path(1,0),'手改'); self.plan(ch=2)
        with self.assertRaises(n.Invalid): n.confirm_plan(self.root,2)

    def test_path_escape_symlink_and_official_write_rejected(self):
        for path in ['../outside.md','正文/第001章.md','草稿/第1章/場景1.md']:
            with self.assertRaises(n.Invalid): n.check(self.root,path)
        self.write('target.md','x'); (self.root/'alias.md').symlink_to(self.root/'target.md')
        with self.assertRaises(n.Invalid): n.inside(self.root,'alias.md')

    def test_absolute_paths_outside_project_skip_gate(self):
        other = tempfile.TemporaryDirectory(prefix='novel-other-'); self.addCleanup(other.cleanup)
        elsewhere = Path(other.name).resolve()
        for path in [elsewhere/'正文/第001章.md', elsewhere/'追蹤/場景狀態.md', elsewhere/'memory/MEMORY.md']:
            self.assertTrue(n.outside(self.root,str(path)),path)
            n.check(self.root,str(path))
        # Relative, drive-relative and '..' forms are never "outside": inside() rejects them.
        for path in ['../outside.md','D:outside.md',str(self.root/'..'/self.root.name/'正文/第001章.md'),
                     str(elsewhere/'..'/self.root.name/'正文/第001章.md')]:
            self.assertFalse(n.outside(self.root,path),path)
            with self.assertRaises(n.Invalid): n.check(self.root,path)

    def test_outside_alias_back_into_project_is_gated(self):
        other = tempfile.TemporaryDirectory(prefix='novel-other-'); self.addCleanup(other.cleanup)
        link = Path(other.name).resolve()/'alias'
        try: link.symlink_to(self.root,target_is_directory=True)
        except OSError: self.skipTest('無法建立符號連結')
        with self.assertRaises(n.Invalid): n.check(self.root,str(link/'正文/第001章.md'))
        self.assertFalse(n.outside(self.root,str(link/'設定/設定.md')))

    @unittest.skipUnless(os.name=='nt','Windows 路徑別名')
    def test_windows_device_and_unc_aliases_are_gated(self):
        drive, rest = str(self.root)[0], str(self.root)[2:]
        for path in ['\\\\?\\'+str(self.root)+'\\正文\\第001章.md', '\\\\.\\'+str(self.root)+'\\正文\\第001章.md',
                     f'\\\\localhost\\{drive}$'+rest+'\\正文\\第001章.md', str(self.root).upper()+'\\正文\\第001章.md']:
            self.assertFalse(n.outside(self.root,path),path)
            with self.assertRaises(n.Invalid): n.check(self.root,path)

    def test_tool_owned_files_rejected(self):
        self.ready()
        for path in [n.STATE,'追蹤/場景狀態.MD','審閱/採用/s1/journal.json','審閱/採用/s1/other.md',
                     '審閱/修訂/fix/任務.json','審閱/修訂/fix/任務.JSON','導入/清單.json','導入/清單.Json']:
            with self.assertRaises(n.Invalid) as e: n.check(self.root,path)
            self.assertIn('novel.py 維護',str(e.exception),path)
        # Windows drops trailing dots/spaces and writes '::$DATA' to the main stream.
        for path in ['導入/清單.json.','追蹤/場景狀態.md ','追蹤/場景狀態.md::$DATA','設定/設定.md:x']:
            with self.assertRaises(n.Invalid): n.check(self.root,path)
        for path in ['追蹤/追蹤.md','設定/設定.md','審閱/第001章/場景01_交付.md','審閱/修訂/fix/候選.md','審閱/修訂/fix/任務說明.json']:
            n.check(self.root,path)

    def test_hook_write_edit_and_malformed_input(self):
        self.ready()
        env=dict(os.environ,CLAUDE_PROJECT_DIR=str(self.root))
        for tool in ['Write','Edit','MultiEdit','NotebookEdit']:
            key='notebook_path' if tool=='NotebookEdit' else 'file_path'
            payload={'tool_name':tool,'tool_input':{key:str(self.root/n.scene_path(1,2))}}
            result=subprocess.run([sys.executable,str(HOOK)],input=json.dumps(payload),text=True,encoding='utf-8',capture_output=True,env=env)
            self.assertEqual(result.returncode,2)
        result=subprocess.run([sys.executable,str(HOOK)],input='{',text=True,encoding='utf-8',capture_output=True,env=env)
        self.assertEqual(result.returncode,2)
        result=subprocess.run([sys.executable,str(HOOK)],input=json.dumps({'tool_name':'Read'}),text=True,encoding='utf-8',capture_output=True,env=env)
        self.assertEqual(result.returncode,0)

    def test_rollback_restores_interrupted_revision(self):
        self.adopted_chapter(); target=n.scene_path(1,0)
        n.revision_start(self.root,'fix',[target]); n.prepare(self.root,self.revision_delivery())
        real=n.atomic
        def stop(path,data):
            if path.name=='任務.json': raise OSError('crash')
            real(path,data)
        with patch.object(n,'atomic',stop):
            with self.assertRaises(OSError): n.accept(self.root,'r1','approved')
        n.rollback(self.root,'r1','cancel interrupted adoption')
        self.assertEqual((self.root/target).read_text(encoding='utf-8'),'已採用整章')
        self.assertEqual(n.rollback(self.root,'r1','again'),'already-cancelled')
        self.assertIsNone(json.loads(n.task_path(self.root,'fix').read_text(encoding='utf-8'))['targets'][0]['adopted'])
        with self.assertRaises(n.Invalid): n.accept(self.root,'r1','approved')
        n.idle(self.root)

    def test_rollback_removes_only_new_official_candidate(self):
        self.ready(scenes=1); self.adopt_scene(); n.begin(self.root,1,0)
        self.write('草稿/第001章/整章候選.md','candidate'); self.write('審閱/end.md','delivery')
        s={'id':'end','kind':'chapter','chapter':1,'delivery':'審閱/end.md',
           'files':[{'source':'草稿/第001章/整章候選.md','target':n.scene_path(1,0)}],
           'review':{'mode':'章節','completed':sorted(n.REVIEWERS['章節']),'unresolved':[]}}
        n.prepare(self.root,s); real=n.atomic
        def stop(path,data):
            if path==self.root/n.STATE: raise OSError('crash')
            real(path,data)
        with patch.object(n,'atomic',stop):
            with self.assertRaises(OSError): n.accept(self.root,'end','approved')
        self.assertTrue((self.root/n.scene_path(1,0)).exists())
        n.rollback(self.root,'end','cancel')
        self.assertFalse((self.root/n.scene_path(1,0)).exists())
        self.assertTrue((self.root/'草稿/第001章/整章候選.md').exists())

    def test_other_chapter_pending_blocks_write(self):
        self.ready(); data=n.rows(self.root)
        data[2,1]={'status':'待審','meta':{}}
        self.write(n.STATE,n.table(data))
        with self.assertRaises(n.Invalid): n.check(self.root,n.scene_path(1,1))

    def test_registered_import_requires_previous_chapter_without_gap(self):
        self.write(n.scene_path(1,0),'chapter'); self.write('導入/原稿/book.txt','chapter')
        n.confirm_import(self.root,[{'chapter':1,'source':'導入/原稿/book.txt','location':'first','coverage':'摘要'}])
        self.plan(ch=3)
        with self.assertRaises(n.Invalid): n.confirm_plan(self.root,3)

    def test_reconfirm_only_unstarted_outline(self):
        self.ready(); self.plan(scenes=3); n.confirm_plan(self.root,1)
        self.assertIn((1,3),n.rows(self.root))
        n.begin(self.root,1,1)
        with self.assertRaises(n.Invalid): n.confirm_plan(self.root,1)

    def test_historical_scenes_cannot_replace_adopted_chapter(self):
        self.adopted_chapter()
        with self.assertRaises(n.Invalid): n.revision_start(self.root,'fix',[n.scene_path(1,1)])

    def test_hook_rejects_wrong_json_shapes(self):
        env=dict(os.environ,CLAUDE_PROJECT_DIR=str(self.root))
        for value in [[], None, {'tool_name':'Write','tool_input':[]}, {'tool_name':'Edit','tool_input':{'file_path':3}}]:
            r=subprocess.run([sys.executable,str(HOOK)],input=json.dumps(value),text=True,encoding='utf-8',capture_output=True,env=env)
            self.assertEqual(r.returncode,2,r.stderr)

    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.root),*args])

    def init_git(self):
        self.git('init','-q'); self.git('config','user.name','Fixture'); self.git('config','user.email','fixture@example.invalid')
        self.write('baseline.txt','base'); self.git('add','baseline.txt'); self.git('commit','-qm','baseline')

    def test_commit_does_not_touch_existing_staged_content(self):
        self.init_git(); self.write('other.txt','unrelated'); self.git('add','other.txt')
        before=self.git('diff','--cached','--binary'); self.write('正文/第001章.md','正文')
        with self.assertRaises(n.Invalid): n.safe_commit(self.root,['正文/第001章.md'],'chapter')
        self.assertEqual(self.git('diff','--cached','--binary'),before)

    def test_commit_only_named_files_and_keeps_unrelated_dirty(self):
        self.init_git(); self.write('baseline.txt','unrelated edit'); self.write('正文/第001章.md','正文')
        n.safe_commit(self.root,['正文/第001章.md'],'chapter')
        self.assertEqual(self.git('-c','core.quotePath=false','show','--format=','--name-only','HEAD').decode().strip(),'正文/第001章.md')
        self.assertEqual(self.git('diff','--cached','--name-only'),b'')
        self.assertIn(b'baseline.txt',self.git('diff','--name-only'))

    def test_commit_failure_leaves_real_index_unchanged(self):
        self.init_git(); self.write('正文/第001章.md','正文')
        hook=self.write('.git/hooks/pre-commit','#!/bin/sh\nexit 1\n'); hook.chmod(0o755)
        before=(self.root/'.git/index').read_bytes()
        with self.assertRaises(subprocess.CalledProcessError): n.safe_commit(self.root,['正文/第001章.md'],'chapter')
        self.assertEqual((self.root/'.git/index').read_bytes(),before)

    def test_cli_works_without_git(self):
        self.plan()
        r=subprocess.run([sys.executable,str(SCRIPT),'--root',str(self.root),'confirm-plan','1'],text=True,encoding='utf-8',errors='replace',capture_output=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertFalse((self.root/'.git').exists())


if __name__=='__main__': unittest.main()
