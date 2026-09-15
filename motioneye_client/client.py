#!/usr/bin/env python
"""Client for motionEye."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import hashlib
import json
import logging
from pathlib import PurePath
from types import TracebackType
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

import aiohttp

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


class MotionEyeClientMediaResponse:
    """Streaming media response from motionEye."""

    def __init__(self, response: aiohttp.ClientResponse) -> None:
        """Initialize a streaming media response."""
        self.response = response

    @property
    def status(self) -> int:
        """Return the HTTP status code."""
        return self.response.status

    @property
    def headers(self) -> aiohttp.typedefs.LooseHeaders:
        """Return the HTTP response headers."""
        return self.response.headers

    @property
    def content(self) -> aiohttp.StreamReader:
        """Return the streaming response body."""
        return self.response.content


class MotionEyeClient:
    """MotionEye Client."""

    def __init__(
        self,
        url: str,
        admin_username: str | None = None,
        admin_password: str | None = None,
        surveillance_username: str | None = None,
        surveillance_password: str | None = None,
        session: aiohttp.ClientSession | None = None,
    ):
        """Construct a new motionEye client."""
        parsed = urlsplit(url)
        if not parsed.scheme or not parsed.netloc:
            raise MotionEyeClientURLParseError(
                "Invalid URL, must have a URL scheme and host: %s" % url
            )

        self._url = url
        if session:
            self._session = session
            self._created_session = False
        else:
            self._session = aiohttp.ClientSession()
            self._created_session = True
        self._admin_username = admin_username or DEFAULT_ADMIN_USERNAME
        self._admin_password = admin_password or ""
        self._surveillance_username = (
            surveillance_username or DEFAULT_SURVEILLANCE_USERNAME
        )
        self._surveillance_password = surveillance_password or ""
        self._auth_mode: str | None = None
        self._session_cookie: str | None = None

    async def __aenter__(self) -> MotionEyeClient | None:
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

    def _build_session_url(
        self, path: str, params: dict[str, Any] | None = None
    ) -> str:
        """Build a URL for session-authenticated motionEye requests."""
        query = f"?{urlencode(params)}" if params else ""
        return urljoin(self._url, path + query)

    def _session_headers(self, serialized_json: str | None = None) -> dict[str, str]:
        """Build headers for a session-authenticated request."""
        headers: dict[str, str] = {}
        if serialized_json is not None:
            headers["Content-Type"] = "application/json"
        if self._session_cookie:
            headers["Cookie"] = f"user={self._session_cookie}"
        return headers

    async def _async_session_login(self) -> dict[str, Any] | None:
        """Login using session authentication introduced in motionEye 0.44."""
        url = urljoin(self._url, "/login")

        try:
            async with self._session.post(
                url,
                data={
                    "username": self._admin_username,
                    "password": self._admin_password,
                },
            ) as response:
                _LOGGER.debug(f"POST {url} -> {response.status}")

                # Older motionEye releases don't implement POST /login. Their
                # BaseHandler returns 400 for unsupported methods, while other
                # deployments may return 404/405.
                if response.status in (400, 404, 405):
                    return None

                if response.status in (401, 403):
                    _LOGGER.warning(f"Authentication failed in request to {url}")
                    raise MotionEyeClientInvalidAuthError(response)

                if not response.ok:
                    _LOGGER.warning(
                        f"Unexpected HTTP response status code {response.status} for request: {url}"
                    )
                    raise MotionEyeClientRequestError(response)

                cookie = response.cookies.get("user")
                if cookie is None:
                    _LOGGER.warning(
                        "motionEye session login succeeded without a user cookie"
                    )
                    raise MotionEyeClientRequestError(response)

                # Keep the cookie explicitly. aiohttp's default CookieJar rejects
                # cookies set by IP-address hosts unless unsafe=True, while IP
                # addresses are common for motionEye installations.
                self._session_cookie = cookie.value
                self._auth_mode = "session"

                try:
                    return_value: dict[str, Any] | None = await response.json(
                        content_type=None
                    )
                    return return_value
                except (json.decoder.JSONDecodeError, UnicodeDecodeError) as exc:
                    _LOGGER.error(f"Could not JSON decode: {await response.read()!r}")
                    raise MotionEyeClientRequestError(response) from exc
        except aiohttp.client_exceptions.ClientConnectorError as exc:
            _LOGGER.warning(f"Connection failed to motionEye: {exc}")
            raise MotionEyeClientConnectionError(exc) from exc
        except aiohttp.client_exceptions.ClientError as exc:
            _LOGGER.warning(f"Request failed to motionEye: {exc}")
            raise MotionEyeClientRequestError(exc) from exc

    async def _async_legacy_login(self) -> dict[str, Any] | None:
        """Login using legacy signature authentication."""
        self._auth_mode = "legacy"
        return await self._async_request("/login", allow_reauth=False)

    async def _async_request(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        method: str = "GET",
        admin: bool = True,
        allow_reauth: bool = True,
    ) -> dict[str, Any] | None:
        """Fetch return code and JSON from motionEye server."""

        serialized_json = json.dumps(data) if data is not None else None

        if self._auth_mode == "session":
            url = self._build_session_url(path, params=params)
            headers = self._session_headers(serialized_json)
        else:
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

        func = self._session.get if method == "GET" else self._session.post

        try:
            async with func(url, data=serialized_json, headers=headers) as response:
                _LOGGER.debug(f"{method} {url} -> {response.status}")

                if response.status == 403:
                    if self._auth_mode == "session" and allow_reauth:
                        _LOGGER.debug("motionEye session expired; logging in again")
                        await self._async_session_login()
                        return await self._async_request(
                            path,
                            params=params,
                            data=data,
                            method=method,
                            admin=admin,
                            allow_reauth=False,
                        )

                    _LOGGER.warning(
                        f"Authentication failed in request to {url} : {response}"
                    )
                    raise MotionEyeClientInvalidAuthError(response)

                if not response.ok:
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
                    _LOGGER.error(f"Could not JSON decode: {await response.read()!r}")
                    raise MotionEyeClientRequestError(response) from exc
        except aiohttp.client_exceptions.ClientConnectorError as exc:
            _LOGGER.warning(f"Connection failed to motionEye: {exc}")
            raise MotionEyeClientConnectionError(exc) from exc
        except aiohttp.client_exceptions.ClientError as exc:
            _LOGGER.warning(f"Request failed to motionEye: {exc}")
            raise MotionEyeClientRequestError(exc) from exc

    async def async_client_login(self) -> dict[str, Any] | None:
        """Login to the motionEye server."""
        session_response = await self._async_session_login()
        if self._auth_mode == "session":
            return session_response
        return await self._async_legacy_login()

    async def async_client_close(self) -> bool:
        """Disconnect from the MotionEye server."""
        if self._created_session:
            await self._session.close()
        return True

    async def async_get_manifest(self) -> dict[str, Any] | None:
        """Get the motionEye manifest."""
        return await self._async_request("/manifest.json")

    async def async_get_camera_snapshot(
        self, camera_id: int, allow_reauth: bool = True
    ) -> bytes:
        """Fetch the current camera snapshot."""
        path = f"/picture/{camera_id}/current/"

        if self._auth_mode == "session":
            url = self._build_session_url(path)
            headers = self._session_headers()
        else:
            url = self._build_url(path, admin=False)
            headers = {}

        try:
            async with self._session.get(url, headers=headers) as response:
                _LOGGER.debug(f"GET {url} -> {response.status}")

                if response.status == 403:
                    if self._auth_mode == "session" and allow_reauth:
                        _LOGGER.debug("motionEye session expired; logging in again")
                        await self._async_session_login()
                        return await self.async_get_camera_snapshot(
                            camera_id, allow_reauth=False
                        )

                    _LOGGER.warning(
                        f"Authentication failed in request to {url} : {response}"
                    )
                    raise MotionEyeClientInvalidAuthError(response)

                if not response.ok:
                    _LOGGER.warning(
                        f"Unexpected HTTP response status code {response.status} for request: {url}"
                    )
                    raise MotionEyeClientRequestError(response)

                return await response.read()
        except aiohttp.client_exceptions.ClientConnectorError as exc:
            _LOGGER.warning(f"Connection failed to motionEye: {exc}")
            raise MotionEyeClientConnectionError(exc) from exc
        except aiohttp.client_exceptions.ClientError as exc:
            _LOGGER.warning(f"Request failed to motionEye: {exc}")
            raise MotionEyeClientRequestError(exc) from exc

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
            # Remote motionEye instances will provide a host in their camera
            # dictionary, use that if specified, otherwise extract the hostname
            # from the URL (removing the port if present). Url validity is
            # checked on construction so this will always succeed.
            host = camera.get("host", urlsplit(self._url).netloc.split(":")[0])

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

    async def async_get_media(
        self,
        camera_id: int,
        path: str,
        *,
        image: bool,
        preview: bool = False,
        allow_reauth: bool = True,
    ) -> bytes:
        """Fetch saved image or movie data using the active authentication mode."""
        media_type = "picture" if image else "movie"
        action = "preview" if preview else ("download" if image else "playback")
        request_path = (
            f"/{media_type}/{camera_id}/{action}/{self._strip_leading_slash(path)}"
        )

        if self._auth_mode == "session":
            url = self._build_session_url(request_path)
            headers = self._session_headers()
        else:
            url = self._build_url(urljoin(self._url, request_path), admin=False)
            headers = {}

        try:
            async with self._session.get(url, headers=headers) as response:
                _LOGGER.debug(f"GET {url} -> {response.status}")

                if response.status == 403:
                    if self._auth_mode == "session" and allow_reauth:
                        _LOGGER.debug("motionEye session expired; logging in again")
                        await self._async_session_login()
                        return await self.async_get_media(
                            camera_id,
                            path,
                            image=image,
                            preview=preview,
                            allow_reauth=False,
                        )

                    _LOGGER.warning(
                        f"Authentication failed in request to {url} : {response}"
                    )
                    raise MotionEyeClientInvalidAuthError(response)

                if not response.ok:
                    _LOGGER.warning(
                        f"Unexpected HTTP response status code {response.status} for request: {url}"
                    )
                    raise MotionEyeClientRequestError(response)

                return await response.read()
        except aiohttp.client_exceptions.ClientConnectorError as exc:
            _LOGGER.warning(f"Connection failed to motionEye: {exc}")
            raise MotionEyeClientConnectionError(exc) from exc
        except aiohttp.client_exceptions.ClientError as exc:
            _LOGGER.warning(f"Request failed to motionEye: {exc}")
            raise MotionEyeClientRequestError(exc) from exc

    @asynccontextmanager
    async def async_get_media_stream(
        self,
        camera_id: int,
        path: str,
        *,
        image: bool,
        preview: bool = False,
        range_header: str | None = None,
        allow_reauth: bool = True,
    ) -> AsyncIterator[MotionEyeClientMediaResponse]:
        """Open saved media as a streaming response."""
        media_type = "picture" if image else "movie"
        action = "preview" if preview else ("download" if image else "playback")
        request_path = (
            f"/{media_type}/{camera_id}/{action}/{self._strip_leading_slash(path)}"
        )
        reauth_allowed = allow_reauth

        while True:
            if self._auth_mode == "session":
                url = self._build_session_url(request_path)
                headers = self._session_headers()
            else:
                url = self._build_url(
                    urljoin(self._url, request_path), admin=False
                )
                headers = {}

            if range_header is not None:
                headers["Range"] = range_header

            retry = False

            try:
                async with self._session.get(url, headers=headers) as response:
                    _LOGGER.debug(f"GET {url} -> {response.status}")

                    if response.status == 403:
                        if self._auth_mode == "session" and reauth_allowed:
                            retry = True
                        else:
                            _LOGGER.warning(
                                f"Authentication failed in request to {url} : "
                                f"{response}"
                            )
                            raise MotionEyeClientInvalidAuthError(response)

                    elif not response.ok and response.status != 416:
                        _LOGGER.warning(
                            f"Unexpected HTTP response status code "
                            f"{response.status} for request: {url}"
                        )
                        raise MotionEyeClientRequestError(response)

                    else:
                        yield MotionEyeClientMediaResponse(response)
                        return

            except aiohttp.client_exceptions.ClientConnectorError as exc:
                _LOGGER.warning(f"Connection failed to motionEye: {exc}")
                raise MotionEyeClientConnectionError(exc) from exc
            except aiohttp.client_exceptions.ClientError as exc:
                _LOGGER.warning(f"Request failed to motionEye: {exc}")
                raise MotionEyeClientRequestError(exc) from exc

            if retry:
                _LOGGER.debug("motionEye session expired; logging in again")
                await self._async_session_login()
                reauth_allowed = False

    def get_movie_url(self, camera_id: int, path: str, preview: bool = False) -> str:
        """Get the movie playback URL."""
        action = "preview" if preview else "playback"
        return self._build_url(
            urljoin(
                self._url,
                f"/movie/{camera_id}/{action}/{self._strip_leading_slash(path)}",
            ),
            admin=False,
        )

    def get_image_url(self, camera_id: int, path: str, preview: bool = False) -> str:
        """Get the image URL."""
        action = "preview" if preview else "download"
        return self._build_url(
            urljoin(
                self._url,
                f"/picture/{camera_id}/{action}/{self._strip_leading_slash(path)}",
            ),
            admin=False,
        )

    @classmethod
    def is_file_type_image(cls, file_type: int) -> bool:
        """Determine if a file_type represents an image."""
        # It's an image if the event file_type is <8.
        # See: https://github.com/Motion-Project/motion/blob/master/src/motion.h#L177
        return file_type < 8

    @classmethod
    def is_file_type_movie(cls, file_type: int) -> bool:
        """Determine if a file_type represents an image."""
        return not cls.is_file_type_image(file_type)

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
