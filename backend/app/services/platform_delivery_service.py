"""Live dashboard and offline report inspection, without execution or data imports."""
import json
import math
from datetime import datetime, timezone
from sqlalchemy import select, func, text
from ..db.session import SessionLocal
from ..db.models import PlatformRun
from ..db.models.platform_catalog import AgentVersion, BenchmarkVersion
from ..db.models.platform_experiment import PlatformExperiment, ExperimentMember
from .experiment_contract_service import digest

MAX_REPORT_BYTES = 10_000_000


def dashboard():
    with SessionLocal() as session:
        session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        def counts(column):
            return dict(session.execute(select(column, func.count()).group_by(column)).all())
        return dict(source='live_database_only', observed_at=datetime.now(timezone.utc).isoformat(),
            agents=counts(AgentVersion.status), benchmarks=counts(BenchmarkVersion.status),
            experiments=session.scalar(select(func.count()).select_from(PlatformExperiment)),
            preparation=counts(ExperimentMember.status),
            lifecycle=counts(PlatformRun.lifecycle), execution=counts(PlatformRun.execution_status),
            evaluation=counts(PlatformRun.evaluation_outcome),
            recent_experiments=[dict(id=str(row.id), name=row.manifest['draft']['name'],created_at=row.created_at)
                for row in session.scalars(select(PlatformExperiment).order_by(PlatformExperiment.created_at.desc(),PlatformExperiment.id.desc()).limit(5))],
            recent_runs=[dict(id=str(row.id), execution=row.execution_status, evaluation=row.evaluation_outcome,
                lifecycle=row.lifecycle) for row in session.scalars(select(PlatformRun).order_by(PlatformRun.created_at.desc(),PlatformRun.id.desc()).limit(5))],
            note='Counts include fixtures and all live records; not a cross-benchmark success rate. Archived files excluded.')


def inspect_report(raw: bytes):
    if len(raw) > MAX_REPORT_BYTES:
        raise ValueError('Report exceeds 10 MB')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError('Non-finite JSON number')
    try:
        report = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs, parse_constant=invalid_constant)
        def bounded(value, depth=0):
            if depth > 40:
                raise ValueError('Report nesting too deep')
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError('Non-finite JSON number')
            if isinstance(value, dict):
                for item in value.values(): bounded(item, depth+1)
            elif isinstance(value, list):
                for item in value: bounded(item, depth+1)
        bounded(report)
        if not isinstance(report, dict) or report.get('schema_version') != 1 or report.get('report_type') != 'experiment_comparison_snapshot':
            raise ValueError('Unsupported report format')
        if digest({k:v for k,v in report.items() if k != 'report_sha256'}) != report['report_sha256']:
            raise ValueError('Report content hash differs')
        if digest(report['manifest']) != report['manifest_sha256']:
            raise ValueError('Manifest content hash differs')
        comparison = report['comparison']
        if (comparison['experiment_id'] != report['experiment_id']
                or comparison['manifest_sha256'] != report['manifest_sha256']):
            raise ValueError('Report identity binding differs')
        def comparison_hash(value):
            return digest({k:v for k,v in value.items() if k not in ('comparison_sha256','observed_at')})
        if comparison_hash(comparison) != comparison['comparison_sha256']:
            raise ValueError('Comparison content hash differs')
        for review in report['reviews']:
            snapshot = review['snapshot']
            if (snapshot['experiment_id'] != report['experiment_id']
                    or snapshot['comparison_sha256'] != review['comparison_sha256']
                    or comparison_hash(snapshot) != review['comparison_sha256']):
                raise ValueError('Review snapshot differs')
        # Return the file as evidence, not a recomputed score or an imported live experiment.
        return dict(source='uploaded_report_only', integrity='hashes_consistent', report=report,
                    warning='Hash consistency is not a signature or proof of authenticity. No database writes or score recomputation.')
    except (KeyError, TypeError, UnicodeError, RecursionError) as exc:
        raise ValueError('Malformed report structure') from exc
