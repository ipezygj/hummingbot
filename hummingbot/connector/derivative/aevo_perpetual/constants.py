

"""Constants for Aevo Perpetual connector."""

from hummingbot.core.api_throttler.data_types import LinkedLimitWeightPair, RateLimit

# Exchange name
EXCHANGE_NAME = "aevo_perpetual"

# Base URLs
REST_URL = "https://api.aevo.xyz"
WS_URL = "wss://ws.aevo.xyz"

# Testnet URLs
TESTNET_REST_URL = "https://api-testnet.aevo.xyz"
TESTNET_WS_URL = "wss://ws-testnet.aevo.xyz"

# Public REST API Endpoints
EXCHANGE_INFO_URL = "/assets"
MARKETS_URL = "/markets"
TICKER_URL = "/ticker"
ORDERBOOK_URL = "/orderbook"
TRADES_URL = "/trades"
FUNDING_RATE_URL = "/funding"
INDEX_URL = "/index"
MARK_PRICE_URL = "/mark-price"
SERVER_TIME_URL = "/time"
COINGECKO_URL = "/coingecko"
STATISTICS_URL = "/statistics"
INSTRUMENT_URL = "/instrument/{instrument_name}"

# Private REST API Endpoints
ACCOUNT_URL = "/account"
PORTFOLIO_URL = "/portfolio"
ORDERS_URL = "/orders"
ORDER_URL = "/orders/{order_id}"
CANCEL_ORDER_URL = "/orders/{order_id}"
CANCEL_ALL_ORDERS_URL = "/orders-all"
OPEN_ORDERS_URL = "/orders"
ORDER_HISTORY_URL = "/order-history"
TRADE_HISTORY_URL = "/trade-history"
POSITIONS_URL = "/positions"
LEVERAGE_URL = "/account/leverage"
MARGIN_TYPE_URL = "/account/margin-type"

# WebSocket Channels
WS_ORDERBOOK_CHANNEL = "orderbook"
WS_TRADES_CHANNEL = "trades"
WS_TICKER_CHANNEL = "ticker"
WS_INDEX_CHANNEL = "index"
WS_FUNDING_CHANNEL = "funding"
WS_MARK_PRICE_CHANNEL = "mark-price"

# Private WebSocket Channels
WS_ORDERS_CHANNEL = "orders"
WS_FILLS_CHANNEL = "fills"
WS_POSITIONS_CHANNEL = "positions"
WS_ACCOUNT_CHANNEL = "account"

# WebSocket Event Types
WS_SUBSCRIBE = "subscribe"
WS_UNSUBSCRIBE = "unsubscribe"
WS_AUTH = "auth"
WS_PING = "ping"
WS_PONG = "pong"

# Order Types
ORDER_TYPE_LIMIT = "limit"
ORDER_TYPE_MARKET = "market"
ORDER_TYPE_STOP_LIMIT = "stop_limit"
ORDER_TYPE_STOP_MARKET = "stop_market"
ORDER_TYPE_TAKE_PROFIT_LIMIT = "take_profit_limit"
ORDER_TYPE_TAKE_PROFIT_MARKET = "take_profit_market"

# Order Sides
SIDE_BUY = "buy"
SIDE_SELL = "sell"

# Order Status
ORDER_STATUS_OPEN = "opened"
ORDER_STATUS_PARTIALLY_FILLED = "partial"
ORDER_STATUS_FILLED = "filled"
ORDER_STATUS_CANCELLED = "cancelled"
ORDER_STATUS_EXPIRED = "expired"
ORDER_STATUS_REJECTED = "rejected"

# Time in Force
TIME_IN_FORCE_GTC = "GTC"  # Good Till Cancel
TIME_IN_FORCE_IOC = "IOC"  # Immediate Or Cancel
TIME_IN_FORCE_FOK = "FOK"  # Fill Or Kill
TIME_IN_FORCE_GTD = "GTD"  # Good Till Date

# Position Sides
POSITION_SIDE_LONG = "long"
POSITION_SIDE_SHORT = "short"
POSITION_SIDE_BOTH = "both"

# Margin Types
MARGIN_TYPE_CROSS = "cross"
MARGIN_TYPE_ISOLATED = "isolated"

# Intervals & Timeouts
HEARTBEAT_INTERVAL = 15.0  # seconds
WS_HEARTBEAT_TIME_INTERVAL = 10.0  # seconds
MESSAGE_TIMEOUT = 30.0  # seconds
PING_TIMEOUT = 10.0  # seconds
API_CALL_TIMEOUT = 10.0  # seconds
API_MAX_RETRIES = 3
UPDATE_ORDER_STATUS_INTERVAL = 10.0  # seconds
ORDER_NOT_FOUND_ERROR_CODE = 404

# Precision
DEFAULT_DOMAIN = ""

# Max results per request
MAX_ORDER_BOOK_DEPTH = 100
MAX_RESULTS_PER_PAGE = 100

# Funding rate interval
FUNDING_RATE_INTERVAL = 3600  # 1 hour in seconds

# Rate Limits
NO_LIMIT = "no_limit"
GENERAL_LIMIT_ID = "general"
ORDERS_LIMIT_ID = "orders"
ORDER_CANCEL_LIMIT_ID = "order_cancel"
ORDER_CREATE_LIMIT_ID = "order_create"
WS_CONNECTIONS_LIMIT_ID = "ws_connections"
WS_REQUESTS_LIMIT_ID = "ws_requests"

# Rate limit periods (in seconds)
ONE_MINUTE = 60
ONE_SECOND = 1
FIVE_MINUTES = 300

# Rate limit values
GENERAL_REQUESTS_PER_MINUTE = 600
ORDER_REQUESTS_PER_MINUTE = 300
WS_CONNECTIONS_PER_MINUTE = 30
WS_REQUESTS_PER_SECOND = 50

RATE_LIMITS = [
    RateLimit(
        limit_id=GENERAL_LIMIT_ID,
        limit=GENERAL_REQUESTS_PER_MINUTE,
        time_interval=ONE_MINUTE,
    ),
    RateLimit(
        limit_id=ORDER_CREATE_LIMIT_ID,
        limit=ORDER_REQUESTS_PER_MINUTE,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(GENERAL_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=ORDER_CANCEL_LIMIT_ID,
        limit=ORDER_REQUESTS_PER_MINUTE,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(GENERAL_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=ORDERS_LIMIT_ID,
        limit=ORDER_REQUESTS_PER_MINUTE,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(GENERAL_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=EXCHANGE_INFO_URL,
        limit=GENERAL_REQUESTS_PER_MINUTE,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(GENERAL_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=MARKETS_URL,
        limit=GENERAL_REQUESTS_PER_MINUTE,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(GENERAL_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=TICKER_URL,
        limit=GENERAL_REQUESTS_PER_MINUTE,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(GENERAL_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=ORDERBOOK_URL,
        limit=GENERAL_REQUESTS_PER_MINUTE,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(GENERAL_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=TRADES_URL,
        limit=GENERAL_REQUESTS_PER_MINUTE,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(GENERAL_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=FUNDING_RATE_URL,
        limit=GENERAL_REQUESTS_PER_MINUTE,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(GENERAL_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=ACCOUNT_URL,
        limit=GENERAL_REQUESTS_PER_MINUTE,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(GENERAL_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=PORTFOLIO_URL,
        limit=GENERAL_REQUESTS_PER_MINUTE,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(GENERAL_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=POSITIONS_URL,
        limit=GENERAL_REQUESTS_PER_MINUTE,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(GENERAL_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=ORDERS_URL,
        limit=ORDER_REQUESTS_PER_MINUTE,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(GENERAL_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=CANCEL_ALL_ORDERS_URL,
        limit=ORDER_REQUESTS_PER_MINUTE,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(GENERAL_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=ORDER_HISTORY_URL,
        limit=GENERAL_REQUESTS_PER_MINUTE,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(GENERAL_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=TRADE_HISTORY_URL,
        limit=GENERAL_REQUESTS_PER_MINUTE,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(GENERAL_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=LEVERAGE_URL,
        limit=GENERAL_REQUESTS_PER_MINUTE,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(GENERAL_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=SERVER_TIME_URL,
        limit=GENERAL_REQUESTS_PER_MINUTE,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(GENERAL_LIMIT_ID)],
    ),
    RateLimit(
        limit_id=WS_CONNECTIONS_LIMIT_ID,
        limit=WS_CONNECTIONS_PER_MINUTE,
        time_interval=ONE_MINUTE,
    ),
    RateLimit(
        limit_id=WS_REQUESTS_LIMIT_ID,
        limit=WS_REQUESTS_PER_SECOND,
        time_interval=ONE_SECOND,
    ),
]

# Hummingbot client order ID prefix
HBOT_ORDER_ID_PREFIX = "HBOT"
MAX_ORDER_ID_LEN = 32

# Error codes
UNKNOWN_ORDER_ERROR_CODE = -2011
ORDER_NOT_EXIST_ERROR_CODE = -2013
ORDER_NOT_EXIST_MESSAGE = "Order does not exist"
