from typing import Dict

EXCHANGE_NAME: str = "hyperliquid"
DEFAULT_DOMAIN: str = "hyperliquid_testnet"

# API Endpoints
REST_URLS: Dict[str, str] = {
    "hyperliquid_testnet": "https://api.hyperliquid-testnet.xyz",
    "hyperliquid_mainnet": "https://api.hyperliquid.xyz"
}

WSS_URLS: Dict[str, str] = {
    "hyperliquid_testnet": "wss://api.hyperliquid-testnet.xyz/ws",
    "hyperliquid_mainnet": "wss://api.hyperliquid.xyz/ws"
}

# Connector Settings
HEARTBEAT_INTERVAL_THRESHOLD: float = 20.0
UPDATE_ORDER_STATUS_INTERVAL: float = 5.0
MAX_ORDER_ID_LEN: int = 40