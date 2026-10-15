"""python -m scripts.platform_worker [--once] [--allow-model]"""
import argparse
import logging
from uuid import UUID


def main():
    parser = argparse.ArgumentParser(description='v2 persistent single worker; no model calls unless explicitly enabled')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--allow-model', action='store_true')
    parser.add_argument('--recover-run', type=UUID)
    parser.add_argument('--recover-validation', type=UUID)
    parser.add_argument('--recover-preparation', type=UUID)
    parser.add_argument('--token', type=UUID)
    parser.add_argument('--confirm-writers-stopped', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if sum(bool(x) for x in (args.recover_run,args.recover_validation,args.recover_preparation)) > 1:
        parser.error('Choose one recovery target')
    if args.recover_run or args.recover_validation or args.recover_preparation:
        if not args.token or not args.confirm_writers_stopped:
            parser.error('Recovery requires the exact step token and --confirm-writers-stopped')
        from sqlalchemy import text
        from backend.app.db.session import engine
        from backend.app.services.run_worker_service import WORKER_LOCK, recover_interrupted
        with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            if not connection.scalar(text('SELECT pg_try_advisory_lock(:key)'), {'key': WORKER_LOCK}):
                raise RuntimeError('Stop the existing worker before recovery')
            try:
                if args.recover_preparation:
                    from backend.app.services.platform_experiment_service import recover_preparation
                    recover_preparation(args.recover_preparation,args.token)
                elif args.recover_validation:
                    from backend.app.services.platform_catalog_service import recover_validation
                    recover_validation(args.recover_validation, args.token)
                else:
                    recover_interrupted(args.recover_run, args.token)
            finally:
                connection.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': WORKER_LOCK})
        print('Ownership recovered without replay; target remains unsuccessful.')
        return
    if args.token or args.confirm_writers_stopped:
        parser.error('Recovery options require --recover-run')
    from backend.app.services.platform_worker import run_worker
    if args.allow_model:
        print('Native planning and candidate stages may make paid model/embedding calls.')
    else:
        print('Model stages disabled; preparation, decisions and cancellation only.')
    run_worker(once=args.once, allow_model=args.allow_model)


if __name__ == '__main__':
    main()
