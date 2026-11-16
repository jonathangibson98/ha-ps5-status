"""A tiny PlayStation Network client: sign in with an NPSSO token and read what an account is playing.

This is what the PlayStation Network integration (through PSNAWP) does under the hood, cut down to the few calls
PS5 Status needs, so that integration isn't needed at all.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import aiohttp

_LOGGER = logging.getLogger(__name__)

AUTH_URL = "https://ca.account.sony.com/api/authz/v3/oauth/authorize"
TOKEN_URL = "https://ca.account.sony.com/api/authz/v3/oauth/token"
ACCOUNT_URL = "https://dms.api.playstation.com/api/v1/devices/accounts/me"
PROFILE_URL = "https://us-prof.np.community.playstation.net/userProfile/v1/users/me/profile2"
PRESENCE_URL = "https://m.np.playstation.com/api/userProfile/v1/internal/users/me/basicPresences"

# the PlayStation App's public client (the same one PSNAWP and the PlayStation Network integration use)
CLIENT_ID = "09515159-7237-4370-9b40-3806e67c0891"
CLIENT_AUTH = "Basic MDk1MTUxNTktNzIzNy00MzcwLTliNDAtMzgwNmU2N2MwODkxOnVjUGprYTV0bnRCMktxc1A="
REDIRECT_URI = "com.scee.psxandroid.scecompcall://redirect"
SCOPE = "psn:mobile.v2.core psn:clientapp"
UA = "Mozilla/5.0 (Linux; Android 11; sdk_gphone_x86 Build/RSR1.201013.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/83.0.4103.106 Mobile Safari/537.36"


class PsnAuthError(Exception):
    """The NPSSO token is wrong or expired: get a new one."""


class PsnError(Exception):
    """PSN didn't answer properly (down, rate limited, network)."""


@dataclass
class Presence:
    """What one account is doing right now."""

    online: bool = False
    platform: str | None = None       # PS5, PS4, ...
    title: str | None = None
    title_id: str | None = None
    image: str | None = None          # the game's picture on Sony's image server
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def on_ps5(self) -> bool:
        return self.online and (self.platform or "").upper() == "PS5"


def parse_presence(body: dict[str, Any]) -> Presence:
    """basicPresences answer -> Presence."""
    bp = body.get("basicPresence") or {}
    info = bp.get("primaryPlatformInfo") or {}
    online = info.get("onlineStatus") == "online"
    platform = info.get("platform")
    games = bp.get("gameTitleInfoList") or []
    game = next((g for g in games if (g.get("launchPlatform") or g.get("format") or "").upper() == "PS5"), None)
    game = game or (games[0] if games else None)
    if game:
        image = game.get("conceptIconUrl") or game.get("npTitleIconUrl") or game.get("titleImageUrl")
        return Presence(online, platform, game.get("titleName"), game.get("npTitleId"), image, bp)
    return Presence(online, platform, raw=bp)


class PsnAccount:
    """One PSN account, signed in with its NPSSO token. Keeps its own access token fresh."""

    def __init__(self, session: aiohttp.ClientSession, npsso: str) -> None:
        self._session = session
        self.npsso = npsso.strip()
        self._access: str | None = None
        self._refresh: str | None = None
        self._expires = 0.0
        self.account_id: str | None = None
        self.online_id: str | None = None

    async def _token(self, data: dict[str, str]) -> None:
        headers = {"Authorization": CLIENT_AUTH, "Content-Type": "application/x-www-form-urlencoded", "User-Agent": UA}
        async with self._session.post(TOKEN_URL, data=data, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
            body = await r.json(content_type=None)
            if r.status in (400, 401):
                raise PsnAuthError(body.get("error_description") or "sign-in refused")
            if r.status != 200:
                raise PsnError(f"token request answered {r.status}")
        self._access = body["access_token"]
        self._refresh = body.get("refresh_token") or self._refresh
        self._expires = time.monotonic() + int(body.get("expires_in", 3600)) - 120

    async def _sign_in(self) -> None:
        """NPSSO -> authorization code -> tokens."""
        params = {"access_type": "offline", "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI,
                  "response_type": "code", "scope": SCOPE}
        try:
            async with self._session.get(AUTH_URL, params=params, headers={"Cookie": f"npsso={self.npsso}", "User-Agent": UA},
                                         allow_redirects=False, timeout=aiohttp.ClientTimeout(total=15)) as r:
                location = r.headers.get("Location", "")
        except aiohttp.ClientError as err:
            raise PsnError(f"couldn't reach Sony: {err}") from err
        code = parse_qs(urlparse(location).query).get("code", [None])[0]
        if not code:
            raise PsnAuthError("the NPSSO token was refused (it's wrong or expired)")
        await self._token({"code": code, "redirect_uri": REDIRECT_URI, "grant_type": "authorization_code",
                           "token_format": "jwt"})

    async def _ensure(self) -> str:
        if self._access and time.monotonic() < self._expires:
            return self._access
        if self._refresh:
            try:
                await self._token({"refresh_token": self._refresh, "grant_type": "refresh_token", "scope": SCOPE,
                                   "token_format": "jwt"})
                return self._access  # type: ignore[return-value]
            except PsnAuthError:
                self._refresh = None  # fall back to the NPSSO
        await self._sign_in()
        return self._access  # type: ignore[return-value]

    async def _get(self, url: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        token = await self._ensure()
        try:
            async with self._session.get(url, params=params, headers={"Authorization": f"Bearer {token}", "User-Agent": UA},
                                         timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 401:
                    self._access, self._expires = None, 0.0
                    raise PsnError("access token expired")
                if r.status != 200:
                    raise PsnError(f"{url} answered {r.status}")
                return await r.json(content_type=None)
        except aiohttp.ClientError as err:
            raise PsnError(str(err)) from err

    async def async_login(self) -> None:
        """Sign in and learn who this is (account ID for Remote Play linking, online ID for showing)."""
        await self._ensure()
        try:
            self.account_id = str((await self._get(ACCOUNT_URL)).get("accountId") or "") or None
        except PsnError:
            _LOGGER.debug("Couldn't read the PSN account ID", exc_info=True)
        try:
            prof = await self._get(PROFILE_URL, {"fields": "onlineId"})
            self.online_id = (prof.get("profile") or {}).get("onlineId")
        except PsnError:
            _LOGGER.debug("Couldn't read the PSN online ID", exc_info=True)

    async def async_presence(self) -> Presence:
        return parse_presence(await self._get(PRESENCE_URL, {"type": "primary"}))
