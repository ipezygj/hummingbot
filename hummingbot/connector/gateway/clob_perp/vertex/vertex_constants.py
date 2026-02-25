from typing import Dict

EXCHANGE_NAME = vertex
DEFAULT_DOMAIN = vertex_arbitrum_mainnet
PRICE_SCALING = 10**18
AMOUNT_SCALING = 10**6
SUBACCOUNT_NAME = default

REST_URLS: Dict[str, str] = {
    vertex_arbitrum_mainnet: https://gateway.prod.vertexprotocol.com/v1,
    vertex_arbitrum_testnet: https://gateway.test.vertexprotocol.com/v1
}