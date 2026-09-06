"""One bounded edit pass using actual sequential model reading observations."""
import argparse
import difflib
import importlib.util
import json
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location("delivery", Path(__file__).with_name("build_delivery_checks.py"))
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)

EDITS = {
    1: [{"problem": "重复说明不将推测写上说明牌", "changes": [
        ("这问题该留在她手边，不能先落进说明牌。", "")]}],
    2: [{"problem": "母女关系无必要延迟，提前回答并清理后文对应动作", "changes": [
        ('程雪没有立刻答，先将手底下的便条往回收了一点。', '"那个人是我妈。"程雪将手底下的便条往回收了一点。'),
        ('宋棠本来想问她是不是当事人的家人，听到这里，改问："您希望我们写到什么程度？"', '宋棠问："您希望我们写到什么程度？"'),
        ('程雪看她把本子合上，才说："那个人是我妈。"\n齐叔抬头，像要立刻朝照片叫出一个称呼，张了张嘴，又把话停住了。\n宋棠也没有马上去拿说明牌。\n', '')]},
        {"problem": "借外套只撤销职业推断依据，不足以直接排除职工身份", "changes": [
        ('她将两张照片一左一右摆着，心里那条沿着职工名字往下找的路，到这里已走不通。灰蓝色的衣服确实属于车站，却未必属于穿它的人。若还拿着名单逐个对，只会把刚到手的线索又绕回去。', '她将两张照片一左一右摆着，把草纸上凭外套猜身份的那一行划掉。')]}],
    3: [{"problem": "明确齐叔记混箱子，修正前后事实冲突", "changes": [
        ('现在两个参与搬书的人说起箱子，前后就接上了。', '齐叔指着合影里的箱子说："我早上说这只漏底，说岔了，漏的是前一只。后来换了，才把大家叫到一块儿拍照。"')]},
        {"problem": "删除相认过程后的重复总结，保留人物玩笑", "changes": [
        ('他们没靠盯着脸认出彼此，倒是在托箱子、卷袖子、从窗口递衣服这些话里，越说越熟。', '')]}],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", type=Path, required=True)
    args = parser.parse_args()
    pilot = args.pilot.resolve()
    output = pilot / "heldout/edited"
    assert not output.exists(), "retain previous edit pass"
    # Wait for the actual three-chapter reading, even if only local issues change.
    reports = [pilot / f"blind/reviews/heldout-reader-H74-chapter-{n:02d}.json" for n in range(1, 4)]
    assert all(p.is_file() for p in reports)
    output.mkdir()
    records = []
    for n, source in enumerate(sorted((pilot / "heldout/raw").glob("第*章*.md")), 1):
        old = source.read_text(encoding="utf-8")
        new = old
        problems = EDITS.get(n, [])
        assert len(problems) <= 2
        for problem in problems:
            for before, after in problem["changes"]:
                assert new.count(before) == 1, before
                new = new.replace(before, after, 1)
        target = output / source.name
        target.write_text(new, encoding="utf-8")
        (output / f"chapter-{n:02d}.diff").write_text("".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile=source.name, tofile="edited/" + source.name)), encoding="utf-8")
        records.append({"chapter": n, "creative_edit_passes": 1 if problems else 0, "main_problems": problems,
                        "reader_report": str(reports[n - 1]), "reader_report_sha256": h.c.sha256_file(reports[n - 1]),
                        "original_sha256": h.c.sha256_file(source), "edited_sha256": h.c.sha256_file(target),
                        "before": h.c.wordcount.fanqie_length(old), "after": h.c.wordcount.fanqie_length(new),
                        "scope": "Chapter 2 moves a within-chapter identity disclosure and corrects an inference, not purely word deletion. Core plot and ending preserved subject to fresh reading."})
    h.save(output / "edit-record.json", records)
    print(json.dumps([{k: r[k] for k in ("chapter", "creative_edit_passes", "after")} for r in records]))


if __name__ == "__main__":
    main()
