"""The network check against a fake PS5 listening on this machine."""
import asyncio

import pytest_socket

from custom_components.ps5_status.ddp import async_query, parse_reply

AWAKE = b"HTTP/1.1 200 Ok\nhost-id:001122AABBCC\nhost-type:PS5\nhost-name:PS5-512\nhost-request-port:997\nsystem-version:09400000\n"
REST = b"HTTP/1.1 620 Server Standby\nhost-id:001122AABBCC\nhost-type:PS5\nhost-name:PS5-512\n"


class FakePs5(asyncio.DatagramProtocol):
    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        self.asked.append(data)
        if self.answer:
            self.transport.sendto(self.answer, addr)


async def _serve(answer):
    loop = asyncio.get_running_loop()
    transport, proto = await loop.create_datagram_endpoint(lambda: FakePs5(answer), local_addr=("127.0.0.1", 0))
    return transport, proto, transport.get_extra_info("sockname")[1]


def test_parse():
    r = parse_reply(AWAKE, "10.0.0.5")
    assert r.awake and not r.standby and r.host_name == "PS5-512" and r.host_id == "001122AABBCC" and r.host_type == "PS5"
    assert parse_reply(REST, "x").standby
    assert parse_reply(b"garbage", "x") is None


async def test_awake_rest_off():
    pytest_socket.enable_socket()  # a real UDP round trip on this machine
    for answer, check in ((AWAKE, lambda r: r.awake), (REST, lambda r: r.standby)):
        t, proto, port = await _serve(answer)
        try:
            r = await async_query("127.0.0.1", timeout=1, port=port)
            assert r is not None and check(r)
            assert proto.asked[0].startswith(b"SRCH * HTTP/1.1") and b"device-discovery-protocol-version:00030010" in proto.asked[0]
        finally:
            t.close()
    t, proto, port = await _serve(None)  # off: never answers
    try:
        assert await async_query("127.0.0.1", timeout=0.6, port=port) is None
        assert len(proto.asked) == 2  # asked twice in case a packet was dropped
    finally:
        t.close()
