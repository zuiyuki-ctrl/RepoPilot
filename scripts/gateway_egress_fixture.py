"""Disposable B3b network fixture. Never a production gateway entrypoint.

Only the proxy test process substitutes the dialer; target parsing/relay is the
image's production implementation. This deliberately tests TCP, not real TLS.
"""
import asyncio
import json
import socket
import sys

sys.path.insert(0, '/app')
from backend.app.services import gateway_egress as egress


async def main(mode):
    if mode == 'proxy':
        async def fake_only():
            return await asyncio.open_connection('fake-supplier',443)
        egress.open_fixed_upstream=fake_only
        await egress.serve()
    elif mode == 'supplier':
        async def echo(reader,writer):
            try:
                data=await reader.read(32)
                writer.write(data);await writer.drain()
            finally: await egress.close(writer)
        servers=[await asyncio.start_server(echo,'0.0.0.0',port) for port in (443,8000,5432)]
        try: await asyncio.Event().wait()
        finally:
            for server in servers: server.close();await server.wait_closed()
    else:
        await asyncio.Event().wait()


def check(kind,host,port,target):
    try:
        with socket.create_connection((host,int(port)),timeout=1) as stream:
            if kind=='tcp':return True
            if kind=='tunnel':
                header=('CONNECT '+target+' HTTP/1.1\r\nHost: '+target+'\r\n\r\n').encode('ascii')
                stream.sendall(header)
                data=b''
                while b'\r\n\r\n' not in data and len(data)<4096:
                    part=stream.recv(1)
                    if not part: break
                    data+=part
                if target!='dashscope.aliyuncs.com:443':return data.startswith(b'HTTP/1.1 403 ')
                if not data.startswith(b'HTTP/1.1 200 '):return False
                stream.sendall(b'echo')
                data=b''
                while len(data)<4:
                    part=stream.recv(4-len(data))
                    if not part:break
                    data+=part
                return data==b'echo'
    except (OSError,ValueError):return False
    return False


if __name__=='__main__':
    if sys.argv[1]=='check':print(json.dumps({'ok':check(*sys.argv[2:])}))
    else:asyncio.run(main(sys.argv[1]))
