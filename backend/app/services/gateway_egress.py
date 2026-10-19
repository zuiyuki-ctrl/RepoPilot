"""Fixed-destination CONNECT relay. No credentials, arbitrary URLs or live-mode switch.

Deploy only on a gateway-only internal network plus an egress network. Agent and
DB networks must not include this service. TLS verification remains end-to-end
in the trusted gateway client; this relay restricts destinations, not HTTP paths.
"""
import asyncio
import ipaddress
import socket

AUTHORITY = b'dashscope.aliyuncs.com:443'
MAX_HEADER = 4096
MAX_TUNNEL_BYTES = 1_048_576  # Each direction, including TLS overhead.
MAX_SECONDS = 120


def validate_connect(header):
    if len(header) > MAX_HEADER or not header.endswith(b'\r\n\r\n'):
        raise ValueError('Invalid CONNECT')
    lines = header[:-4].split(b'\r\n')
    if lines[0] != b'CONNECT ' + AUTHORITY + b' HTTP/1.1':
        raise ValueError('Destination denied')
    seen = set()
    for line in lines[1:]:
        key, separator, value = line.partition(b':')
        key = key.lower()
        if not separator or key not in (b'host', b'accept') or key in seen:
            raise ValueError('Header denied')
        seen.add(key)
        if key == b'host' and value.strip() != AUTHORITY:
            raise ValueError('Host differs')
        if key == b'accept' and value.strip() != b'*/*':
            raise ValueError('Header denied')
    if b'host' not in seen:
        raise ValueError('Host required')


def public_ipv4(records):
    addresses = []
    for family, kind, proto, _, address in records:
        ip = ipaddress.ip_address(address[0])
        if (family != socket.AF_INET or kind != socket.SOCK_STREAM or proto != socket.IPPROTO_TCP
                or ip.version != 4 or not ip.is_global or ip.is_multicast or ip.is_reserved
                or address[1] != 443):
            raise ValueError('Non-public destination denied')
        if str(ip) not in addresses:
            addresses.append(str(ip))
    if not addresses:
        raise ValueError('No approved address')
    return addresses


async def open_fixed_upstream():
    # Resolve once, reject ANY private answer, then dial a numeric address: no
    # second DNS lookup/rebinding and no fallback/retry to a different endpoint.
    records = await asyncio.get_running_loop().getaddrinfo(
        'dashscope.aliyuncs.com', 443, family=socket.AF_INET,
        type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    address = public_ipv4(records)[0]
    return await asyncio.open_connection(address, 443, family=socket.AF_INET)


async def close(writer):
    if writer is not None:
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), 1)
        except (OSError, TimeoutError):
            pass


class FixedEgressRelay:
    def __init__(self):
        self.active = 0

    async def handle(self, reader, writer):
        if self.active >= 16:
            await close(writer)
            return
        self.active += 1
        upstream = None
        accepted = False
        pumps = []
        try:
            async with asyncio.timeout(MAX_SECONDS):
                header = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 5)
                validate_connect(header)
                upstream_reader, upstream = await asyncio.wait_for(open_fixed_upstream(), 5)
                writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                await writer.drain()
                accepted = True

                async def pump(source, target):
                    total = 0
                    while data := await source.read(16384):
                        total += len(data)
                        if total > MAX_TUNNEL_BYTES:
                            raise ValueError('Tunnel limit')
                        target.write(data)
                        await target.drain()

                pumps = [asyncio.create_task(pump(reader, upstream)),
                         asyncio.create_task(pump(upstream_reader, writer))]
                await asyncio.wait(pumps, return_when=asyncio.FIRST_COMPLETED)
        except (OSError, ValueError, TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            if not accepted:
                writer.write(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
                try:
                    await writer.drain()
                except OSError:
                    pass
        finally:
            for task in pumps:
                task.cancel()
            await asyncio.gather(*pumps, return_exceptions=True)
            await close(upstream)
            await close(writer)
            self.active -= 1


async def serve():
    server = await asyncio.start_server(FixedEgressRelay().handle, '0.0.0.0', 8081, limit=MAX_HEADER)
    async with server:
        await server.serve_forever()
