#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Dict, List

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


DATETIME_FMT = "%Y-%m-%d %H:%M"
DATE_FMT = "%Y-%m-%d"
TIME_FMT = "%H:%M"


def parse_dt(value: str) -> dt.datetime:
    return dt.datetime.strptime(value, DATETIME_FMT)


def parse_time(value: str) -> dt.time:
    return dt.datetime.strptime(value, TIME_FMT).time()


def read_scheduled_file(path_arg: str) -> List[dt.datetime]:
    path = pathlib.Path(path_arg).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError("missing scheduled file: %s" % path)
    items: List[dt.datetime] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        items.append(parse_dt(line))
    return items


def next_slot(
    scheduled: List[dt.datetime],
    preferred_time: dt.time,
    cadence_days: int,
    min_lead_minutes: int,
    now: dt.datetime,
) -> dt.datetime:
    earliest = now + dt.timedelta(minutes=min_lead_minutes)
    if scheduled:
        candidate = max(scheduled) + dt.timedelta(days=cadence_days)
    else:
        candidate = earliest.replace(
            hour=preferred_time.hour,
            minute=preferred_time.minute,
            second=0,
            microsecond=0,
        )
        if candidate < earliest:
            candidate += dt.timedelta(days=cadence_days)

    while candidate < earliest:
        candidate += dt.timedelta(days=cadence_days)
    return candidate


def payload_for(slot: dt.datetime, earliest: dt.datetime) -> Dict[str, object]:
    return {
        "scheduled_for": slot.strftime(DATETIME_FMT),
        "date": slot.strftime(DATE_FMT),
        "time": slot.strftime(TIME_FMT),
        "meets_min_lead": slot >= earliest,
        "min_valid_time": earliest.strftime(DATETIME_FMT),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Suggest the next Fanqie scheduled publish time."
    )
    parser.add_argument(
        "--scheduled",
        action="append",
        default=[],
        help="Existing scheduled publish time in YYYY-MM-DD HH:MM format. Repeatable.",
    )
    parser.add_argument(
        "--scheduled-file",
        action="append",
        default=[],
        help="File containing one scheduled publish time per line in YYYY-MM-DD HH:MM format. Repeatable.",
    )
    parser.add_argument(
        "--preferred-time",
        default="09:01",
        help="Preferred daily publish time in HH:MM format. Defaults to 09:01.",
    )
    parser.add_argument(
        "--cadence-days",
        type=int,
        default=1,
        help="How many days to move forward each slot. Defaults to 1.",
    )
    parser.add_argument(
        "--min-lead-minutes",
        type=int,
        default=30,
        help="Minimum minutes after now that Fanqie will accept. Defaults to 30.",
    )
    parser.add_argument(
        "--now",
        help="Override current time in YYYY-MM-DD HH:MM format.",
    )
    args = parser.parse_args()

    try:
        scheduled = [parse_dt(item) for item in args.scheduled]
        for file_arg in args.scheduled_file:
            scheduled.extend(read_scheduled_file(file_arg))
        preferred_time = parse_time(args.preferred_time)
        now = parse_dt(args.now) if args.now else dt.datetime.now()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    earliest = now + dt.timedelta(minutes=args.min_lead_minutes)
    slot = next_slot(
        scheduled=scheduled,
        preferred_time=preferred_time,
        cadence_days=args.cadence_days,
        min_lead_minutes=args.min_lead_minutes,
        now=now,
    )
    print(json.dumps(payload_for(slot, earliest), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
