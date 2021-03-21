#!/usr/bin/env python
"""Client for motionEye."""
import aiohttp  # type: ignore
import hashlib
import logging
import json
from typing import cast, Any, Dict, Optional, Type
from . import utils
from .const import (
    DEFAULT_ADMIN_USERNAME,
    DEFAULT_SURVEILLANCE_USERNAME,
    KEY_STREAMING_PORT,
    KEY_VIDEO_STREAMING,
    KEY_ID,
)
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
        host: str,
        port: int,
        admin_username: Optional[str] = None,
        admin_password: Optional[str] = None,
        surveillance_username: Optional[str] = None,
        surveillance_password: Optional[str] = None,
    ):
        """Construct a new motionEye client."""
        self._host = host
        self._port = port
        self._session = aiohttp.ClientSession()
        self._admin_username = admin_username or DEFAULT_ADMIN_USERNAME
        self._admin_password = admin_password or ""
        self._surveillance_username = (
            surveillance_username or DEFAULT_SURVEILLANCE_USERNAME
        )
        self._surveillance_password = surveillance_password or ""
        _LOGGER.error(
            "%s / %s / %s / %s"
            % (
                self._admin_username,
                self._admin_password,
                self._surveillance_username,
                self._surveillance_password,
            )
        )
        # TODO: basic http auth

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
        admin: bool = True,
    ) -> str:
        """Build a motionEye URL."""
        username = self._admin_username if admin else self._surveillance_username
        password = self._admin_password if admin else self._surveillance_password

        params = params or {}
        params.update(
            {
                "_username": username,
            }
        )
        url = urljoin(
            f"http://{self._host}:{self._port}", path + "?" + urlencode(params)
        )
        key = hashlib.sha1(password.encode("UTF-8")).hexdigest()
        signature = utils.compute_signature(method, url, data, key)
        url += f"&_signature={signature}"
        return url

    async def _async_request(
        self,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        method: str = "GET",
        admin: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Fetch return code and JSON from motionEye server."""

        serialized_json = json.dumps(data) if data else None
        url = self._build_url(
            path,
            data=serialized_json,
            method=method,
            admin=admin,
        )

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
                        f"Authentication failed in request to {self._host}:{self._port} : {response}"
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

    @classmethod
    def is_camera_streaming(cls, camera: Dict[str, Any]) -> bool:
        """Determine if a given camera is streaming."""
        return bool(
            camera
            and KEY_STREAMING_PORT in camera
            and camera.get(KEY_VIDEO_STREAMING, False)
        )

    def get_camera_steam_url(self, camera: Dict[str, Any]) -> Optional[str]:
        """Get the camera stream URL."""
        if MotionEyeClient.is_camera_streaming(camera):
            return f"http://{self._host}:{camera[KEY_STREAMING_PORT]}/"
        return None

    def get_camera_snapshot_url(self, camera: Dict[str, Any]) -> Optional[str]:
        """Get the camera stream URL."""
        if not MotionEyeClient.is_camera_streaming(camera) or KEY_ID not in camera:
            return None
        snapshot_url = f"http://{self._host}:{self._port}/picture/{camera[KEY_ID]}/current/?_username={self._surveillance_username}"
        snapshot_url += "&_signature=" + utils.compute_signature_from_password(
            "GET",
            snapshot_url,
            None,
            self._surveillance_password,
        )
        return snapshot_url
