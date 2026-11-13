"""Worker-only baseline and one tool-disabled model turn, under durable ownership."""
import logging
from ..schemas.case_draft import DraftSelection
from ..rag.model_observation import ModelObservation
from . import case_draft_service as store, case_draft_source as source, platform_artifacts as artifacts
from . import platform_test_collector as collector
from .catalog_validation_service import require_image
from .platform_container import remove_owned
from .test_report_parser import read_test_report

logger = logging.getLogger(__name__)
REASONS = {
    'baseline_timed_out': '基线运行超过 120 秒',
    'test_report_missing_or_invalid': '未得到有效 JUnit 报告，测试可能无法启动或收集',
    'required_tests_missing': '声明的验收测试未全部收集，请核对 classname 和参数化测试名称',
    'tests_errored_or_skipped': '出现测试收集错误、运行错误或跳过项，不能视为预期断言失败',
    'baseline_all_passed': '原始提交的测试全部通过，不是已复现的 bug_fix 题',
    'test_process_failed': 'pytest 未以有效的失败测试状态退出',
    'baseline_failures_mismatch': '实际失败项与声明不一致；请查看缺失失败项和额外失败项',
}


def check_baseline(claim, selection, files):
    require_image(selection.test_image)
    directory = artifacts.run_directory(claim['id'])
    directory.mkdir(exist_ok=False)
    artifacts.copy_files(files, directory / 'original')
    artifacts.copy_files({p: files[p] for p in selection.protected_test_files}, directory / 'authority')
    (directory / 'authority' / 'pytest.ini').write_bytes(b'[pytest]\n')
    output = directory / 'baseline-results'
    output.mkdir()
    output.chmod(0o777)
    result = collector.run_authority(claim['id'], 'baseline', image=selection.test_image,
        snapshot=directory / 'original', authority=directory / 'authority', output=output,
        tests=selection.protected_test_files)
    report = read_test_report(output / 'junit.xml')
    checked = collector.assess_baseline(report, exit_code=result['exit_code'], timed_out=result['timed_out'],
        rule=selection.acceptance, task_type='bug_fix', exact_failures=True)
    return {**checked, 'test_report': report, 'process': result,
            'snapshot_sha256': claim['preview']['snapshot_sha256'],
            'runner_sha256': collector.runner_fingerprint(), 'image': selection.test_image}


def execute_draft(claim, *, allow_model=False):
    result = baseline = observation_payload = error = None
    cleanup_confirmed = True
    stage = 'preflight'
    observation = ModelObservation()
    attempted_baseline = False
    try:
        if not allow_model:
            raise source.DraftInputError('Worker 未显式开启 --allow-model，未调用模型')
        if claim['preview'].get('authorization') != dict(allow_model=True, allow_baseline_tests=True):
            raise source.DraftInputError('缺少针对预览内容的显式授权，未运行测试或调用模型')
        selection = DraftSelection.model_validate(claim['selection'])
        _, files = source.repository_files(selection.repository_id, selection.repository_commit)
        preview = source.preview(selection, files=files)
        if preview['preview_sha256'] != claim['preview']['preview_sha256']:
            raise source.DraftInputError('预览后文件、模型配置或校验实现发生变化；请重新预览并授权')
        stage, attempted_baseline = 'baseline', True
        baseline = check_baseline(claim, selection, files)
        if not baseline['passed']:
            error = dict(reason=baseline['reason'], message=REASONS[baseline['reason']])
        else:
            store.progress(claim, status='generating', baseline=baseline)
            stage = 'model'
            if source.model_identity() != preview['model']:
                raise source.DraftInputError('模型配置变化，请重新预览授权')
            result = source.generate_text(selection, preview['contents'], observation).model_dump(mode='json')
            observation_payload = observation.to_payload()
    except Exception as exc:
        logger.warning('Draft failed id=%s stage=%s error=%s', claim['id'], stage, type(exc).__name__)
        error = dict(reason=f'{stage}_failed', message=str(exc) if isinstance(exc, source.DraftInputError) else (
            '基线无法运行，请检查 Docker、本地完整镜像 ID 和 pytest 环境' if stage == 'baseline' else
            '模型调用或草稿格式校验失败，请检查配置或重新生成' if stage == 'model' else '草稿输入预检查失败'),
            error_type=type(exc).__name__)
        if stage == 'baseline' and str(exc) in ('local_image_unavailable', 'Required local image unavailable'):
            error.update(reason='local_image_unavailable', message='本机没有指定的不可变测试镜像；请核对 docker image inspect 的完整 Id')
        if observation.request_attempted:
            observation_payload = observation.to_payload(exc)
    finally:
        if attempted_baseline:
            try:
                remove_owned(claim['id'], 'baseline')
            except Exception:
                cleanup_confirmed = False
                error = dict(reason='cleanup_unconfirmed', message='容器清理未确认，必须停止 worker 并显式恢复')
        store.settle(claim, result=result, baseline=baseline, observation=observation_payload,
                     error=error, cleanup_confirmed=cleanup_confirmed)
