"""Remote Play linking and wake-up for a PS5.

Turning a PS5 on needs a key the console only gives to a device it has been linked with, the same way the
PS Remote Play app is linked: on the PS5, Settings > System > Remote Play > Link Device shows an 8-digit code. This
module does that one-time registration and sends the wake-up packet afterwards.

The protocol (registration handshake, key derivation and the wake-up message) was worked out by the Chiaki project
and implemented in Python by pyremoteplay (https://github.com/ktnrg45/pyremoteplay, GPLv3). This is a small
adaptation of those parts for PS5 only, using the `cryptography` package Home Assistant already ships instead of
pycryptodome, so nothing extra has to be installed. Like its sources, this file is GPLv3.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import os
import socket

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .ddp import DDP_PORT, DDP_VERSION

RP_PORT = 9295
WAKE_SOURCE_PORT = 9303  # the PS5 expects the wake-up from this port
USER_AGENT = "remoteplay Windows"
RP_VERSION = "1.0"
CLIENT_TYPE = "dabfa2ec873de5839bee8d3f4c0239c4282c07c25c6077a2931afcf0adc0d34f"
REG_PATH = "/sie/ps5/rp/sess/rgst"
REG_INIT, REG_START = b"SRC3", b"RES3"

# The only bytes of the PS5 registration key tables the derivation reads (every 32nd byte from offset 1 and 8).
HMAC_KEY = bytes.fromhex("464687b349ca8ce859c5270f5d7a69d6")
REG_KEY_0 = bytes.fromhex("d860e146bdb0bd94b460070bb14fe723")
REG_KEY_1 = bytes.fromhex("a83761b527fc076e62433aa701958a85")
REG_PAD = b"A" * 480


class RemotePlayError(Exception):
    """Linking failed; the message says why, in plain words."""


def account_id_to_rp(account_id: str | int) -> str:
    """PSN account ID (a long number) -> the base64 form Remote Play uses."""
    return base64.b64encode(int(account_id).to_bytes(8, "little")).decode()


def _key_0(pin: int) -> bytes:
    key = bytearray(REG_KEY_0)
    for i, index in enumerate(range(12, 16)):  # the PIN goes into the last 4 bytes
        key[index] ^= (pin >> (24 - i * 8)) & 0xFF
    return bytes(key)


def _key_1(nonce: bytes) -> bytes:
    return bytes(((nonce[i] ^ REG_KEY_1[i]) - 45 + i) % 256 for i in range(16))


def _cipher(key: bytes, nonce: bytes, counter: int = 0) -> Cipher:
    iv = hmac.new(HMAC_KEY, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()[:16]
    return Cipher(algorithms.AES(key), modes.CFB(iv))  # AES-CFB-128


def build_request(account_rp_id: str, pin: str, nonce: bytes | None = None) -> tuple[bytes, bytes, bytes]:
    """(request bytes, key 0, nonce) for the registration POST."""
    nonce = nonce or os.urandom(16)
    k0, k1 = _key_0(int(pin)), _key_1(nonce)
    body = REG_PAD[0:199] + k1[8:] + REG_PAD[207:401] + k1[0:8] + REG_PAD[409:]
    secret = f"Client-Type: {CLIENT_TYPE}\r\nNp-AccountId: {account_rp_id}\r\n".encode()
    enc = _cipher(k0, nonce).encryptor()
    body += enc.update(secret) + enc.finalize()
    head = (f"POST {REG_PATH} HTTP/1.1\r\n HTTP/1.1\r\nHOST: 10.0.2.15\r\nUser-Agent: {USER_AGENT}\r\n"
            f"Connection: close\r\nContent-Length: {len(body)}\r\nRP-Version: {RP_VERSION}\r\n\r\n").encode()
    return head + body, k0, nonce


def parse_response(response: bytes, k0: bytes, nonce: bytes) -> dict[str, str]:
    """Decrypt the console's answer into its fields (PS5-RegistKey, PS5-Nickname, ...)."""
    lines = response.split(b"\r\n")
    if not lines or b"200 OK" not in lines[0]:
        status = lines[0].decode("utf-8", "replace") if lines else "no answer"
        raise RemotePlayError("The PS5 refused the code (%s). Get a new code and try again." % status)
    dec = _cipher(k0, nonce).decryptor()
    text = (dec.update(lines[-1]) + dec.finalize()).decode("utf-8", "replace")
    info = {}
    for line in text.split("\r\n"):
        key, sep, value = line.partition(": ")
        if sep:
            info[key] = value
    if not info.get("PS5-RegistKey"):
        raise RemotePlayError("The PS5 answered, but without a key. Get a new code and try again.")
    return info


async def async_register(host: str, account_id: str | int, pin: str, timeout: float = 5.0) -> dict[str, str]:
    """Link with the PS5 while it shows the Link Device code. Returns its answer; keep PS5-RegistKey."""
    pin = "".join(ch for ch in str(pin) if ch.isdigit())
    if len(pin) != 8:
        raise RemotePlayError("The code is 8 digits.")
    loop = asyncio.get_running_loop()

    # 1. Is it waiting for a device to link?
    class _Init(asyncio.DatagramProtocol):
        def __init__(self):
            self.got = loop.create_future()

        def datagram_received(self, data, addr):
            if not self.got.done():
                self.got.set_result(data)

    transport, proto = await loop.create_datagram_endpoint(_Init, remote_addr=(host, RP_PORT))
    try:
        transport.sendto(REG_INIT)
        try:
            answer = await asyncio.wait_for(proto.got, timeout)
        except asyncio.TimeoutError:
            answer = b""
    finally:
        transport.close()
    if not answer.startswith(REG_START):
        raise RemotePlayError("The PS5 isn't waiting to link. On the PS5 open Settings > System > Remote Play > "
                              "Link Device, then enter the code it shows while it's still on screen.")

    # 2. The encrypted registration request.
    request, k0, nonce = build_request(account_id_to_rp(account_id), pin)
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, RP_PORT), timeout)
    except (OSError, asyncio.TimeoutError) as err:
        raise RemotePlayError("Couldn't connect to the PS5 to link (%s)." % err) from err
    try:
        writer.write(request)
        await writer.drain()
        response = b""
        try:
            while len(response) < 4096:
                chunk = await asyncio.wait_for(reader.read(1024), timeout)
                if not chunk:
                    break
                response += chunk
        except asyncio.TimeoutError:
            pass
    finally:
        writer.close()
    if not response:
        raise RemotePlayError("The PS5 didn't answer the link request. Get a new code and try again.")
    return parse_response(response, k0, nonce)


def wake_credential(regist_key: str) -> str:
    """The PS5-RegistKey from linking -> the number the wake-up message carries."""
    try:
        return str(int.from_bytes(bytes.fromhex(bytes.fromhex(regist_key).decode()), "big"))
    except ValueError:
        return str(int(regist_key, 16))


def wake_message(regist_key: str) -> bytes:
    fields = {"user-credential": wake_credential(regist_key), "client-type": "vr", "auth-type": "R", "model": "w",
              "app-type": "r"}
    return ("WAKEUP * HTTP/1.1\n" + "".join(f"{k}:{v}\n" for k, v in fields.items())
            + f"device-discovery-protocol-version:{DDP_VERSION}\n").encode()


async def async_wake(host: str, regist_key: str, port: int = DDP_PORT) -> None:
    """Send the wake-up (a few times, it's UDP). The console takes 10-20 seconds to come up."""
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", WAKE_SOURCE_PORT))
    except OSError:
        sock.bind(("0.0.0.0", 0))
    sock.setblocking(False)
    transport, _ = await loop.create_datagram_endpoint(asyncio.DatagramProtocol, sock=sock)
    try:
        msg = wake_message(regist_key)
        for _ in range(3):
            transport.sendto(msg, (host, port))
            await asyncio.sleep(0.3)
    finally:
        transport.close()
