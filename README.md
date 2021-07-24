<img src="https://github.com/dermotduffy/hass-motioneye/blob/main/images/motioneye.png?raw=true"
     alt="motionEye icon"
     width="15%"
     align="right"
     style="float: right; margin: 10px 0px 20px 20px;" />

[![PyPi](https://img.shields.io/pypi/v/motioneye-client.svg?style=flat-square)](https://pypi.org/project/motioneye-client/)
[![PyPi](https://img.shields.io/pypi/pyversions/motioneye-client.svg?style=flat-square)](https://pypi.org/project/motioneye-client/)
[![Build Status](https://img.shields.io/github/workflow/status/dermotduffy/motioneye-client/Build?style=flat-square)](https://github.com/dermotduffy/motioneye-client/actions/workflows/build.yaml)
[![Test Coverage](https://img.shields.io/codecov/c/gh/dermotduffy/motioneye-client?style=flat-square)](https://codecov.io/gh/dermotduffy/motioneye-client)
[![License](https://img.shields.io/github/license/dermotduffy/hass-motioneye.svg?style=flat-square)](LICENSE)
[![BuyMeCoffee](https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=flat-square)](https://www.buymeacoffee.com/dermotdu)

# motionEye Client

A simple async API client for [motionEye](https://github.com/ccrisan/motioneye).

## Constructor arguments

The following arguments may be passed to the `MotionEyeClient` constructor:

| Argument              | Type                    | Default                     | Description                         |
| --------------------- | ----------------------- | --------------------------- | ----------------------------------- |
| url                   | `str`                   | URL of the motionEye server |
| admin_username        | `str`                   | admin                       | The motionEye admin username        |
| admin_password        | `str`                   | ""                          | The motionEye admin password        |
| surveillance_username | `str`                   | user                        | The motionEye surveillance username |
| surveillance_password | `str`                   | ""                          | The motionEye surveillance password |
| session               | `aiohttp.ClientSession` | None                        | Optional aiohttp session to use     |

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

### async_action

Perform a motionEye action on a camera. Takes an integer `camera_id` argument and an
action string.

Common actions include `snapshot`, `record_start` and `record_stop`. motionEye also
supports other user configurable actions which may be called in this manner. See
[Action Buttons](https://github.com/ccrisan/motioneye/wiki/Action-Buttons) for more details.

### async_get_movies

Get a list of recorded movies for a given `camera_id`. Accepts a `prefix` argument that
gives a path prefix to list (does not recurse).

### async_get_images

Get a list of saved images for a given `camera_id`. Accepts a `prefix` argument that
gives a path prefix to list (does not recurse).

## Convenience Methods

### is_camera_streaming

Convenience method to take a camera dictionary (returned by `async_get_camera` or
`async_get_cameras`) and return True if the camera has video stream enabled.

### get_camera_stream_url

Convenience method to take a camera dictionary (returned by `async_get_camera` or
`async_get_cameras`) and return the string URL of the streamed content (which can be
opened separately). This extracts the hostname out of the motionEye URL and attaches the
streaming port to it -- depending on the configuration this may not necessarily lead to
an accessible URL (e.g. in the use of motionEye behind a reverse proxy).

Will raise [MotionEyeClientURLParseError](#MotionEyeClientURLParseError) if the hostname
cannot be extracted from the motionEye server URL.

### get_camera_snapshot_url

Convenience method to take a camera dictionary (returned by `async_get_camera` or
`async_get_cameras`) and return the string URL of a single still frame.

### get_movie_url

Convenience method to take a camera id and the path to a saved movie, and return a link
to playback the movie. Takes a `preview` argument that if `True` returns a URL to a thumbnail.

### get_image_url

Convenience method to take a camera id and the path to a saved image, and return a link
to that image. Takes a `preview` argument that if `True` returns a URL to a thumbnail.

### is_file_type_image / is_file_type_movie

Determine if a given file_type `int` (from a web hook callback) represents an image or a movie respectively.

## Context Manager

The client may be used in as a context manager, which will automatically close the
session.

```python
async with client.MotionEyeClient("http://localhost:8765", ) as mec:
    if not mec:
        return
    ...
````

## Exceptions / Errors

### MotionEyeClientError

A generic base class -- all motionEye client exceptions inherit from this.

### MotionEyeClientInvalidAuthError

Invalid authentication detected during a request.

### MotionEyeClientConnectionError

Connected failed to given URL.

<a name="MotionEyeClientURLParseError"></a>
### MotionEyeClientURLParseError

Unable to parse the required URL.


### MotionEyeClientPathError

Unable to parse a path.


### MotionEyeClientRequestError

A request failed in some other undefined way.

## Simple Example

```python
#!/usr/bin/env python
"""Client test for motionEye."""
import asyncio
import logging

from motioneye_client.client import MotionEyeClient

async def query_motioneye_server():
  async with MotionEyeClient("http://localhost:8765") as client:
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
