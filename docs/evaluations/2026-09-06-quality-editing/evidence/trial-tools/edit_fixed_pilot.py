"""One bounded editing pass based on reader-a's actual prose observations."""
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PILOT = Path(__file__).with_name("pilot-location.txt").read_text().strip()
book = Path(PILOT) / "fixed"
spec = importlib.util.spec_from_file_location("wc", ROOT / "skills/_shared/scripts/wordcount_core.py")
wc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wc)

edits = {
    1: [(
        '"你跟我说句准话，到底能不能修？"\n"能修。需要的东西我认得，下午能取。但你要我保证现在就凉，我做不到。"\n"下午你过来，三两下修完？"\n"拿到配件我就来。修完还得看它能不能稳稳降温，不能听见响了就算完。"',
        '"你跟我说句准话，到底能不能修？"\n"能修，拿到配件我就来。修完得试稳了，不能听见响就算完。"')],
    2: [(
        '小满把何桂香比的大小记在眼里，对照柜内的空处看了一遍。箱子盖好能顺着放进去，不必压到食材，也不用让陈望把别的东西搬出去。她告诉何桂香可以，才站起来。',
        '小满看过柜里的空处，朝何桂香点了点头。'), (
        '她把工具包提到肩上，又看了一眼手机里的确认记录。取件的时间定下来了，鱼也放好了。离下午还有一阵，她终于可以先把自己铺子的门完全推上去。',
        '她把工具包提到肩上，回去把自己铺子的门完全推了上去。')],
    3: [(
        '何桂香把手机搁回台上，听着冷柜的动静，又问了一次大概还要多久。小满告诉她要看降温情况，到了合适温度还要观察，不能只算过去几分钟。她把测温的东西摆好，也没有让何桂香反复掀盖伸手试。\n何桂香本来要搬凳子往柜边坐，听她说完，干脆把凳子放远一些。',
        '何桂香把手机搁回台上。小满摆好测温的东西，提醒她别反复掀盖。何桂香搬来凳子，看了一眼柜盖，又把凳子放远一些。'), (
        '"早上一百，现在两百，三百齐了。存放那三十，我已经另外付给他。"',
        '"尾款两百，给你。"')]
}

results = []
for n, pairs in edits.items():
    source = next(p for p in (book / "raw").glob("*.md") if p.name.startswith(f"第{n:03d}章"))
    old = source.read_text(encoding="utf-8")
    new = old
    for before, after in pairs:
        assert new.count(before) == 1, (n, before)
        new = new.replace(before, after, 1)
    target = book / "edited" / source.name
    assert not target.exists(), "preserve previous editing attempts"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new, encoding="utf-8")
    report = json.loads((Path(PILOT) / f"blind/reviews/reader-a-R31-chapter-{n:02d}.json").read_text(encoding="utf-8"))
    protected = report["interest"]["protected_original"]["anchor"]
    assert protected in new
    diff = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile="original", tofile="edited"))
    (book / "edited" / f"chapter-{n:02d}.diff").write_text(diff, encoding="utf-8")
    results.append({"chapter": n, "edits": pairs, "before": wc.fanqie_length(old), "after": wc.fanqie_length(new),
                    "protected_anchor": protected, "original_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "edited_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    "reader_source": f"reader-a-R31-chapter-{n:02d}.json", "creative_edit_passes": 1})
(book / "edited/edit-record.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps([{k: r[k] for k in ("chapter", "before", "after")} for r in results], ensure_ascii=False))
