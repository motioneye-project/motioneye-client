#!/usr/bin/env python
"""Client for motionEye."""
import aiohttp  # type: ignore
import hashlib
import logging
import json
from typing import cast, Any, Dict, Optional, Type
from . import utils
from urllib.parse import urlencode, urljoin
from types import TracebackType


_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)

# Attempts to vaguely follow the below such that when the server
# supports a more fully-formed API, this client could be converted.
# https://github.com/ccrisan/motioneye/wiki/API-(Draft)


class MotionEyeClientError(Exception):
    """General MotionEyeClient error."""


class MotionEyeClientInvalidAuth(MotionEyeClientError):
    """Invalid motionEye authentication."""


class MotionEyeClientConnectionFailure(MotionEyeClientError):
    """Connection failure."""


class MotionEyeClientRequestFailed(MotionEyeClientError):
    """Request failure."""


class MotionEyeClient:
    """MotionEye Client."""

    def __init__(
        self,
        base_url: str,
        username: str = "admin",
        password: str = "",
    ):
        """Construct a new motionEye client."""
        self._base_url = base_url
        self._session = aiohttp.ClientSession()
        self._username = username

        # TODO: basic http auth
        self._password = password

    async def __aenter__(self) -> Optional["MotionEyeClient"]:
        """Enter context manager and connect the client."""
        try:
            await self.async_client_login()
        except MotionEyeClientError:
            return None
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        """Leave context manager and close the client."""
        await self.async_client_close()

    def _build_url(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[str] = None,
        method: str = "GET",
    ) -> str:
        """Build a motionEye URL."""
        params = params or {}
        params.update(
            {
                "_username": self._username,
            }
        )
        url = urljoin(self._base_url, path + "?" + urlencode(params))
        key = hashlib.sha1(self._password.encode("UTF-8")).hexdigest()
        signature = utils.compute_signature(method, url, data, key)
        url += f"&_signature={signature}"
        return url

    async def _async_request(
        self, path: str, data: Optional[Dict[str, Any]] = None, method: str = "GET"
    ) -> Optional[Dict[str, Any]]:
        """Fetch return code and JSON from motionEye server."""

        serialized_json = json.dumps(data) if data else None
        url = self._build_url(path, data=serialized_json, method=method)

        headers = {}
        if serialized_json:
            headers = {"Content-Type": "application/json"}

        if method == "GET":
            func = self._session.get
        else:
            func = self._session.post

        coro = func(url, data=serialized_json, headers=headers)

        try:
            async with coro as response:
                _LOGGER.debug("%s %s -> %i", method, url, response.status)
                if response.status == 403:
                    _LOGGER.warning(
                        f"Authentication failed in request to {self._base_url}: {response}"
                    )
                    raise MotionEyeClientInvalidAuth(response)
                elif not response.ok:
                    _LOGGER.warning(
                        f"Unexpected return code {response.status} for request: {url}"
                    )
                    raise MotionEyeClientRequestFailed(response)
                try:
                    return cast(
                        Optional[Dict[str, Any]],
                        await response.json(content_type=None),
                    )
                except json.decoder.JSONDecodeError:
                    _LOGGER.debug(f"Could not JSON decode: {await response.text()}")
                    raise MotionEyeClientRequestFailed(response)
        except aiohttp.client_exceptions.ClientConnectorError as exc:
            _LOGGER.warning(f"Connection failed to motionEye: {exc}")
            raise MotionEyeClientConnectionFailure(exc)

    async def async_client_login(self) -> Optional[Dict[str, Any]]:
        """Login to the motionEye server."""

        return await self._async_request("/login")

    async def async_client_close(self) -> bool:
        """Disconnect to the MotionEye server."""

        await self._session.close()
        return True

    async def async_get_manifest(self) -> Optional[Dict[str, Any]]:
        """Get the motionEye manifest."""
        return await self._async_request("/manifest.json")

    async def async_get_server_config(self) -> Optional[Dict[str, Any]]:
        """Get the motionEye server config ."""
        return await self._async_request("/config/main/get")

    async def async_get_cameras(self) -> Optional[Dict[str, Any]]:
        """Get all motionEye cameras config."""
        return await self._async_request("/config/list")

    async def async_get_camera(self, camera_id: int) -> Optional[Dict[str, Any]]:
        """Get a motionEye camera config."""
        return await self._async_request(f"/config/{camera_id}/get")

    async def async_set_camera(
        self, camera_id: int, config: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Set a motionEye camera config."""
        return await self._async_request(
            f"/config/{camera_id}/set",
            method="POST",
            data=config,
        )
