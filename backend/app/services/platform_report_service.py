"""Read stored Day 3 evidence, never recompute from the current repository."""
from sqlalchemy import select
from ..db.session import SessionLocal
from ..db.models import PlatformRun, RunWork, RunEvaluation
from . import platform_artifacts as artifacts
import hashlib


def get_report(run_id):
    with SessionLocal() as session:
        run = session.get(PlatformRun, run_id)
        if run is None:
            return None
        evaluation = session.scalar(select(RunEvaluation).where(RunEvaluation.run_id == run_id)
                                    .order_by(RunEvaluation.created_at.desc(), RunEvaluation.id.desc()).limit(1))
        work = session.get(RunWork, run_id)
        state = work.state if work else {}
        evidence = evaluation.evidence if evaluation else {}
        process = state.get('process_execution', {})
        result = dict(source='live', run_id=str(run_id), execution_status=run.execution_status,
            evaluation_outcome=run.evaluation_outcome, reason=evaluation.reason if evaluation else None,
            baseline_test=state.get('baseline_test'), final_test=evidence.get('final_test'),
            final_snapshot_hash=evidence.get('final_snapshot_hash'), diff=None, diff_truncated=False,
            changed_files=[], artifact_status='not_recorded',
            process={key: process.get(key) for key in ('exit_code', 'timed_out', 'protocol_error',
                                                      'stdout', 'stderr', 'stdout_truncated', 'stderr_truncated')})
        result['process']['trace_status'] = process.get('trace', {}).get('status', 'unsupported')
    # Expose parsed counts, hash and binding, not arbitrary XML or file paths.
    for key in ('baseline_test', 'final_test'):
        test = result[key]
        if test:
            report = test.get('test_report') or {}
            result[key] = {name: test.get(name) for name in ('test_run_id', 'snapshot_hash', 'exit_code', 'timed_out')}
            result[key]['report'] = {name: report.get(name) for name in ('status', 'sha256', 'counts')}
    if evidence.get('diff_sha256'):
        try:
            diff = artifacts.decode_json(artifacts.read_bytes(artifacts.run_directory(run_id) / 'diff.json', 25_000_000))
            if hashlib.sha256(diff['diff'].encode()).hexdigest() != evidence['diff_sha256']:
                raise ValueError('Stored diff hash differs')
            result.update(diff=diff['diff'][:50_000], diff_truncated=len(diff['diff']) > 50_000,
                          changed_files=diff['changed_files'], artifact_status='recorded')
        except (OSError, ValueError, KeyError):
            result['artifact_status'] = 'missing_or_invalid'
    return result
