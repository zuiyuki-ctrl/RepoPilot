"""Read the existing singleton connection marker; not a progress/health guarantee."""
from sqlalchemy import text
from ..db.session import engine
from .run_worker_service import WORKER_LOCK


def get_worker_status():
    # Bigint advisory locks use high/low uint32 parts and objsubid=1.
    # Read pg_locks rather than acquiring a probe lock on an API pooled connection.
    with engine.connect() as connection:
        present = bool(connection.scalar(text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_locks
                WHERE locktype = 'advisory' AND granted
                  AND mode = 'ExclusiveLock' AND objsubid = 1
                  AND classid = :high AND objid = :low
                  AND database = (SELECT oid FROM pg_database WHERE datname = current_database())
            )
        """), {'high': WORKER_LOCK >> 32, 'low': WORKER_LOCK & 0xffffffff}))
    return {'connection_present': present, 'basis': 'database_advisory_lock'}
