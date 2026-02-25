"""
Vertex Protocol constants for Gateway V2.1.
"""
from hummingbot.core.data_type.common import OrderType, TradeType

EXCHANGE_NAME = "vertex"
BROKER_ID = "hummingbot"

# API Endpoints (Arbitrum)
REST_URL = "https://gateway.prod.vertexprotocol.com/v1"
WSS_URL = "wss://gateway.prod.vertexprotocol.com/v1/ws"
QUERY_URL = "https://archive.prod.vertexprotocol.com/v1"

# Execution
DEFAULT_ASSET_ID = 0  # USDC
ORDER_TYPES = [OrderType.LIMIT, OrderType.MARKET, OrderType.LIMIT_MAKER]
TRADE_TYPES = [TradeType.BUY, TradeType.SELL]
