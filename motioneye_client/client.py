#!/usr/bin/env python
"""Client for motionEye."""
import aiohttp  # type: ignore
import hashlib
import logging
from typing import cast, Any, Dict, Optional
from . import utils
from urllib.parse import urlencode, urljoin

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)


class MotionEyeClient:
    """MotionEye Client."""

    def __init__(
        self,
        base_url: str,
        username: str,
        password: Optional[str] = None,
    ):
        """Construct a new motionEye client."""
        self._base_url = base_url
        self._session = aiohttp.ClientSession()
        self._username = username

        # TODO: Test empty password
        # TODO: basic http auth
        self._password = password

    def _build_url(self, path: str, params: Optional[Dict[str, Any]] = None) -> str:
        """Build a motionEye URL."""
        params = params or {}
        params.update(
            {
                "_username": self._username,
            }
        )
        url = urljoin(self._base_url, path + "?" + urlencode(params))
        if self._password is not None:
            key = hashlib.sha1(self._password.encode("UTF-8")).hexdigest()
            signature = utils.compute_signature(
                "GET",
                url,
                None,
                key,
            )
            url += f"&_signature={signature}"
        return url

    async def _async_get_json(self, url: str) -> Optional[Dict[str, Any]]:
        """Fetch JSON from motionEye server."""
        # TODO exceptions
        async with self._session.get(url) as response:
            _LOGGER.debug("GET %s -> %i", url, response.status)
            return cast(
                Optional[Dict[str, Any]], await response.json(content_type=None)
            )

    async def async_client_login(self) -> bool:
        """Login to the motionEye server."""

        response = await self._async_get_json(self._build_url("/login"))
        return response is not None

    async def async_get_manifest(self) -> Optional[Dict[str, Any]]:
        """Get the motionEye manifest."""

        return await self._async_get_json(self._build_url("/manifest.json"))

    async def async_client_close(self) -> bool:
        """Disconnect to the MotionEye server."""

        await self._session.close()
        return True
