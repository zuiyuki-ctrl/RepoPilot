"""Dedicated mock gateway application, never included in backend.app.main.

No credential-issuance, cancellation, database, business or management routes.
Deployment is opt-in via this factory; there is no auto-starting global app.
"""
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from .services.gateway_credentials import GatewayUnauthorized
from .services.gateway_exchange import GatewayExchange, GatewayUpstreamUnknown
from .services.platform_artifacts import decode_json
from .services.run_lifecycle import RunConflictError

MAX_BODY = 262144


def error(status, code):
    return JSONResponse({'error': code}, status_code=status, headers={'Cache-Control': 'no-store'})


def create_gateway_app(exchange=None):
    service = exchange if exchange is not None else GatewayExchange()
    app = FastAPI(title='RepoPilot dedicated model gateway', docs_url=None,
                  redoc_url=None, openapi_url=None, redirect_slashes=False)

    @app.get('/health')
    def health():
        return {'status': 'ok', 'transport': service.transport.mode,
                'model_access': service.transport.mode == 'dashscope_live'}

    @app.post('/v1/model-calls')
    async def model_call(request: Request):
        # Avoid ambiguous duplicate Authorization/Content-Length interpretations.
        for key in ('authorization', 'content-length', 'content-type'):
            if len(request.headers.getlist(key)) > 1:
                return error(400, 'ambiguous_headers')
        auth = request.headers.get('authorization', '')
        if not auth.startswith('Bearer ') or len(auth) > 80:
            return error(401, 'invalid_credential')
        if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
            return error(415, 'json_required')
        try:
            identity = await run_in_threadpool(service.authenticate, auth[7:])
            limit = min(MAX_BODY, identity.policy.max_request_bytes)
            declared = request.headers.get('content-length')
            if declared is not None and (not declared.isascii() or not declared.isdecimal()):
                return error(400, 'invalid_content_length')
            if declared is not None and (len(declared) > 9 or int(declared) > limit):
                return error(413, 'request_too_large')
            data = bytearray()
            async with asyncio.timeout(5):
                async for chunk in request.stream():
                    if len(data) + len(chunk) > limit:
                        return error(413, 'request_too_large')
                    data.extend(chunk)
            if declared is not None and len(data) != int(declared):
                return error(400, 'content_length_mismatch')
            payload = decode_json(bytes(data))
            result = await run_in_threadpool(service.call, identity, payload)
            status = 202 if result['status'] in ('reserved', 'dispatched') else (
                200 if result['status'] == 'succeeded' else 502)
            return JSONResponse(result, status_code=status, headers={'Cache-Control': 'no-store'})
        except GatewayUnauthorized:
            return error(401, 'invalid_credential')
        except RunConflictError:
            return error(409, 'call_conflict_or_budget_closed')
        except (ValidationError, ValueError, UnicodeError, RecursionError):
            return error(422, 'invalid_model_request')
        except TimeoutError:
            return error(408, 'request_read_timeout')
        except GatewayUpstreamUnknown:
            return error(502, 'upstream_result_unknown')
        except Exception:
            # Do not return/log sensitive database or provider exception strings.
            return error(503, 'gateway_unavailable')

    return app
