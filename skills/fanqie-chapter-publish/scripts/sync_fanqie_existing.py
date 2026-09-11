#!/usr/bin/env python3
import hashlib
import html
import json
import pathlib
import sys
import time
import urllib.request
from html.parser import HTMLParser

import argparse
import datetime
import os
import re
import signal
from contextlib import contextmanager
import extract_fanqie_chapter as extract
import update_fanqie_existing_fast as fanqie


class Paragraphs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.current = []

    def handle_starttag(self, tag, attrs):
        if tag == 'br':
            self.current.append('\n')

    def handle_data(self, data):
        self.current.append(data)

    def handle_endtag(self, tag):
        if tag in ('p', 'div'):
            value = ''.join(self.current).strip()
            self.current = []
            if value:
                self.parts.append(value)

    def text(self):
        if self.current:
            value = ''.join(self.current).strip()
            self.current = []
            if value:
                self.parts.append(value)
        return '\n'.join(self.parts)


def body_text(raw):
    parser = Paragraphs()
    parser.feed(raw or '')
    return parser.text()


def evaluate(page, expression):
    result = page.send('Runtime.evaluate', {
        'expression': expression,
        'returnByValue': True,
        'awaitPromise': True,
    })['result']
    if result.get('exceptionDetails'):
        raise RuntimeError(result['exceptionDetails'])
    return result['result'].get('value')


def request(page, endpoint, params, method='GET', timeout_s=10):
    if method == 'GET':
        expression = """(async()=>{const c=new AbortController();const t=setTimeout(()=>c.abort(),%d);try{const u=new URL(%s,location.origin);Object.entries(%s).forEach(([k,v])=>u.searchParams.set(k,v));const r=await fetch(u,{signal:c.signal});return {http_status:r.status,response:await r.json()}}finally{clearTimeout(t)}})()""" % (
            timeout_s * 1000, json.dumps(endpoint), json.dumps(params, ensure_ascii=False)
        )
    else:
        expression = """(async()=>{const c=new AbortController();const t=setTimeout(()=>c.abort(),%d);try{const r=await fetch(%s,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams(%s).toString(),signal:c.signal});return {http_status:r.status,response:await r.json()}}finally{clearTimeout(t)}})()""" % (
            timeout_s * 1000, json.dumps(endpoint), json.dumps(params, ensure_ascii=False)
        )
    return evaluate(page, expression)


def get_article(page, target, book):
    return request(page, '/api/author/edit_article/v0/', {
        'aid': 2503,
        'app_name': 'muye_novel',
        'book_id': book,
        'item_id': target['item_id'],
        'from_source': 0,
    })


def checks(article, meta, baseline):
    return {
        'body': body_text(article['content']) == meta['body'],
        'title': article['title'] == meta['display_title'],
        'ai_no': article.get('use_ai') == 2,
        'metadata': all(article.get(key) == baseline.get(key) for key in (
            'timer_status', 'timer_time', 'volume_id', 'display_status'
        )),
    }


@contextmanager
def deadline(seconds):
    # Also bounds CDP hangs when a browser-side AbortController cannot run.
    if not hasattr(signal, 'SIGALRM'):
        yield
        return
    previous = signal.getsignal(signal.SIGALRM)
    def expired(*_):
        raise TimeoutError('CDP operation timed out; do not retry a submission blindly')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def save(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def event(out, **data):
    data['time'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with (out / 'events.jsonl').open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(data, ensure_ascii=False) + '\n')
        handle.flush()
        os.fsync(handle.fileno())
    print(json.dumps(data, ensure_ascii=False), flush=True)


def connect():
    tabs = json.load(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=5))
    tab = next((t for t in tabs if t.get('type') == 'page' and t.get('url', '').startswith('https://fanqienovel.com/')), None)
    if not tab:
        raise RuntimeError('Open a Fanqie page in CDP Chrome; no need to wait for the editor')
    with deadline(20):
        page = fanqie.CDPPage(tab['webSocketDebuggerUrl'])
    page._ws.settimeout(20)
    return page


def article(page, target, book):
    with deadline(15):
        response = get_article(page, target, book)
    if response['http_status'] != 200:
        raise RuntimeError('HTTP read failed')
    return response['response']


def prepare(args, out, page):
    if (out / 'plan.json').exists():
        raise RuntimeError('Plan exists; use submit/verify, or a fresh output directory for a new comparison')
    files = sorted(pathlib.Path(args.source_dir).resolve().rglob('第*章*.md'))
    local = {}
    for path in files:
        meta = extract.extract(path)
        n = meta['chapter_no']
        if not args.start <= n <= args.end:
            continue
        if n in local:
            raise RuntimeError(f'Duplicate local chapter {n}')
        if meta['char_count'] < 1000:
            raise RuntimeError(f'Chapter {n} below 1000 characters')
        meta['source_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        local[n] = meta
    if set(local) != set(range(args.start, args.end + 1)):
        raise RuntimeError('Local chapter range incomplete')
    rows = []
    index = 0
    while True:
        with deadline(15):
            r = request(page, '/api/author/chapter/chapter_list/v1', {
                'aid':2503, 'app_name':'muye_novel', 'book_id':args.book_id,
                'volume_id':args.volume_id, 'page_index':index, 'page_count':15,
                'status':0, 'must_have_correction_feedback':0,
                'need_correction_feedback_num':1, 'sort':'',
            })
        if r['http_status'] != 200 or r['response'].get('code') != 0:
            raise RuntimeError('Chapter list unavailable: ' + str(r['response'].get('code')))
        d = r['response']['data']
        rows.extend(d['item_list'])
        print(f'LIST {len(rows)}/{d["total_count"]}', flush=True)
        if len(rows) >= d['total_count']:
            break
        if not d['item_list']:
            raise RuntimeError('Unexpected empty list page')
        index += 1
    mapping = {}
    for row in rows:
        n = int(re.search(r'第(\d+)章', row['title'])[1])
        if n in local:
            if n in mapping or row['volume_id'] != args.volume_id:
                raise RuntimeError('Duplicate chapter or volume mismatch')
            mapping[n] = row
    if set(mapping) != set(local):
        raise RuntimeError('Platform chapter range incomplete')
    save(out / 'local-snapshot.json', local)
    save(out / 'platform-before.json', rows)
    targets = []
    (out / 'articles-before').mkdir(exist_ok=True)
    for n, meta in sorted(local.items()):
        row = mapping[n]
        a = article(page, row, args.book_id)
        if a.get('code') != 0:
            raise RuntimeError(f'Chapter {n} unreadable: {a.get("code")}')
        a = a['data']
        save(out / 'articles-before' / (row['item_id'] + '.json'), a)
        targets.append({'chapter_no':n, 'item_id':row['item_id'],
                        'changed':body_text(a['content']) != meta['body'] or a['title'] != meta['display_title']})
        print(f'COMPARE {n}: ' + ('DIFFERENT' if targets[-1]['changed'] else 'SAME'), flush=True)
    save(out / 'plan.json', {'book_id':args.book_id, 'volume_id':args.volume_id, 'targets':targets})
    print(f'READY differences={sum(t["changed"] for t in targets)} total={len(targets)}', flush=True)


def payload(target, meta, current, book):
    # Proven endpoint shape for ordinary published chapters only.
    if current.get('timer_status') != 0 or current.get('display_status') != 1:
        raise RuntimeError('Scheduled/draft state: use existing UI workflow preserving its schedule')
    if current.get('speak_content') or current.get('has_chapter_ad') or current.get('timer_chapter_preview'):
        raise RuntimeError('Special author-note/ad/preview fields: use UI to preserve them')
    return {
        'aid':'2503', 'app_name':'muye_novel', 'book_id':book, 'item_id':target['item_id'],
        'content':''.join('<p>'+html.escape(s, quote=False)+'</p>' for s in meta['body'].splitlines()),
        'title':meta['display_title'], 'timer_status':'0', 'publish_status':'1',
        'volume_id':current['volume_id'],
        'volume_name':next(v['volume_name'] for v in current['volume_data'] if v['volume_id']==current['volume_id']),
        'need_pay':str(current['column_data']['need_pay']), 'device_platform':'pc',
        'speak_type':str(current.get('speak_type',0)), 'use_ai':'2',
        'timer_chapter_preview':'[]', 'has_chapter_ad':'false',
    }


def run(args, out, page):
    plan = json.loads((out / 'plan.json').read_text())
    local = json.loads((out / 'local-snapshot.json').read_text())
    events_path = out / 'events.jsonl'
    history = [json.loads(s) for s in events_path.read_text().splitlines()] if events_path.exists() else []
    attempted = {e['chapter_no'] for e in history if e.get('status') in ('attempting','submitted','unknown')}
    if args.command == 'submit' and any(e.get('code') == -1019 for e in history):
        raise RuntimeError('Quota stop recorded. After quota recovery prepare a fresh comparison; verify remains available.')
    results = []
    for target in plan['targets']:
        n = target['chapter_no']
        if args.command == 'submit' and not target['changed']:
            continue
        meta = local[str(n)]
        baseline = json.loads((out/'articles-before'/(target['item_id']+'.json')).read_text())
        if hashlib.sha256(pathlib.Path(meta['source_path']).read_bytes()).hexdigest() != meta['source_sha256']:
            raise RuntimeError(f'Local source changed: {n}; prepare a fresh comparison')
        d = article(page, target, plan['book_id'])
        if d.get('code') == -2014:
            results.append({'chapter_no':n,'status':'audit_pending'})
            event(out, chapter_no=n, status='audit_pending')
            continue
        if d.get('code') != 0:
            raise RuntimeError(f'Read failed: {n} code={d.get("code")}')
        a = d['data']
        checked = checks(a, meta, baseline)
        if checked['body'] and checked['title']:
            status = 'verified' if all(checked.values()) else 'metadata_mismatch'
            results.append({'chapter_no':n,'status':status,'checks':checked})
            event(out, chapter_no=n, status=status)
            if status != 'verified' and args.command == 'submit':
                break
            continue
        if args.command == 'verify':
            unchanged = all(a.get(k)==baseline.get(k) for k in ('content','title','timer_time','timer_status','volume_id','display_status'))
            results.append({'chapter_no':n,'status':'different','old_content_unchanged':unchanged})
            print(f'VERIFY {n}: DIFFERENT unchanged={unchanged}', flush=True)
            continue
        if n in attempted:
            raise RuntimeError(f'Prior attempt {n} not yet verified; ambiguous submit must not be repeated')
        if any(a.get(k)!=baseline.get(k) for k in ('content','title','timer_time','timer_status','volume_id','display_status')):
            raise RuntimeError(f'Platform changed: {n}')
        params = payload(target, meta, a, plan['book_id'])
        event(out, chapter_no=n, status='attempting')
        try:
            with deadline(20):
                response = request(page, '/api/author/publish_article/v0/', params, 'POST', 15)
        except Exception:
            event(out, chapter_no=n, status='unknown')
            raise
        r = response['response']
        success = response['http_status']==200 and r.get('code')==0 and r.get('data',{}).get('item_id')==target['item_id']
        event(out, chapter_no=n, status='submitted' if success else 'rejected', code=r.get('code'), message=r.get('message',''))
        if not success:
            raise RuntimeError(f'Submission stopped at {n}: code={r.get("code")} {r.get("message", "")}')
        d = article(page, target, plan['book_id'])
        if d.get('code') == -2014:
            event(out, chapter_no=n, status='audit_pending')
            continue
        if d.get('code') != 0 or not all(checks(d['data'],meta,baseline).values()):
            raise RuntimeError(f'Readback mismatch: {n}')
        event(out, chapter_no=n, status='verified')
    if args.command == 'verify':
        save(out / 'verification.json', results)


def main():
    parser = argparse.ArgumentParser(description='Differential update for existing Fanqie chapters through logged-in CDP Chrome.')
    parser.add_argument('command', choices=['prepare','submit','verify'])
    parser.add_argument('--out', required=True, help='Persistent run directory; never reuse it for a new prepare')
    parser.add_argument('--book-id')
    parser.add_argument('--volume-id')
    parser.add_argument('--source-dir')
    parser.add_argument('--from', dest='start', type=int)
    parser.add_argument('--to', dest='end', type=int)
    args = parser.parse_args()
    if args.command == 'prepare' and (not all([args.book_id,args.volume_id,args.source_dir,args.start,args.end]) or args.start > args.end):
        parser.error('prepare requires book-id, volume-id, source-dir and a valid from/to range')
    out = pathlib.Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    lock = out / '.running'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError('Run already active; inspect recorded PID before removing a stale .running lock')
    os.write(fd, str(os.getpid()).encode()); os.close(fd)
    page = None
    try:
        page = connect()
        if args.command == 'prepare':
            prepare(args, out, page)
        else:
            run(args, out, page)
    finally:
        if page:
            page.close()
        lock.unlink()


if __name__ == '__main__':
    main()
