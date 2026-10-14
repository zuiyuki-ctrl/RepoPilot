"""模块开发入口；请求 JSON 必须由可信平台准备器产生，不接收 Agent 自报成绩。"""
import argparse
from pathlib import Path
from uuid import UUID


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--repository-id', type=UUID, required=True)
    parser.add_argument('--task-id', type=UUID, required=True)
    parser.add_argument('--creation-key', required=True)
    args = parser.parse_args()
    from backend.app.schemas.platform_run import AgentRunRequest
    from backend.app.services.platform_run_service import create_run
    from backend.app.services.run_control_service import enqueue_native
    request = AgentRunRequest.model_validate_json(args.request.read_text(encoding='utf-8'))
    if request.agent.adapter != 'native':
        parser.error('This development entry supports native only')
    run = create_run(request, repository_id=args.repository_id,
                     legacy_task_id=args.task_id, creation_key=args.creation_key)
    enqueue_native(run.id)
    print(f'Queued run: {run.id}; no model called. Open /live/runs/{run.id}')


if __name__ == '__main__':
    main()
