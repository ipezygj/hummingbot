from hummingbot.core.api_throttler.data_types import RateLimit

DOMAIN = "grvt_perpetual"
REST_URL = ""
WSS_URL = "wss://trades.grvt.io/ws"

ORDER_PLACE_PATH = "/v1/order/place"
ORDER_CANCEL_PATH = "/v1/order/cancel"
ACCOUNT_BALANCES_PATH = "/v1/account/balances"

RATE_LIMITS = [
RateLimit(limit_id=ORDER_PLACE_PATH, limit=50, time_interval=1),
RateLimit(limit_id=ORDER_CANCEL_PATH, limit=50, time_interval=1),
RateLimit(limit_id=ACCOUNT_BALANCES_PATH, limit=10, time_interval=1),
]
