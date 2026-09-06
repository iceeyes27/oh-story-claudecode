#!/usr/bin/env python3
import argparse
import json
import pathlib
import sys
from typing import Dict, List, Optional

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

import extract_fanqie_chapter
import extract_fanqie_queue
import locate_fanqie_chapter
import next_fanqie_schedule


def resolve_chapter_path(
    chapter_path: Optional[str],
    chapter_no: Optional[str],
    project_root: pathlib.Path,
) -> pathlib.Path:
    if chapter_path:
        path = pathlib.Path(chapter_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError("missing chapter file: %s" % path)
        return path

    if not chapter_no:
        raise ValueError("provide --chapter-path or --chapter-no")

    normalized_no = locate_fanqie_chapter.normalize_no(chapter_no)
    result = locate_fanqie_chapter.render(
        project_root,
        normalized_no,
        locate_fanqie_chapter.collect_candidates(project_root, normalized_no),
    )
    status = result["status"]
    if status == "unique":
        return (project_root / result["path"]).resolve()
    if status == "multiple":
        raise ValueError(
            "multiple chapter files found: %s" % " | ".join(result["candidates"])
        )
    raise ValueError("chapter not found for 第%d章" % normalized_no)


def load_queue(queue_file: Optional[str]) -> Dict[str, object]:
    if not queue_file:
        return {"count": 0, "entries": [], "times": []}
    try:
        text = extract_fanqie_queue.read_text(queue_file)
    except FileNotFoundError as exc:
        return {
            "count": 0,
            "entries": [],
            "times": [],
            "warning": "queue file unavailable, continuing without schedule data: %s" % exc,
        }
    lines = extract_fanqie_queue.normalize_lines(text)
    entries = extract_fanqie_queue.extract_entries(lines)
    return {
        "count": len(entries),
        "entries": entries,
        "times": [item["publish_time"] for item in entries],
    }


def schedule_payload(
    queue_times: List[str],
    preferred_time: str,
    cadence_days: int,
    min_lead_minutes: int,
    now: Optional[str],
) -> Optional[Dict[str, object]]:
    if not queue_times:
        return None
    scheduled = [next_fanqie_schedule.parse_dt(item) for item in queue_times]
    now_dt = (
        next_fanqie_schedule.parse_dt(now)
        if now
        else next_fanqie_schedule.dt.datetime.now()
    )
    preferred = next_fanqie_schedule.parse_time(preferred_time)
    earliest = now_dt + next_fanqie_schedule.dt.timedelta(minutes=min_lead_minutes)
    slot = next_fanqie_schedule.next_slot(
        scheduled=scheduled,
        preferred_time=preferred,
        cadence_days=cadence_days,
        min_lead_minutes=min_lead_minutes,
        now=now_dt,
    )
    return next_fanqie_schedule.payload_for(slot, earliest)


def build_checklist(
    chapter_meta: Dict[str, object],
    chapter_manage_url: Optional[str],
    queue: Dict[str, object],
    schedule: Optional[Dict[str, object]],
) -> List[str]:
    checklist = [
        "Open Fanqie chapter-manage page%s."
        % (" at %s" % chapter_manage_url if chapter_manage_url else ""),
        "Create or open the draft for %s." % chapter_meta["display_title"],
        "Fill chapter number with %s." % chapter_meta["chapter_no"],
        "Fill title with %s." % chapter_meta["title"],
        "Write normalized body with %s paragraphs and save draft."
        % chapter_meta["paragraph_count"],
        "Set 是否使用AI to 否.",
    ]
    if queue["count"]:
        checklist.append(
            "Current queue has %s pending/review chapter times; prefer scheduled publish."
            % queue["count"]
        )
    if schedule:
        checklist.append(
            "If immediate publish is blocked, set 定时发布 to %s."
            % schedule["scheduled_for"]
        )
    checklist.append("Return to chapter list and verify title, status, and publish time.")
    return checklist


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a one-shot local checklist for Fanqie chapter publishing."
    )
    parser.add_argument("--chapter-path", help="Absolute or relative local chapter file path.")
    parser.add_argument("--chapter-no", help="Target chapter number, for example 52 or 第52章.")
    parser.add_argument(
        "--project-root",
        default=".",
        help="Project root used when resolving --chapter-no. Defaults to current directory.",
    )
    parser.add_argument(
        "--queue-file",
        help="Text file captured from Fanqie chapter-manage page body text.",
    )
    parser.add_argument(
        "--chapter-manage-url",
        help="Optional Fanqie chapter-manage URL for the target work.",
    )
    parser.add_argument(
        "--preferred-time",
        default="09:01",
        help="Preferred publish time in HH:MM. Defaults to 09:01.",
    )
    parser.add_argument(
        "--cadence-days",
        type=int,
        default=1,
        help="Cadence in days when deriving the next schedule. Defaults to 1.",
    )
    parser.add_argument(
        "--min-lead-minutes",
        type=int,
        default=30,
        help="Minimum lead time in minutes for a legal Fanqie schedule. Defaults to 30.",
    )
    parser.add_argument(
        "--now",
        help="Override current time in YYYY-MM-DD HH:MM for deterministic scheduling.",
    )
    args = parser.parse_args()

    try:
        project_root = pathlib.Path(args.project_root).expanduser().resolve()
        chapter_path = resolve_chapter_path(args.chapter_path, args.chapter_no, project_root)
        chapter_meta = extract_fanqie_chapter.extract(chapter_path)
        queue = load_queue(args.queue_file)
        schedule = schedule_payload(
            queue_times=queue["times"],
            preferred_time=args.preferred_time,
            cadence_days=args.cadence_days,
            min_lead_minutes=args.min_lead_minutes,
            now=args.now,
        )
        payload = {
            "chapter": chapter_meta,
            "chapter_manage_url": args.chapter_manage_url or "",
            "queue": queue,
            "suggested_schedule": schedule,
            "checklist": build_checklist(
                chapter_meta=chapter_meta,
                chapter_manage_url=args.chapter_manage_url,
                queue=queue,
                schedule=schedule,
            ),
        }
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
