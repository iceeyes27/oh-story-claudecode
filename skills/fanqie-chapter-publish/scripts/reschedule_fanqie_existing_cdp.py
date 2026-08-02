#!/usr/bin/env python3
import argparse
import itertools
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from typing import Dict, Optional

from websocket import create_connection

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

BASE_URL = "https://fanqienovel.com"
MANAGE_URL_RE = re.compile(r"chapter-manage/(\d+)")


def book_id_from_url(url: str) -> str:
    match = MANAGE_URL_RE.search(url)
    if not match:
        raise ValueError(f"Could not infer book id from {url}")
    return match.group(1)


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


def open_manage_page(page: CDPPage, manage_url: str, book_id: str) -> None:
    home_url = f"{BASE_URL}/main/writer/home"
    page.navigate(home_url)
    page.wait_for(
        f"""(() => {{
          const body = document.body.innerText || '';
          return body.includes('我在越南捞沉船') && body.includes('章节管理') &&
            Array.from(document.querySelectorAll('a')).some(a =>
              (a.innerText || '').trim() === '章节管理' &&
              (a.href || '').includes('chapter-manage/{book_id}')
            );
        }})()""",
        timeout_s=40,
    )
    clicked = page.eval(
        f"""(() => {{
          const a = Array.from(document.querySelectorAll('a')).find(a =>
            (a.innerText || '').trim() === '章节管理' &&
            (a.href || '').includes('chapter-manage/{book_id}')
          );
          if (!a) return false;
          a.click();
          return true;
        }})()"""
    )
    if not clicked:
        raise RuntimeError("Could not find chapter-manage link from home page")
    page.wait_for(
        """(() => {
          const body = document.body.innerText || '';
          return body.includes('新建章节') && body.includes('搜索章节') && body.includes('审核状态');
        })()""",
        timeout_s=40,
    )


def scrape_rows(page: CDPPage):
    raw = page.eval(
        """JSON.stringify(Array.from(document.querySelectorAll('tr.arco-table-tr')).map(tr => ({
          title: tr.querySelector('td:first-child .table-title')?.innerText?.trim() || '',
          status: tr.children[3]?.innerText?.trim() || '',
          time: tr.children[4]?.innerText?.trim() || '',
          edit: tr.querySelector('a.link')?.getAttribute('href') || ''
        })).filter(r => r.title))"""
    )
    return json.loads(raw)


def find_edit_urls(page: CDPPage, needed: Dict[str, str]) -> Dict[str, str]:
    found: Dict[str, str] = {}
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
        for row in scrape_rows(page):
            if row["title"] in needed and row["edit"]:
                found[row["title"]] = urllib.parse.urljoin(BASE_URL, row["edit"])
        if all(title in found for title in needed):
            break
        has_next = page.eval(
            """(() => {
              const next = document.querySelector('li.arco-pagination-item-next');
              return !!next && !next.classList.contains('arco-pagination-item-disabled');
            })()"""
        )
        if not has_next:
            break
        page.eval(
            """(() => {
              const next = document.querySelector('li.arco-pagination-item-next');
              if (next && !next.classList.contains('arco-pagination-item-disabled')) next.click();
              return true;
            })()"""
        )
        page.wait_for(
            f"""(() => {{
              const active = parseInt((document.querySelector('li.arco-pagination-item-active')?.innerText || '0').trim(), 10);
              return Number.isFinite(active) && active === {active_page + 1};
            }})()""",
            timeout_s=20,
        )
        time.sleep(2)
    return found


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


def choose_date(page: CDPPage, date_str: str) -> None:
    year, month, day = [int(x) for x in date_str.split("-")]
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
              const year = {year}, month = {month}, day = {day};
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
    got = page.eval(
        """(() => {
          const wrapper = Array.from(document.querySelectorAll('.arco-modal-wrapper'))
            .find(w => (w.innerText || '').includes('发布设置'));
          return wrapper?.querySelector('input[placeholder="请选择日期"]')?.value || '';
        })()"""
    )
    if got != date_str:
        raise RuntimeError(f"date set failed: expected {date_str}, got {got}")


def choose_time(page: CDPPage, time_str: str) -> None:
    hour, minute = time_str.split(":")
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
          const hour = {json.dumps(hour)};
          const minute = {json.dumps(minute)};
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
    got = page.eval(
        """(() => {
          const wrapper = Array.from(document.querySelectorAll('.arco-modal-wrapper'))
            .find(w => (w.innerText || '').includes('发布设置'));
          return wrapper?.querySelector('input[placeholder="请选择时间"]')?.value || '';
        })()"""
    )
    if got != time_str:
        page.eval(
            f"""(() => {{
              const wrapper = Array.from(document.querySelectorAll('.arco-modal-wrapper'))
                .find(w => (w.innerText || '').includes('发布设置'));
              const el = wrapper?.querySelector('input[placeholder="请选择时间"]');
              if (!el) return false;
              const proto = Object.getPrototypeOf(el);
              const desc = Object.getOwnPropertyDescriptor(proto, 'value') ||
                Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
              desc.set.call(el, {json.dumps(time_str)});
              el.dispatchEvent(new Event('input', {{ bubbles: true }}));
              el.dispatchEvent(new Event('change', {{ bubbles: true }}));
              el.blur();
              return true;
            }})()"""
        )
        time.sleep(0.5)
        got = page.eval(
            """(() => {
              const wrapper = Array.from(document.querySelectorAll('.arco-modal-wrapper'))
                .find(w => (w.innerText || '').includes('发布设置'));
              return wrapper?.querySelector('input[placeholder="请选择时间"]')?.value || '';
            })()"""
        )
    if got != time_str:
        raise RuntimeError(f"time set failed: expected {time_str}, got {got}")


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


def verify_row(page: CDPPage, manage_url: str, book_id: str, title: str):
    open_manage_page(page, manage_url, book_id)
    page.wait_for(
        f"""(() => (document.body.innerText || '').includes({json.dumps(title, ensure_ascii=False)}))()""",
        timeout_s=40,
        interval_s=1,
    )
    raw = page.eval(
        f"""JSON.stringify((() => {{
          const rows = Array.from(document.querySelectorAll('tr.arco-table-tr')).map(tr => ({{
            title: tr.querySelector('td:first-child .table-title')?.innerText?.trim() || '',
            status: tr.children[3]?.innerText?.trim() || '',
            time: tr.children[4]?.innerText?.trim() || ''
          }}));
          return rows.find(r => r.title === {json.dumps(title, ensure_ascii=False)}) || null;
        }})())"""
    )
    payload = json.loads(raw)
    if not payload:
        raise RuntimeError(f"Could not verify row for {title}")
    return payload


def reschedule_one(page: CDPPage, manage_url: str, book_id: str, edit_url: str, title: str, date_str: str, time_str: str):
    page.navigate(edit_url)
    wait_editor_ready(page)
    click_next(page)
    reach_publish_settings(page)
    select_ai_no(page)
    toggle_schedule(page, True)
    choose_date(page, date_str)
    choose_time(page, time_str)
    confirm_publish(page)
    time.sleep(3)
    row = verify_row(page, manage_url, book_id, title)
    return {
        "title": title,
        "status": row["status"],
        "time": row["time"],
    }


def parse_target(item: str):
    if "=" not in item:
        raise ValueError(f"Expected TITLE=YYYY-MM-DD HH:MM, got: {item}")
    title, schedule = item.split("=", 1)
    schedule = schedule.strip()
    if " " not in schedule:
        raise ValueError(f"Expected datetime in target: {item}")
    date_str, time_str = schedule.split(" ", 1)
    return title.strip(), date_str.strip(), time_str.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Reschedule existing Fanqie chapters via CDP Chrome.")
    parser.add_argument("--chapter-manage-url", required=True, help="Fanqie chapter-manage URL.")
    parser.add_argument("targets", nargs="+", help='Targets like "第55章 会安这口海，先问谁点头=2026-07-10 09:02"')
    args = parser.parse_args()

    manage_url = args.chapter_manage_url.strip()
    book_id = book_id_from_url(manage_url)
    plan = {}
    for item in args.targets:
        title, date_str, time_str = parse_target(item)
        plan[title] = {"date": date_str, "time": time_str}

    page = open_target(f"{BASE_URL}/main/writer/home")
    try:
        open_manage_page(page, manage_url, book_id)
        edit_map = find_edit_urls(page, plan)
        missing = [title for title in plan if title not in edit_map]
        if missing:
            raise RuntimeError(f"Missing edit URLs for: {', '.join(missing)}")
        results = []
        for title, schedule in plan.items():
            results.append(
                reschedule_one(
                    page,
                    manage_url,
                    book_id,
                    edit_map[title],
                    title,
                    schedule["date"],
                    schedule["time"],
                )
            )
        print(json.dumps({"book_id": book_id, "results": results}, ensure_ascii=False, indent=2))
        return 0
    finally:
        page.close()


if __name__ == "__main__":
    raise SystemExit(main())
