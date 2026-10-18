"""Independent operator decisions; never mutate Run evaluations or frozen policies."""
from sqlalchemy import select, text
from ..db.session import SessionLocal
from ..db.models.platform_experiment import ExperimentReview, PlatformExperiment
from .platform_comparison_service import get_comparison
from .experiment_contract_service import digest
from .run_lifecycle import RunConflictError


def as_read(row):
    return dict(id=row.id, experiment_id=row.experiment_id, comparison_sha256=row.comparison_sha256,
                reviewer=row.reviewer, action=row.action, rationale=row.rationale, created_at=row.created_at,
                machine_decision=row.snapshot['decision'], snapshot=row.snapshot)


def save_review(experiment_id, data):
    with SessionLocal.begin() as session:
        session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
        return record_review(session, experiment_id, data)


def record_review(session, experiment_id, data):
    """Caller owns a repeatable-read transaction; append only, no commit here."""
    fingerprint = digest(dict(experiment_id=str(experiment_id), request=data.model_dump(mode='json')))
    # Serialize human submissions; a concurrent snapshot conflict is retried with the same request key.
    session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': 714202606})
    previous = session.scalar(select(ExperimentReview).where(ExperimentReview.request_key == data.request_key))
    if previous:
        if previous.request_sha256 != fingerprint:
            raise RunConflictError('Review request key already used with different content')
        return as_read(previous)
    comparison = get_comparison(experiment_id, session=session)
    if comparison is None:
        raise LookupError('Experiment not found')
    if comparison['comparison_sha256'] != data.comparison_sha256:
        raise RunConflictError('Comparison changed; inspect the current evidence before deciding')
    snapshot = {k: v for k, v in comparison.items() if k != 'observed_at'}
    row = ExperimentReview(experiment_id=experiment_id, request_key=data.request_key,
        request_sha256=fingerprint, comparison_sha256=data.comparison_sha256, snapshot=snapshot,
        reviewer=data.reviewer, action=data.action, rationale=data.rationale)
    session.add(row)
    session.flush()
    return as_read(row)


def list_reviews(experiment_id, *, limit=20, offset=0):
    with SessionLocal() as session:
        if session.get(PlatformExperiment, experiment_id) is None:
            return None
        return [as_read(row) for row in session.scalars(select(ExperimentReview).where(
            ExperimentReview.experiment_id == experiment_id).order_by(
                ExperimentReview.created_at.desc(), ExperimentReview.id.desc()).limit(limit).offset(offset))]
