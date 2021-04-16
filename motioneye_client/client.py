#!/usr/bin/env python
"""Client for motionEye."""
from __future__ import annotations

import aiohttp  # type: ignore
import hashlib
import logging
import json
from typing import Any
from . import utils
from .const import (
    DEFAULT_ADMIN_USERNAME,
    DEFAULT_URL_SCHEME,
    DEFAULT_SURVEILLANCE_USERNAME,
    KEY_STREAMING_PORT,
    KEY_VIDEO_STREAMING,
    KEY_ID,
)
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
from types import TracebackType


_LOGGER = logging.getLogger(__name__)


class MotionEyeClientError(Exception):
    """General MotionEyeClient error."""


class MotionEyeClientInvalidAuthError(MotionEyeClientError):
    """Invalid motionEye authentication."""


class MotionEyeClientConnectionError(MotionEyeClientError):
    """Connection failure."""


class MotionEyeClientRequestError(MotionEyeClientError):
    """Request failure."""


class MotionEyeClientURLParseError(MotionEyeClientError):
    """Unable to parse the URL."""


class MotionEyeClient:
    """MotionEye Client."""

    def __init__(
        self,
        url: str,
        admin_username: str | None = None,
        admin_password: str | None = None,
        surveillance_username: str | None = None,
        surveillance_password: str | None = None,
    ):
        """Construct a new motionEye client."""
        if not url.lower().startswith("http://") and not url.lower().startswith(
            "https://"
        ):
            url = f"{DEFAULT_URL_SCHEME}://" + url

        self._url = url
        self._session = aiohttp.ClientSession()
        self._admin_username = admin_username or DEFAULT_ADMIN_USERNAME
        self._admin_password = admin_password or ""
        self._surveillance_username = (
            surveillance_username or DEFAULT_SURVEILLANCE_USERNAME
        )
        self._surveillance_password = surveillance_password or ""

    async def __aenter__(self) -> "MotionEyeClient" | None:
        """Enter context manager and connect the client."""
        try:
            await self.async_client_login()
        except MotionEyeClientError:
            return None
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: type[BaseException] | None,
        traceback: TracebackType | None,
    ) -> None:
        """Leave context manager and close the client."""
        await self.async_client_close()

    def _build_url(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        data: str | None = None,
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
        url = urljoin(self._url, path + "?" + urlencode(params))
        key = hashlib.sha1(password.encode("UTF-8")).hexdigest()
        signature = utils.compute_signature(method, url, data, key)
        url += f"&_signature={signature}"
        return url

    async def _async_request(
        self,
        path: str,
        data: dict[str, Any] | None = None,
        method: str = "GET",
        admin: bool = True,
    ) -> dict[str, Any] | None:
        """Fetch return code and JSON from motionEye server."""

        serialized_json = json.dumps(data) if data is not None else None
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
                        f"Authentication failed in request to {url} : {response}"
                    )
                    raise MotionEyeClientInvalidAuthError(response)
                elif not response.ok:
                    _LOGGER.warning(
                        f"Unexpected return code {response.status} for request: {url}"
                    )
                    raise MotionEyeClientRequestError(response)
                try:
                    return_value: dict[str, Any] | None = await response.json(
                        content_type=None
                    )
                    return return_value
                except json.decoder.JSONDecodeError:
                    _LOGGER.debug(f"Could not JSON decode: {await response.text()}")
                    raise MotionEyeClientRequestError(response)
        except aiohttp.client_exceptions.ClientConnectorError as exc:
            _LOGGER.warning(f"Connection failed to motionEye: {exc}")
            raise MotionEyeClientConnectionError(exc)

    async def async_client_login(self) -> dict[str, Any] | None:
        """Login to the motionEye server."""

        return await self._async_request("/login")

    async def async_client_close(self) -> bool:
        """Disconnect to the MotionEye server."""

        await self._session.close()
        return True

    async def async_get_manifest(self) -> dict[str, Any] | None:
        """Get the motionEye manifest."""
        return await self._async_request("/manifest.json")

    async def async_get_server_config(self) -> dict[str, Any] | None:
        """Get the motionEye server config ."""
        return await self._async_request("/config/main/get")

    async def async_get_cameras(self) -> dict[str, Any] | None:
        """Get all motionEye cameras config."""
        return await self._async_request("/config/list")

    async def async_get_camera(self, camera_id: int) -> dict[str, Any] | None:
        """Get a motionEye camera config."""
        return await self._async_request(f"/config/{camera_id}/get")

    async def async_set_camera(
        self, camera_id: int, config: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Set a motionEye camera config."""
        return await self._async_request(
            f"/config/{camera_id}/set",
            method="POST",
            data=config,
        )

    async def async_action(self, camera_id: int, action: str) -> dict[str, Any] | None:
        """Trigger a motionEye action."""
        return await self._async_request(
            f"/action/{camera_id}/{action}",
            method="POST",
            data={},
        )

    @classmethod
    def is_camera_streaming(cls, camera: dict[str, Any] | None) -> bool:
        """Determine if a given camera is streaming."""
        return bool(
            camera
            and KEY_STREAMING_PORT in camera
            and camera.get(KEY_VIDEO_STREAMING, False)
        )

    def get_camera_steam_url(self, camera: dict[str, Any]) -> str | None:
        """Get the camera stream URL."""
        if MotionEyeClient.is_camera_streaming(camera):
            # Attempt to extract the hostname from the URL (removing the port if present)
            host = urlsplit(self._url).netloc.split(":")[0]
            if not host:
                raise MotionEyeClientURLParseError(
                    f"Could not extract hostname from {self._url}."
                )

            # motion (the process underlying motionEye) cannot natively do https on the
            # stream port, it will always be http regardless of what protocol is used to
            # talk to motionEye itself.
            return urlunsplit(
                (
                    DEFAULT_URL_SCHEME,
                    f"{host}:{camera[KEY_STREAMING_PORT]}",
                    "/",
                    "",
                    "",
                )
            )
        return None

    def get_camera_snapshot_url(self, camera: dict[str, Any]) -> str | None:
        """Get the camera stream URL."""
        if not MotionEyeClient.is_camera_streaming(camera) or KEY_ID not in camera:
            return None
        snapshot_url = urljoin(
            self._url,
            f"/picture/{camera[KEY_ID]}/current/?_username={self._surveillance_username}",
        )
        snapshot_url += "&_signature=" + utils.compute_signature_from_password(
            "GET",
            snapshot_url,
            None,
            self._surveillance_password,
        )
        return snapshot_url
