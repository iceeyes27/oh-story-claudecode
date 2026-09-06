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
from typing import Dict, List, Optional, Sequence

from websocket import create_connection

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import extract_fanqie_chapter
import extract_fanqie_queue
import locate_fanqie_chapter
import next_fanqie_schedule

BASE_URL = "https://fanqienovel.com"
MANAGE_URL_RE = re.compile(r"chapter-manage/(\d+)")
UPLOAD_LIMIT_HINTS = (
    "超过当日上传",
    "超过今日上传",
    "今日上传字数限制",
    "当日上传字数限制",
    "上传字数限制",
)


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


class CDPPage:
    def __init__(self, websocket_url: str) -> None:
        self._ws = create_connection(websocket_url, timeout=60)
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
          const options = Array.from(document.querySelectorAll('.byte-select-option, [class*=option]'))
            .filter(el => (el.innerText || '').trim() === {json.dumps(volume_name, ensure_ascii=False)});
          const option = options[0];
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
          return (current?.innerText || '').trim() === {json.dumps(volume_name, ensure_ascii=False)} &&
            (document.body.innerText || '').includes({json.dumps(volume_name, ensure_ascii=False)});
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


def queue_entries_from_manage(page: CDPPage) -> List[Dict[str, str]]:
    deadline = time.time() + 10
    while time.time() < deadline:
        rows_raw = page.eval(
            """JSON.stringify(Array.from(document.querySelectorAll('tr.arco-table-tr'))
              .map(tr => Array.from(tr.children).map(td => (td.innerText || '').trim())))"""
        )
        rows = json.loads(rows_raw or "[]")
        entries = []
        for cells in rows:
            if len(cells) < 5:
                continue
            title, status, publish_time = cells[0], cells[3], cells[4]
            if status in extract_fanqie_queue.STATUS_SET and extract_fanqie_queue.TITLE_RE.match(title):
                match = extract_fanqie_queue.TIME_RE.match(publish_time)
                if match:
                    entries.append(
                        {
                            "title": title,
                            "status": status,
                            "publish_time": "%s %s" % (match.group(1), match.group(2)),
                        }
                    )
        if entries:
            return entries

        text = page.eval("document.body.innerText") or ""
        lines = extract_fanqie_queue.normalize_lines(text)
        entries = extract_fanqie_queue.extract_entries(lines)
        if entries:
            return entries
        if "暂无章节内容" in text:
            return []
        time.sleep(0.5)
    return []


def earliest_batch_slot(preferred_time: str, min_lead_minutes: int):
    # Fanqie allows consecutive queued chapters to share the same earliest legal slot.
    # We intentionally ignore already-picked slots from the current batch so later
    # chapters don't drift one day at a time.
    now = next_fanqie_schedule.dt.datetime.now()
    preferred = next_fanqie_schedule.parse_time(preferred_time)
    return next_fanqie_schedule.next_slot(
        scheduled=[],
        preferred_time=preferred,
        cadence_days=1,
        min_lead_minutes=min_lead_minutes,
        now=now,
    )


def build_publish_plan(
    queue_entries: Sequence[Dict[str, str]],
    chapter_meta_list: Sequence[Dict[str, object]],
    preferred_time: str,
    min_lead_minutes: int,
    no_immediate: bool = False,
    start_scheduled=None,
):
    immediate_first = (not no_immediate) and not queue_entries
    scheduled_count = len(chapter_meta_list) - (1 if immediate_first and chapter_meta_list else 0)
    shared_slot = None
    if scheduled_count > 0:
        shared_slot = start_scheduled or earliest_batch_slot(preferred_time, min_lead_minutes)

    plan = []
    for idx, meta in enumerate(chapter_meta_list):
        immediate = immediate_first and idx == 0
        slot = None if immediate else shared_slot
        plan.append(
            {
                "chapter_meta": meta,
                "immediate": immediate,
                "slot": slot,
                "fallback_slot": shared_slot,
            }
        )
    return plan


def wait_new_editor_ready(page: CDPPage) -> None:
    page.wait_for(
        """(() => {
          return !!document.querySelector('input.serial-input.byte-input') &&
            !!document.querySelector('input[placeholder="请输入标题"]') &&
            !!document.querySelector('.ProseMirror');
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
    payload = json.loads(raw) if isinstance(raw, str) else raw
    if not payload or not payload.get("ok"):
        raise RuntimeError(f"Body inject failed: {payload}")
    return payload


def wait_next_enabled(page: CDPPage) -> None:
    page.wait_for(
        """(() => {
          const next = document.querySelector('button.auto-editor-next');
          const body = document.body.innerText || '';
          return !!next && next.disabled === false && body.includes('已保存');
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


def toggle_schedule(page: CDPPage, enabled: bool) -> None:
    page.eval(
        f"""(() => {{
          const enabled = {json.dumps(enabled)};
          const wrapper = Array.from(document.querySelectorAll('.arco-modal-wrapper'))
            .find(w => (w.innerText || '').includes('发布设置'));
          if (!wrapper) return false;
          const btn = wrapper.querySelector('button[role="switch"]');
          if (!btn) return false;
          const current = btn.getAttribute('aria-checked') === 'true';
          if (current !== enabled) btn.click();
          return true;
        }})()"""
    )
    page.wait_for(
        f"""(() => {{
          const wrapper = Array.from(document.querySelectorAll('.arco-modal-wrapper'))
            .find(w => (w.innerText || '').includes('发布设置'));
          if (!wrapper) return false;
          const btn = wrapper.querySelector('button[role="switch"]');
          return !!btn && ((btn.getAttribute('aria-checked') === 'true') === {json.dumps(enabled)});
        }})()""",
        timeout_s=10,
        interval_s=0.5,
    )


def choose_date(page: CDPPage, slot) -> None:
    page.eval(
        """(() => {
          const wrapper = Array.from(document.querySelectorAll('.arco-modal-wrapper'))
            .find(w => (w.innerText || '').includes('发布设置'));
          const input = wrapper?.querySelector('input[placeholder="请选择日期"]');
          if (input) input.click();
          return true;
        })()"""
    )
    time.sleep(0.5)
    for _ in range(12):
        matched = page.eval(
            f"""(() => {{
              const year = {slot.year}, month = {slot.month}, day = {slot.day};
              const popup = Array.from(document.querySelectorAll('.arco-picker-container'))
                .find(p => (p.innerText || '').includes('年') && (p.innerText || '').includes('月'));
              if (!popup) return {{ok:false, reason:'no popup'}};
              const labels = Array.from(popup.querySelectorAll('.arco-picker-header-label')).map(x => (x.innerText || '').trim());
              const currentYear = parseInt((labels[0] || '').replace('年', ''), 10);
              const currentMonth = parseInt((labels[1] || '').replace('月', ''), 10);
              if (currentYear === year && currentMonth === month) {{
                const cell = Array.from(popup.querySelectorAll('.arco-picker-cell-in-view'))
                  .find(c => c.querySelector('.arco-picker-date-value')?.innerText.trim() === String(day));
                if (!cell) return {{ok:false, reason:'day not found'}};
                cell.click();
                return {{ok:true, done:true}};
              }}
              const nextBtn = popup.querySelector('.arco-icon-right')?.closest('.arco-picker-header-icon');
              const prevBtn = popup.querySelector('.arco-icon-left')?.closest('.arco-picker-header-icon');
              if (!nextBtn || !prevBtn) return {{ok:false, reason:'nav missing'}};
              if (currentYear < year || (currentYear === year && currentMonth < month)) nextBtn.click(); else prevBtn.click();
              return {{ok:true, done:false}};
            }})()"""
        )
        if matched and matched.get("done"):
            break
        time.sleep(0.4)
    expected = slot.strftime("%Y-%m-%d")
    got = page.eval(
        """(() => {
          const wrapper = Array.from(document.querySelectorAll('.arco-modal-wrapper'))
            .find(w => (w.innerText || '').includes('发布设置'));
          return wrapper?.querySelector('input[placeholder="请选择日期"]')?.value || '';
        })()"""
    )
    if got != expected:
        raise RuntimeError(f"date set failed: expected {expected}, got {got}")


def choose_time(page: CDPPage, slot) -> None:
    page.eval(
        """(() => {
          const wrapper = Array.from(document.querySelectorAll('.arco-modal-wrapper'))
            .find(w => (w.innerText || '').includes('发布设置'));
          const input = wrapper?.querySelector('input[placeholder="请选择时间"]');
          if (input) input.click();
          return true;
        })()"""
    )
    time.sleep(0.5)
    page.eval(
        f"""(() => {{
          const hour = {json.dumps(slot.strftime('%H'))};
          const minute = {json.dumps(slot.strftime('%M'))};
          const wrapper = Array.from(document.querySelectorAll('.arco-modal-wrapper'))
            .find(w => (w.innerText || '').includes('发布设置'));
          if (!wrapper) return false;
          const lists = wrapper.querySelectorAll('.arco-timepicker-list ul');
          if (lists.length < 2) return false;
          const hourCell = Array.from(lists[0].querySelectorAll('.arco-timepicker-cell')).find(c => c.innerText.trim() === hour);
          const minuteCell = Array.from(lists[1].querySelectorAll('.arco-timepicker-cell')).find(c => c.innerText.trim() === minute);
          hourCell?.click();
          minuteCell?.click();
          const confirm = Array.from(wrapper.querySelectorAll('button')).find(b => (b.innerText || '').trim() === '确定');
          confirm?.click();
          return true;
        }})()"""
    )
    time.sleep(0.5)
    expected = slot.strftime("%H:%M")
    got = page.eval(
        """(() => {
          const wrapper = Array.from(document.querySelectorAll('.arco-modal-wrapper'))
            .find(w => (w.innerText || '').includes('发布设置'));
          return wrapper?.querySelector('input[placeholder="请选择时间"]')?.value || '';
        })()"""
    )
    if got != expected:
        raise RuntimeError(f"time set failed: expected {expected}, got {got}")


def click_confirm_publish(page: CDPPage) -> None:
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


def publish_modal_text(page: CDPPage) -> str:
    return page.eval(
        """(() => {
          const wrapper = Array.from(document.querySelectorAll('.arco-modal-wrapper'))
            .find(w => (w.innerText || '').includes('发布设置'));
          return (wrapper?.innerText || '').trim();
        })()"""
    ) or ""


def manage_page_ready(page: CDPPage) -> bool:
    return bool(
        page.eval(
            """(() => {
              const body = document.body.innerText || '';
              return body.includes('章节管理') && body.includes('审核状态');
            })()"""
        )
    )


def submit_publish_with_retry(page: CDPPage, slot, fallback_slot):
    current_slot = slot
    retry_budget = 5
    while True:
        click_confirm_publish(page)
        deadline = time.time() + 30
        while time.time() < deadline:
            if manage_page_ready(page):
                return current_slot
            text = publish_modal_text(page)
            if text and any(hint in text for hint in UPLOAD_LIMIT_HINTS):
                if retry_budget <= 0:
                    raise RuntimeError(f"publish blocked by upload limit after retries: {text}")
                retry_budget -= 1
                if current_slot is None:
                    current_slot = fallback_slot
                    toggle_schedule(page, True)
                else:
                    current_slot = current_slot + next_fanqie_schedule.dt.timedelta(days=1)
                if current_slot is None:
                    raise RuntimeError(f"publish blocked by upload limit and no fallback slot available: {text}")
                choose_date(page, current_slot)
                choose_time(page, current_slot)
                break
            time.sleep(1)
        else:
            raise TimeoutError("Timed out waiting for publish confirmation result")


def verify_manage_row(
    page: CDPPage,
    manage_url: str,
    book_id: str,
    display_title: str,
    volume_name: Optional[str] = None,
) -> Dict[str, str]:
    open_manage_page(page, manage_url, book_id, volume_name)
    page.wait_for(
        f"""(() => (document.body.innerText || '').includes({json.dumps(display_title, ensure_ascii=False)}))()""",
        timeout_s=40,
        interval_s=1,
    )
    row_raw = page.eval(
        f"""JSON.stringify((() => {{
          const rowEls = Array.from(document.querySelectorAll('tr.arco-table-tr'));
          const match = rowEls.map(tr => ({{
            title: tr.querySelector('td:first-child .table-title')?.innerText?.trim() || '',
            text: (tr.innerText || '').trim(),
            status: tr.children[3]?.innerText?.trim() || '',
            time: tr.children[4]?.innerText?.trim() || ''
          }})).find(r => r.title === {json.dumps(display_title, ensure_ascii=False)});
          return match || null;
        }})())"""
    )
    payload = json.loads(row_raw)
    if not payload:
        raise RuntimeError(f"Could not find row for {display_title}")
    return payload


def publish_one(
    page: CDPPage,
    manage_url: str,
    book_id: str,
    chapter_meta: Dict[str, object],
    immediate: bool,
    slot,
    fallback_slot,
    volume_name: Optional[str] = None,
):
    page.navigate(f"{BASE_URL}/main/writer/{book_id}/publish/?enter_from=newchapter")
    wait_new_editor_ready(page)
    dismiss_transient_popups(page)
    set_input_value(page, "input.serial-input.byte-input", str(chapter_meta["chapter_no"]))
    set_input_value(page, 'input[placeholder="请输入标题"]', str(chapter_meta["title"]))
    verify_input_value(page, "input.serial-input.byte-input", str(chapter_meta["chapter_no"]))
    verify_input_value(page, 'input[placeholder="请输入标题"]', str(chapter_meta["title"]))
    inject_result = inject_body(page, str(chapter_meta["body"]).split("\n"))
    if int(inject_result["char_count"]) != int(chapter_meta["char_count"]):
        raise RuntimeError(
            f"Injected char count mismatch for {chapter_meta['display_title']}: "
            f"{inject_result['char_count']} != {chapter_meta['char_count']}"
        )
    wait_next_enabled(page)
    click_next(page)
    reach_publish_settings(page)
    select_ai_no(page)
    toggle_schedule(page, not immediate)
    if slot is not None:
        choose_date(page, slot)
        choose_time(page, slot)
    resolved_slot = submit_publish_with_retry(page, slot, fallback_slot)
    time.sleep(3)
    row = verify_manage_row(page, manage_url, book_id, str(chapter_meta["display_title"]), volume_name)
    return {
        "display_title": chapter_meta["display_title"],
        "immediate": immediate,
        "scheduled_for": "" if resolved_slot is None else resolved_slot.strftime("%Y-%m-%d %H:%M"),
        "status": row["status"],
        "time": row["time"],
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
    parser = argparse.ArgumentParser(description="Publish new local Fanqie chapters via CDP Chrome.")
    parser.add_argument("chapters", nargs="+", help="Chapter file paths, 第NN章 values, or ranges like 54-60.")
    parser.add_argument("--chapter-manage-url", required=True, help="Fanqie chapter-manage URL.")
    parser.add_argument("--project-root", default=".", help="Project root for resolving 第NN章.")
    parser.add_argument("--volume-name", help="Optional target Fanqie volume name, for example 第二卷：堤岸·华埠.")
    parser.add_argument("--no-immediate", action="store_true", help="Schedule every chapter instead of publishing the first one immediately.")
    parser.add_argument("--start-scheduled", help="Optional first scheduled slot, formatted as YYYY-MM-DD HH:MM.")
    parser.add_argument("--preferred-time", default="09:02", help="Preferred daily schedule time in HH:MM.")
    parser.add_argument("--min-lead-minutes", type=int, default=30, help="Minimum legal lead time.")
    args = parser.parse_args()

    manage_url = args.chapter_manage_url.strip()
    project_root = pathlib.Path(args.project_root).expanduser().resolve()
    book_id = book_id_from_url(manage_url)

    requested = expand_chapter_args(args.chapters)
    chapter_paths = [resolve_chapter_path(project_root, item) for item in requested]
    chapter_meta_list = [extract_fanqie_chapter.extract(path) for path in chapter_paths]
    start_scheduled = None
    if args.start_scheduled:
        start_scheduled = next_fanqie_schedule.dt.datetime.strptime(args.start_scheduled, "%Y-%m-%d %H:%M")

    page = open_target(f"{BASE_URL}/main/writer/home")
    try:
        open_manage_page(page, manage_url, book_id, args.volume_name)
        queue_entries = queue_entries_from_manage(page)
        plan = build_publish_plan(
            queue_entries,
            chapter_meta_list,
            args.preferred_time,
            args.min_lead_minutes,
            args.no_immediate,
            start_scheduled,
        )
        results = []
        for item in plan:
            meta = item["chapter_meta"]
            print(f"Publishing {meta['display_title']}...", flush=True)
            result = publish_one(
                page,
                manage_url,
                book_id,
                meta,
                item["immediate"],
                item["slot"],
                item["fallback_slot"],
                args.volume_name,
            )
            results.append(result)
            print(f"Published {result['display_title']}: {result['status']} {result['time']}", flush=True)
        print(json.dumps({"book_id": book_id, "queue": queue_entries, "results": results}, ensure_ascii=False, indent=2))
        return 0
    finally:
        page.close()


if __name__ == "__main__":
    raise SystemExit(main())
