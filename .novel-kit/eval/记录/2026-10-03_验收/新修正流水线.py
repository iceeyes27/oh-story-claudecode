"""本轮写手修正与独立修后盲读，分阶段冻结，不覆写历史。"""
from pathlib import Path
import datetime
import hashlib
import importlib.util
import json
import shutil

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

runner = module('runner', BASE / '继续执行器.py')
evidence = module('evidence', ROOT / '.novel-kit/scripts/eval_evidence.py')

def record(value):
    with (BASE / '本轮修正/执行记录.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + '\n')
    print(json.dumps(value, ensure_ascii=False), flush=True)

def main():
    jobs = json.loads((BASE / '本轮修正/修正任务.json').read_text(encoding='utf-8'))['jobs']
    for job in jobs:
        result = runner.execute(job, 3)
        record(result)
        if result.get('status') not in ['完成', '已有报告未改']:
            continue
        sid = job['sample']
        body = Path(job['output'])
        frozen = BASE / '本轮修正/冻结候选' / (sid + '.md')
        frozen.parent.mkdir(parents=True, exist_ok=True)
        if not frozen.exists():
            frozen.write_bytes(body.read_bytes())
            frozen.chmod(0o444)
        elif frozen.read_bytes() != body.read_bytes():
            raise RuntimeError('修正副本漂移，不覆盖冻结：' + sid)
        common = [BASE / '输入/.novel-kit/roles/copy-editor.md',
                  BASE / '输入/.novel-kit/standards/语文规格.md',
                  BASE / '输入/.novel-kit/workflows/review-loop.md',
                  BASE / '输入/.novel-kit/eval/文风样本.md', frozen]
        output = BASE / '本轮修正/outputs' / (sid + '_新修正盲读.md')
        prompt = ('你是novel-kit工具验收中的独立copy-editor。仅完整阅读以下冻结文件：\n'
                  + '\n'.join(str(p) for p in common)
                  + '\n以指定角色规则独立三遍通读完整候选，只按现有原文检查。不要读取任何答案、作者意图、修正意见、原稿或其他审阅。缺前文只列供给待核，不定正文错误。没有问题不凑数。完整报告须包含阅读范围、理解摘要、问题及原文依据、前文不足和保留项。只创建新报告 '
                  + str(output) + '；不改任何输入或真实小说。报告简体，原文引用准确；模型ID未提供记unknown。你已经处于独立新会话，本次直接承担指定审阅角色，不再委派。其他代理在工作，不回退他人修改。')
        reader = {'id': sid + '_new_repair_review', 'sample': sid, 'role': 'copy-editor',
                  'attempt': 1, 'phase': 'repair_review', 'dataset': 'new_repair',
                  'allowed_inputs': [str(p) for p in common],
                  'input_hashes': {str(p): runner.digest(p) for p in common},
                  'prompt': prompt, 'output': str(output)}
        destination = BASE / '工具证据' / ('new_repair_' + sid)
        config_path = BASE / '本轮修正' / (sid + '_修后开读配置.json')
        input_rows, identifiers = [], {}
        for path in job['allowed_inputs'] + reader['allowed_inputs']:
            if path not in identifiers:
                identifier = 'i' + str(len(identifiers) + 1)
                identifiers[path] = identifier
                kind = 'role' if '/roles/' in path else 'standard' if '/standards/' in path or '/workflows/' in path else 'style' if Path(path).name == '文风样本.md' else 'prose'
                input_rows.append({'id': identifier, 'path': path, 'kind': kind})
        input_rows.append({'id': 'answer_' + sid, 'path': str(ROOT / '.novel-kit/eval/答案' / (sid + '.json')), 'kind': 'answer', 'audience': 'coordinator'})
        inputs_manifest = BASE / '工具证据/new_repair_write/manifest.json'
        input_rows.append({'id': 'writer_opening', 'path': str(inputs_manifest), 'kind': 'execution_evidence', 'audience': 'coordinator'})
        runs = []
        for item in [job, reader]:
            runs.append({'id': item['id'], 'sample': sid, 'role': item['role'], 'attempt': 1,
                         'phase': item['phase'], 'context': [identifiers[p] for p in item['allowed_inputs']],
                         'prompt': item['prompt'], 'independent_context': True,
                         'output': 'outputs/' + Path(item['output']).name})
        config = {'schema_version': 1, 'scope': 'full', 'label': 'new_repair_' + sid,
                  'inputs': input_rows, 'runs': runs,
                  'note': '写手开读前冻结在new_repair_write；本清单在写手完成后、独立盲读开读前冻结新副本，并绑定原写手清单。不是用修后冻结补造修正前历史。'}
        if not destination.exists():
            config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            evidence.freeze(config_path, destination)
            (BASE / '本轮修正' / (sid + '_盲读任务.json')).write_text(json.dumps(reader, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        result = runner.execute(reader, 3)
        record(result)
        for item in [job, reader]:
            origin = Path(item['output'])
            target = destination / 'outputs' / origin.name
            if origin.is_file() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(origin, target)
                target.chmod(0o444)
        target = BASE / '工具证据/new_repair_write/outputs' / body.name
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(body, target)
            target.chmod(0o444)
    record({'event': '本轮新修正流水线结束', 'utc': runner.utc(), 'note': '仍须逐项判分和完整性核对。'})

if __name__ == '__main__':
    main()
