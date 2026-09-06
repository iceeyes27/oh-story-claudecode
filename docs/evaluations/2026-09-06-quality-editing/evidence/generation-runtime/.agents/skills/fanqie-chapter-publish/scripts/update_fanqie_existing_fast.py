#!/usr/bin/env python3
import argparse
import itertools
import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from websocket import create_connection

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import extract_fanqie_chapter
import locate_fanqie_chapter

BASE_URL = "https://fanqienovel.com"
MANAGE_URL_RE = re.compile(r"chapter-manage/(\d+)")
CHAPTER_NO_RE = re.compile(r"第0*(\d+)章")


def book_id_from_url(url: str) -> str:
    match = MANAGE_URL_RE.search(url)
    if not match:
        raise ValueError(f"Could not infer book id from {url}")
    return match.group(1)


def resolve_chapter_path(project_root: pathlib.Path, raw: str) -> pathlib.Path:
    candidate = pathlib.Path(raw).expanduser()
    if candidate.exists():
        return candidate.resolve()
    normalized_no = locate_fanqie_chapter.normalize_no(raw)
    result = locate_fanqie_chapter.render(
        project_root,
        normalized_no,
        locate_fanqie_chapter.collect_candidates(project_root, normalized_no),
    )
    if result["status"] == "unique":
        return (project_root / result["path"]).resolve()
    if result["status"] == "multiple":
        raise ValueError("multiple chapter files found: %s" % " | ".join(result["candidates"]))
    raise ValueError(f"chapter not found for 第{normalized_no}章")


@dataclass
class CDPPage:
    websocket_url: str

    def __post_init__(self) -> None:
        self._ws = create_connection(self.websocket_url, timeout=60)
        self._ids = itertools.count(1)
        self.send("Page.enable")
        self.send("Runtime.enable")

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:
            pass

    def send(self, method: str, params: Optional[Dict[str, object]] = None) -> Dict[str, object]:
        message_id = next(self._ids)
        self._ws.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        while True:
            data = json.loads(self._ws.recv())
            if data.get("id") == message_id:
                return data

    def navigate(self, url: str) -> None:
        self.send("Page.navigate", {"url": url})

    def eval(self, expression: str):
        result = self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        return result["result"]["result"].get("value")

    def wait_for(self, predicate_js: str, *, timeout_s: int = 30, interval_s: float = 1.0):
        deadline = time.time() + timeout_s
        last = None
        while time.time() < deadline:
            last = self.eval(predicate_js)
            if last:
                return last
            time.sleep(interval_s)
        raise TimeoutError(f"Condition not met within {timeout_s}s: {predicate_js}\nlast={last!r}")


def open_target(url: str) -> CDPPage:
    req = urllib.request.Request(
        "http://127.0.0.1:9222/json/new?" + urllib.parse.quote(url, safe=":/?&=%"),
        method="PUT",
    )
    payload = json.load(urllib.request.urlopen(req))
    return CDPPage(payload["webSocketDebuggerUrl"])


def select_manage_volume(page: CDPPage, volume_name: Optional[str]) -> None:
    if not volume_name:
        return
    selected = page.eval(
        f"""(() => {{
          const current = document.querySelector('.serial-select .byte-select-view-value');
          return (current?.innerText || '').trim() === {json.dumps(volume_name, ensure_ascii=False)};
        }})()"""
    )
    if selected:
        return
    clicked = page.eval(
        """(() => {
          const view = document.querySelector('.serial-select .byte-select-view');
          if (!view) return false;
          view.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
          view.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}));
          view.click();
          return true;
        })()"""
    )
    if not clicked:
        raise RuntimeError("Could not open volume selector")
    page.wait_for(
        f"""(() => Array.from(document.querySelectorAll('.byte-trigger, .byte-select-option, [class*=option]'))
          .some(el => (el.innerText || '').includes({json.dumps(volume_name, ensure_ascii=False)})))()""",
        timeout_s=10,
        interval_s=0.5,
    )
    picked = page.eval(
        f"""(() => {{
          const option = Array.from(document.querySelectorAll('.byte-select-option, [class*=option]'))
            .find(el => (el.innerText || '').trim() === {json.dumps(volume_name, ensure_ascii=False)});
          if (!option) return false;
          option.click();
          return true;
        }})()"""
    )
    if not picked:
        raise RuntimeError(f"Could not pick volume {volume_name}")
    page.wait_for(
        f"""(() => {{
          const current = document.querySelector('.serial-select .byte-select-view-value');
          return (current?.innerText || '').trim() === {json.dumps(volume_name, ensure_ascii=False)};
        }})()""",
        timeout_s=15,
        interval_s=0.5,
    )
    dismiss_transient_popups(page)


def dismiss_transient_popups(page: CDPPage) -> None:
    page.eval(
        """(() => {
          document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', code: 'Escape', bubbles: true}));
          document.body.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
          document.body.click();
          for (const w of Array.from(document.querySelectorAll('.arco-modal-wrapper, .byte-modal-wrapper'))) {
            const text = (w.innerText || '').trim();
            if (text.includes('新建分卷') && !text.includes('发布设置')) {
              const cancel = Array.from(w.querySelectorAll('button')).find(b => (b.innerText || '').trim() === '取消');
              cancel?.click();
            }
          }
          return true;
        })()"""
    )
    time.sleep(0.5)


def open_manage_page(page: CDPPage, manage_url: str, book_id: str, volume_name: Optional[str] = None) -> None:
    page.navigate(manage_url)
    page.wait_for(
        """(() => {
          const body = document.body.innerText || '';
          return body.includes('章节管理') && body.includes('新建章节') &&
            body.includes('搜索章节') && body.includes('审核状态');
        })()""",
        timeout_s=40,
    )
    current_url = page.eval("location.href")
    if f"chapter-manage/{book_id}" not in str(current_url):
        raise RuntimeError(f"Unexpected manage page URL: {current_url}")
    select_manage_volume(page, volume_name)
    page.wait_for(
        """(() => {
          const text = document.body.innerText || '';
          return text.includes('暂无章节内容') ||
            Array.from(document.querySelectorAll('tr.arco-table-tr')).length >= 2;
        })()""",
        timeout_s=40,
    )


def scrape_edit_links(page: CDPPage) -> Dict[int, str]:
    mapping: Dict[int, str] = {}
    seen_pages = set()
    while True:
        active_page = int(
            page.eval(
                """(() => {
                  const active = (document.querySelector('li.arco-pagination-item-active')?.innerText || '').trim();
                  return parseInt(active || '1', 10);
                })()"""
            )
        )
        if active_page in seen_pages:
            break
        seen_pages.add(active_page)
        payload = page.eval(
            """JSON.stringify(
              Array.from(document.querySelectorAll('tr.arco-table-tr')).map(tr => {
                const title = tr.querySelector('td:first-child .table-title')?.innerText?.trim() || '';
                const edit = tr.querySelector('a.link')?.getAttribute('href') || '';
                return { title, edit };
              })
            )"""
        )
        rows = json.loads(payload)
        for row in rows:
            title = row["title"]
            edit = row["edit"]
            if not title or not edit:
                continue
            match = CHAPTER_NO_RE.search(title)
            if not match:
                continue
            mapping[int(match.group(1))] = edit
        has_next = page.eval(
            """(() => {
              const next = document.querySelector('li.arco-pagination-item-next');
              return !!next && !next.classList.contains('arco-pagination-item-disabled');
            })()"""
        )
        if not has_next:
            break
        changed = page.eval(
            """(() => {
              const next = document.querySelector('li.arco-pagination-item-next');
              if (!next || next.classList.contains('arco-pagination-item-disabled')) return false;
              next.click();
              return true;
            })()"""
        )
        if not changed:
            break
        page.wait_for(
            f"""(() => {{
              const active = parseInt((document.querySelector('li.arco-pagination-item-active')?.innerText || '0').trim(), 10);
              return Number.isFinite(active) && active === {active_page + 1};
            }})()""",
            timeout_s=20,
        )
        page.wait_for(
            """(() => Array.from(document.querySelectorAll('tr.arco-table-tr')).length >= 2)()""",
            timeout_s=20,
        )
    return mapping


def scrape_edit_links_by_numbers(page: CDPPage) -> Dict[int, str]:
    max_page = int(
        page.eval(
            """(() => {
              const nums = Array.from(document.querySelectorAll('li.arco-pagination-item'))
                .map(li => parseInt((li.innerText || '').trim(), 10))
                .filter(Number.isFinite);
              return nums.length ? Math.max(...nums) : 1;
            })()"""
        )
    )
    mapping: Dict[int, str] = {}
    for page_no in range(1, max_page + 1):
        if page_no > 1:
            clicked = page.eval(
                f"""(() => {{
                  const li = Array.from(document.querySelectorAll('li.arco-pagination-item'))
                    .find(li => (li.innerText || '').trim() === '{page_no}');
                  if (!li) return false;
                  li.click();
                  return true;
                }})()"""
            )
            if not clicked:
                continue
            page.wait_for(
                f"""(() => {{
                  const active = (document.querySelector('li.arco-pagination-item-active')?.innerText || '').trim();
                  return active === '{page_no}';
                }})()""",
                timeout_s=20,
            )
            time.sleep(2)
        payload = page.eval(
            """JSON.stringify(
              Array.from(document.querySelectorAll('tr.arco-table-tr')).map(tr => {
                const title = tr.querySelector('td:first-child .table-title')?.innerText?.trim() || '';
                const edit = tr.querySelector('a.link')?.getAttribute('href') || '';
                return { title, edit };
              })
            )"""
        )
        rows = json.loads(payload)
        for row in rows:
            title = row["title"]
            edit = row["edit"]
            if not title or not edit:
                continue
            match = CHAPTER_NO_RE.search(title)
            if not match:
                continue
            mapping[int(match.group(1))] = edit
    return mapping


def wait_editor_ready(page: CDPPage) -> None:
    page.wait_for(
        """(() => {
          const serial = document.querySelector('input.serial-input.byte-input')?.value || '';
          const title = document.querySelector('input[placeholder="请输入标题"]')?.value || '';
          const editor = document.querySelector('.ProseMirror');
          const next = document.querySelector('button.auto-editor-next');
          return !!serial && !!title && !!editor && !!next && next.disabled === false;
        })()""",
        timeout_s=40,
    )


def set_input_value(page: CDPPage, selector: str, value: str) -> None:
    ok = page.eval(
        f"""(() => {{
          const el = document.querySelector({json.dumps(selector)});
          if (!el) return false;
          const proto = Object.getPrototypeOf(el);
          const desc = Object.getOwnPropertyDescriptor(proto, 'value') ||
            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
          desc.set.call(el, {json.dumps(value, ensure_ascii=False)});
          el.dispatchEvent(new Event('input', {{ bubbles: true }}));
          el.dispatchEvent(new Event('change', {{ bubbles: true }}));
          return true;
        }})()"""
    )
    if not ok:
        raise RuntimeError(f"Missing input: {selector}")


def verify_input_value(page: CDPPage, selector: str, value: str) -> None:
    page.wait_for(
        f"""(() => {{
          const el = document.querySelector({json.dumps(selector)});
          return !!el && el.value === {json.dumps(value, ensure_ascii=False)};
        }})()""",
        timeout_s=10,
        interval_s=0.5,
    )


def inject_body(page: CDPPage, body_lines: Sequence[str]) -> Dict[str, object]:
    raw = page.eval(extract_fanqie_chapter.eval_js_for(list(body_lines)))
    if isinstance(raw, str):
        payload = json.loads(raw)
    else:
        payload = raw
    if not payload or not payload.get("ok"):
        raise RuntimeError(f"Body inject failed: {payload}")
    return payload


def wait_saved(page: CDPPage) -> None:
    page.wait_for(
        """(() => {
          const text = document.body.innerText || '';
          const next = document.querySelector('button.auto-editor-next');
          return text.includes('已保存') && !!next && next.disabled === false;
        })()""",
        timeout_s=30,
        interval_s=0.5,
    )


def click_next(page: CDPPage) -> None:
    clicked = page.eval(
        """(() => {
          const btn = document.querySelector('button.auto-editor-next');
          if (!btn) return false;
          btn.click();
          return true;
        })()"""
    )
    if not clicked:
        raise RuntimeError("Missing 下一步 button")


def reach_publish_settings(page: CDPPage) -> None:
    deadline = time.time() + 40
    while time.time() < deadline:
        state_raw = page.eval(
            """JSON.stringify((() => {
              const result = { typo: false, detect: false, publish: false };
              for (const w of Array.from(document.querySelectorAll('.arco-modal-wrapper, .byte-modal-wrapper'))) {
                const text = (w.innerText || '').trim();
                if (text.includes('错别字未修改')) {
                  const btn = Array.from(w.querySelectorAll('button')).find(b => (b.innerText || '').trim() === '提交');
                  if (btn) { btn.click(); result.typo = true; }
                } else if (text.includes('请选择内容检测方式')) {
                  const btn = Array.from(w.querySelectorAll('button')).find(b => (b.innerText || '').trim() === '仅基础检测');
                  if (btn) { btn.click(); result.detect = true; }
                } else if (text.includes('发布设置')) {
                  result.publish = true;
                }
              }
              return result;
            })())"""
        )
        state = json.loads(state_raw)
        if state["publish"]:
            return
        time.sleep(1)
    raise TimeoutError("Publish settings modal did not appear")


def select_ai_no(page: CDPPage) -> None:
    page.eval(
        """(() => {
          const wrapper = Array.from(document.querySelectorAll('.arco-modal-wrapper'))
            .find(w => (w.innerText || '').includes('发布设置'));
          if (!wrapper) return false;
          const label = Array.from(wrapper.querySelectorAll('label.arco-radio'))
            .find(l => (l.innerText || '').trim() === '否');
          if (label) label.click();
          return true;
        })()"""
    )
    page.wait_for(
        """(() => {
          const wrapper = Array.from(document.querySelectorAll('.arco-modal-wrapper'))
            .find(w => (w.innerText || '').includes('发布设置'));
          if (!wrapper) return false;
          const label = Array.from(wrapper.querySelectorAll('label.arco-radio'))
            .find(l => (l.innerText || '').trim() === '否');
          return !!label && !!label.querySelector('input:checked');
        })()""",
        timeout_s=10,
        interval_s=0.5,
    )


def confirm_publish(page: CDPPage) -> None:
    clicked = page.eval(
        """(() => {
          const wrapper = Array.from(document.querySelectorAll('.arco-modal-wrapper'))
            .find(w => (w.innerText || '').includes('发布设置'));
          if (!wrapper) return false;
          const btn = Array.from(wrapper.querySelectorAll('button'))
            .find(b => (b.innerText || '').trim() === '确认发布');
          if (!btn) return false;
          btn.click();
          return true;
        })()"""
    )
    if not clicked:
        raise RuntimeError("Could not click 确认发布")
    deadline = time.time() + 45
    last_text = ""
    while time.time() < deadline:
        state_raw = page.eval(
            """JSON.stringify((() => {
              const wrappers = Array.from(document.querySelectorAll('.arco-modal-wrapper, .byte-modal-wrapper'));
              const publish = wrappers.find(w => (w.innerText || '').includes('发布设置'));
              const messages = Array.from(document.querySelectorAll('.arco-message, .arco-notification'))
                .map(el => (el.innerText || '').trim()).filter(Boolean).join('\\n');
              return {
                hasPublishModal: !!publish,
                publishText: (publish?.innerText || '').trim(),
                messages,
                body: (document.body.innerText || '').slice(0, 1200)
              };
            })())"""
        )
        state = json.loads(state_raw)
        last_text = "\n".join([state.get("publishText") or "", state.get("messages") or "", state.get("body") or ""])
        if any(hint in last_text for hint in ("失败", "错误", "超出", "限制", "请稍后", "不合法")):
            raise RuntimeError(f"Fanqie rejected update: {last_text}")
        if not state.get("hasPublishModal"):
            return
        if any(hint in last_text for hint in ("已提交", "提交成功", "预计1小时内完成审核")):
            return
        time.sleep(1)
    raise TimeoutError(f"Timed out waiting for update confirmation. Last page text: {last_text}")


def return_to_manage_and_find_row(
    page: CDPPage,
    manage_url: str,
    book_id: str,
    chapter_no: int,
    display_title: str,
) -> Dict[str, str]:
    # Fanqie sometimes lingers on the editor after confirm, so navigate back explicitly for verification.
    open_manage_page(page, manage_url, book_id)
    page.wait_for(
        f"""(() => (document.body.innerText || '').includes("第{chapter_no}章"))()""",
        timeout_s=40,
        interval_s=1,
    )
    row_raw = page.eval(
        f"""JSON.stringify((() => {{
          const rowEls = Array.from(document.querySelectorAll('tr.arco-table-tr'));
          const rows = rowEls.map(tr => {{
            const title = tr.querySelector('td:first-child .table-title')?.innerText?.trim() || '';
            return {{
              title,
              text: (tr.innerText || '').trim(),
            }};
          }}).filter(Boolean);
          const exact = rows.find(row => row.title === {json.dumps(display_title, ensure_ascii=False)});
          const fallback = rows.find(row => row.title.includes("第{chapter_no}章"));
          const chosen = exact || fallback || {{ title: '', text: '' }};
          return {{ row: chosen.text, title: chosen.title, href: location.href }};
        }})())"""
    )
    return json.loads(row_raw)


def update_one(
    page: CDPPage,
    manage_url: str,
    book_id: str,
    edit_url: str,
    chapter_meta: Dict[str, object],
) -> Dict[str, object]:
    page.navigate(edit_url)
    wait_editor_ready(page)
    dismiss_transient_popups(page)
    set_input_value(page, "input.serial-input.byte-input", str(chapter_meta["chapter_no"]))
    set_input_value(page, 'input[placeholder="请输入标题"]', str(chapter_meta["title"]))
    verify_input_value(page, "input.serial-input.byte-input", str(chapter_meta["chapter_no"]))
    verify_input_value(page, 'input[placeholder="请输入标题"]', str(chapter_meta["title"]))
    inject_result = inject_body(page, str(chapter_meta["body"]).split("\n"))
    expected_char_count = int(chapter_meta["char_count"])
    if int(inject_result["char_count"]) != expected_char_count:
        raise RuntimeError(
            f"Injected char count mismatch for {chapter_meta['display_title']}: "
            f"{inject_result['char_count']} != {expected_char_count}"
        )
    wait_saved(page)
    click_next(page)
    reach_publish_settings(page)
    select_ai_no(page)
    confirm_publish(page)
    time.sleep(3)
    return {
        "display_title": chapter_meta["display_title"],
        "edit_url": edit_url,
        "submitted": True,
        "chapter_no": int(chapter_meta["chapter_no"]),
    }


def expand_chapter_args(values: Sequence[str]) -> List[str]:
    result: List[str] = []
    for value in values:
        if re.fullmatch(r"\d+-\d+", value):
            start_s, end_s = value.split("-", 1)
            start, end = int(start_s), int(end_s)
            step = 1 if end >= start else -1
            result.extend([f"第{i}章" for i in range(start, end + step, step)])
        else:
            result.append(value)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Update existing published Fanqie chapters from local markdown files.")
    parser.add_argument("chapters", nargs="+", help="Chapter file paths, 第NN章 values, or ranges like 1-53.")
    parser.add_argument("--chapter-manage-url", required=True, help="Fanqie chapter-manage URL.")
    parser.add_argument("--project-root", default=".", help="Project root for resolving 第NN章.")
    parser.add_argument("--volume-name", help="Optional target Fanqie volume name, for example 第一卷：会安·活下来.")
    args = parser.parse_args()

    manage_url = args.chapter_manage_url.strip()
    project_root = pathlib.Path(args.project_root).expanduser().resolve()
    requested = expand_chapter_args(args.chapters)
    chapter_paths = [resolve_chapter_path(project_root, item) for item in requested]
    chapter_meta_list = [extract_fanqie_chapter.extract(path) for path in chapter_paths]

    book_id = book_id_from_url(manage_url)
    page = open_target(f"{BASE_URL}/main/writer/home")
    try:
        open_manage_page(page, manage_url, book_id, args.volume_name)
        edit_map = scrape_edit_links(page)
        missing = [meta["display_title"] for meta in chapter_meta_list if int(meta["chapter_no"]) not in edit_map]
        if missing:
            open_manage_page(page, manage_url, book_id, args.volume_name)
            fallback_map = scrape_edit_links_by_numbers(page)
            edit_map.update(fallback_map)
            missing = [meta["display_title"] for meta in chapter_meta_list if int(meta["chapter_no"]) not in edit_map]
        if missing:
            raise RuntimeError(f"Missing edit URLs for: {', '.join(missing)}")

        results = []
        for meta in chapter_meta_list:
            chapter_no = int(meta["chapter_no"])
            edit_path = edit_map[chapter_no]
            edit_url = urllib.parse.urljoin(BASE_URL, edit_path)
            print(f"Updating {meta['display_title']}...", flush=True)
            result = update_one(page, manage_url, book_id, edit_url, meta)
            results.append(result)
            print(f"Updated {result['display_title']}", flush=True)
        print(json.dumps({"book_id": book_id, "results": results}, ensure_ascii=False, indent=2))
        return 0
    finally:
        page.close()


if __name__ == "__main__":
    raise SystemExit(main())
