"""Actual TLS over actual CONNECT, fake certificates/key, simulated ledger SQL."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import ssl
import subprocess
from unittest.mock import patch

import httpx
import pytest

from backend.app.services import gateway_tls as tls, gateway_egress as egress
from backend.app.services.gateway_exchange import GatewayExchange, GatewayUpstreamUnknown
from backend.app.services import gateway_credentials as credentials, model_gateway_service as ledger_service
from backend.app.services.gateway_upstream import ENDPOINT, UpstreamFailure
from backend.app.schemas.model_gateway import body_bytes, forwarded_body, ModelCallRequest
from tests.test_gateway_upstream import fake_gateway, answer
from tests.test_model_gateway import ledger, payload, USAGE


@pytest.fixture(scope='module')
def certificates(tmp_path_factory):
    executable=shutil.which('openssl') or 'C:/Program Files/Git/usr/bin/openssl.exe'
    if not Path(executable).is_file():pytest.skip('OpenSSL needed for actual TLS acceptance')
    root=tmp_path_factory.mktemp('gateway_tls')
    for name,host in (('good','dashscope.aliyuncs.com'),('wrong','wrong.invalid'),('untrusted','dashscope.aliyuncs.com')):
        subprocess.run([executable,'req','-x509','-newkey','rsa:2048','-nodes','-days','1',
            '-subj','/CN='+host,'-addext','subjectAltName=DNS:'+host,
            '-keyout',str(root/(name+'.key')),'-out',str(root/(name+'.pem'))],
            check=True,capture_output=True,timeout=20)
    yield root
    # Generated test private keys must not remain after a successful acceptance.
    for path in root.iterdir():path.unlink()


@pytest.fixture
def credential(tmp_path):
    path=tmp_path/'fake-key';path.write_text(tls.FAKE_SECRET,encoding='ascii');path.chmod(0o444)
    yield path
    path.chmod(0o600);path.unlink()


@asynccontextmanager
async def network(certs,*,certificate='good',reply=None,delay=0):
    received=[];snis=[];connects=[];tasks=set()
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certs/(certificate+'.pem'),certs/(certificate+'.key'))
    context.set_servername_callback(lambda sock,name,ctx:snis.append(name))
    async def supplier(reader,writer):
        tasks.add(asyncio.current_task())
        try:
            header=await reader.readuntil(b'\r\n\r\n')
            length=int(next(line.split(b':',1)[1] for line in header.split(b'\r\n') if line.lower().startswith(b'content-length:')))
            body=await reader.readexactly(length);received.append((header,body))
            await asyncio.sleep(delay)
            if callable(reply): value=reply()
            else:value=answer() if reply is None else reply
            raw=body_bytes(value)
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: '+str(len(raw)).encode()+b'\r\nConnection: close\r\n\r\n'+raw)
            await writer.drain()
        except (ConnectionError,asyncio.IncompleteReadError):pass
        finally:
            await egress.close(writer);tasks.discard(asyncio.current_task())
    server=await asyncio.start_server(supplier,'127.0.0.1',0,ssl=context)
    async def dial():
        connects.append(1)
        return await asyncio.open_connection('127.0.0.1',server.sockets[0].getsockname()[1])
    relay=egress.FixedEgressRelay()
    async def proxy(reader,writer):
        tasks.add(asyncio.current_task())
        try:await relay.handle(reader,writer)
        finally:tasks.discard(asyncio.current_task())
    proxy_server=await asyncio.start_server(proxy,'127.0.0.1',0,limit=egress.MAX_HEADER)
    async with server,proxy_server:
        with patch.object(egress,'open_fixed_upstream',dial),patch.object(tls,'PROXY_URL',
                'http://127.0.0.1:'+str(proxy_server.sockets[0].getsockname()[1])):
            try:yield received,snis,connects
            finally:
                for task in list(tasks):task.cancel()
                await asyncio.gather(*list(tasks),return_exceptions=True)


def test_tls_ledger_success_and_cache(fake_gateway,certificates,credential,monkeypatch):
    monkeypatch.setenv('HTTPS_PROXY','http://unreachable.invalid:1')
    monkeypatch.setenv('SSL_CERT_FILE','/nonexistent-ca')
    g=fake_gateway
    async def run():
        async with network(certificates) as (received,snis,connects):
            transport=tls.fake_tls_transport(ca_file=certificates/'good.pem',credential_file=credential)
            exchange=GatewayExchange(transport=transport)
            result=await asyncio.to_thread(exchange.call,g.identity,payload())
            assert result['usage']==USAGE and result['usage_source']=='fake_upstream'
            assert result==await asyncio.to_thread(exchange.call,g.identity,payload())
            assert len(received)==len(connects)==1 and snis==['dashscope.aliyuncs.com']
            header,body=received[0]
            assert b'POST /compatible-mode/v1/chat/completions HTTP/1.1' in header
            assert b'Bearer '+tls.FAKE_SECRET.encode() in header
            assert body==body_bytes(forwarded_body(g.identity.policy,ModelCallRequest(**payload())))
            await asyncio.to_thread(exchange.call,g.identity,payload(call_id='second'))
            assert len(received)==2 and g.l.grant.calls_reserved==2
    asyncio.run(run())
    assert tls.FAKE_SECRET not in ''.join(p.read_text() for p in g.root.rglob('*.json'))


@pytest.mark.parametrize('certificate,ca',[('wrong','wrong'),('good','untrusted')])
def test_wrong_host_or_untrusted_ca_no_request_no_retry(fake_gateway,certificates,credential,certificate,ca):
    async def run():
        async with network(certificates,certificate=certificate) as (received,snis,connects):
            service=GatewayExchange(transport=tls.fake_tls_transport(ca_file=certificates/(ca+'.pem'),credential_file=credential))
            with pytest.raises(GatewayUpstreamUnknown):await asyncio.to_thread(service.call,fake_gateway.identity,payload())
            result=await asyncio.to_thread(service.call,fake_gateway.identity,payload())
            assert result['status']=='unknown' and result['usage'] is None
            assert received==[] and len(connects)==1
            assert fake_gateway.l.grant.calls_reserved==1
    asyncio.run(run())


def test_cancelled_tls_reply_retained_not_delivered(fake_gateway,certificates,credential):
    g=fake_gateway
    def cancel():
        ledger_service.revoke_attempt(g.l.session,g.l.run);g.l.work.cancel_requested=True
        return answer()
    async def run():
        async with network(certificates,reply=cancel):
            service=GatewayExchange(transport=tls.fake_tls_transport(ca_file=certificates/'good.pem',credential_file=credential))
            with pytest.raises(credentials.GatewayUnauthorized):await asyncio.to_thread(service.call,g.identity,payload())
    asyncio.run(run())
    assert g.l.calls[0].status=='succeeded' and g.l.grant.known_total_tokens==15


def test_tls_total_timeout(fake_gateway,certificates,credential):
    async def run():
        async with network(certificates,delay=2) as (received,snis,connects):
            transport=tls.fake_tls_transport(ca_file=certificates/'good.pem',credential_file=credential)
            body=body_bytes(forwarded_body(fake_gateway.identity.policy,ModelCallRequest(**payload())))
            with pytest.raises(UpstreamFailure,match='upstream_timeout'):
                await asyncio.to_thread(transport.invoke,body,deadline=datetime.now(timezone.utc)+timedelta(seconds=.3))
            assert len(connects)==1
    asyncio.run(run())


@pytest.mark.parametrize('value',[b'',b'short',b'a'*257,b'a'*16+b'\r\nInjected: x',b'\xff'*20,b'a b'*10])
def test_invalid_secret_fixed_error(tmp_path,value):
    path=tmp_path/'key';path.write_bytes(value);path.chmod(0o444)
    try:
        with pytest.raises(ValueError,match='^Invalid mounted provider credential$'):tls.read_mounted_secret(path)
    finally:path.chmod(0o600)


def test_writable_secret_and_real_mode_rejected(tmp_path,certificates):
    path=tmp_path/'key';path.write_text('not-a-real-provider-credential',encoding='ascii')
    with pytest.raises(ValueError):tls.read_mounted_secret(path)
    path.chmod(0o444)
    try:
        assert 'not-a-real' not in repr(tls.read_mounted_secret(path))
        with pytest.raises(ValueError,match='Live provider credentials are not enabled'):
            tls.fake_tls_transport(ca_file=certificates/'good.pem',credential_file=path)
    finally:path.chmod(0o600)


def test_unverified_tls_rejected():
    with pytest.raises(ValueError):tls.FixedProxyTLSAdapter(ssl._create_unverified_context())


def test_other_endpoint_never_dialed():
    async def run():
        adapter=tls.FixedProxyTLSAdapter(ssl.create_default_context())
        try:
            with pytest.raises(ValueError):await adapter.handle_async_request(httpx.Request('POST','https://example.com'))
        finally:await adapter.aclose()
    asyncio.run(run())
