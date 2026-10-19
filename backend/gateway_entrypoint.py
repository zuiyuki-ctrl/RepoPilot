"""Container-only bootstrap. No dotenv, provider keys or business HTTP routes."""
import os
from pathlib import Path
import sys
from uuid import UUID


def main():
    # -I omits /app from sys.path; add only the image's trusted source, not mounts.
    sys.path.insert(0, '/app')
    import dotenv
    dotenv.load_dotenv = lambda *args, **kwargs: False
    raw = Path('/run/repopilot/database.json').read_bytes()
    if len(raw) > 8192:
        raise ValueError('Invalid gateway DB configuration')
    from backend.app.services.platform_artifacts import decode_json
    database = decode_json(raw)
    required = {'DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD'}
    if (not isinstance(database, dict) or set(database) != required
            or any(not isinstance(v, str) or not v or '\x00' in v for v in database.values())
            or not database['DB_PORT'].isdigit() or not 1 <= int(database['DB_PORT']) <= 65535):
        raise ValueError('Invalid gateway DB configuration')
    for key in tuple(os.environ):
        if key.startswith(('DB_', 'CHAT_', 'EMBEDDING_', 'DASHSCOPE_', 'OPENAI_')):
            del os.environ[key]
    os.environ.update(database)
    os.environ['PLATFORM_ARTIFACT_ROOT'] = '/evidence'
    run_id = UUID(os.environ['REPOPILOT_GATEWAY_RUN_ID'])
    token = UUID(os.environ['REPOPILOT_GATEWAY_ATTEMPT_ID'])
    from backend.app.services.gateway_runtime import ensure_active
    from backend.app.services.gateway_exchange import GatewayExchange
    from backend.app.db.session import engine
    engine.hide_parameters = True
    from sqlalchemy import text
    with engine.connect() as connection:
        flags = connection.execute(text('SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls '
                                        'FROM pg_roles WHERE rolname = current_user')).one()
        if any(flags):
            raise ValueError('Gateway must not use a privileged database role')
        # Catch accidental reuse of the business worker credentials. Deployment
        # still requires a DBA-reviewed role: this is not a complete ACL auditor.
        if connection.scalar(text("SELECT has_table_privilege('run_work', 'INSERT,UPDATE,DELETE') "
                                  "OR has_table_privilege('platform_run_events', 'INSERT,UPDATE,DELETE') "
                                  "OR has_column_privilege('platform_runs', 'lifecycle', 'UPDATE')")):
            raise ValueError('Gateway database role can mutate business lifecycle')
    ensure_active(run_id, token)  # Readiness includes current ledger schema and ownership.
    from backend.app.gateway_app import create_gateway_app
    app = create_gateway_app(GatewayExchange(run_id=run_id, worker_token=token))
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8080, access_log=False, log_level='critical',
                proxy_headers=False, server_header=False, limit_concurrency=16,
                timeout_keep_alive=2, timeout_graceful_shutdown=5)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # DB errors may contain connection information. Never emit raw traceback.
        print('Gateway startup failed', file=sys.stderr)
        raise SystemExit(1) from None
