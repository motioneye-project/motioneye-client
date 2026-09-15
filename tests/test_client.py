"""Test the motionEye client."""

from __future__ import annotations

import asyncio
from contextlib import closing
import socket
from typing import Any
from unittest.mock import AsyncMock, Mock

import aiohttp
from aiohttp import web
import pytest

from motioneye_client.client import (
    MotionEyeClient,
    MotionEyeClientConnectionError,
    MotionEyeClientInvalidAuthError,
    MotionEyeClientPathError,
    MotionEyeClientRequestError,
    MotionEyeClientURLParseError,
)
from motioneye_client.const import (
    KEY_HOST,
    KEY_ID,
    KEY_STREAMING_PORT,
    KEY_VIDEO_STREAMING,
)


async def _create_motioneye_server(aiohttp_server: Any, handlers: list[Any]) -> Any:
    app = web.Application()
    app.add_routes(handlers)

    # Add a login handler unless one is explicitly added (i.e. for testing logins).
    for route in handlers:
        if "/login" == route.path:
            break
    else:
        login_handler = AsyncMock(return_value=web.json_response({}))
        app.add_routes([web.get("/login", login_handler)])
    return await aiohttp_server(app)


@pytest.mark.asyncio
async def test_signature(aiohttp_server: Any) -> None:
    """Test signature."""

    async def login_handler(request: web.Request) -> web.Response:
        assert "_signature" in request.query
        assert request.query["_signature"] == "010aec346f06cb5cf7f25dd5e3a33798d3032ae7"
        return web.json_response({})

    server = await _create_motioneye_server(
        aiohttp_server, [web.get("/login", login_handler)]
    )
    async with MotionEyeClient(
        str(server.make_url("/")),
        "admin",
        "password",
        "user",
        "user_password",
    ) as client:
        assert client


@pytest.mark.asyncio
async def test_failed_request(caplog: Any, aiohttp_server: Any) -> None:
    """Test a non-JSON response."""

    async def login_handler(request: web.Request) -> web.Response:
        raise web.HTTPNotFound()

    server = await _create_motioneye_server(
        aiohttp_server, [web.get("/login", login_handler)]
    )

    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert not client
    assert "Unexpected HTTP response status" in caplog.text


@pytest.mark.asyncio
async def test_non_200_response(aiohttp_server: Any) -> None:
    """Test a non-200 response."""

    async def login_handler(request: web.Request) -> web.Response:
        return web.Response(body="this is not json")

    server = await _create_motioneye_server(
        aiohttp_server, [web.get("/login", login_handler)]
    )

    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert not client


@pytest.mark.asyncio
async def test_cannot_connect(caplog: Any, aiohttp_server: Any) -> None:
    """Test a failed connection."""

    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("localhost", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        port = s.getsockname()[1]

        async with MotionEyeClient(f"http://localhost:{port}") as client:
            assert not client
    assert "Connection failed" in caplog.text


@pytest.mark.asyncio
async def test_client_login_success(aiohttp_server: Any) -> None:
    """Test successful client login."""

    login_handler = AsyncMock(return_value=web.json_response({}))

    server = await _create_motioneye_server(
        aiohttp_server, [web.get("/login", login_handler)]
    )

    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert client


@pytest.mark.asyncio
async def test_session_login_and_request(aiohttp_server: Any) -> None:
    """Test motionEye 0.44 session login and authenticated request."""

    async def login_handler(request: web.Request) -> web.Response:
        data = await request.post()
        assert data["username"] == "admin"
        assert data["password"] == "password"
        response = web.json_response({"user": "admin"})
        response.set_cookie("user", "session-token")
        return response

    async def config_handler(request: web.Request) -> web.Response:
        assert "_username" not in request.query
        assert "_signature" not in request.query
        assert request.headers["Cookie"] == "user=session-token"
        return web.json_response({"key": "value"})

    server = await _create_motioneye_server(
        aiohttp_server,
        [
            web.post("/login", login_handler),
            web.get("/config/main/get", config_handler),
        ],
    )

    async with MotionEyeClient(
        str(server.make_url("/")),
        admin_username="admin",
        admin_password="password",
    ) as client:
        assert client
        assert await client.async_get_server_config() == {"key": "value"}


@pytest.mark.asyncio
async def test_session_request_with_params_and_json(aiohttp_server: Any) -> None:
    """Test query parameters and JSON body with session authentication."""

    async def login_handler(request: web.Request) -> web.Response:
        response = web.json_response({"user": "admin"})
        response.set_cookie("user", "session-token")
        return response

    async def images_handler(request: web.Request) -> web.Response:
        assert request.query["prefix"] == "foo"
        assert request.headers["Cookie"] == "user=session-token"
        return web.json_response({"mediaList": []})

    async def set_camera_handler(request: web.Request) -> web.Response:
        assert request.headers["Content-Type"] == "application/json"
        assert request.headers["Cookie"] == "user=session-token"
        assert await request.json() == {"key": "value"}
        return web.json_response({})

    server = await _create_motioneye_server(
        aiohttp_server,
        [
            web.post("/login", login_handler),
            web.get("/picture/1/list", images_handler),
            web.post("/config/1/set", set_camera_handler),
        ],
    )

    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert client
        assert await client.async_get_images(1, prefix="foo") == {"mediaList": []}
        assert await client.async_set_camera(1, {"key": "value"}) == {}


@pytest.mark.asyncio
async def test_session_reauthentication(aiohttp_server: Any) -> None:
    """Test automatic re-login after an expired motionEye session."""

    login_count = 0
    request_count = 0

    async def login_handler(request: web.Request) -> web.Response:
        nonlocal login_count
        login_count += 1
        response = web.json_response({"user": "admin"})
        response.set_cookie("user", f"session-{login_count}")
        return response

    async def config_handler(request: web.Request) -> web.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            assert request.headers["Cookie"] == "user=session-1"
            return web.json_response({"error": "unauthorized"}, status=403)

        assert request.headers["Cookie"] == "user=session-2"
        return web.json_response({"key": "value"})

    server = await _create_motioneye_server(
        aiohttp_server,
        [
            web.post("/login", login_handler),
            web.get("/config/main/get", config_handler),
        ],
    )

    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert client
        assert await client.async_get_server_config() == {"key": "value"}

    assert login_count == 2
    assert request_count == 2


@pytest.mark.asyncio
async def test_session_login_invalid_credentials(
    caplog: Any, aiohttp_server: Any
) -> None:
    """Test invalid credentials with motionEye 0.44 session login."""

    async def login_handler(request: web.Request) -> web.Response:
        return web.json_response({"error": "invalid credentials"}, status=401)

    server = await _create_motioneye_server(
        aiohttp_server, [web.post("/login", login_handler)]
    )

    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert not client

    assert "Authentication failed" in caplog.text


@pytest.mark.asyncio
async def test_session_login_missing_cookie(caplog: Any, aiohttp_server: Any) -> None:
    """Test a successful session login response without a session cookie."""

    async def login_handler(request: web.Request) -> web.Response:
        return web.json_response({"user": "admin"})

    server = await _create_motioneye_server(
        aiohttp_server, [web.post("/login", login_handler)]
    )

    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert not client

    assert "without a user cookie" in caplog.text


@pytest.mark.asyncio
async def test_session_login_bad_response(caplog: Any, aiohttp_server: Any) -> None:
    """Test an unexpected response to session login."""

    async def login_handler(request: web.Request) -> web.Response:
        return web.json_response({"error": "failed"}, status=500)

    server = await _create_motioneye_server(
        aiohttp_server, [web.post("/login", login_handler)]
    )

    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert not client

    assert "Unexpected HTTP response status code 500" in caplog.text


@pytest.mark.asyncio
async def test_session_login_non_json_response(aiohttp_server: Any) -> None:
    """Test a non-JSON session login response."""

    async def login_handler(request: web.Request) -> web.Response:
        response = web.Response(text="not json")
        response.set_cookie("user", "session-token")
        return response

    server = await _create_motioneye_server(
        aiohttp_server, [web.post("/login", login_handler)]
    )

    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert not client


@pytest.mark.asyncio
async def test_session_request_connection_error(
    caplog: Any, aiohttp_server: Any
) -> None:
    """Test a connection error after a successful session login."""

    async def login_handler(request: web.Request) -> web.Response:
        response = web.json_response({"user": "admin"})
        response.set_cookie("user", "session-token")
        return response

    server = await _create_motioneye_server(
        aiohttp_server, [web.post("/login", login_handler)]
    )

    client = MotionEyeClient(str(server.make_url("/")))
    assert await client.async_client_login() == {"user": "admin"}
    await server.close()

    with pytest.raises(MotionEyeClientConnectionError):
        await client.async_get_server_config()
    assert "Connection failed to motionEye" in caplog.text
    await client.async_client_close()


@pytest.mark.asyncio
async def test_session_request_client_error(caplog: Any, aiohttp_server: Any) -> None:
    """Test an aiohttp client error after a successful session login."""

    async def login_handler(request: web.Request) -> web.Response:
        response = web.json_response({"user": "admin"})
        response.set_cookie("user", "session-token")
        return response

    server = await _create_motioneye_server(
        aiohttp_server, [web.post("/login", login_handler)]
    )

    async with aiohttp.ClientSession() as session:
        client = MotionEyeClient(str(server.make_url("/")), session=session)
        assert await client.async_client_login() == {"user": "admin"}
        session.get = Mock(  # type: ignore[method-assign]
            side_effect=aiohttp.ClientError("request failed")
        )

        with pytest.raises(MotionEyeClientRequestError):
            await client.async_get_server_config()

    assert "Request failed to motionEye" in caplog.text


@pytest.mark.asyncio
async def test_session_camera_snapshot(aiohttp_server: Any) -> None:
    """Test fetching a camera snapshot with session authentication."""
    requests = {"snapshot": 0}

    async def login_handler(request: web.Request) -> web.Response:
        response = web.json_response({"user": "admin"})
        response.set_cookie("user", "session-token")
        return response

    async def snapshot_handler(request: web.Request) -> web.Response:
        requests["snapshot"] += 1
        assert request.cookies.get("user") == "session-token"
        return web.Response(body=b"jpeg-data", content_type="image/jpeg")

    server = await _create_motioneye_server(
        aiohttp_server,
        [
            web.post("/login", login_handler),
            web.get("/picture/1/current/", snapshot_handler),
        ],
    )

    client = MotionEyeClient(str(server.make_url("/")))
    await client.async_client_login()

    assert await client.async_get_camera_snapshot(1) == b"jpeg-data"
    assert requests["snapshot"] == 1
    await client.async_client_close()


@pytest.mark.asyncio
async def test_session_camera_snapshot_reauth(aiohttp_server: Any) -> None:
    """Test snapshot reauthentication after an expired session."""
    login_count = 0

    async def login_handler(request: web.Request) -> web.Response:
        nonlocal login_count
        login_count += 1
        response = web.json_response({"user": "admin"})
        response.set_cookie("user", f"session-token-{login_count}")
        return response

    async def snapshot_handler(request: web.Request) -> web.Response:
        if request.cookies.get("user") == "session-token-1":
            return web.Response(status=403)
        assert request.cookies.get("user") == "session-token-2"
        return web.Response(body=b"jpeg-data", content_type="image/jpeg")

    server = await _create_motioneye_server(
        aiohttp_server,
        [
            web.post("/login", login_handler),
            web.get("/picture/1/current/", snapshot_handler),
        ],
    )

    client = MotionEyeClient(str(server.make_url("/")))
    await client.async_client_login()

    assert await client.async_get_camera_snapshot(1) == b"jpeg-data"
    assert login_count == 2
    await client.async_client_close()


@pytest.mark.asyncio
async def test_legacy_camera_snapshot(aiohttp_server: Any) -> None:
    """Test fetching a snapshot with legacy signature authentication."""

    async def login_handler(request: web.Request) -> web.Response:
        return web.json_response({})

    async def snapshot_handler(request: web.Request) -> web.Response:
        assert request.query["_username"] == "user"
        assert "_signature" in request.query
        return web.Response(body=b"jpeg-data", content_type="image/jpeg")

    server = await _create_motioneye_server(
        aiohttp_server,
        [
            web.get("/login", login_handler),
            web.get("/picture/1/current/", snapshot_handler),
        ],
    )

    client = MotionEyeClient(str(server.make_url("/")))
    await client.async_client_login()

    assert await client.async_get_camera_snapshot(1) == b"jpeg-data"
    await client.async_client_close()


@pytest.mark.asyncio
async def test_session_camera_snapshot_forbidden_after_reauth(
    aiohttp_server: Any,
) -> None:
    """Test snapshot authentication failure after a single retry."""

    async def login_handler(request: web.Request) -> web.Response:
        response = web.json_response({"user": "admin"})
        response.set_cookie("user", "session-token")
        return response

    async def snapshot_handler(request: web.Request) -> web.Response:
        return web.Response(status=403)

    server = await _create_motioneye_server(
        aiohttp_server,
        [
            web.post("/login", login_handler),
            web.get("/picture/1/current/", snapshot_handler),
        ],
    )

    client = MotionEyeClient(str(server.make_url("/")))
    await client.async_client_login()

    with pytest.raises(MotionEyeClientInvalidAuthError):
        await client.async_get_camera_snapshot(1)
    await client.async_client_close()


@pytest.mark.asyncio
async def test_session_camera_snapshot_bad_response(aiohttp_server: Any) -> None:
    """Test an unexpected snapshot HTTP response."""

    async def login_handler(request: web.Request) -> web.Response:
        response = web.json_response({"user": "admin"})
        response.set_cookie("user", "session-token")
        return response

    async def snapshot_handler(request: web.Request) -> web.Response:
        return web.Response(status=500)

    server = await _create_motioneye_server(
        aiohttp_server,
        [
            web.post("/login", login_handler),
            web.get("/picture/1/current/", snapshot_handler),
        ],
    )

    client = MotionEyeClient(str(server.make_url("/")))
    await client.async_client_login()

    with pytest.raises(MotionEyeClientRequestError):
        await client.async_get_camera_snapshot(1)
    await client.async_client_close()


@pytest.mark.asyncio
async def test_session_camera_snapshot_connection_error(aiohttp_server: Any) -> None:
    """Test a connection error while fetching a snapshot."""

    async def login_handler(request: web.Request) -> web.Response:
        response = web.json_response({"user": "admin"})
        response.set_cookie("user", "session-token")
        return response

    server = await _create_motioneye_server(
        aiohttp_server, [web.post("/login", login_handler)]
    )

    client = MotionEyeClient(str(server.make_url("/")))
    await client.async_client_login()
    await server.close()

    with pytest.raises(MotionEyeClientConnectionError):
        await client.async_get_camera_snapshot(1)
    await client.async_client_close()


@pytest.mark.asyncio
async def test_session_camera_snapshot_client_error(aiohttp_server: Any) -> None:
    """Test an aiohttp client error while fetching a snapshot."""

    async def login_handler(request: web.Request) -> web.Response:
        response = web.json_response({"user": "admin"})
        response.set_cookie("user", "session-token")
        return response

    server = await _create_motioneye_server(
        aiohttp_server, [web.post("/login", login_handler)]
    )

    async with aiohttp.ClientSession() as session:
        client = MotionEyeClient(str(server.make_url("/")), session=session)
        await client.async_client_login()
        session.get = Mock(  # type: ignore[method-assign]
            side_effect=aiohttp.ClientError("request failed")
        )

        with pytest.raises(MotionEyeClientRequestError):
            await client.async_get_camera_snapshot(1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("image", "preview", "expected_path"),
    [
        (True, False, "/picture/1/download/2026-09-07/test.jpg"),
        (True, True, "/picture/1/preview/2026-09-07/test.jpg"),
        (False, False, "/movie/1/playback/2026-09-07/test.mp4"),
        (False, True, "/movie/1/preview/2026-09-07/test.mp4"),
    ],
)
async def test_session_saved_media(
    aiohttp_server: Any, image: bool, preview: bool, expected_path: str
) -> None:
    """Test saved media fetch with session authentication."""

    async def login_handler(request: web.Request) -> web.Response:
        response = web.json_response({"user": "admin"})
        response.set_cookie("user", "session-token")
        return response

    async def media_handler(request: web.Request) -> web.Response:
        assert request.cookies.get("user") == "session-token"
        return web.Response(body=b"media-data")

    server = await _create_motioneye_server(
        aiohttp_server,
        [
            web.post("/login", login_handler),
            web.get(expected_path, media_handler),
        ],
    )

    client = MotionEyeClient(str(server.make_url("/")))
    await client.async_client_login()

    path = "/2026-09-07/test.jpg" if image else "/2026-09-07/test.mp4"
    assert (
        await client.async_get_media(1, path, image=image, preview=preview)
        == b"media-data"
    )
    await client.async_client_close()


@pytest.mark.asyncio
async def test_session_saved_media_stream(aiohttp_server: Any) -> None:
    """Test streaming saved media with session authentication."""

    async def login_handler(request: web.Request) -> web.Response:
        response = web.json_response({"user": "admin"})
        response.set_cookie("user", "session-token")
        return response

    async def media_handler(request: web.Request) -> web.Response:
        assert request.cookies.get("user") == "session-token"
        return web.Response(
            body=b"streaming-media-data",
            content_type="video/mp4",
        )

    server = await _create_motioneye_server(
        aiohttp_server,
        [
            web.post("/login", login_handler),
            web.get("/movie/1/playback/test.mp4", media_handler),
        ],
    )

    client = MotionEyeClient(str(server.make_url("/")))
    await client.async_client_login()

    response = await client.async_get_media_stream(
        1,
        "/test.mp4",
        image=False,
    )

    assert response.status == 200
    assert response.headers["Content-Type"] == "video/mp4"
    assert await response.content.read() == b"streaming-media-data"

    await response.close()
    await client.async_client_close()


@pytest.mark.asyncio
async def test_session_saved_media_stream_range(aiohttp_server: Any) -> None:
    """Test Range requests when streaming saved media."""

    async def login_handler(request: web.Request) -> web.Response:
        response = web.json_response({"user": "admin"})
        response.set_cookie("user", "session-token")
        return response

    async def media_handler(request: web.Request) -> web.Response:
        assert request.cookies.get("user") == "session-token"
        assert request.headers["Range"] == "bytes=0-3"
        return web.Response(
            body=b"0123",
            status=206,
            headers={
                "Content-Range": "bytes 0-3/10",
                "Accept-Ranges": "bytes",
                "Content-Type": "video/mp4",
            },
        )

    server = await _create_motioneye_server(
        aiohttp_server,
        [
            web.post("/login", login_handler),
            web.get("/movie/1/playback/test.mp4", media_handler),
        ],
    )

    client = MotionEyeClient(str(server.make_url("/")))
    await client.async_client_login()

    response = await client.async_get_media_stream(
        1,
        "/test.mp4",
        image=False,
        range_header="bytes=0-3",
    )

    assert response.status == 206
    assert response.headers["Content-Range"] == "bytes 0-3/10"
    assert response.headers["Accept-Ranges"] == "bytes"
    assert response.headers["Content-Type"] == "video/mp4"
    assert await response.content.read() == b"0123"

    await response.close()
    await client.async_client_close()


@pytest.mark.asyncio
async def test_session_saved_media_reauth(aiohttp_server: Any) -> None:
    """Test saved media reauthentication."""
    login_count = 0

    async def login_handler(request: web.Request) -> web.Response:
        nonlocal login_count
        login_count += 1
        response = web.json_response({"user": "admin"})
        response.set_cookie("user", f"session-token-{login_count}")
        return response

    async def media_handler(request: web.Request) -> web.Response:
        if request.cookies.get("user") == "session-token-1":
            return web.Response(status=403)
        return web.Response(body=b"media-data")

    server = await _create_motioneye_server(
        aiohttp_server,
        [
            web.post("/login", login_handler),
            web.get("/picture/1/download/test.jpg", media_handler),
        ],
    )

    client = MotionEyeClient(str(server.make_url("/")))
    await client.async_client_login()
    assert await client.async_get_media(1, "/test.jpg", image=True) == b"media-data"
    assert login_count == 2
    await client.async_client_close()


@pytest.mark.asyncio
async def test_legacy_saved_media(aiohttp_server: Any) -> None:
    """Test saved media fetch with legacy authentication."""

    async def login_handler(request: web.Request) -> web.Response:
        return web.json_response({})

    async def media_handler(request: web.Request) -> web.Response:
        assert request.query["_username"] == "user"
        assert "_signature" in request.query
        return web.Response(body=b"media-data")

    server = await _create_motioneye_server(
        aiohttp_server,
        [
            web.get("/login", login_handler),
            web.get("/picture/1/download/test.jpg", media_handler),
        ],
    )

    client = MotionEyeClient(str(server.make_url("/")))
    await client.async_client_login()
    assert await client.async_get_media(1, "/test.jpg", image=True) == b"media-data"
    await client.async_client_close()


@pytest.mark.asyncio
async def test_session_saved_media_forbidden_after_reauth(
    aiohttp_server: Any,
) -> None:
    """Test media authentication failure after one retry."""

    async def login_handler(request: web.Request) -> web.Response:
        response = web.json_response({"user": "admin"})
        response.set_cookie("user", "session-token")
        return response

    async def media_handler(request: web.Request) -> web.Response:
        return web.Response(status=403)

    server = await _create_motioneye_server(
        aiohttp_server,
        [
            web.post("/login", login_handler),
            web.get("/picture/1/download/test.jpg", media_handler),
        ],
    )

    client = MotionEyeClient(str(server.make_url("/")))
    await client.async_client_login()

    with pytest.raises(MotionEyeClientInvalidAuthError):
        await client.async_get_media(1, "/test.jpg", image=True)
    await client.async_client_close()


@pytest.mark.asyncio
async def test_session_saved_media_bad_response(aiohttp_server: Any) -> None:
    """Test unexpected media HTTP response."""

    async def login_handler(request: web.Request) -> web.Response:
        response = web.json_response({"user": "admin"})
        response.set_cookie("user", "session-token")
        return response

    async def media_handler(request: web.Request) -> web.Response:
        return web.Response(status=500)

    server = await _create_motioneye_server(
        aiohttp_server,
        [
            web.post("/login", login_handler),
            web.get("/picture/1/download/test.jpg", media_handler),
        ],
    )

    client = MotionEyeClient(str(server.make_url("/")))
    await client.async_client_login()

    with pytest.raises(MotionEyeClientRequestError):
        await client.async_get_media(1, "/test.jpg", image=True)
    await client.async_client_close()


@pytest.mark.asyncio
async def test_session_saved_media_connection_error(aiohttp_server: Any) -> None:
    """Test connection error while fetching saved media."""

    async def login_handler(request: web.Request) -> web.Response:
        response = web.json_response({"user": "admin"})
        response.set_cookie("user", "session-token")
        return response

    server = await _create_motioneye_server(
        aiohttp_server, [web.post("/login", login_handler)]
    )

    client = MotionEyeClient(str(server.make_url("/")))
    await client.async_client_login()
    await server.close()

    with pytest.raises(MotionEyeClientConnectionError):
        await client.async_get_media(1, "/test.jpg", image=True)
    await client.async_client_close()


@pytest.mark.asyncio
async def test_session_saved_media_client_error(aiohttp_server: Any) -> None:
    """Test aiohttp client error while fetching saved media."""

    async def login_handler(request: web.Request) -> web.Response:
        response = web.json_response({"user": "admin"})
        response.set_cookie("user", "session-token")
        return response

    server = await _create_motioneye_server(
        aiohttp_server, [web.post("/login", login_handler)]
    )

    async with aiohttp.ClientSession() as session:
        client = MotionEyeClient(str(server.make_url("/")), session=session)
        await client.async_client_login()
        session.get = Mock(  # type: ignore[method-assign]
            side_effect=aiohttp.ClientError("request failed")
        )

        with pytest.raises(MotionEyeClientRequestError):
            await client.async_get_media(1, "/test.jpg", image=True)


@pytest.mark.asyncio
async def test_client_login_failure(caplog: Any, aiohttp_server: Any) -> None:
    """Test failed client login."""

    login_handler = AsyncMock(
        return_value=web.json_response(
            {"prompt": True, "error": "unauthorized"}, status=403
        )
    )

    server = await _create_motioneye_server(
        aiohttp_server, [web.get("/login", login_handler)]
    )

    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert not client
    assert "Authentication failed" in caplog.text


@pytest.mark.asyncio
async def test_get_manifest(aiohttp_server: Any) -> None:
    """Test getting the motionEye manifest."""

    manifest = {"key": "value"}
    manifest_handler = AsyncMock(return_value=web.json_response(manifest))

    server = await _create_motioneye_server(
        aiohttp_server, [web.get("/manifest.json", manifest_handler)]
    )

    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert client
        assert await client.async_get_manifest() == manifest


@pytest.mark.asyncio
async def test_get_server_config(aiohttp_server: Any) -> None:
    """Test getting the motionEye server config."""

    server_config = {"key": "value"}
    server_config_handler = AsyncMock(return_value=web.json_response(server_config))

    server = await _create_motioneye_server(
        aiohttp_server, [web.get("/config/main/get", server_config_handler)]
    )

    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert client
        assert await client.async_get_server_config() == server_config


@pytest.mark.asyncio
async def test_get_cameras(aiohttp_server: Any) -> None:
    """Test getting the motionEye cameras."""

    cameras = {"key": "value"}
    list_cameras_handler = AsyncMock(return_value=web.json_response(cameras))

    server = await _create_motioneye_server(
        aiohttp_server, [web.get("/config/list", list_cameras_handler)]
    )

    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert client
        assert await client.async_get_cameras() == cameras


@pytest.mark.asyncio
async def test_get_camera(aiohttp_server: Any) -> None:
    """Test getting a motionEye camera."""

    camera = {"key": "value"}
    get_camera_handler = AsyncMock(return_value=web.json_response(camera))

    server = await _create_motioneye_server(
        aiohttp_server, [web.get("/config/100/get", get_camera_handler)]
    )
    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert client
        assert await client.async_get_camera(100) == camera


@pytest.mark.asyncio
async def test_set_camera(aiohttp_server: Any) -> None:
    """Test setting a motionEye camera."""

    camera = {"key": "value"}

    async def set_camera_handler(request: web.Request) -> web.Response:
        assert await request.json() == camera
        return web.json_response({})

    server = await _create_motioneye_server(
        aiohttp_server, [web.post("/config/100/set", set_camera_handler)]
    )

    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert client
        assert await client.async_set_camera(100, config=camera) == {}


@pytest.mark.asyncio
async def test_is_camera_streaming() -> None:
    """Test whether a camera is streaming."""
    assert MotionEyeClient.is_camera_streaming(
        {KEY_STREAMING_PORT: 8000, KEY_VIDEO_STREAMING: True}
    )

    assert not MotionEyeClient.is_camera_streaming(
        {KEY_STREAMING_PORT: 8000, KEY_VIDEO_STREAMING: False}
    )

    assert not MotionEyeClient.is_camera_streaming({KEY_VIDEO_STREAMING: True})
    assert not MotionEyeClient.is_camera_streaming({})


@pytest.mark.asyncio
async def test_get_camera_stream_url(aiohttp_server: Any) -> None:
    """Test retrieving the stream URL."""
    client = MotionEyeClient("http://host:8000")
    assert (
        client.get_camera_stream_url(
            {KEY_STREAMING_PORT: 8000, KEY_VIDEO_STREAMING: True}
        )
        == "http://host:8000/"
    )

    assert not client.get_camera_stream_url({})


@pytest.mark.asyncio
async def test_get_camera_stream_url_remote_motioneye(aiohttp_server: Any) -> None:
    """Test retrieving the stream URL for a remote motioneye."""
    client = MotionEyeClient("http://host:8000")
    assert (
        client.get_camera_stream_url(
            {KEY_STREAMING_PORT: 8001, KEY_VIDEO_STREAMING: True, KEY_HOST: "foobar"}
        )
        == "http://foobar:8001/"
    )

    assert not client.get_camera_stream_url({})


@pytest.mark.asyncio
async def test_get_camera_snapshot_url(aiohttp_server: Any) -> None:
    """Test retrieving the snapshot URL."""
    client = MotionEyeClient("http://host:8000")
    assert client.get_camera_snapshot_url(
        {KEY_STREAMING_PORT: 8000, KEY_VIDEO_STREAMING: True, KEY_ID: 100}
    ) == (
        "http://host:8000/picture/100/current/?_username=user"
        "&_signature=5419538a3223b63a72d79982cd7604e17442b350"
    )

    assert not client.get_camera_snapshot_url(
        {KEY_STREAMING_PORT: 8000, KEY_VIDEO_STREAMING: True}
    )


@pytest.mark.asyncio
async def test_action(aiohttp_server: Any) -> None:
    """Test performing an action on a motionEye camera."""

    async def action_handler(request: web.Request) -> web.Response:
        assert await request.json() == {}
        return web.json_response({})

    action = "foo"
    server = await _create_motioneye_server(
        aiohttp_server, [web.post(f"/action/100/{action}", action_handler)]
    )

    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert client
        assert await client.async_action(100, action) == {}


@pytest.mark.asyncio
async def test_invalid_urls(aiohttp_server: Any) -> None:
    """Test invalid URLs."""
    server = await _create_motioneye_server(aiohttp_server, [])

    with pytest.raises(MotionEyeClientURLParseError):
        async with MotionEyeClient(f"{server.host}:{server.port}/"):
            pass

    with pytest.raises(MotionEyeClientURLParseError):
        async with MotionEyeClient("http://"):
            pass


@pytest.mark.asyncio
async def test_get_movie_url(aiohttp_server: Any) -> None:
    """Test retrieving a movie URL."""
    client = MotionEyeClient("http://host:8000")
    for path in ["/foo", "foo"]:
        assert (
            client.get_movie_url(1, path)
            == "http://host:8000/movie/1/playback/foo?_username=user&_signature=35fc45e2c603f2cddb7d04182da600bf89b5b68b"
        )
        assert (
            client.get_movie_url(1, path, preview=True)
            == "http://host:8000/movie/1/preview/foo?_username=user&_signature=a6b08336b27416e9909306ea3ece5306ed1ece76"
        )

    with pytest.raises(MotionEyeClientPathError):
        client.get_movie_url(1, "")


@pytest.mark.asyncio
async def test_get_image_url(aiohttp_server: Any) -> None:
    """Test retrieving an image URL."""
    client = MotionEyeClient("http://host:8000")
    for path in ["/foo", "foo"]:
        assert (
            client.get_image_url(1, path)
            == "http://host:8000/picture/1/download/foo?_username=user&_signature=7b6f7ff41cd08cdc5b1ec0327da54279dc31a990"
        )
        assert (
            client.get_image_url(1, path, preview=True)
            == "http://host:8000/picture/1/preview/foo?_username=user&_signature=939d10d5a2ed1788b34f7a9bf77ad7b8a8eb3ff0"
        )

    with pytest.raises(MotionEyeClientPathError):
        client.get_image_url(1, "")


@pytest.mark.asyncio
async def test_async_get_movies(aiohttp_server: Any) -> None:
    """Test getting motionEye movies."""

    async def get_movies_handler(request: web.Request) -> web.Response:
        assert "prefix" not in request.query
        return web.json_response({"one": "two"})

    async def get_movies_prefix_handler(request: web.Request) -> web.Response:
        assert request.query["prefix"] == "moo"
        return web.json_response({"three": "four"})

    server = await _create_motioneye_server(
        aiohttp_server,
        [
            web.get("/movie/100/list", get_movies_handler),
            web.get("/movie/101/list", get_movies_prefix_handler),
        ],
    )
    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert client
        assert await client.async_get_movies(100) == {"one": "two"}
        assert await client.async_get_movies(101, prefix="moo") == {"three": "four"}


@pytest.mark.asyncio
async def test_async_get_images(aiohttp_server: Any) -> None:
    """Test getting motionEye images."""

    async def get_images_handler(request: web.Request) -> web.Response:
        assert "prefix" not in request.query
        return web.json_response({"one": "two"})

    async def get_images_prefix_handler(request: web.Request) -> web.Response:
        assert request.query["prefix"] == "moo"
        return web.json_response({"three": "four"})

    server = await _create_motioneye_server(
        aiohttp_server,
        [
            web.get("/picture/100/list", get_images_handler),
            web.get("/picture/101/list", get_images_prefix_handler),
        ],
    )
    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert client
        assert await client.async_get_images(100) == {"one": "two"}
        assert await client.async_get_images(101, prefix="moo") == {"three": "four"}


@pytest.mark.asyncio
async def test_client_response_error(aiohttp_server: Any) -> None:
    """Test invalid server."""

    async def not_motioneye_server(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        writer.close()

    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("localhost", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        port = s.getsockname()[1]

        await asyncio.start_server(not_motioneye_server, "127.0.0.1", port)

        with pytest.raises(MotionEyeClientRequestError):
            client = MotionEyeClient(f"http://localhost:{port}/")
            await client.async_client_login()

        await client.async_client_close()


@pytest.mark.asyncio
async def test_unicode_decode_error(aiohttp_server: Any) -> None:
    """Test unicode bytes that cannot be decoded."""

    app = web.Application()
    login_handler = AsyncMock(
        return_value=web.Response(
            body=b"\xff", charset="UTF-8", content_type="application/octet-stream"
        )
    )
    app.add_routes([web.get("/login", login_handler)])
    server = await aiohttp_server(app)

    with pytest.raises(MotionEyeClientRequestError):
        client = MotionEyeClient(str(server.make_url("/")))
        await client.async_client_login()
    await client.async_client_close()


@pytest.mark.asyncio
async def test_json_decode_error(aiohttp_server: Any) -> None:
    """Test JSON that cannot be decoded."""

    app = web.Application()
    login_handler = AsyncMock(return_value=web.Response(body="this is not valid json"))
    app.add_routes([web.get("/login", login_handler)])
    server = await aiohttp_server(app)

    with pytest.raises(MotionEyeClientRequestError):
        client = MotionEyeClient(str(server.make_url("/")))
        await client.async_client_login()
    await client.async_client_close()


@pytest.mark.asyncio
async def test_is_file_type_image() -> None:
    """Test is_file_type_image."""

    client = MotionEyeClient("http://localhost")
    assert client.is_file_type_image(0)
    assert client.is_file_type_image(7)
    assert not client.is_file_type_image(8)
    assert not client.is_file_type_image(100)


@pytest.mark.asyncio
async def test_is_file_type_movie() -> None:
    """Test is_file_type_movie."""

    client = MotionEyeClient("http://localhost")
    assert not client.is_file_type_movie(0)
    assert not client.is_file_type_movie(7)
    assert client.is_file_type_movie(8)
    assert client.is_file_type_movie(100)


@pytest.mark.asyncio
async def test_session_passed_in_is_not_closed() -> None:
    """Test a session passed in is not closed."""

    session = AsyncMock()
    client = MotionEyeClient("http://localhost", session=session)
    await client.async_client_close()
    assert not session.close.called
