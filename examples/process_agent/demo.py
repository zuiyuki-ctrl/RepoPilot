"""Deterministic task-list protocol fixture, NOT a general coding agent. Stdlib only."""
import argparse
import json
from pathlib import Path
import time

FIX = '''def list_tasks(tasks: list[dict], *, status: str | None = None,
               limit: int = 20, offset: int = 0) -> list[dict]:
    if limit < 1 or offset < 0:
        raise ValueError("invalid pagination")
    filtered = tasks if status is None else [task for task in tasks if task["status"] == status]
    return filtered[offset:offset + limit]
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['fix', 'noop', 'wrong-id', 'invalid-json', 'missing',
                                        'nonzero', 'timeout', 'tamper', 'outside'], default='noop')
    args = parser.parse_args()
    request = json.loads(Path('/input/request.json').read_text(encoding='utf-8'))
    if args.mode == 'timeout':
        time.sleep(7200)
    if args.mode == 'fix':
        if request['case_id'] != 'task-list' or request['editable_files'] != ['task_list.py']:
            raise ValueError('This fixture only supports task-list')
        Path('/workspace/task_list.py').write_text(FIX, encoding='utf-8')
    if args.mode == 'tamper':
        Path('/workspace/tests/test_task_list.py').write_text('def test_fake(): pass\n', encoding='utf-8')
    if args.mode == 'outside':
        Path('/workspace/outside.txt').write_text('out of scope', encoding='utf-8')
    if args.mode == 'missing':
        return
    output = Path('/output/result.json')
    if args.mode == 'invalid-json':
        output.write_text('{broken', encoding='utf-8')
        return
    result = dict(protocol_version=1, run_id=request['run_id'], agent=request['agent'],
                  execution_status='completed')
    if args.mode == 'wrong-id':
        result['run_id'] = '00000000-0000-0000-0000-000000000000'
    output.write_text(json.dumps(result), encoding='utf-8')
    print('Deterministic protocol fixture finished; only the platform evaluates correctness.')
    if args.mode == 'nonzero':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
