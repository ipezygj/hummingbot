

"""Vertex Perpetual API Order Book Data Source."""

import asyncio
import logging
import time
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import ujson

from hummingbot.connector.derivative.vertex_perpetual import (
    vertex_perpetual_constants as CONSTANTS,
    vertex_perpetual_web_utils as web_utils,
)
from hummingbot.core.data_type.common import TradeType
from hummingbot.core.data_type.funding_info import FundingInfo, FundingInfoUpdate
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType
from hummingbot.core.data_type.order_book_row import OrderBookRow
from hummingbot.core.data_type.perpetual_api_order_book_data_source import PerpetualAPIOrderBookDataSource
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger


class VertexPerpetualAPIOrderBookDataSource(PerpetualAPIOrderBookDataSource):
    """
    Data source for Vertex Protocol perpetual order book data.

    Uses:
    - Gateway REST API for order book snapshots
    - Indexer REST API for historical trades and funding data
    - WebSocket subscriptions for real-time L2 orderbook and trade updates

    Vertex Protocol docs: https://docs.vertexprotocol.com/
    """

    _logger: Optional[HummingbotLogger] = None
    _trading_pair_symbol_map: Dict[str, str] = {}
    _mapping_initialization_lock = asyncio.Lock()

    def __init__(
        self,
        trading_pairs: List[str],
        connector: "VertexPerpetualDerivative",  # noqa: F821
        api_factory: Optional[WebAssistantsFactory] = None,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
        throttler: Optional[Any] = None,
    ):
        super().__init__(trading_pairs)
        self._connector = connector
        self._api_factory = api_factory
        self._domain = domain
        self._throttler = throttler
        self._trading_pairs: List[str] = trading_pairs
        self._message_queue: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self._ws_assistant: Optional[WSAssistant] = None
        self._last_ws_message_sent_timestamp = 0
        self._ping_interval = CONSTANTS.WS_HEARTBEAT_INTERVAL
        self._order_book_snapshot_stream: asyncio.Queue = asyncio.Queue()
        self._order_book_diff_stream: asyncio.Queue = asyncio.Queue()
        self._trade_messages_queue: asyncio.Queue = asyncio.Queue()
        self._funding_info: Dict[str, FundingInfo] = {}
        self._last_traded_prices: Dict[str, Decimal] = {}

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(HummingbotLogger.logger_name_for_class(cls))
        return cls._logger

    @property
    def order_book_snapshot_stream(self) -> asyncio.Queue:
        return self._message_queue.get(
            CONSTANTS.ORDER_BOOK_SNAPSHOT_CHANNEL, asyncio.Queue()
        )

    @property
    def order_book_diff_stream(self) -> asyncio.Queue:
        return self._message_queue.get(
            CONSTANTS.ORDER_BOOK_DIFF_CHANNEL, asyncio.Queue()
        )

    @property
    def trade_stream(self) -> asyncio.Queue:
        return self._message_queue.get(
            CONSTANTS.TRADE_CHANNEL, asyncio.Queue()
        )

    @property
    def funding_info_stream(self) -> asyncio.Queue:
        return self._message_queue.get(
            CONSTANTS.FUNDING_INFO_CHANNEL, asyncio.Queue()
        )

    async def get_last_traded_prices(
        self,
        trading_pairs: List[str],
        domain: Optional[str] = None,
    ) -> Dict[str, float]:
        """
        Fetches the last traded price for each trading pair from the Vertex Indexer.
        """
        last_traded_prices = {}
        for trading_pair in trading_pairs:
            try:
                product_id = self._connector.trading_pair_to_product_id(trading_pair)
                response = await self._request_indexer(
                    endpoint=CONSTANTS.INDEXER_MARKET_SNAPSHOTS_ENDPOINT,
                    params={
                        "product_id": product_id,
                    },
                )
                if response and "snapshots" in response and len(response["snapshots"]) > 0:
                    snapshot = response["snapshots"][0]
                    last_price = self._parse_last_traded_price(snapshot)
                    last_traded_prices[trading_pair] = float(last_price)
                    self._last_traded_prices[trading_pair] = last_price
                elif trading_pair in self._last_traded_prices:
                    last_traded_prices[trading_pair] = float(
                        self._last_traded_prices[trading_pair]
                    )
                else:
                    # Fallback: try gateway market price
                    last_traded_prices[trading_pair] = await self._get_last_traded_price_from_gateway(
                        trading_pair
                    )
            except Exception:
                self.logger().warning(
                    f"Error fetching last traded price for {trading_pair}. "
                    f"Using cached value if available.",
                    exc_info=True,
                )
                if trading_pair in self._last_traded_prices:
                    last_traded_prices[trading_pair] = float(
                        self._last_traded_prices[trading_pair]
                    )
        return last_traded_prices

    async def _get_last_traded_price_from_gateway(self, trading_pair: str) -> float:
        """Fallback to get last traded price from Gateway."""
        try:
            product_id = self._connector.trading_pair_to_product_id(trading_pair)
            response = await self._request_gateway(
                endpoint=CONSTANTS.GATEWAY_MARKET_PRICE_ENDPOINT,
                params={"product_id": product_id},
            )
            if response and "price" in response:
                return float(response["price"])
        except Exception:
            self.logger().warning(
                f"Error fetching last traded price from gateway for {trading_pair}.",
                exc_info=True,
            )
        return 0.0

    def _parse_last_traded_price(self, snapshot: Dict[str, Any]) -> Decimal:
        """Parse the last traded price from an indexer market snapshot."""
        if "last_fill_price" in snapshot:
            return Decimal(str(snapshot["last_fill_price"]))
        elif "oracle_price" in snapshot:
            return Decimal(str(snapshot["oracle_price"]))
        return Decimal("0")

    async def _order_book_snapshot(self, trading_pair: str) -> OrderBookMessage:
        """
        Retrieves the full order book snapshot from the Vertex Gateway.

        The Gateway provides real-time L2 order book data for Vertex Protocol.
        """
        product_id = self._connector.trading_pair_to_product_id(trading_pair)
        snapshot_response = await self._request_gateway(
            endpoint=CONSTANTS.GATEWAY_ORDER_BOOK_ENDPOINT,
            params={
                "product_id": product_id,
                "depth": CONSTANTS.ORDER_BOOK_DEPTH,
            },
        )

        snapshot_timestamp = time.time()
        snapshot_msg = self._parse_order_book_snapshot_message(
            trading_pair=trading_pair,
            snapshot_data=snapshot_response,
            timestamp=snapshot_timestamp,
        )
        return snapshot_msg

    def _parse_order_book_snapshot_message(
        self,
        trading_pair: str,
        snapshot_data: Dict[str, Any],
        timestamp: float,
    ) -> OrderBookMessage:
        """Parse the order book snapshot from Gateway response into an OrderBookMessage."""
        bids = []
        asks = []

        if "bids" in snapshot_data:
            for bid in snapshot_data["bids"]:
                price = Decimal(str(bid[0])) if isinstance(bid, (list, tuple)) else Decimal(str(bid["price"]))
                amount = Decimal(str(bid[1])) if isinstance(bid, (list, tuple)) else Decimal(str(bid["quantity"]))
                # Vertex uses x18 format internally - normalize if needed
                price = self._normalize_vertex_value(price)
                amount = self._normalize_vertex_value(amount)
                bids.append(OrderBookRow(float(price), float(amount), int(timestamp * 1e3)))

        if "asks" in snapshot_data:
            for ask in snapshot_data["asks"]:
                price = Decimal(str(ask[0])) if isinstance(ask, (list, tuple)) else Decimal(str(ask["price"]))
                amount = Decimal(str(ask[1])) if isinstance(ask, (list, tuple)) else Decimal(str(ask["quantity"]))
                price = self._normalize_vertex_value(price)
                amount = self._normalize_vertex_value(amount)
                asks.append(OrderBookRow(float(price), float(amount), int(timestamp * 1e3)))

        update_id = snapshot_data.get("timestamp", int(timestamp * 1e3))
        if isinstance(update_id, str):
            update_id = int(update_id)

        content = {
            "trading_pair": trading_pair,
            "update_id": update_id,
            "bids": [(row.price, row.amount) for row in bids],
            "asks": [(row.price, row.amount) for row in asks],
        }

        return OrderBookMessage(
            message_type=OrderBookMessageType.SNAPSHOT,
            content=content,
            timestamp=timestamp,
        )

    @staticmethod
    def _normalize_vertex_value(value: Decimal) -> Decimal:
        """
        Normalize Vertex x18 format values if they appear to be in that format.
        Vertex Protocol uses x18 fixed-point representation (multiply by 10^18).
        Values greater than 10^15 are likely in x18 format.
        """
        if abs(value) > Decimal("1e15"):
            return value / Decimal("1e18")
        return value

    async def _parse_trade_message(
        self, raw_message: Dict[str, Any], message_queue: asyncio.Queue
    ):
        """Parse a trade message from WebSocket and add to message queue."""
        trading_pair = self._get_trading_pair_from_message(raw_message)
        if trading_pair is None:
            return

        trades = raw_message.get("trades", [raw_message])
        if not isinstance(trades, list):
            trades = [trades]

        for trade_data in trades:
            try:
                trade_timestamp = float(trade_data.get("timestamp", time.time()))
                price = Decimal(str(trade_data.get("price", "0")))
                amount = Decimal(str(trade_data.get("qty", trade_data.get("quantity", "0"))))

                price = self._normalize_vertex_value(price)
                amount = self._normalize_vertex_value(amount)

                # Determine trade type from taker side
                is_taker_buyer = trade_data.get("is_taker_buyer", trade_data.get("side", "") == "buy")
                trade_type = TradeType.BUY if is_taker_buyer else TradeType.SELL

                trade_id = trade_data.get(
                    "submission_idx",
                    trade_data.get("trade_id", str(int(trade_timestamp * 1e6)))
                )

                self._last_traded_prices[trading_pair] = price

                content = {
                    "trading_pair": trading_pair,
                    "trade_type": float(trade_type.value),
                    "trade_id": str(trade_id),
                    "update_id": int(trade_timestamp * 1e3),
                    "price": str(price),
                    "amount": str(amount),
                }

                trade_message = OrderBookMessage(
                    message_type=OrderBookMessageType.TRADE,
                    content=content,
                    timestamp=trade_timestamp,
                )
                message_queue.put_nowait(trade_message)

            except Exception:
                self.logger().warning(
                    f"Error parsing trade message for {trading_pair}: {trade_data}",
                    exc_info=True,
                )

    async def _parse_order_book_diff_message(
        self, raw_message: Dict[str, Any], message_queue: asyncio.Queue
    ):
        """Parse an order book diff/update message from WebSocket."""
        trading_pair = self._get_trading_pair_from_message(raw_message)
        if trading_pair is None:
            return

        try:
            timestamp = float(raw_message.get("timestamp", time.time()))
            update_id = int(raw_message.get("last_max_timestamp", timestamp * 1e3))

            bids = []
            asks = []

            for bid_data in raw_message.get("bids", []):
                if isinstance(bid_data, (list, tuple)):
                    price = self._normalize_vertex_value(Decimal(str(bid_data[0])))
                    amount = self._normalize_vertex_value(Decimal(str(bid_data[1])))
                else:
                    price = self._normalize_vertex_value(Decimal(str(bid_data.get("price", "0"))))
                    amount = self._normalize_vertex_value(Decimal(str(bid_data.get("qty", "0"))))
                bids.append((float(price), float(amount)))

            for ask_data in raw_message.get("asks", []):
                if isinstance(ask_data, (list, tuple)):
                    price = self._normalize_vertex_value(Decimal(str(ask_data[0])))
                    amount = self._normalize_vertex_value(Decimal(str(ask_data[1])))
                else:
                    price = self._normalize_vertex_value(Decimal(str(ask_data.get("price", "0"))))
                    amount = self._normalize_vertex_value(Decimal(str(ask_data.get("qty", "0"))))
                asks.append((float(price), float(amount)))

            content = {
                "trading_pair": trading_pair,
                "update_id": update_id,
                "bids": bids,
                "asks": asks,
            }

            diff_message = OrderBookMessage(
                message_type=OrderBookMessageType.DIFF,
                content=content,
                timestamp=timestamp,
            )
            message_queue.put_nowait(diff_message)

        except Exception:
            self.logger().warning(
                f"Error parsing order book diff message for {trading_pair}",
                exc_info=True,
            )

    async def _parse_order_book_snapshot_message_ws(
        self, raw_message: Dict[str, Any], message_queue: asyncio.Queue
    ):
        """Parse an order book snapshot message received via WebSocket."""
        trading_pair = self._get_trading_pair_from_message(raw_message)
        if trading_pair is None:
            return

        try:
            timestamp = float(raw_message.get("timestamp", time.time()))
            snapshot_msg = self._parse_order_book_snapshot_message(
                trading_pair=trading_pair,
                snapshot_data=raw_message,
                timestamp