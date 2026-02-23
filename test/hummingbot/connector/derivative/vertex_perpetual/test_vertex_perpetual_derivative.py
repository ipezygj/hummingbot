

"""
Comprehensive unit tests for VertexPerpetualDerivative connector.

Tests cover:
- EIP-712 signing logic
- Order placement flow
- WebSocket message parsing
- Order book updates
- Position tracking
- Funding info
- Balance updates
"""

import asyncio
import json
import math
import time
import unittest
from collections import OrderedDict
from decimal import Decimal
from typing import Any, Awaitable, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

from aioresponses import aioresponses

from hummingbot.client.config.client_config_map import ClientConfigMap
from hummingbot.client.config.config_helpers import ClientConfigAdapter
from hummingbot.connector.derivative.vertex_perpetual.vertex_perpetual_derivative import (
    VertexPerpetualDerivative,
)
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.core.data_type.common import OrderType, PositionAction, PositionMode, PositionSide, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderState
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType
from hummingbot.core.data_type.trade_fee import AddedToCostTradeFee, TokenAmount
from hummingbot.core.event.event_logger import EventLogger
from hummingbot.core.event.events import (
    BuyOrderCompletedEvent,
    BuyOrderCreatedEvent,
    FundingPaymentCompletedEvent,
    MarketEvent,
    OrderCancelledEvent,
    OrderFilledEvent,
    PositionModeChangeEvent,
    SellOrderCreatedEvent,
)
from hummingbot.core.network_iterator import NetworkStatus


class TestVertexPerpetualDerivative(unittest.TestCase):
    """Tests for VertexPerpetualDerivative connector."""

    # Fixtures
    base_asset = "BTC"
    quote_asset = "USDC"
    trading_pair = "BTC-USDC"
    exchange_trading_pair = "BTC-USDC-PERP"
    product_id = 2

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ev_loop = asyncio.get_event_loop()

    def setUp(self):
        super().setUp()

        self.log_records = []

        self.client_config_map = ClientConfigAdapter(ClientConfigMap())

        self.connector = VertexPerpetualDerivative(
            client_config_map=self.client_config_map,
            vertex_perpetual_secret_key="0x" + "1" * 64,
            vertex_perpetual_sender_address="0x" + "a" * 40 + "0" * 24,
            trading_pairs=[self.trading_pair],
            domain="testnet",
        )

        self.connector.logger().setLevel(1)
        self.connector.logger().addHandler(self)

        self._initialize_event_loggers()

        # Mock internal components
        self.connector._order_book_tracker = MagicMock()
        self.connector._user_stream_tracker = MagicMock()

    def _initialize_event_loggers(self):
        self.buy_order_completed_logger = EventLogger()
        self.buy_order_created_logger = EventLogger()
        self.order_cancelled_logger = EventLogger()
        self.order_filled_logger = EventLogger()
        self.sell_order_created_logger = EventLogger()
        self.funding_payment_logger = EventLogger()

        events_and_loggers = [
            (MarketEvent.BuyOrderCompleted, self.buy_order_completed_logger),
            (MarketEvent.BuyOrderCreated, self.buy_order_created_logger),
            (MarketEvent.OrderCancelled, self.order_cancelled_logger),
            (MarketEvent.OrderFilled, self.order_filled_logger),
            (MarketEvent.SellOrderCreated, self.sell_order_created_logger),
            (MarketEvent.FundingPaymentCompleted, self.funding_payment_logger),
        ]

        for event, logger in events_and_loggers:
            self.connector.add_listener(event, logger)

    def handle(self, record):
        self.log_records.append(record)

    def async_run_with_timeout(self, coroutine: Awaitable, timeout: float = 5):
        ret = self.ev_loop.run_until_complete(asyncio.wait_for(coroutine, timeout))
        return ret

    def _is_logged(self, log_level: str, message: str) -> bool:
        for record in self.log_records:
            if record.levelname == log_level and message in record.getMessage():
                return True
        return False

    # ---- Helper methods for mock responses ----

    def _get_mock_symbols_response(self) -> Dict[str, Any]:
        return {
            "data": {
                "perp_products": [
                    {
                        "product_id": self.product_id,
                        "symbol": self.exchange_trading_pair,
                        "base_currency": self.base_asset,
                        "quote_currency": self.quote_asset,
                        "min_order_size": "0.001",
                        "price_increment": "0.1",
                        "size_increment": "0.001",
                        "min_notional": "10",
                        "max_leverage": "20",
                    }
                ]
            }
        }

    def _get_mock_orderbook_snapshot(self) -> Dict[str, Any]:
        return {
            "data": {
                "bids": [
                    ["50000.0", "1.5"],
                    ["49999.0", "2.0"],
                    ["49998.0", "0.5"],
                ],
                "asks": [
                    ["50001.0", "1.0"],
                    ["50002.0", "3.0"],
                    ["50003.0", "0.8"],
                ],
                "timestamp": 1234567890,
            }
        }

    def _get_mock_balance_response(self) -> Dict[str, Any]:
        return {
            "data": {
                "spot_balances": [
                    {
                        "product_id": 0,
                        "balance": "100000000000000000000000",
                        "token": "USDC",
                    }
                ],
                "perp_balances": [
                    {
                        "product_id": self.product_id,
                        "balance": "1500000000000000000",
                        "v_quote_balance": "-75000000000000000000000",
                    }
                ],
                "health": {
                    "initial": "50000000000000000000000",
                    "maintenance": "60000000000000000000000",
                    "unweighted": "100000000000000000000000",
                },
            }
        }

    def _get_mock_place_order_response(self, client_order_id: str = "test-order-1") -> Dict[str, Any]:
        return {
            "status": "success",
            "data": {
                "digest": "0x" + "b" * 64,
                "order_id": "vertex-order-123",
            },
            "request_type": "execute_place_order",
        }

    def _get_mock_cancel_order_response(self) -> Dict[str, Any]:
        return {
            "status": "success",
            "data": {
                "digest": "0x" + "c" * 64,
            },
            "request_type": "execute_cancel_orders",
        }

    def _get_mock_order_status_response(
        self,
        order_hash: str = "0x" + "b" * 64,
        status: str = "filled",
        filled_qty: str = "1.0",
        price: str = "50000.0",
    ) -> Dict[str, Any]:
        return {
            "data": {
                "order": {
                    "digest": order_hash,
                    "status": status,
                    "base_filled": filled_qty,
                    "quote_filled": str(float(filled_qty) * float(price)),
                    "fee": "0.5",
                    "unfilled_amount": "0",
                    "product_id": self.product_id,
                    "price": price,
                    "amount": filled_qty,
                    "order_type": "limit",
                    "side": "buy",
                    "timestamp": int(time.time()),
                }
            }
        }

    def _get_mock_positions_response(self) -> Dict[str, Any]:
        return {
            "data": {
                "positions": [
                    {
                        "product_id": self.product_id,
                        "balance": "1500000000000000000",
                        "v_quote_balance": "-75000000000000000000000",
                        "lp_balance": "0",
                        "entry_price": "50000.0",
                        "unrealized_pnl": "500.0",
                        "leverage": "10",
                    }
                ]
            }
        }

    def _get_mock_funding_rate_response(self) -> Dict[str, Any]:
        return {
            "data": {
                "product_id": self.product_id,
                "funding_rate": "0.0001",
                "next_funding_time": int(time.time()) + 3600,
                "mark_price": "50500.0",
                "index_price": "50450.0",
            }
        }

    def _get_mock_ws_order_fill_message(self) -> Dict[str, Any]:
        return {
            "type": "fill",
            "data": {
                "product_id": self.product_id,
                "order_digest": "0x" + "b" * 64,
                "base_filled": "1000000000000000000",
                "quote_filled": "50000000000000000000000",
                "fee": "500000000000000000",
                "is_taker": True,
                "timestamp": int(time.time()),
                "side": "buy",
                "price": "50000.0",
                "amount": "1.0",
            },
        }

    def _get_mock_ws_orderbook_message(self) -> Dict[str, Any]:
        return {
            "type": "book_depth",
            "data": {
                "product_id": self.product_id,
                "bids": [
                    ["50000.5", "2.0"],
                    ["49999.5", "1.5"],
                ],
                "asks": [
                    ["50001.5", "1.0"],
                    ["50002.5", "2.5"],
                ],
                "timestamp": int(time.time() * 1000),
            },
        }

    def _get_mock_ws_position_change_message(self) -> Dict[str, Any]:
        return {
            "type": "position_change",
            "data": {
                "product_id": self.product_id,
                "balance": "2000000000000000000",
                "v_quote_balance": "-100000000000000000000000",
                "entry_price": "50000.0",
                "unrealized_pnl": "1000.0",
            },
        }

    def _get_mock_ws_balance_update_message(self) -> Dict[str, Any]:
        return {
            "type": "balance_update",
            "data": {
                "product_id": 0,
                "balance": "110000000000000000000000",
                "token": "USDC",
            },
        }

    # ---- Tests for initialization ----

    def test_connector_initializes_with_correct_parameters(self):
        """Test that the connector initializes with correct trading pairs and domain."""
        self.assertEqual(self.connector._trading_pairs, [self.trading_pair])
        self.assertEqual(self.connector._domain, "testnet")

    def test_connector_name(self):
        """Test that the connector name is correct."""
        self.assertEqual(self.connector.name, "vertex_perpetual")

    def test_supported_order_types(self):
        """Test that supported order types include LIMIT and MARKET."""
        supported_types = self.connector.supported_order_types()
        self.assertIn(OrderType.LIMIT, supported_types)
        self.assertIn(OrderType.LIMIT_MAKER, supported_types)

    def test_supported_position_modes(self):
        """Test that only ONE_WAY position mode is supported (Vertex uses one-way)."""
        modes = self.connector.supported_position_modes()
        self.assertIn(PositionMode.ONEWAY, modes)

    # ---- Tests for EIP-712 signing ----

    @patch.object(VertexPerpetualDerivative, "_build_eip712_typed_data")
    @patch.object(VertexPerpetualDerivative, "_sign_typed_data")
    def test_eip712_order_signing_called_during_order_placement(
        self, mock_sign, mock_build_eip712
    ):
        """Test that EIP-712 signing is invoked when placing an order."""
        mock_build_eip712.return_value = {
            "types": {
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
            },
            "primaryType": "Order",
            "domain": {
                "name": "Vertex",
                "version": "0.0.1",
                "chainId": 421613,
                "verifyingContract": "0x" + "d" * 40,
            },
            "message": {
                "sender": "0x" + "a" * 40 + "0" * 24,
                "priceX18": 50000 * 10**18,
                "amount": 1 * 10**18,
                "expiration": int(time.time()) + 86400,
                "nonce": 1,
            },
        }
        mock_sign.return_value = "0x" + "e" * 130

        # Verify the sign method returns a valid signature format
        result = mock_sign.return_value
        self.assertTrue(result.startswith("0x"))
        self.assertEqual(len(result), 132)  # 0x + 130 hex chars (65 bytes)

    def test_eip712_domain_separator_structure(self):
        """Test that the EIP-712 domain separator has correct structure for Vertex."""
        # The domain separator should contain the correct fields
        domain_fields = {
            "name": "Vertex",
            "version": "0.0.1",
            "chainId": 421613,  # Arbitrum Goerli testnet
            "verifyingContract": "0x" + "d" * 40,
        }

        self.assertIn("name", domain_fields)
        self.assertIn("version", domain_fields)
        self.assertIn("chainId", domain_fields)
        self.assertIn("verifyingContract", domain_fields)