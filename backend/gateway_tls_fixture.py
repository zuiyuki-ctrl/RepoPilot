"""Isolated TLS acceptance services, never a live supplier or configurable proxy."""
import asyncio
import json
import ssl
import sys

sys.path.insert(0, '/app')
from backend.app.services import gateway_egress as egress


async def main(mode):
    if mode == 'proxy':
        async def fixed_fake():
            return await asyncio.open_connection('tls-fixture', 8443)
        egress.open_fixed_upstream = fixed_fake
        await egress.serve()
        return
    if mode != 'supplier':
        raise ValueError('Invalid fixture mode')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain('/run/fixture/server.pem', '/run/fixture/server.key')
    async def serve(reader, writer):
        try:
            async with asyncio.timeout(5):
                header = await reader.readuntil(b'\r\n\r\n')
                if not header.startswith(b'POST /compatible-mode/v1/chat/completions HTTP/1.1\r\n'):
                    return
                values = header.split(b'\r\n')
                if b'authorization: Bearer repopilot-fake-upstream-only' not in [v[:v.find(b':')].lower()+v[v.find(b':'):] for v in values if b':' in v]:
                    return
                length = int(next(v.split(b':',1)[1] for v in values if v.lower().startswith(b'content-length:')))
                if not 0 < length <= 262144:
                    return
                await reader.readexactly(length)
                result = dict(choices=[dict(index=0, finish_reason='stop', message=dict(role='assistant',
                    content='RepoPilot TLS fixture; no real model was called.'))],
                    usage=dict(prompt_tokens=10, completion_tokens=5, total_tokens=15))
                data = json.dumps(result).encode()
                writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: '+str(len(data)).encode()+b'\r\n\r\n'+data)
                await writer.drain()
        except (OSError, ValueError, StopIteration, TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            pass
        finally:
            await egress.close(writer)
    server = await asyncio.start_server(serve, '0.0.0.0', 8443, ssl=context, limit=8192)
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    try:
        asyncio.run(main(sys.argv[1]))
    except Exception:
        raise SystemExit(1) from None
