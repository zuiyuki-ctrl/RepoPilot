"""No environment/provider configuration and no request/error logging."""
import asyncio
import sys

if __name__ == '__main__':
    sys.path.insert(0, '/app')
    from backend.app.services.gateway_egress import serve
    try:
        asyncio.run(serve())
    except Exception:
        raise SystemExit(1) from None
