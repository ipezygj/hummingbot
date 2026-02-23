

"""
Constants for Vertex Protocol Perpetual Connector

Vertex Protocol is a decentralized exchange on Arbitrum that uses an off-chain
orderbook with on-chain settlement. It supports spot, perpetual, and money market
products.

Reference: https://docs.vertexprotocol.com/
"""

from hummingbot.core.api_throttler.data_types import LinkedLimitWeightPair, RateLimit

# ==============================================================================
# General Connector Constants
# ==============================================================================

EXCHANGE_NAME = "vertex_perpetual"
CONNECTOR_NAME = "vertex_perpetual"
DEFAULT_DOMAIN = "vertex_perpetual"
HBOT_BROKER_ID = "hummingbot"

# Max number of retries for API requests
MAX_ORDER_ID_LEN = 40
MAX_RETRIES = 3
RETRY_INTERVAL = 1.0  # seconds

# ==============================================================================
# Chain Constants (Arbitrum One)
# ==============================================================================

CHAIN_ID = 42161  # Arbitrum One mainnet chain ID
CHAIN_NAME = "Arbitrum One"
NATIVE_TOKEN = "ETH"
WRAPPED_NATIVE_TOKEN = "WETH"

# Arbitrum Testnet (Sepolia) - for testing
TESTNET_CHAIN_ID = 421614
TESTNET_CHAIN_NAME = "Arbitrum Sepolia"

# ==============================================================================
# Vertex Protocol Contract Addresses (Arbitrum One Mainnet)
# ==============================================================================

# Mainnet contract addresses
ENDPOINT_ADDRESS = "0xbbEE07B3e8121227AfCFe1E2B82772571571CE2B"
CLEARINGHOUSE_ADDRESS = "0xAde6FBA6d0EBa2a224d23b5Eff10e4e83F0dA48e"
QUERIER_ADDRESS = "0x1A215D8e3A4eD76E3d3C163B3B35a1382260184D"
SPOT_ENGINE_ADDRESS = "0x32d91Af2B17054D575A7bF1ACfa7615f205e4a06"
PERP_ENGINE_ADDRESS = "0xb74C78ceb684E1B9D80d15F9CF59411a0b7d9F2F"
ORDERBOOK_ADDRESS = "0xbFE2ECC58E21E6d2c1c876Ba81E0e2fE13159C40"

# Testnet contract addresses (Arbitrum Sepolia)
TESTNET_ENDPOINT_ADDRESS = "0xaDeFa2F3932E24d07e30Ff0A8b4f1046Fa46bFcc"
TESTNET_CLEARINGHOUSE_ADDRESS = "0x3A0e59ea25B40f9CCaF67aBA9Bd926B2DC8F8F8F"

# ==============================================================================
# Vertex Gateway & Indexer URLs
# ==============================================================================

# Production (Mainnet) URLs
GATEWAY_URL = "https://gateway.prod.vertexprotocol.com/v1"
INDEXER_URL = "https://archive.prod.vertexprotocol.com/v1"
TRIGGER_URL = "https://trigger.prod.vertexprotocol.com/v1"
SUBSCRIPTION_URL = "wss://gateway.prod.vertexprotocol.com/v1/ws"

# Testnet URLs
TESTNET_GATEWAY_URL = "https://gateway.sepolia-test.vertexprotocol.com/v1"
TESTNET_INDEXER_URL = "https://archive.sepolia-test.vertexprotocol.com/v1"
TESTNET_TRIGGER_URL = "https://trigger.sepolia-test.vertexprotocol.com/v1"
TESTNET_SUBSCRIPTION_URL = "wss://gateway.sepolia-test.vertexprotocol.com/v1/ws"

# Base REST URL mapping by domain
REST_URLS = {
    "vertex_perpetual": GATEWAY_URL,
    "vertex_perpetual_testnet": TESTNET_GATEWAY_URL,
}

INDEXER_URLS = {
    "vertex_perpetual": INDEXER_URL,
    "vertex_perpetual_testnet": TESTNET_INDEXER_URL,
}

WS_URLS = {
    "vertex_perpetual": SUBSCRIPTION_URL,
    "vertex_perpetual_testnet": TESTNET_SUBSCRIPTION_URL,
}

# ==============================================================================
# EIP-712 Domain and Type Definitions for Vertex Protocol
# ==============================================================================

# EIP-712 Domain Separator for Vertex on Arbitrum
EIP712_DOMAIN_NAME = "Vertex"
EIP712_DOMAIN_VERSION = "0.0.1"
EIP712_DOMAIN_VERIFYING_CONTRACT = ENDPOINT_ADDRESS

# EIP-712 Domain struct
EIP712_DOMAIN = {
    "name": EIP712_DOMAIN_NAME,
    "version": EIP712_DOMAIN_VERSION,
    "chainId": CHAIN_ID,
    "verifyingContract": EIP712_DOMAIN_VERIFYING_CONTRACT,
}

# Testnet EIP-712 Domain
EIP712_TESTNET_DOMAIN = {
    "name": EIP712_DOMAIN_NAME,
    "version": EIP712_DOMAIN_VERSION,
    "chainId": TESTNET_CHAIN_ID,
    "verifyingContract": TESTNET_ENDPOINT_ADDRESS,
}

# EIP-712 Type Definitions for Order Signing
EIP712_ORDER_TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "Order": [
        {"name": "sender", "type": "bytes32"},
        {"name": "priceX18", "type": "int128"},
        {"name": "amount", "type": "int128"},
        {"name": "expiration", "type": "uint64"},
        {"name": "nonce", "type": "uint64"},
    ],
}

# EIP-712 Type Definitions for Cancel Order
EIP712_CANCEL_ORDERS_TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "Cancellation": [
        {"name": "sender", "type": "bytes32"},
        {"name": "productIds", "type": "uint32[]"},
        {"name": "digests", "type": "bytes32[]"},
        {"name": "nonce", "type": "uint64"},
    ],
}

# EIP-712 Type Definitions for Cancel Product Orders
EIP712_CANCEL_PRODUCT_ORDERS_TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "CancellationProducts": [
        {"name": "sender", "type": "bytes32"},
        {"name": "productIds", "type": "uint32[]"},
        {"name": "nonce", "type": "uint64"},
    ],
}

# EIP-712 Type Definitions for Liquidate Subaccount
EIP712_LIQUIDATE_SUBACCOUNT_TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "LiquidateSubaccount": [
        {"name": "sender", "type": "bytes32"},
        {"name": "liquidatee", "type": "bytes32"},
        {"name": "mode", "type": "uint8"},
        {"name": "healthGroup", "type": "uint32"},
        {"name": "amount", "type": "int128"},
        {"name": "nonce", "type": "uint64"},
    ],
}

# EIP-712 Type Definitions for Withdraw Collateral
EIP712_WITHDRAW_COLLATERAL_TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "WithdrawCollateral": [
        {"name": "sender", "type": "bytes32"},
        {"name": "productId", "type": "uint32"},
        {"name": "amount", "type": "uint128"},
        {"name": "nonce", "type": "uint64"},
    ],
}

# EIP-712 Type Definitions for Link Signer
EIP712_LINK_SIGNER_TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "LinkSigner": [
        {"name": "sender", "type": "bytes32"},
        {"name": "signer", "type": "bytes32"},
        {"name": "nonce", "type": "uint64"},
    ],
}

# ==============================================================================
# Gateway API Endpoints (Execute / Query)
# ==============================================================================

# Gateway Execute Endpoints (POST to /execute)
GATEWAY_EXECUTE_PATH = "/execute"

# Gateway Query Endpoints (POST to /query)
GATEWAY_QUERY_PATH = "/query"

# Indexer Query Path
INDEXER_QUERY_PATH = "/indexer"

# ==============================================================================
# Gateway Execute Request Types
# ==============================================================================

EXECUTE_PLACE_ORDER = "place_order"
EXECUTE_CANCEL_ORDERS = "cancel_orders"
EXECUTE_CANCEL_PRODUCT_ORDERS = "cancel_product_orders"
EXECUTE_CANCEL_AND_PLACE = "cancel_and_place"
EXECUTE_WITHDRAW_COLLATERAL = "withdraw_collateral"
EXECUTE_LIQUIDATE_SUBACCOUNT = "liquidate_subaccount"
EXECUTE_MINT_LP = "mint_lp"
EXECUTE_BURN_LP = "burn_lp"
EXECUTE_LINK_SIGNER = "link_signer"

# ==============================================================================
# Gateway Query Request Types
# ==============================================================================

QUERY_STATUS = "status"
QUERY_CONTRACTS = "contracts"
QUERY_NONCES = "nonces"
QUERY_ORDER = "order"
QUERY_ORDERS = "orders"
QUERY_SUBACCOUNT_INFO = "subaccount_info"
QUERY_SUBACCOUNT_OPEN_ORDERS = "subaccount_open_orders"
QUERY_MARKET_PRICE = "market_price"
QUERY_MAX_ORDER_SIZE = "max_order_size"
QUERY_MAX_WITHDRAWABLE = "max_withdrawable"
QUERY_MAX_LP_MINTABLE = "max_lp_mintable"
QUERY_FEE_RATES = "fee_rates"
QUERY_HEALTH_GROUPS = "health_groups"
QUERY_LINKED_SIGNER = "linked_signer"
QUERY_ALL_PRODUCTS = "all_products"
QUERY_MARKET_LIQUIDITY = "market_liquidity"
QUERY_SYMBOLS = "symbols"
QUERY_MIN_DEPOSIT_RATES = "min_deposit_rates"

# ==============================================================================
# Indexer Query Types
# ==============================================================================

INDEXER_MATCHES = "matches"
INDEXER_ORDERS = "orders"
INDEXER_SUBACCOUNT_HISTORICAL_ORDERS = "historical_orders"
INDEXER_PRODUCTS = "products"
INDEXER_CANDLESTICKS = "candlesticks"
INDEXER_FUNDING_RATE = "funding_rate"
INDEXER_FUNDING_RATES = "funding_rates"
INDEXER_PERP_PRICES = "perp_prices"
INDEXER_ORACLE_PRICES = "oracle_prices"
INDEXER_TOKEN_REWARDS = "token_rewards"
INDEXER_MAKER_STATISTICS = "maker_statistics"
INDEXER_LIQUIDATION_FEED = "liquidation_feed"
INDEXER_LINKED_SIGNER_RATE_LIMIT = "linked_signer_rate_limit"
INDEXER_INTEREST_AND_FUNDING = "interest_and_funding"
INDEXER_SNAPSHOTS = "snapshots"
INDEXER_MARKET_SNAPSHOTS = "market_snapshots"

# ==============================================================================
# WebSocket Subscription Types
# ==============================================================================

WS_METHOD_SUBSCRIBE = "subscribe"
WS_METHOD_UNSUBSCRIBE = "unsubscribe"

WS_CHANNEL_ORDERBOOK = "book_depth"
WS_CHANNEL_TRADES = "trade"
WS_CHANNEL_FILL = "fill"
WS_CHANNEL_POSITION_CHANGE = "position_change"
WS_CHANNEL_BEST_BID_OFFER = "best_bid_offer"

# ==============================================================================
# Product IDs
# ==============================================================================

# Vertex uses numeric product IDs
# Product ID 0 is USDC (quote currency)
# Even product IDs (2, 4, 6, ...) are spot products
# Odd product IDs (1, 3, 5, ...) are perpetual products

PRODUCT_ID_USDC = 0

# Common perpetual product IDs (Mainnet)
PRODUCT_ID_BTC_PERP = 2  # BTC-PERP (product_id=2 is spot, perp is associated)
PRODUCT_ID_ETH_PERP = 4  # ETH-PERP

# Perpetual product IDs - these are odd numbers for perp products
PERP_PRODUCT_IDS = {
    "BTC-PERP": 2,
    "ETH-PERP": 4,
    "ARB-PERP": 6,
    "BNB-PERP": 8,
    "SOL-PERP": 14,
    "MATIC-PERP": 16,
    "SUI-PERP": 18,
    "OP-PERP": 20,
    "APT-PERP": 22,
    "LTC-PERP": 24,
    "BCH-PERP": 26,
    "COMP-PERP": 28,
    "MKR-PERP": 30,
    "PEPE-PERP": 32,
    "DOGE-PERP": 34,
    "LINK-PERP": 36,
    "DYDX-PERP": 38,
    "CRV-PERP": 40,
    "XRP-PERP": 42,
    "MEME-PERP": 46,
    "TIA-PERP": 48,
    "BLUR-PERP": 50,
    "JTO-PERP": 52,
    "AVAX-PERP": 54,
}

# ==============================================================================
# Precision & Scaling Constants
# ==============================================================================

# Vertex uses X18 format for prices and amounts (scaled by 10^18)
X18_DECIMALS = 18
X18_MULTIPLIER = 10 ** X18_DECIMALS

# USDC has 6 decimals on Arbitrum
USDC_DECIMALS = 6
USDC_MULTIPLIER = 10 ** USDC_DECIMALS

# Default price and amount precision
DEFAULT_PRICE_PRECISION = 18
DEFAULT_AMOUNT_PRECISION = 18