[![PyPi](https://img.shields.io/pypi/v/motioneye-client.svg)](https://pypi.org/project/motioneye-client/)
[![PyPi](https://img.shields.io/pypi/pyversions/motioneye-client.svg)](https://pypi.org/project/motioneye-client/)
[![Build Status](https://travis-ci.com/dermotduffy/motioneye-client.svg?branch=master)](https://travis-ci.com/dermotduffy/motioneye-client)
[![Coverage](https://img.shields.io/codecov/c/github/dermotduffy/motioneye-client)](https://codecov.io/gh/dermotduffy/motioneye-client)

# motionEye Client

A simple async API client for [motionEye](https://github.com/ccrisan/motioneye).

## Constructor arguments

The following arguments may be passed to the `MotionEyeClient` constructor:

|Argument|Type|Default|Description|
|--------|----|-------|-----------|
|host    |`str`||Host or IP to connect to|
|port    |`int`|8765|Port to connect to|
|admin_username|`str`|admin|The motionEye admin username|
|admin_password|`str`|""|The motionEye admin password
|surveillance_username|`str`|user|The motionEye surveillance username|
|surveillance_password|`str`|""|The motionEye surveillance password|

This client needs both `admin` and `surveillance` passwords in order to interact with
the API (which generally require the `admin` user), as well as prepare the URLs for
data streaming (which require the `surveillance` user).

## Primary Client Methods

All async calls start with `async_`, and return the JSON response from the server (if any).

### async_client_login

Login to the motionEye server. Not actually necessary, but useful for verifying credentials.
### async_client_close

Close the client session. Always returns True.

### async_get_manifest

Get the motionEye server manifest (e.g. server version number).

### async_get_server_config

Get the main motionEye server config.

### async_get_cameras

Get the listing of all cameras.

### async_get_camera

Get the configuration of a single camera. Takes an integer `camera_id` argument.

### async_set_camera

Set the configuration of a single camera. Takes an integer `camera_id` argument, and a
dictionary of the same format as returned by `async_get_camera`.

## Convenience Methods

### is_camera_streaming

Convenience method to take a camera dictionary (returned by `async_get_camera` or
`async_get_cameras`) and return True if the camera has video stream enabled.

### get_camera_steam_url

Convenience method to take a camera dictionary (returned by `async_get_camera` or
`async_get_cameras`) and return the string URL of the streamed content (which can be
opened separately).

### get_camera_snapshot_url

Convenience method to take a camera dictionary (returned by `async_get_camera` or
`async_get_cameras`) and return the string URL of a single still frame.

## Context Manager

The client may be used in as a context manager, which will automatically close the
session.

```python
async with client.MotionEyeClient("localhost", ) as mec:
    if not mec:
        return
    ...
````

## Exceptions / Errors 

### MotionEyeClientError

A generic base class -- all motionEye client exceptions inherit from this.

### MotionEyeClientInvalidAuth

Invalid authentication detected during a request.

### MotionEyeClientConnectionFailure

Connected failed to given host and port.

### MotionEyeClientRequestFailed

A request failed in some other undefined way.

## Simple Example

```python
#!/usr/bin/env python
"""Client test for motionEye."""
import asyncio
import logging

from motioneye_client.client import MotionEyeClient

async def query_motioneye_server():
  async with MotionEyeClient("localhost", 8765) as client:
      if not client:
        return

      manifest = await client.async_get_manifest()
      print ("Manifest: %s" % manifest)

      camera_list = await client.async_get_cameras()
      print ("Cameras: %s" % camera_list)

asyncio.get_event_loop().run_until_complete(query_motioneye_server())
```

## Building / Testing

This library is built using [Poetry](https://python-poetry.org/).

Building:

```bash
$ poetry build
```

Testing:
```bash
$ poetry run pytest
```