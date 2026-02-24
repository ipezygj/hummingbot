from hummingbot.core.api_throttler.data_types import LinkedLimitWeightPair, RateLimit

DOMAIN = "grvt_perpetual"
TESTNET_DOMAIN = "grvt_perpetual_testnet"

# Base URLs
REST_URL = "https://trades.grvt.io"
WSS_URL = "wss://trades.grvt.io/ws"

# API Endpoints
ORDER_PLACE_PATH = "/v1/order/place"
ORDER_CANCEL_PATH = "/v1/order/cancel"
ACCOUNT_BALANCES_PATH = "/v1/account/balances"

# Rate Limits
RATE_LIMITS = [
    RateLimit(limit_id=ORDER_PLACE_PATH, limit=50, time_interval=1),
    RateLimit(limit_id=ORDER_CANCEL_PATH, limit=50, time_interval=1),
    RateLimit(limit_id=ACCOUNT_BALANCES_PATH, limit=10, time_interval=1),
]
