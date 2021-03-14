#!/usr/bin/env python
"""Client for motionEye."""
import aiohttp  # type: ignore
import hashlib
import logging
import json
from typing import cast, Any, Dict, Optional, Tuple, Type
from . import utils
from urllib.parse import urlencode, urljoin
from types import TracebackType


_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)

# Attempts to vaguely follow the below such that when the server
# supports a more fully-formed API, this client could be converted.
# https://github.com/ccrisan/motioneye/wiki/API-(Draft)


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
        result = await self.async_client_login()
        return self if result else None

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
    ) -> Tuple[int, Optional[Dict[str, Any]]]:
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

        async with coro as response:
            _LOGGER.debug("%s %s -> %i", method, url, response.status)
            if response.status != 200:
                _LOGGER.warning(
                    f"Unexpected return code {response.status} for request: {url}"
                )
            try:
                return (
                    response.status,
                    cast(
                        Optional[Dict[str, Any]], await response.json(content_type=None)
                    ),
                )
            except json.decoder.JSONDecodeError:
                _LOGGER.debug(f"Could not JSON decode: {await response.text()}")
                return (response.status, None)

    async def async_client_login(self) -> bool:
        """Login to the motionEye server."""

        status, response = await self._async_request("/login")
        success = status == 200 and response is not None and "error" not in response
        if not success:
            _LOGGER.warning(
                f"Login failed to {self._base_url}" + ": " + str(response)
                if response
                else ""
            )
        return success

    async def async_client_close(self) -> bool:
        """Disconnect to the MotionEye server."""

        await self._session.close()
        return True

    async def async_get_manifest(self) -> Optional[Dict[str, Any]]:
        """Get the motionEye manifest."""
        _, response = await self._async_request("/manifest.json")
        return response

    async def async_get_server_config(self) -> Optional[Dict[str, Any]]:
        """Get the motionEye server config ."""
        _, response = await self._async_request("/config/main/get")
        return response

    async def async_get_cameras(self) -> Optional[Dict[str, Any]]:
        """Get all motionEye cameras config."""
        _, response = await self._async_request("/config/list")
        return response

    async def async_get_camera(self, camera_id: int) -> Optional[Dict[str, Any]]:
        """Get a motionEye camera config."""
        _, response = await self._async_request(f"/config/{camera_id}/get")
        return response

    async def async_set_camera(self, camera_id: int, config: Dict[str, Any]) -> bool:
        """Set a motionEye camera config."""
        status, _ = await self._async_request(
            f"/config/{camera_id}/set",
            method="POST",
            data=config,
        )
        return status == 200
