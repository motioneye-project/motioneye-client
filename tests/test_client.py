"""Test the motionEye client."""

import logging
from aiohttp import web  # type: ignore
from typing import Any

from motioneye_client.client import MotionEyeClient

_LOGGER = logging.getLogger(__name__)


async def test_login(aiohttp_server: Any) -> None:
    """Test client login."""

    async def login_handler(request: web.Request) -> web.Response:
        return web.json_response({"moo": "foo"})

    app = web.Application()
    app.add_routes([web.get("/login", login_handler)])
    server = await aiohttp_server(app)

    client = MotionEyeClient(str(server.make_url("/")), "username", "password")
    assert await client.async_client_login()
    assert await client.async_client_close()
