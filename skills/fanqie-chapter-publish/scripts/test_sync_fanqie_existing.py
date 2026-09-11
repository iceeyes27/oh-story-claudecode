import contextlib
import copy
import hashlib
import io
import json
import pathlib
import tempfile
import types
import unittest
from unittest.mock import patch

import sync_fanqie_existing as sync


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = pathlib.Path(self.tmp.name)
        self.source = self.out/'第001章_证据.md'
        self.source.write_text('原文', encoding='utf-8')
        self.meta = {'body':'新正文', 'display_title':'第1章 证据',
                     'source_path':str(self.source), 'char_count':1000,
                     'source_sha256':hashlib.sha256(self.source.read_bytes()).hexdigest()}
        self.before = {'content':'<p>旧正文</p>', 'title':'第1章 证据', 'use_ai':2,
                       'timer_status':0, 'timer_time':'0', 'display_status':1,
                       'volume_id':'volume', 'volume_data':[{'volume_id':'volume','volume_name':'卷'}],
                       'column_data':{'need_pay':0}}
        sync.save(self.out/'local-snapshot.json', {'1':self.meta})
        sync.save(self.out/'plan.json', {'book_id':'book','targets':[{'chapter_no':1,'item_id':'item','changed':True}]})
        (self.out/'articles-before').mkdir()
        sync.save(self.out/'articles-before/item.json', self.before)
        self.args = types.SimpleNamespace(command='submit')

    def run_sync(self, reads, response=None, error=None):
        with patch.object(sync,'article',side_effect=reads), patch.object(sync,'request',return_value=response,side_effect=error) as post, contextlib.redirect_stdout(io.StringIO()):
            sync.run(self.args,self.out,object())
            return post

    def test_paragraph_normalization(self):
        self.assertEqual(sync.body_text('<p>甲&amp;乙</p><p></p><p>丙<br>丁</p>'), '甲&乙\n丙\n丁')

    def test_identical_skips_post(self):
        a={**self.before,'content':'<p>新正文</p>'}
        post=self.run_sync([{'code':0,'data':a}])
        post.assert_not_called()

    def test_quota_blocks_next_run(self):
        with self.assertRaisesRegex(RuntimeError,'Submission stopped'):
            self.run_sync([{'code':0,'data':self.before}], {'http_status':200,'response':{'code':-1019}})
        with self.assertRaisesRegex(RuntimeError,'Quota stop'):
            self.run_sync([])

    def test_timeout_is_durable_and_not_retried(self):
        with self.assertRaises(TimeoutError):
            self.run_sync([{'code':0,'data':self.before}],error=TimeoutError())
        events=[json.loads(x) for x in (self.out/'events.jsonl').read_text().splitlines()]
        self.assertEqual([e['status'] for e in events],['attempting','unknown'])
        with self.assertRaisesRegex(RuntimeError,'Prior attempt'):
            self.run_sync([{'code':0,'data':self.before}])

    def test_success_requires_readback(self):
        a={**self.before,'content':'<p>新正文</p>'}
        post=self.run_sync([{'code':0,'data':self.before},{'code':0,'data':a}],
                           {'http_status':200,'response':{'code':0,'data':{'item_id':'item'}}})
        self.assertEqual(post.call_count,1)
        self.assertEqual(json.loads((self.out/'events.jsonl').read_text().splitlines()[-1])['status'],'verified')

    def test_pending_does_not_resubmit(self):
        self.run_sync([{'code':0,'data':self.before},{'code':-2014}],
                      {'http_status':200,'response':{'code':0,'data':{'item_id':'item'}}})
        post=self.run_sync([{'code':-2014}])
        post.assert_not_called()

    def test_special_fields_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'Special'):
            sync.payload({'item_id':'item'},self.meta,{**self.before,'speak_content':'作者的话'},'book')

    def test_changed_local_stops(self):
        self.source.write_text('已再改',encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError,'Local source changed'):
            self.run_sync([])

    def test_prepare_rejects_short_source_before_network(self):
        args=types.SimpleNamespace(source_dir=str(self.out),start=1,end=1)
        (self.out/'plan.json').unlink()
        with patch.object(sync,'request') as request:
            with self.assertRaisesRegex(RuntimeError,'below 1000'):
                sync.prepare(args,self.out,object())
            request.assert_not_called()

    def test_prepare_refuses_overwrite(self):
        with self.assertRaisesRegex(RuntimeError,'Plan exists'):
            sync.prepare(None,self.out,object())

    def test_posix_wall_clock_timeout(self):
        if not hasattr(sync.signal,'SIGALRM'):
            self.skipTest('POSIX timer only')
        with self.assertRaises(TimeoutError):
            with sync.deadline(0.01):
                sync.time.sleep(0.1)


if __name__ == '__main__':
    unittest.main()
