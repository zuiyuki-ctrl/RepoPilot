from fastapi import APIRouter, HTTPException, Request
from .platform_catalog import invoke
from ...services.platform_delivery_service import dashboard, inspect_report, MAX_REPORT_BYTES

router = APIRouter(prefix='/api/v2', tags=['v2 delivery'])


@router.get('/dashboard')
def overview():
    return invoke(dashboard)


@router.post('/reports/inspect')
async def inspect(request: Request):
    data = bytearray()
    async for chunk in request.stream():
        if len(data)+len(chunk) > MAX_REPORT_BYTES:
            raise HTTPException(413, 'Report exceeds 10 MB')
        data.extend(chunk)
    try:
        return inspect_report(bytes(data))
    except ValueError as exc:
        raise HTTPException(422, 'Invalid report format or evidence hash') from exc
