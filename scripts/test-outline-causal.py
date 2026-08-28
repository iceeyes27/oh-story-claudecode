#!/usr/bin/env python3
"""test-outline-causal.py — check-outline-causal.py 回归测试"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass

SCRIPT = Path(__file__).resolve().parent.parent / "skills/story-write/scripts/check-outline-causal.py"

_pass = 0
_fail = 0


def ok(name, cond, detail=""):
    global _pass, _fail
    if cond:
        print(f"  [PASS] {name}")
        _pass += 1
    else:
        print(f"  [FAIL] {name}  {detail}")
        _fail += 1


def make_book(chapters: dict[int, str]) -> Path:
    d = Path(tempfile.mkdtemp(prefix="oc-"))
    (d / "大纲").mkdir()
    for num, body in chapters.items():
        (d / "大纲" / f"细纲_第{num:03d}章.md").write_text(body, encoding="utf-8")
    return d


def causal(cause, effect="下一章用到", known="读者已知任务"):
    return (f"#### 因果链\n- 前因：{cause}\n- 后果指向：{effect}\n- 读者已知：{known}\n")


def run(book: Path):
    r = subprocess.run([sys.executable, str(SCRIPT), str(book), "--json"],
                       capture_output=True, text=True, encoding="utf-8")
    import json
    data = json.loads(r.stdout) if r.stdout.strip() else {}
    return r.returncode, data


# 1) 正常：前因指向更早章 → 无 blocking，exit 0
b = make_book({
    1: "# 细纲\n" + causal("开篇无前因"),
    2: "# 细纲\n" + causal("第1章：主角接下涨粉任务"),
    3: "# 细纲\n" + causal("第2章：MV 拍完发布"),
})
code, data = run(b)
ok("正常因果链无 blocking", code == 0 and data.get("blocking") == 0, f"code={code} data={data}")

# 2) 前因指向未来章 → blocking exit 1
b = make_book({
    1: "# 细纲\n" + causal("开篇无前因"),
    2: "# 细纲\n" + causal("第5章：还没发生的事"),
    3: "# 细纲\n" + causal("第2章：ok"),
    4: "# 细纲\n" + causal("第3章：ok"),
    5: "# 细纲\n" + causal("第4章：ok"),
})
code, data = run(b)
ok("前因指向未来章 blocking", code == 1 and any(f["code"] == "cause-future" for f in data["findings"]),
   f"code={code}")

# 3) 前因指向不存在的章 → blocking
b = make_book({
    1: "# 细纲\n" + causal("开篇无前因"),
    2: "# 细纲\n" + causal("第9章：不存在的章"),  # 9 > 2 → 先判 future
    3: "# 细纲\n" + causal("第8章：不存在且不早于? 8>3 future"),
})
# 用一个 早于本章但不存在的洞：第4章前因指第3章(存在)ok；构造 gap：章号 1,2,5，第5章前因指第3章(不存在)
b2 = make_book({
    1: "# 细纲\n" + causal("开篇无前因"),
    2: "# 细纲\n" + causal("第1章：ok"),
    5: "# 细纲\n" + causal("第3章：这章不存在"),
})
code, data = run(b2)
ok("前因指向不存在的更早章 blocking",
   code == 1 and any(f["code"] == "cause-missing" for f in data["findings"]), f"code={code} data={data}")

# 4) 缺字段 → advisory，exit 0
b = make_book({
    1: "# 细纲\n- 阶段位置：开篇\n",  # 完全没有因果字段
})
code, data = run(b)
ok("缺因果字段仅 advisory", code == 0 and any(f["code"] == "missing-field" for f in data["findings"]),
   f"code={code}")

# 5) 占位 → advisory
b = make_book({
    1: "# 细纲\n- 前因：待补充\n- 后果指向：TBD\n- 读者已知：___\n",
})
code, data = run(b)
ok("占位因果字段仅 advisory",
   code == 0 and any(f["code"] == "placeholder-field" for f in data["findings"]), f"code={code}")

# 6) 缺参数 → exit 2
r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, encoding="utf-8")
ok("缺参数退出码 2", r.returncode == 2)

# 7) 不存在目录 → exit 2
r = subprocess.run([sys.executable, str(SCRIPT), str(Path(tempfile.gettempdir()) / "nope-xyz-123")],
                   capture_output=True, text=True, encoding="utf-8")
ok("不存在目录退出码 2", r.returncode == 2)

print(f"\n共通过 {_pass} 项，失败 {_fail} 项。")
sys.exit(1 if _fail else 0)
