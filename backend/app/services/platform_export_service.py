"""Portable comparison report from one DB snapshot, never current workspace files."""
from datetime import datetime, timezone
import json
from sqlalchemy import select, text
from ..db.session import SessionLocal
from ..db.models.platform_experiment import PlatformExperiment, ExperimentReview
from .platform_comparison_service import get_comparison
from .experiment_contract_service import digest


def export_report(experiment_id):
    with SessionLocal() as session:
        session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        comparison = get_comparison(experiment_id, session=session)
        if comparison is None:
            return None
        experiment = session.get(PlatformExperiment, experiment_id)
        # Each embedded review carries its original snapshot, never a re-created old decision.
        reviews = list(session.scalars(select(ExperimentReview).where(
            ExperimentReview.experiment_id == experiment_id).order_by(ExperimentReview.created_at, ExperimentReview.id)))
        report = dict(schema_version=1, report_type='experiment_comparison_snapshot',
            exported_at=datetime.now(timezone.utc).isoformat(), experiment_id=str(experiment_id),
            manifest=experiment.manifest, manifest_sha256=experiment.manifest_sha256,
            comparison=comparison,
            reviews=[dict(id=str(row.id), reviewer=row.reviewer, action=row.action, rationale=row.rationale,
                created_at=row.created_at.isoformat(), comparison_sha256=row.comparison_sha256,
                matches_current_comparison=row.comparison_sha256 == comparison['comparison_sha256'],
                snapshot=row.snapshot) for row in reviews],
            limitations=['Point-in-time database snapshot; in-progress runs may later change',
                'Comparison and resource report, not a full raw Trace/Diff/workspace archive',
                'Missing historical prices and model usage remain unknown',
                'Human decisions do not override machine evaluations',
                'Save this downloaded file to retain this export; no server-side export history is created'])
        report['report_sha256'] = digest(report)
        return report


def render_markdown(report):
    """Indent all data text so agent/operator strings cannot inject Markdown links/HTML."""
    comparison = report['comparison']
    lines = ['# RepoPilot 实验比较报告', '',
             '本文件是导出时的数据库快照，不是完整源码、Diff 或原始 Trace 证据包。',
             '质量门槛与人工决定独立；未知用量和价格不会记为零。', '']
    def section(title, value):
        lines.extend(['## '+title, ''])
        lines.extend('    '+line for line in json.dumps(value, ensure_ascii=False, indent=2).splitlines())
        lines.append('')
    section('标识与完整性', {k: report[k] for k in ('experiment_id','exported_at','manifest_sha256','report_sha256')})
    section('冻结实验清单', report['manifest'])
    section('质量比较与系统判定', {k: comparison[k] for k in ('comparison_sha256','integrity_issues','summary','groups','decision')})
    section('成对证据', comparison['pairs'])
    section('全部成员（含准备失败与未启动）', comparison['members'])
    section('资源口径与覆盖', comparison['resource_comparison'])
    section('人工决定及当时快照', report['reviews'])
    section('限制', report['limitations'] + comparison['limitations'])
    return '\n'.join(lines)
