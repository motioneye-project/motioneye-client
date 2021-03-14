"""Test the motionEye client."""

import logging
from aiohttp import web  # type: ignore
from typing import Any, List
from unittest.mock import Mock
from motioneye_client.client import MotionEyeClient

_LOGGER = logging.getLogger(__name__)


async def _create_motioneye_server(aiohttp_server: Any, handlers: List[Any]) -> Any:
    app = web.Application()
    app.add_routes(handlers)

    # Add a login handler unless one is explicitly added (i.e. for testing logins).
    for route in handlers:
        if "/login" == route.path:
            break
    else:
        login_handler = Mock(return_value=web.json_response({}))
        app.add_routes([web.get("/login", login_handler)])
    return await aiohttp_server(app)


async def test_signature(aiohttp_server: Any) -> None:
    """Test signature."""

    async def login_handler(request: web.Request) -> web.Response:
        assert "_signature" in request.query
        assert request.query["_signature"] == "2df0446590ac6038c4cec2b3d39639bf22575fed"
        return web.json_response({})

    server = await _create_motioneye_server(
        aiohttp_server, [web.get("/login", login_handler)]
    )

    async with MotionEyeClient(
        str(server.make_url("/")), "username", "password"
    ) as client:
        assert client


async def test_non_json_response(aiohttp_server: Any) -> None:
    """Test a non-JSON response."""

    async def login_handler(request: web.Request) -> web.Response:
        return web.Response(body="this is not json")

    server = await _create_motioneye_server(
        aiohttp_server, [web.get("/login", login_handler)]
    )

    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert not client


async def test_client_login_success(aiohttp_server: Any) -> None:
    """Test successful client login."""

    login_handler = Mock(return_value=web.json_response({}))

    server = await _create_motioneye_server(
        aiohttp_server, [web.get("/login", login_handler)]
    )

    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert client


async def test_client_login_failure(aiohttp_server: Any) -> None:
    """Test failed client login."""

    login_handler = Mock(
        return_value=web.json_response({"prompt": True, "error": "unauthorized"})
    )

    server = await _create_motioneye_server(
        aiohttp_server, [web.get("/login", login_handler)]
    )

    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert not client


async def test_get_manifest(aiohttp_server: Any) -> None:
    """Test getting the motionEye manifest."""

    manifest = {"key": "value"}
    manifest_handler = Mock(return_value=web.json_response(manifest))

    server = await _create_motioneye_server(
        aiohttp_server, [web.get("/manifest.json", manifest_handler)]
    )

    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert client
        assert await client.async_get_manifest() == manifest


async def test_get_server_config(aiohttp_server: Any) -> None:
    """Test getting the motionEye server config."""

    server_config = {"key": "value"}
    server_config_handler = Mock(return_value=web.json_response(server_config))

    server = await _create_motioneye_server(
        aiohttp_server, [web.get("/config/main/get", server_config_handler)]
    )

    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert client
        assert await client.async_get_server_config() == server_config


async def test_get_cameras(aiohttp_server: Any) -> None:
    """Test getting the motionEye cameras."""

    cameras = {"key": "value"}
    list_cameras_handler = Mock(return_value=web.json_response(cameras))

    server = await _create_motioneye_server(
        aiohttp_server, [web.get("/config/list", list_cameras_handler)]
    )

    async with MotionEyeClient(str(server.make_url("/"))) as client:
        assert client
        assert await client.async_get_cameras() == cameras
