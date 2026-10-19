"""Fixed egress policy and real loopback forwarding. Never dial a supplier."""
import asyncio
import socket
from unittest.mock import patch
import pytest
from backend.app.services import gateway_egress as egress

HEADER = b'CONNECT dashscope.aliyuncs.com:443 HTTP/1.1\r\nHost: dashscope.aliyuncs.com:443\r\n\r\n'


def test_exact_httpx_connect_shape():
    egress.validate_connect(HEADER)
    egress.validate_connect(HEADER[:-2] + b'Accept: */*\r\n\r\n')


@pytest.mark.parametrize('target', [b'example.com:443', b'127.0.0.1:443', b'[::1]:443',
    b'host.docker.internal:8000', b'dashscope.aliyuncs.com:80', b'dashscope.aliyuncs.com.evil:443',
    b'dashscope.aliyuncs.com.:443', b'user@dashscope.aliyuncs.com:443'])
def test_other_targets_denied(target):
    with pytest.raises(ValueError):
        egress.validate_connect(HEADER.replace(egress.AUTHORITY, target))


@pytest.mark.parametrize('extra', [b'Host: dashscope.aliyuncs.com:443', b'Content-Length: 1',
    b'Transfer-Encoding: chunked', b'Proxy-Authorization: secret', b' Host: other', b'X: '+b'a'*4096])
def test_extra_headers_denied(extra):
    with pytest.raises(ValueError):
        egress.validate_connect(HEADER[:-2]+extra+b'\r\n\r\n')


def records(ip):
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (ip, 443))]


@pytest.mark.parametrize('ip', ['127.0.0.1','10.0.0.1','169.254.169.254','192.168.1.1',
    '172.16.1.1','0.0.0.0','224.0.0.1','240.0.0.1','100.64.0.1'])
def test_private_or_mixed_dns_answers_denied(ip):
    with pytest.raises(ValueError):
        egress.public_ipv4(records('1.1.1.1')+records(ip))


def test_dns_once_and_numeric_connection():
    async def exercise():
        from unittest.mock import AsyncMock
        resolver=AsyncMock(return_value=records('1.1.1.1'))
        dial=AsyncMock(return_value=('reader','writer'))
        with patch.object(asyncio.get_running_loop(),'getaddrinfo',resolver),patch.object(asyncio,'open_connection',dial):
            assert await egress.open_fixed_upstream()==('reader','writer')
        assert resolver.call_count==dial.call_count==1
        assert dial.call_args.args==('1.1.1.1',443)
    asyncio.run(exercise())


@pytest.mark.parametrize('header', [b'GET https://dashscope.aliyuncs.com/ HTTP/1.1\r\n\r\n',
    b'CONNECT dashscope.aliyuncs.com:443 HTTP/1.0\r\n\r\n',
    b'CONNECT dashscope.aliyuncs.com:443 HTTP/1.1\r\n\r\n',
    HEADER.replace(b'Host: dashscope.aliyuncs.com:443',b'Host: other')])
def test_no_forward_proxy_or_ambiguous_host(header):
    with pytest.raises(ValueError):egress.validate_connect(header)


def test_timeout_closes_both_sides_and_releases_slot():
    async def exercise():
        closed=asyncio.Event()
        async def hold(reader,writer):
            try:await reader.read()
            finally:await egress.close(writer);closed.set()
        upstream=await asyncio.start_server(hold,'127.0.0.1',0)
        async def fixed():return await asyncio.open_connection('127.0.0.1',upstream.sockets[0].getsockname()[1])
        relay=egress.FixedEgressRelay()
        server=await asyncio.start_server(relay.handle,'127.0.0.1',0)
        async with upstream,server:
            with patch.object(egress,'MAX_SECONDS',.1),patch.object(egress,'open_fixed_upstream',fixed):
                r,w=await asyncio.open_connection('127.0.0.1',server.sockets[0].getsockname()[1])
                w.write(HEADER);await w.drain()
                assert b'200' in await r.readuntil(b'\r\n\r\n')
                assert await r.read()==b''
                await closed.wait();await egress.close(w);await asyncio.sleep(.02)
        assert relay.active==0
    asyncio.run(asyncio.wait_for(exercise(),3))


def test_connection_limit_does_not_dial():
    async def exercise():
        from unittest.mock import AsyncMock
        relay=egress.FixedEgressRelay();relay.active=16
        reader=AsyncMock();writer=AsyncMock();writer.close=lambda:None
        with patch.object(egress,'open_fixed_upstream',AsyncMock()) as dial:
            await relay.handle(reader,writer)
            dial.assert_not_called();reader.readuntil.assert_not_called()
        assert relay.active==16
    asyncio.run(exercise())


def test_real_loopback_success_denial_and_disconnect():
    async def exercise():
        calls=[]
        async def echo(reader,writer):
            try:
                data=await reader.read(100)
                writer.write(data);await writer.drain()
            finally: await egress.close(writer)
        upstream=await asyncio.start_server(echo,'127.0.0.1',0)
        async def fixed():
            calls.append(1)
            return await asyncio.open_connection('127.0.0.1',upstream.sockets[0].getsockname()[1])
        relay=egress.FixedEgressRelay()
        server=await asyncio.start_server(relay.handle,'127.0.0.1',0,limit=egress.MAX_HEADER)
        async with upstream,server:
            with patch.object(egress,'open_fixed_upstream',fixed):
                for header,expected in [(HEADER,b'200'),(HEADER.replace(b':443',b':80'),b'403')]:
                    r,w=await asyncio.open_connection('127.0.0.1',server.sockets[0].getsockname()[1])
                    w.write(header);await w.drain()
                    assert expected in await r.readuntil(b'\r\n\r\n')
                    if expected==b'200':
                        w.write(b'fixture');await w.drain()
                        assert await r.readexactly(7)==b'fixture'
                    await egress.close(w)
                await asyncio.sleep(.05)
        assert calls==[1] and relay.active==0
    asyncio.run(asyncio.wait_for(exercise(),5))
