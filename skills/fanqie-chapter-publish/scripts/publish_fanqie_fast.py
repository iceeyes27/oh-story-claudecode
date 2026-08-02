#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import pathlib
import re
import sys
import time
from typing import Dict, List, Optional, Sequence
from urllib.parse import urlparse

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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

MANAGE_URL_RE = re.compile(r"chapter-manage/(\d+)")
TITLE_RE = re.compile(r"^第\d+章\s+")
UPLOAD_LIMIT_HINTS = (
    "超过当日上传",
    "超过今日上传",
    "今日上传字数限制",
    "当日上传字数限制",
    "上传字数限制",
)


def attach_driver(port: int) -> webdriver.Chrome:
    opts = Options()
    opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
    return webdriver.Chrome(options=opts)


def normalize_manage_url(url: str) -> str:
    return url.strip()


def book_id_from_url(url: str) -> str:
    match = MANAGE_URL_RE.search(url)
    if not match:
        raise ValueError(f"Could not infer book id from {url}")
    return match.group(1)


def resolve_chapter_path(project_root: pathlib.Path, raw: str) -> pathlib.Path:
    candidate = pathlib.Path(raw)
    if candidate.exists():
        return candidate.expanduser().resolve()
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


def wait_text(driver: webdriver.Chrome, text: str, timeout: int = 20) -> None:
    WebDriverWait(driver, timeout).until(lambda d: text in d.execute_script("return document.body.innerText"))


def click_js(driver: webdriver.Chrome, element) -> None:
    driver.execute_script("arguments[0].click()", element)


def body_text(driver: webdriver.Chrome) -> str:
    return driver.execute_script("return document.body.innerText")


def set_input_value(driver: webdriver.Chrome, element, value: str) -> None:
    driver.execute_script(
        """
const el = arguments[0], value = arguments[1];
const proto = Object.getPrototypeOf(el);
const desc = Object.getOwnPropertyDescriptor(proto, 'value') || Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
desc.set.call(el, value);
el.dispatchEvent(new Event('input', { bubbles: true }));
el.dispatchEvent(new Event('change', { bubbles: true }));
""",
        element,
        value,
    )


def visible_modal_wrappers(driver: webdriver.Chrome):
    return driver.execute_script(
        """
return Array.from(document.querySelectorAll('.arco-modal-wrapper, .byte-modal-wrapper, .reactour__helper')).filter(el => {
  const style = getComputedStyle(el);
  return style.display !== 'none' && style.visibility !== 'hidden';
}).map(el => el);
"""
    )


def dismiss_guides(driver: webdriver.Chrome) -> None:
    for _ in range(5):
        handled = driver.execute_script(
            """
let count = 0;
for (const w of Array.from(document.querySelectorAll('.reactour__helper, .byte-modal-wrapper, .arco-modal-wrapper'))) {
  const text = (w.innerText || '').trim();
  const btn = Array.from(w.querySelectorAll('button')).find(b => ['我知道了', '下一步', '完成', '知道了'].includes((b.innerText || '').trim()));
  if (btn && (text.includes('历史版本') || text.includes('请在发布时间前30分钟提交修改内容') || text.includes('提示'))) {
    btn.click();
    count += 1;
  }
}
return count;
"""
        )
        if not handled:
            return
        time.sleep(0.4)


def handle_transition_modals(driver: webdriver.Chrome) -> None:
    for _ in range(6):
        dismiss_guides(driver)
        state = driver.execute_script(
            """
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
"""
        )
        if state.get("publish"):
            return
        time.sleep(0.6)
    raise RuntimeError("publish settings modal did not appear")


def open_manage_page(driver: webdriver.Chrome, manage_url: str) -> None:
    driver.get(manage_url)
    wait_text(driver, "章节管理")
    WebDriverWait(driver, 20).until(
        lambda d: "章节名称" in body_text(d) and ("新建章节" in body_text(d) or "搜索章节" in body_text(d))
    )
    time.sleep(1.0)


def queue_entries_from_manage(driver: webdriver.Chrome) -> List[Dict[str, str]]:
    for _ in range(8):
        lines = extract_fanqie_queue.normalize_lines(body_text(driver))
        entries = extract_fanqie_queue.extract_entries(lines)
        if entries:
            return entries
        if any(TITLE_RE.match(line) for line in lines):
            return entries
        time.sleep(0.8)
    return []


def earliest_batch_slot(preferred_time: str, min_lead_minutes: int) -> dt.datetime:
    # Fanqie allows consecutive queued chapters in the same batch to share
    # the same earliest legal slot, so we do not cascade later chapters by day.
    now = dt.datetime.now()
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
) -> List[Dict[str, object]]:
    immediate_first = not queue_entries
    scheduled_count = len(chapter_meta_list) - (1 if immediate_first and chapter_meta_list else 0)
    shared_slot: Optional[dt.datetime] = None
    if scheduled_count > 0:
        shared_slot = earliest_batch_slot(preferred_time, min_lead_minutes)

    plan: List[Dict[str, object]] = []
    for idx, meta in enumerate(chapter_meta_list):
        immediate = immediate_first and idx == 0
        slot = None if immediate else shared_slot
        plan.append(
            {
                "chapter_meta": meta,
                "display_title": meta["display_title"],
                "chapter_no": meta["chapter_no"],
                "title": meta["title"],
                "immediate": immediate,
                "slot": slot,
                "fallback_slot": shared_slot,
                "scheduled_for": "" if slot is None else slot.strftime("%Y-%m-%d %H:%M"),
            }
        )
    return plan


def ensure_editor_page(driver: webdriver.Chrome, book_id: str) -> None:
    driver.get(f"https://fanqienovel.com/main/writer/{book_id}/publish/?enter_from=newchapter")
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input.serial-input.byte-input")))
    dismiss_guides(driver)


def fill_editor(driver: webdriver.Chrome, chapter_meta: Dict[str, object]) -> None:
    num_input = driver.find_element(By.CSS_SELECTOR, "input.serial-input.byte-input")
    title_input = driver.find_element(By.CSS_SELECTOR, 'input[placeholder="请输入标题"]')
    set_input_value(driver, num_input, str(chapter_meta["chapter_no"]))
    set_input_value(driver, title_input, str(chapter_meta["title"]))
    script = extract_fanqie_chapter.eval_js_for(str(chapter_meta["body"]).split("\n"))
    result = driver.execute_script(script)
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            result = {"ok": False, "raw": result}
    if not result or not result.get("ok"):
        raise RuntimeError(f"body inject failed: {result}")
    save_btn = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.auto-editor-save-btn")))
    click_js(driver, save_btn)
    WebDriverWait(driver, 20).until(lambda d: "已保存" in body_text(d))


def proceed_to_publish_settings(driver: webdriver.Chrome) -> None:
    dismiss_guides(driver)
    next_btn = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "button.auto-editor-next")))
    click_js(driver, next_btn)
    handle_transition_modals(driver)
    WebDriverWait(driver, 20).until(lambda d: "发布设置" in body_text(d))


def find_publish_modal(driver: webdriver.Chrome):
    return driver.execute_script(
        """
return Array.from(document.querySelectorAll('.arco-modal-wrapper')).find(w => (w.innerText || '').includes('发布设置')) || null;
"""
    )


def select_radio_by_label(driver: webdriver.Chrome, label_text: str) -> None:
    driver.execute_script(
        """
const target = arguments[0];
for (const w of Array.from(document.querySelectorAll('.arco-modal-wrapper'))) {
  if (!(w.innerText || '').includes('发布设置')) continue;
  const label = Array.from(w.querySelectorAll('label.arco-radio')).find(l => (l.innerText || '').trim() === target);
  if (label) { label.click(); return true; }
}
return false;
""",
        label_text,
    )


def toggle_schedule(driver: webdriver.Chrome, enabled: bool) -> None:
    script = """
const enabled = arguments[0];
for (const w of Array.from(document.querySelectorAll('.arco-modal-wrapper'))) {
  if (!(w.innerText || '').includes('发布设置')) continue;
  const btn = w.querySelector('button[role="switch"]');
  if (!btn) return false;
  const current = btn.getAttribute('aria-checked') === 'true';
  if (current !== enabled) btn.click();
  return true;
}
return false;
"""
    driver.execute_script(script, enabled)
    time.sleep(0.6)


def choose_date(driver: webdriver.Chrome, target: dt.datetime) -> None:
    driver.execute_script(
        """
for (const w of Array.from(document.querySelectorAll('.arco-modal-wrapper'))) {
  if (!(w.innerText || '').includes('发布设置')) continue;
  const input = w.querySelector('input[placeholder="请选择日期"]');
  if (input) { input.click(); return true; }
}
return false;
"""
    )
    time.sleep(0.5)
    for _ in range(12):
        matched = driver.execute_script(
            """
const year = arguments[0], month = arguments[1], day = arguments[2];
const popup = Array.from(document.querySelectorAll('.arco-picker-container')).find(p => (p.innerText || '').includes('年') && (p.innerText || '').includes('月'));
if (!popup) return {ok:false, reason:'no popup'};
const labels = Array.from(popup.querySelectorAll('.arco-picker-header-label')).map(x => (x.innerText || '').trim());
const currentYear = parseInt((labels[0] || '').replace('年', ''), 10);
const currentMonth = parseInt((labels[1] || '').replace('月', ''), 10);
if (currentYear === year && currentMonth === month) {
  const cell = Array.from(popup.querySelectorAll('.arco-picker-cell-in-view')).find(c => c.querySelector('.arco-picker-date-value')?.innerText.trim() === String(day));
  if (!cell) return {ok:false, reason:'day not found'};
  cell.click();
  return {ok:true, done:true};
}
const nextBtn = popup.querySelector('.arco-icon-right')?.closest('.arco-picker-header-icon');
const prevBtn = popup.querySelector('.arco-icon-left')?.closest('.arco-picker-header-icon');
if (!nextBtn || !prevBtn) return {ok:false, reason:'nav missing'};
if (currentYear < year || (currentYear === year && currentMonth < month)) nextBtn.click(); else prevBtn.click();
return {ok:true, done:false, currentYear, currentMonth};
""",
            target.year,
            target.month,
            target.day,
        )
        if matched.get("done"):
            break
        time.sleep(0.4)
    value = driver.execute_script(
        """
for (const w of Array.from(document.querySelectorAll('.arco-modal-wrapper'))) {
  if (!(w.innerText || '').includes('发布设置')) continue;
  return w.querySelector('input[placeholder="请选择日期"]')?.value || '';
}
return '';
"""
    )
    expected = target.strftime("%Y-%m-%d")
    if value != expected:
        raise RuntimeError(f"date set failed: expected {expected}, got {value}")


def choose_time(driver: webdriver.Chrome, target: dt.datetime) -> None:
    target_hour = target.strftime("%H")
    target_minute = target.strftime("%M")
    driver.execute_script(
        """
for (const w of Array.from(document.querySelectorAll('.arco-modal-wrapper'))) {
  if (!(w.innerText || '').includes('发布设置')) continue;
  const input = w.querySelector('input[placeholder="请选择时间"]');
  if (input) { input.click(); return true; }
}
return false;
"""
    )
    time.sleep(0.5)
    driver.execute_script(
        """
const hour = arguments[0], minute = arguments[1];
const wrapper = Array.from(document.querySelectorAll('.arco-modal-wrapper')).find(w => (w.innerText || '').includes('发布设置'));
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
""",
        target_hour,
        target_minute,
    )
    time.sleep(0.5)
    value = driver.execute_script(
        """
for (const w of Array.from(document.querySelectorAll('.arco-modal-wrapper'))) {
  if (!(w.innerText || '').includes('发布设置')) continue;
  return w.querySelector('input[placeholder="请选择时间"]')?.value || '';
}
return '';
"""
    )
    expected = target.strftime("%H:%M")
    if value != expected:
        raise RuntimeError(f"time set failed: expected {expected}, got {value}")


def click_confirm_publish(driver: webdriver.Chrome) -> None:
    clicked = driver.execute_script(
        """
for (const w of Array.from(document.querySelectorAll('.arco-modal-wrapper'))) {
  if (!(w.innerText || '').includes('发布设置')) continue;
  const btn = Array.from(w.querySelectorAll('button')).find(b => (b.innerText || '').trim() === '确认发布');
  if (btn) { btn.click(); return true; }
}
return false;
"""
    )
    if not clicked:
        raise RuntimeError("Could not click 确认发布")


def publish_modal_text(driver: webdriver.Chrome) -> str:
    return driver.execute_script(
        """
for (const w of Array.from(document.querySelectorAll('.arco-modal-wrapper'))) {
  if ((w.innerText || '').includes('发布设置')) return (w.innerText || '').trim();
}
return '';
"""
    )


def submit_publish_with_retry(driver: webdriver.Chrome, slot: Optional[dt.datetime], fallback_slot: Optional[dt.datetime]) -> Optional[dt.datetime]:
    current_slot = slot
    retry_budget = 5
    while True:
        click_confirm_publish(driver)
        deadline = time.time() + 30
        while time.time() < deadline:
            if "章节管理" in body_text(driver):
                return current_slot
            text = publish_modal_text(driver)
            if text and any(hint in text for hint in UPLOAD_LIMIT_HINTS):
                if retry_budget <= 0:
                    raise RuntimeError(f"publish blocked by upload limit after retries: {text}")
                retry_budget -= 1
                if current_slot is None:
                    current_slot = fallback_slot
                    if current_slot is None:
                        raise RuntimeError(f"publish blocked by upload limit and no fallback slot available: {text}")
                    toggle_schedule(driver, True)
                else:
                    current_slot = current_slot + dt.timedelta(days=1)
                choose_date(driver, current_slot)
                choose_time(driver, current_slot)
                break
            time.sleep(1)
        else:
            raise TimeoutError("Timed out waiting for publish confirmation result")


def row_for_title(driver: webdriver.Chrome, display_title: str) -> Optional[str]:
    rows = driver.execute_script(
        """
return Array.from(document.querySelectorAll('tr, .arco-table-tr')).map(r => (r.innerText || '').trim()).filter(Boolean);
"""
    )
    for row in rows:
        if display_title in row:
            return row
    return None


def publish_one(
    driver: webdriver.Chrome,
    manage_url: str,
    book_id: str,
    chapter_meta: Dict[str, object],
    immediate: bool,
    slot: Optional[dt.datetime],
    fallback_slot: Optional[dt.datetime],
) -> Dict[str, object]:
    ensure_editor_page(driver, book_id)
    fill_editor(driver, chapter_meta)
    proceed_to_publish_settings(driver)
    select_radio_by_label(driver, "否")
    toggle_schedule(driver, not immediate)
    if slot is not None:
        choose_date(driver, slot)
        choose_time(driver, slot)
    resolved_slot = submit_publish_with_retry(driver, slot, fallback_slot)
    row = row_for_title(driver, str(chapter_meta["display_title"]))
    return {
        "display_title": chapter_meta["display_title"],
        "row": row or "",
        "immediate": immediate,
        "scheduled_for": resolved_slot.strftime("%Y-%m-%d %H:%M") if resolved_slot else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fast Fanqie publish path via an attached Chrome session.")
    parser.add_argument("chapters", nargs="+", help="Chapter file paths or 第NN章 values.")
    parser.add_argument("--chapter-manage-url", required=True, help="Fanqie chapter-manage URL.")
    parser.add_argument("--project-root", default=".", help="Project root for resolving 第NN章.")
    parser.add_argument("--cdp-port", type=int, default=9222, help="CDP port for an already prepared Chrome.")
    parser.add_argument("--preferred-time", default="00:02", help="Preferred schedule time in HH:MM.")
    parser.add_argument("--min-lead-minutes", type=int, default=30, help="Minimum legal lead time.")
    parser.add_argument("--dry-run", action="store_true", help="Only compute the plan; do not touch the browser.")
    args = parser.parse_args()

    project_root = pathlib.Path(args.project_root).expanduser().resolve()
    manage_url = normalize_manage_url(args.chapter_manage_url)
    book_id = book_id_from_url(manage_url)
    chapter_paths = [resolve_chapter_path(project_root, item) for item in args.chapters]
    chapter_meta_list = [extract_fanqie_chapter.extract(path) for path in chapter_paths]

    driver = None
    try:
        driver = attach_driver(args.cdp_port)
        open_manage_page(driver, manage_url)
        queue_entries = queue_entries_from_manage(driver)
        plan = build_publish_plan(queue_entries, chapter_meta_list, args.preferred_time, args.min_lead_minutes)
        if args.dry_run:
            print(json.dumps({"book_id": book_id, "queue": queue_entries, "plan": plan}, ensure_ascii=False, indent=2))
            return 0

        results = []
        for item in plan:
            open_manage_page(driver, manage_url)
            results.append(
                publish_one(
                    driver,
                    manage_url,
                    book_id,
                    item["chapter_meta"],
                    item["immediate"],
                    item["slot"],
                    item["fallback_slot"],
                )
            )
        print(json.dumps({"book_id": book_id, "results": results}, ensure_ascii=False, indent=2))
        return 0
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
