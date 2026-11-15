"""Linking and waking against a fake PS5 on this machine, over real sockets."""
import asyncio
from unittest.mock import patch

import pytest_socket

from custom_components.ps5_status import remoteplay as rp

ACCOUNT = "1234567890123456789"
PIN = "12345678"


class FakeLinkPs5:
    """Does the PS5's side of linking: answers SRC3 with RES3, then checks the request and returns a key."""

    def __init__(self, pin):
        self.pin, self.account = pin, None

    async def handle(self, reader, writer):
        data = b""
        while b"\r\n\r\n" not in data:
            data += await reader.read(1024)
        head, body = data.split(b"\r\n\r\n", 1)
        length = int([h for h in head.split(b"\r\n") if h.startswith(b"Content-Length")][0].split(b": ")[1])
        while len(body) < length:
            body += await reader.read(1024)
        k1 = body[401:409] + body[199:207]
        nonce = bytes((((k1[i] + 45 - i) % 256) ^ rp.REG_KEY_1[i]) for i in range(16))
        k0 = rp._key_0(int(self.pin))
        dec = rp._cipher(k0, nonce).decryptor()
        secret = (dec.update(body[480:]) + dec.finalize()).decode("utf-8", "replace")
        if "Np-AccountId: " not in secret or "Client-Type: " not in secret:
            writer.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")  # wrong code: it decrypts to garbage
        else:
            self.account = secret.split("Np-AccountId: ")[1].split("\r\n")[0]
            enc = rp._cipher(k0, nonce).encryptor()
            answer = enc.update(b"PS5-RegistKey: 3361613562383339\r\nPS5-Nickname: PS5-512\r\n") + enc.finalize()
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n" % len(answer) + answer)
        await writer.drain()
        writer.close()


class InitUdp(asyncio.DatagramProtocol):
    def connection_made(self, t):
        self.t = t

    def datagram_received(self, data, addr):
        if data == rp.REG_INIT:
            self.t.sendto(rp.REG_START + b"\x00" * 4, addr)


async def _fake_ps5(pin, port):
    loop = asyncio.get_running_loop()
    ps5 = FakeLinkPs5(pin)
    udp, _ = await loop.create_datagram_endpoint(InitUdp, local_addr=("127.0.0.1", port))
    tcp = await asyncio.start_server(ps5.handle, "127.0.0.1", port)
    return ps5, udp, tcp


async def test_link_and_wake():
    pytest_socket.enable_socket()
    port = 19295
    with patch.object(rp, "RP_PORT", port):
        ps5, udp, tcp = await _fake_ps5(PIN, port)
        try:
            info = await rp.async_register("127.0.0.1", ACCOUNT, "1234-5678", timeout=2)
            assert info["PS5-RegistKey"] == "3361613562383339"
            assert ps5.account == rp.account_id_to_rp(ACCOUNT)
            # wrong code
            try:
                await rp.async_register("127.0.0.1", ACCOUNT, "87654321", timeout=2)
                raise AssertionError("should have failed")
            except rp.RemotePlayError as err:
                assert "refused" in str(err)
        finally:
            udp.close()
            tcp.close()
    # not in Link Device mode: nothing answers
    with patch.object(rp, "RP_PORT", 19296):
        try:
            await rp.async_register("127.0.0.1", ACCOUNT, PIN, timeout=0.5)
            raise AssertionError("should have failed")
        except rp.RemotePlayError as err:
            assert "Link Device" in str(err)

    # wake-up message arrives, with the credential from the key
    got = []

    class Rx(asyncio.DatagramProtocol):
        def datagram_received(self, data, addr):
            got.append(data)

    loop = asyncio.get_running_loop()
    t, _ = await loop.create_datagram_endpoint(Rx, local_addr=("127.0.0.1", 19302))
    try:
        await rp.async_wake("127.0.0.1", "3361613562383339", port=19302)
        await asyncio.sleep(0.1)
    finally:
        t.close()
    assert len(got) == 3
    msg = got[0].decode()
    # the key is hex text of hex text: "3361613562383339" -> "3aa5b839" -> 0x3aa5b839
    assert rp.wake_credential("3361613562383339") == str(0x3AA5B839)
    assert msg == ("WAKEUP * HTTP/1.1\nuser-credential:%d\nclient-type:vr\nauth-type:R\nmodel:w\napp-type:r\n"
                   "device-discovery-protocol-version:00030010\n" % 0x3AA5B839)


async def test_bad_pin():
    try:
        await rp.async_register("127.0.0.1", ACCOUNT, "123")
        raise AssertionError
    except rp.RemotePlayError as err:
        assert "8 digits" in str(err)
