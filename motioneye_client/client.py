#!/usr/bin/env python
"""Client for motionEye."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import PurePath
from types import TracebackType
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

import aiohttp  # type: ignore

from . import utils
from .const import (
    DEFAULT_ADMIN_USERNAME,
    DEFAULT_SURVEILLANCE_USERNAME,
    DEFAULT_URL_SCHEME,
    KEY_ID,
    KEY_STREAMING_PORT,
    KEY_VIDEO_STREAMING,
)

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


class MotionEyeClientPathError(MotionEyeClientError):
    """Invalid path provided."""


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
        parsed = urlsplit(url)
        if not parsed.scheme or not parsed.netloc:
            raise MotionEyeClientURLParseError(
                "Invalid URL, must have a URL scheme and host: %s" % url
            )

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
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        method: str = "GET",
        admin: bool = True,
    ) -> dict[str, Any] | None:
        """Fetch return code and JSON from motionEye server."""

        serialized_json = json.dumps(data) if data is not None else None
        url = self._build_url(
            path,
            params=params,
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
                        f"Unexpected HTTP response status code {response.status} for request: {url}"
                    )
                    raise MotionEyeClientRequestError(response)
                try:
                    return_value: dict[str, Any] | None = await response.json(
                        content_type=None
                    )
                    return return_value
                except (json.decoder.JSONDecodeError, UnicodeDecodeError) as exc:
                    _LOGGER.error(f"Could not JSON decode: {await response.read()}")
                    raise MotionEyeClientRequestError(response) from exc
        except aiohttp.client_exceptions.ClientConnectorError as exc:
            _LOGGER.warning(f"Connection failed to motionEye: {exc}")
            raise MotionEyeClientConnectionError(exc) from exc
        except aiohttp.client_exceptions.ClientError as exc:
            _LOGGER.warning(f"Request failed to motionEye: {exc}")
            raise MotionEyeClientRequestError(exc) from exc

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

    def get_camera_stream_url(self, camera: dict[str, Any]) -> str | None:
        """Get the camera stream URL."""
        if MotionEyeClient.is_camera_streaming(camera):
            # Extract the hostname from the URL (removing the port if present)
            # Url validity is checking on construction so this will always succeed.
            host = urlsplit(self._url).netloc.split(":")[0]

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
        return self._build_url(
            urljoin(
                self._url,
                f"/picture/{camera[KEY_ID]}/current/",
            ),
            admin=False,
        )

    def _strip_leading_slash(self, path: str) -> str:
        """Strip leading slash from a path."""
        pure_path = PurePath(path)
        if not pure_path.parts:
            raise MotionEyeClientPathError("Could not parse empty path")
        if pure_path.parts[0] == "/":
            path = str(PurePath(*pure_path.parts[1:]))
        return path

    def get_movie_url(self, camera_id: int, path: str, preview: bool = False) -> str:
        """Get the movie playback URL."""
        action = "preview" if preview else "playback"
        return self._build_url(
            urljoin(
                self._url,
                f"/movie/{camera_id}/{action}/{self._strip_leading_slash(path)}",
            )
        )

    def get_image_url(self, camera_id: int, path: str, preview: bool = False) -> str:
        """Get the image URL."""
        action = "preview" if preview else "download"
        return self._build_url(
            urljoin(
                self._url,
                f"/picture/{camera_id}/{action}/{self._strip_leading_slash(path)}",
            )
        )

    @classmethod
    def is_file_type_image(self, file_type: int) -> bool:
        """Determine if a file_type represents an image."""
        # It's an image if the event file_type is <8.
        # See: https://github.com/Motion-Project/motion/blob/master/src/motion.h#L177
        return file_type < 8

    @classmethod
    def is_file_type_movie(self, file_type: int) -> bool:
        """Determine if a file_type represents an image."""
        return not self.is_file_type_image(file_type)

    async def async_get_movies(
        self, camera_id: int, prefix: str | None = None
    ) -> dict[str, Any] | None:
        """Get a motionEye camera config."""
        return await self._async_request(
            f"/movie/{camera_id}/list", params={"prefix": prefix} if prefix else None
        )

    async def async_get_images(
        self, camera_id: int, prefix: str | None = None
    ) -> dict[str, Any] | None:
        """Get a motionEye camera config."""
        return await self._async_request(
            f"/picture/{camera_id}/list", params={"prefix": prefix} if prefix else None
        )
