from hummingbot.core.api_throttler.data_types import RateLimit

DEFAULT_DOMAIN = "exchange"

REST_URL = "https://api.backpack.{}/api/"
WSS_URL = "wss://ws.backpack.{}/"

PUBLIC_API_VERSION = "v1"
PRIVATE_API_VERSION = "v1"

SERVER_TIME_PATH_URL = "/time"


RATE_LIMITS = [
    RateLimit(limit_id=SERVER_TIME_PATH_URL, limit=6000, time_interval=60),
]
