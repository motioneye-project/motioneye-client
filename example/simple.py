#!/usr/bin/env python
"""Client test for motionEye."""
import asyncio

from motioneye_client.client import MotionEyeClient


async def query_motioneye_server() -> None:
    """Test the motionEye client."""
    async with MotionEyeClient("http://localhost:8765") as client:
        if not client:
            return

        manifest = await client.async_get_manifest()
        print(f"Manifest: {manifest}")

        camera_list = await client.async_get_cameras()
        print(f"Cameras: {camera_list}")


asyncio.get_event_loop().run_until_complete(query_motioneye_server())
