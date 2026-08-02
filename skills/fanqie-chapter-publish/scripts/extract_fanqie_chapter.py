#!/usr/bin/env python3
import argparse
import json
import pathlib
import re
import sys
from typing import Dict, List, Optional, Tuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


HEADER_RE = re.compile(r"^\s*#{1,6}\s*第[一二三四五六七八九十百千万零〇\d]+章[：:\s]*(.*)\s*$")
FILENAME_RE = re.compile(r"第0*(\d+)章[_\s-]*(.+?)\.md$")

EVAL_JS_TEMPLATE = """(() => {
  const editor = document.querySelector('.ProseMirror');
  if (!editor) {
    return JSON.stringify({ ok: false, error: 'no .ProseMirror editor on page' });
  }
  const paragraphs = %s;
  const escape = s => s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  editor.innerHTML = paragraphs.map(p => '<p>' + escape(p) + '</p>').join('');
  editor.dispatchEvent(new Event('input', { bubbles: true }));
  const got = [...editor.querySelectorAll('p')]
    .map(p => (p.innerText || '').trim())
    .filter(Boolean);
  return JSON.stringify({
    ok: true,
    paragraph_count: got.length,
    char_count: got.join('\\n').length,
  });
})()"""


def eval_js_for(body_lines: List[str]) -> str:
    return EVAL_JS_TEMPLATE % json.dumps(body_lines, ensure_ascii=False)


def strip_bom(text: str) -> str:
    return text[1:] if text.startswith("\ufeff") else text


def normalize_lines(text: str) -> List[str]:
    lines = [line.rstrip() for line in strip_bom(text).splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def infer_from_filename(path: pathlib.Path) -> Tuple[Optional[int], Optional[str]]:
    match = FILENAME_RE.search(path.name)
    if not match:
        return None, None
    return int(match.group(1)), match.group(2).strip()


def extract(path: pathlib.Path) -> Dict[str, object]:
    raw = path.read_text(encoding="utf-8")
    lines = normalize_lines(raw)
    chapter_no, title = infer_from_filename(path)

    if lines:
        header_match = HEADER_RE.match(lines[0])
        if header_match:
            inferred_title = header_match.group(1).strip()
            if inferred_title:
                title = inferred_title
            lines = lines[1:]
            while lines and not lines[0].strip():
                lines.pop(0)

    body_lines = [line.strip() for line in lines if line.strip()]
    if chapter_no is None:
        chapter_match = re.search(r"第0*(\d+)章", raw)
        if chapter_match:
            chapter_no = int(chapter_match.group(1))

    if not title:
        raise ValueError(f"Could not infer title from {path}")
    if chapter_no is None:
        raise ValueError(f"Could not infer chapter number from {path}")
    if not body_lines:
        raise ValueError(f"No non-empty body paragraphs found in {path}")

    body = "\n".join(body_lines)
    return {
        "source_path": str(path),
        "chapter_no": chapter_no,
        "title": title,
        "display_title": f"第{chapter_no}章 {title}",
        "paragraph_count": len(body_lines),
        "char_count": len(body),
        "body": body,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract Fanqie-ready chapter metadata and body from a local markdown chapter file."
    )
    parser.add_argument("chapter_path", help="Path to a local chapter markdown file")
    parser.add_argument(
        "--field",
        choices=["chapter_no", "title", "display_title", "paragraph_count", "char_count", "body"],
        help="Print only one field",
    )
    parser.add_argument(
        "--eval-js",
        action="store_true",
        help="Print a self-verifying JS snippet that writes the body into the "
        "Fanqie .ProseMirror editor; pipe it to `agent-browser eval --stdin`.",
    )
    args = parser.parse_args()

    path = pathlib.Path(args.chapter_path).expanduser().resolve()
    if not path.exists():
        print(f"Missing file: {path}", file=sys.stderr)
        return 1

    try:
        payload = extract(path)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.eval_js:
        print(eval_js_for(payload["body"].split("\n")))
    elif args.field:
        print(payload[args.field])
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
