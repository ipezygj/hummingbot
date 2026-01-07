from hummingbot.core.api_throttler.data_types import RateLimit

DEFAULT_DOMAIN = "exchange"

REST_URL = "https://api.backpack.{}/api/"
WSS_URL = "wss://ws.backpack.{}/"

WS_HEARTBEAT_TIME_INTERVAL = 60
MAX_ORDER_ID_LEN = 32
HBOT_ORDER_ID_PREFIX = "x-MG43PCSN"

ALL_ORDERS_CHANNEL = "account.orderUpdate"
SINGLE_ORDERS_CHANNEL = "account.orderUpdate.{}"  # format by symbol

SIDE_BUY = "Bid"
SIDE_SELL = "Ask"
TIME_IN_FORCE_GTC = "GTC"
ORDER_STATE = {}  # TODO

PUBLIC_API_VERSION = "v1"
PRIVATE_API_VERSION = "v1"

DIFF_EVENT_TYPE = "depth"
TRADE_EVENT_TYPE = "trade"

PING_PATH_URL = "/ping"
SERVER_TIME_PATH_URL = "/time"
EXCHANGE_INFO_PATH_URL = "/markets"
SNAPSHOT_PATH_URL = "/depth"
BALANCE_PATH_URL = "/capital"  # instruction balanceQuery
TICKER_BOOK_PATH_URL = "/tickers"
TICKER_PRICE_CHANGE_PATH_URL = "/ticker"
ORDER_PATH_URL = "/order"
MY_TRADES_PATH_URL = "/fills"  # instruction fillHistoryQueryAll

RATE_LIMITS = [
    RateLimit(limit_id=SERVER_TIME_PATH_URL, limit=6000, time_interval=60),
    RateLimit(limit_id=EXCHANGE_INFO_PATH_URL, limit=6000, time_interval=60),
]

ORDER_NOT_EXIST_ERROR_CODE = 1000  # TODO
ORDER_NOT_EXIST_MESSAGE = "TODO"
UNKNOWN_ORDER_ERROR_CODE = 1000  # TODO
UNKNOWN_ORDER_MESSAGE = "TODO"
