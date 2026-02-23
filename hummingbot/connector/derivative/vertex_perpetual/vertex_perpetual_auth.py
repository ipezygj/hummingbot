

# Vertex Perpetual Auth - EIP-712 Signing for Arbitrum

"""
hummingbot/connector/derivative/vertex_perpetual/vertex_perpetual_auth.py

VertexPerpetualAuth: Handles EIP-712 signature generation for Vertex Protocol
on Arbitrum. Supports place_order, cancel_order, withdraw, and other
authenticated operations using the Vertex gateway API.

Reference: https://docs.vertexprotocol.com/
"""

import hashlib
import logging
import time
from decimal import Decimal
from enum import IntEnum
from typing import Any, Dict, List, Optional, Tuple, Union

from eth_abi import encode as eth_abi_encode
from eth_account import Account
from eth_account.messages import encode_structured_data
from eth_utils import keccak, to_bytes, to_checksum_address, to_hex

logger = logging.getLogger(__name__)

# ============================================================================
# Vertex Protocol Constants
# ============================================================================

# Arbitrum One Chain ID
ARBITRUM_ONE_CHAIN_ID = 42161

# Arbitrum Goerli (Testnet) Chain ID
ARBITRUM_GOERLI_CHAIN_ID = 421613

# Vertex Endpoint Contract Addresses
VERTEX_ENDPOINT_ADDRESS_MAINNET = "0xbbEE07B3e8121227AfCFe1E2B82772571571FE18"
VERTEX_ENDPOINT_ADDRESS_TESTNET = "0xaDeFa2F9aCFB1bac7bC0039B3a3a72Dbe9a6eDEe"

# EIP-712 Domain Name and Version for Vertex
VERTEX_EIP712_DOMAIN_NAME = "Vertex"
VERTEX_EIP712_DOMAIN_VERSION = "0.0.1"

# Subaccount name encoding
DEFAULT_SUBACCOUNT_NAME = "default"

# Order expiration types
GOOD_TIL_TIME = 1
IMMEDIATE_OR_CANCEL = 2
FOK = 3
POST_ONLY = 4

# Precision constants (Vertex uses 18 decimal fixed-point for most fields)
X18_DECIMALS = 18
X18_MULTIPLIER = 10 ** X18_DECIMALS


class VertexOrderType(IntEnum):
    """Vertex order types encoded in the expiration field."""
    DEFAULT = 0
    IMMEDIATE_OR_CANCEL = 1
    FOK = 2
    POST_ONLY = 3


# ============================================================================
# EIP-712 Type Definitions for Vertex Protocol
# ============================================================================

ORDER_EIP712_TYPES = {
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

CANCEL_ORDERS_EIP712_TYPES = {
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

CANCEL_PRODUCT_ORDERS_EIP712_TYPES = {
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

WITHDRAW_COLLATERAL_EIP712_TYPES = {
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

LIQUIDATE_SUBACCOUNT_EIP712_TYPES = {
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

LINK_SIGNER_EIP712_TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "StreamAuthentication": [
        {"name": "sender", "type": "bytes32"},
        {"name": "expiration", "type": "uint64"},
    ],
}

LIST_TRIGGER_ORDERS_EIP712_TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "ListTriggerOrders": [
        {"name": "sender", "type": "bytes32"},
        {"name": "recvTime", "type": "uint64"},
    ],
}


class VertexPerpetualAuth:
    """
    Handles authentication and EIP-712 signature generation for Vertex Protocol
    on Arbitrum. This class manages:

    - Subaccount derivation from wallet address
    - EIP-712 structured data signing for all Vertex operations
    - Order placement signatures
    - Order cancellation signatures
    - Withdrawal signatures
    - Stream authentication signatures
    - Nonce management

    Vertex Protocol uses EIP-712 typed structured data signing where each
    operation type has its own type schema. All signatures are verified
    on-chain on Arbitrum.
    """

    def __init__(
        self,
        private_key: str,
        chain_id: int = ARBITRUM_ONE_CHAIN_ID,
        endpoint_address: Optional[str] = None,
        subaccount_name: str = DEFAULT_SUBACCOUNT_NAME,
    ):
        """
        Initialize VertexPerpetualAuth.

        :param private_key: Hex-encoded private key (with or without 0x prefix)
        :param chain_id: Arbitrum chain ID (42161 for mainnet, 421613 for testnet)
        :param endpoint_address: Vertex endpoint contract address (auto-selected if None)
        :param subaccount_name: Subaccount name for the trading account
        """
        # Normalize private key
        if not private_key.startswith("0x"):
            private_key = "0x" + private_key
        self._private_key = private_key
        self._account = Account.from_key(self._private_key)
        self._wallet_address = self._account.address
        self._chain_id = chain_id

        # Set endpoint address based on chain
        if endpoint_address is not None:
            self._endpoint_address = to_checksum_address(endpoint_address)
        elif chain_id == ARBITRUM_ONE_CHAIN_ID:
            self._endpoint_address = to_checksum_address(VERTEX_ENDPOINT_ADDRESS_MAINNET)
        elif chain_id == ARBITRUM_GOERLI_CHAIN_ID:
            self._endpoint_address = to_checksum_address(VERTEX_ENDPOINT_ADDRESS_TESTNET)
        else:
            raise ValueError(f"Unsupported chain_id: {chain_id}. Provide endpoint_address explicitly.")

        self._subaccount_name = subaccount_name
        self._sender = self._compute_sender(self._wallet_address, self._subaccount_name)

        # Internal nonce counter (Vertex uses recv_time-based nonces typically,
        # but we track a local counter as fallback)
        self._nonce_counter = 0

        logger.info(
            f"VertexPerpetualAuth initialized: wallet={self._wallet_address}, "
            f"chain_id={self._chain_id}, endpoint={self._endpoint_address}, "
            f"sender={self._sender.hex()}"
        )

    # ========================================================================
    # Properties
    # ========================================================================

    @property
    def wallet_address(self) -> str:
        """Return the checksummed wallet address."""
        return self._wallet_address

    @property
    def sender(self) -> bytes:
        """Return the 32-byte sender (subaccount) identifier."""
        return self._sender

    @property
    def sender_hex(self) -> str:
        """Return the hex-encoded sender (subaccount) identifier."""
        return "0x" + self._sender.hex()

    @property
    def chain_id(self) -> int:
        """Return the chain ID."""
        return self._chain_id

    @property
    def endpoint_address(self) -> str:
        """Return the Vertex endpoint contract address."""
        return self._endpoint_address

    @property
    def subaccount_name(self) -> str:
        """Return the subaccount name."""
        return self._subaccount_name

    # ========================================================================
    # Subaccount / Sender Computation
    # ========================================================================

    @staticmethod
    def _compute_sender(wallet_address: str, subaccount_name: str) -> bytes:
        """
        Compute the 32-byte sender (subaccount) from a wallet address and
        subaccount name. In Vertex, the sender is constructed as:

            sender = wallet_address (20 bytes) + subaccount_name_hash (12 bytes)

        The subaccount name "default" maps to 12 zero bytes.

        :param wallet_address: Checksummed Ethereum address
        :param subaccount_name: Name of the subaccount
        :return: 32-byte sender identifier
        """
        address_bytes = to_bytes(hexstr=wallet_address)  # 20 bytes

        if subaccount_name == DEFAULT_SUBACCOUNT_NAME:
            # Default subaccount: pad with 12 zero bytes
            name_bytes = b'\x00' * 12
        else:
            # Non-default: use first 12 bytes of the subaccount name,
            # right-padded with zeros
            name_encoded = subaccount_name.encode('utf-8')
            if len(name_encoded) > 12:
                name_bytes = name_encoded[:12]
            else:
                name_bytes = name_encoded + b'\x00' * (12 - len(name_encoded))

        sender = address_bytes + name_bytes
        assert len(sender) == 32, f"Sender must be 32 bytes, got {len(sender)}"
        return sender

    @staticmethod
    def subaccount_to_hex(wallet_address: str, subaccount_name: str = DEFAULT_SUBACCOUNT_NAME) -> str:
        """
        Utility method to compute and return the hex representation of a subaccount.

        :param wallet_address: Checksummed Ethereum address
        :param subaccount_name: Name of the subaccount
        :return: Hex-encoded 32-byte sender
        """
        sender = VertexPerpetualAuth._compute_sender(wallet_address, subaccount_name)
        return "0x" + sender.hex()

    # ========================================================================
    # EIP-712 Domain
    # ========================================================================

    def _get_eip712_domain(self) -> Dict[str, Any]:
        """
        Construct the EIP-712 domain separator parameters.

        :return: Domain dictionary for EIP-712 encoding
        """
        return {
            "name": VERTEX_EIP712_DOMAIN_NAME,
            "version": VERTEX_EIP712_DOMAIN_VERSION,
            "chainId": self._chain_id,
            "verifyingContract": self._endpoint_address,
        }

    # ========================================================================
    # Nonce Generation
    # ========================================================================

    def generate_nonce(self, recv_time_ms: Optional[int] = None) -> int:
        """
        Generate a nonce for Vertex operations. Vertex uses recv_time-based
        nonces. The nonce encodes the recv_time and a sequential counter:

            nonce = (recv_time_seconds << 20) | sequential_counter

        The sequential counter occupies the lower 20 bits.

        :param recv_time_ms: Receive time in milliseconds. If None, uses current time.
        :return: Integer nonce
        """
        if recv_time_ms is None:
            recv_time_ms = int(time.time() * 1000)

        recv_time_seconds = recv_time_ms // 1000

        # Increment counter and mask to 20 bits
        self._nonce_counter = (self._nonce_counter + 1) & 0xFFFFF

        nonce = (recv_time_seconds << 20) | self._nonce_counter
        return nonce

    def generate_order_nonce(self, recv_time_ms: Optional[int] = None) -> int:
        """
        Generate a nonce specifically for order placement.
        Uses the same scheme as generate_nonce but can be extended.

        :param recv_time_ms: Receive time in milliseconds
        :return: Integer nonce
        """
        return self.generate_nonce(recv_time_ms)

    # ========================================================================
    # Expiration Encoding
    # ========================================================================

    @staticmethod
    def encode_expiration(
        expiration_timestamp: int,
        order_type: VertexOrderType = VertexOrderType.DEFAULT,
    ) -> int:
        """
        Encode the expiration field for Vertex orders. The order type is encoded
        in the upper bits of the expiration:

            encoded_expiration = expiration_timestamp | (order_type << 62)

        :param expiration_timestamp: Unix timestamp for order expiry
        :param order_type: Order type (DEFAULT, IOC, FOK, POST_ONLY)
        :return: Encoded expiration value
        """
        return expiration_timestamp | (int(order_type) << 62)

    @staticmethod
    def decode_expiration(encoded_expiration: int) -> Tuple[int, VertexOrderType]:
        """
        Decode the expiration field to extract timestamp and order type.

        :param encoded_expiration: Encoded expiration value
        :return: Tuple of (expiration_timestamp, order_type)
        """
        order_type_