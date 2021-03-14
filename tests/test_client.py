"""Test the motionEye client."""

import logging
from aiohttp import web  # type: ignore
from typing import Any, List

from motioneye_client.client import MotionEyeClient

_LOGGER = logging.getLogger(__name__)


async def _create_motioneye_server(aiohttp_server: Any, handlers: List[Any]) -> Any:
    app = web.Application()
    app.add_routes(handlers)
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


async def test_login(aiohttp_server: Any) -> None:
    """Test client login."""

    async def login_handler(request: web.Request) -> web.Response:
        return web.json_response({"moo": "foo"})

    server = await _create_motioneye_server(
        aiohttp_server, [web.get("/login", login_handler)]
    )

    async with MotionEyeClient(
        str(server.make_url("/")), "username", "password"
    ) as client:
        assert client
