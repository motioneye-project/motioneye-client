"""Constants for motionEye client."""
DEFAULT_PORT = 8765
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_SURVEILLANCE_USERNAME = "user"

KEY_CAMERAS = "cameras"
KEY_ERROR = "error"
KEY_NAME = "name"
KEY_ID = "id"
KEY_VIDEO_STREAMING = "video_streaming"
KEY_STREAMING_PORT = "streaming_port"
KEY_STREAMING_AUTH_MODE = "streaming_auth_mode"
KEY_MOTION_DETECTION = "motion_detection"
KEY_TEXT_OVERLAY = "text_overlay"
KEY_TEXT_OVERLAY_LEFT = "left_text"
KEY_TEXT_OVERLAY_RIGHT = "right_text"
KEY_TEXT_OVERLAY_DISABLED = "disabled"
KEY_TEXT_OVERLAY_TIMESTAMP = "timestamp"
KEY_TEXT_OVERLAY_CAMERA_NAME = "camera-name"
KEY_TEXT_OVERLAY_CUSTOM_TEXT = "custom-text"
KEY_TEXT_OVERLAY_CUSTOM_TEXT_LEFT = "custom_left_text"
KEY_TEXT_OVERLAY_CUSTOM_TEXT_RIGHT = "custom_right_text"
KEY_STILL_IMAGES = "still_images"
KEY_MOVIES = "movies"

KEY_WEB_HOOK_NOTIFICATIONS_ENABLED = "web_hook_notifications_enabled"
KEY_WEB_HOOK_NOTIFICATIONS_URL = "web_hook_notifications_url"
KEY_WEB_HOOK_NOTIFICATIONS_HTTP_METHOD = "web_hook_notifications_http_method"
KEY_WEB_HOOK_STORAGE_URL = "web_hook_storage_url"
KEY_WEB_HOOK_STORAGE_ENABLED = "web_hook_storage_enabled"
KEY_WEB_HOOK_STORAGE_HTTP_METHOD = "web_hook_storage_http_method"

KEY_HTTP_METHOD_GET = "GET"

# Conversion specifiers.
# https://motion-project.github.io/motion_config.html#conversion_specifiers
KEY_WEB_HOOK_CS_YEAR = "year"
KEY_WEB_HOOK_CS_MONTH = "month"
KEY_WEB_HOOK_CS_DAY = "day"
KEY_WEB_HOOK_CS_HOUR = "hour"
KEY_WEB_HOOK_CS_MINUTE = "minute"
KEY_WEB_HOOK_CS_SECOND = "second"
KEY_WEB_HOOK_CS_TIME = "time"
KEY_WEB_HOOK_CS_EVENT = "event"
KEY_WEB_HOOK_CS_FRAME_NUMBER = "frame_number"
KEY_WEB_HOOK_CS_CAMERA_ID = "camera_id"
KEY_WEB_HOOK_CS_CHANGED_PIXELS = "changed_pixels"
KEY_WEB_HOOK_CS_NOISE_LEVEL = "noise_level"
KEY_WEB_HOOK_CS_WIDTH = "width"
KEY_WEB_HOOK_CS_HEIGHT = "height"
KEY_WEB_HOOK_CS_MOTION_WIDTH = "motion_width"
KEY_WEB_HOOK_CS_MOTION_HEIGHT = "motion_height"
KEY_WEB_HOOK_CS_MOTION_CENTER_X = "motion_center_x"
KEY_WEB_HOOK_CS_MOTION_CENTER_Y = "motion_center_y"
KEY_WEB_HOOK_CS_FILE_PATH = "file_path"
KEY_WEB_HOOK_CS_FILE_TYPE = "file_type"
KEY_WEB_HOOK_CS_THRESHOLD = "threshold"
KEY_WEB_HOOK_CS_DESPECKLE_LABELS = "despeckle_labels"
KEY_WEB_HOOK_CS_CAMERA_NAME = "camera_name"
KEY_WEB_HOOK_CS_FPS = "fps"
KEY_WEB_HOOK_CS_HOST = "host"
KEY_WEB_HOOK_CS_MOTION_VERSION = "motion_version"

KEY_WEB_HOOK_CONVERSION_SPECIFIERS = {
    KEY_WEB_HOOK_CS_YEAR: r"%Y",
    KEY_WEB_HOOK_CS_MONTH: r"%m",
    KEY_WEB_HOOK_CS_DAY: r"%d",
    KEY_WEB_HOOK_CS_HOUR: r"%H",
    KEY_WEB_HOOK_CS_MINUTE: r"%M",
    KEY_WEB_HOOK_CS_SECOND: r"%S",
    KEY_WEB_HOOK_CS_TIME: r"%T",
    KEY_WEB_HOOK_CS_EVENT: r"%v",
    KEY_WEB_HOOK_CS_FRAME_NUMBER: r"%q",
    KEY_WEB_HOOK_CS_CAMERA_ID: r"%t",
    KEY_WEB_HOOK_CS_CHANGED_PIXELS: r"%D",
    KEY_WEB_HOOK_CS_NOISE_LEVEL: r"%N",
    KEY_WEB_HOOK_CS_WIDTH: r"%w",
    KEY_WEB_HOOK_CS_HEIGHT: r"%h",
    KEY_WEB_HOOK_CS_MOTION_WIDTH: r"%i",
    KEY_WEB_HOOK_CS_MOTION_HEIGHT: r"%J",
    KEY_WEB_HOOK_CS_MOTION_CENTER_X: r"%K",
    KEY_WEB_HOOK_CS_MOTION_CENTER_Y: r"%L",
    KEY_WEB_HOOK_CS_FILE_PATH: r"%f",
    KEY_WEB_HOOK_CS_FILE_TYPE: r"%n",
    KEY_WEB_HOOK_CS_THRESHOLD: r"%o",
    KEY_WEB_HOOK_CS_DESPECKLE_LABELS: r"%Q",
    KEY_WEB_HOOK_CS_CAMERA_NAME: r"%$",
    KEY_WEB_HOOK_CS_FPS: r"%{fps}",
    KEY_WEB_HOOK_CS_HOST: r"%{host}",
    KEY_WEB_HOOK_CS_MOTION_VERSION: r"%{ver}",
}
