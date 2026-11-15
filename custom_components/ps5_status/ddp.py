"""PlayStation device discovery protocol (DDP): ask a PS5 on the local network whether it's awake.

The console answers a small text request on UDP 9302 with "HTTP/1.1 200 Ok" when it's on and
"HTTP/1.1 620 Server Standby" in rest mode (only when rest mode keeps the network connected). No answer means it's
off or unreachable. No account or pairing is needed. The PS5 doesn't say which game is running, so the game comes
from the PlayStation Network integration instead.
"""
from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass, field

DDP_PORT = 9302  # PS5 (PS4 uses 987)
DDP_VERSION = "00030010"
SEARCH = ("SRCH * HTTP/1.1\ndevice-discovery-protocol-version:%s\n" % DDP_VERSION).encode()


@dataclass
class DdpReply:
    """One console's answer."""

    address: str
    status_code: int
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def awake(self) -> bool:
        return self.status_code == 200

    @property
    def standby(self) -> bool:
        return self.status_code == 620

    @property
    def host_id(self) -> str | None:
        return self.fields.get("host-id")

    @property
    def host_name(self) -> str | None:
        return self.fields.get("host-name")

    @property
    def host_type(self) -> str | None:
        return self.fields.get("host-type")

    @property
    def system_version(self) -> str | None:
        return self.fields.get("system-version")


def parse_reply(data: bytes, address: str) -> DdpReply | None:
    """Parse a DDP answer, or None if it isn't one."""
    try:
        text = data.decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return None
    lines = [line.strip() for line in text.replace("\r", "").split("\n") if line.strip()]
    if not lines or not lines[0].startswith("HTTP/1.1"):
        return None
    parts = lines[0].split()
    try:
        code = int(parts[1])
    except (IndexError, ValueError):
        return None
    fields = {}
    for line in lines[1:]:
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip().lower()] = value.strip()
    return DdpReply(address, code, fields)


class _Protocol(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.replies: list[DdpReply] = []
        self.got_one = asyncio.Event()

    def datagram_received(self, data: bytes, addr) -> None:
        reply = parse_reply(data, addr[0])
        if reply:
            self.replies.append(reply)
            self.got_one.set()

    def error_received(self, exc) -> None:  # e.g. ICMP unreachable: just no answer
        pass


async def _ask(target: str, timeout: float, broadcast: bool, port: int) -> list[DdpReply]:
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if broadcast:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("0.0.0.0", 0))
    sock.setblocking(False)
    transport, proto = await loop.create_datagram_endpoint(_Protocol, sock=sock)
    try:
        for _ in range(2):  # UDP can drop a packet; ask twice
            transport.sendto(SEARCH, (target, port))
            try:
                if broadcast:
                    await asyncio.sleep(timeout / 2)
                else:
                    await asyncio.wait_for(proto.got_one.wait(), timeout / 2)
                    break
            except asyncio.TimeoutError:
                continue
    finally:
        transport.close()
    return proto.replies


async def async_query(host: str, timeout: float = 2.0, port: int = DDP_PORT) -> DdpReply | None:
    """Ask one console for its status. None means no answer (off, or rest mode without network)."""
    replies = await _ask(host, timeout, False, port)
    return replies[0] if replies else None


async def async_discover(timeout: float = 3.0, port: int = DDP_PORT) -> list[DdpReply]:
    """Find PlayStation consoles on the local network (awake or in rest mode)."""
    replies = await _ask("255.255.255.255", timeout, True, port)
    seen, out = set(), []
    for r in replies:
        key = r.host_id or r.address
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out
