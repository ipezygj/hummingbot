

import asyncio
import logging
import time
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from hummingbot.connector.derivative.aevo_perpetual import (
    aevo_perpetual_constants as CONSTANTS,
    aevo_perpetual_web_utils as web_utils,
)
from hummingbot.connector.derivative.aevo_perpetual.aevo_perpetual_auth import AevoPerpetualAuth
from hummingbot.core.data_type.funding_info import FundingInfo, FundingInfoUpdate
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType
from hummingbot.core.data_type.order_book_row import OrderBookRow
from hummingbot.core.data_type.perpetual_api_order_book_data_source import PerpetualAPIOrderBookDataSource
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, WSJSONRequest, WSPlainTextRequest
from hummingbot.core.web_assistant.rest_assistant import RESTAssistant
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger


class AevoPerpetualAPIOrderBookDataSource(PerpetualAPIOrderBookDataSource):
    _logger: Optional[HummingbotLogger] = None

    def __init__(
        self,
        trading_pairs: List[str],
        connector: "AevoPerpetualDerivative",
        api_factory: WebAssistantsFactory,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        super().__init__(trading_pairs)
        self._connector = connector
        self._api_factory = api_factory
        self._domain = domain
        self._trading_pairs: List[str] = trading_pairs
        self._message_queue: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self._last_ws_message_sent_timestamp = 0
        self._ping_interval = 30

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(HummingbotLogger.logger_name_for_class(cls))
        return cls._logger

    async def get_last_traded_prices(
        self,
        trading_pairs: List[str],
        domain: Optional[str] = None,
    ) -> Dict[str, float]:
        """
        Fetches the last traded price for each trading pair using the REST API.
        """
        last_traded_prices: Dict[str, float] = {}
        results = await self._request_last_traded_prices(trading_pairs)
        for trading_pair, price in results.items():
            last_traded_prices[trading_pair] = price
        return last_traded_prices

    async def _request_last_traded_prices(self, trading_pairs: List[str]) -> Dict[str, float]:
        """
        Helper to request last traded prices from the Aevo REST API.
        """
        last_traded_prices: Dict[str, float] = {}
        for trading_pair in trading_pairs:
            try:
                exchange_symbol = await self._connector.exchange_symbol_associated_to_pair(
                    trading_pair=trading_pair
                )
                instrument_id = self._connector._instrument_id_from_exchange_symbol(exchange_symbol)

                rest_assistant = await self._api_factory.get_rest_assistant()
                url = web_utils.public_rest_url(
                    path_url=CONSTANTS.TICKER_PRICE_CHANGE_PATH_URL,
                    domain=self._domain,
                )

                params = {"instrument_name": exchange_symbol}

                data = await rest_assistant.execute_request(
                    url=url,
                    params=params,
                    method=RESTMethod.GET,
                    throttler_limit_id=CONSTANTS.TICKER_PRICE_CHANGE_PATH_URL,
                    is_auth_required=False,
                )

                if "last_price" in data:
                    last_traded_prices[trading_pair] = float(data["last_price"])
                elif "mark" in data and "price" in data["mark"]:
                    last_traded_prices[trading_pair] = float(data["mark"]["price"])
                else:
                    self.logger().warning(
                        f"Could not find last traded price for {trading_pair} in ticker response: {data}"
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().exception(
                    f"Error getting last traded price for {trading_pair}."
                )
        return last_traded_prices

    async def _request_order_book_snapshot(self, trading_pair: str) -> OrderBookMessage:
        """
        Retrieves a copy of the full order book from the exchange via REST API.
        """
        exchange_symbol = await self._connector.exchange_symbol_associated_to_pair(
            trading_pair=trading_pair
        )
        instrument_id = self._connector._instrument_id_from_exchange_symbol(exchange_symbol)

        rest_assistant = await self._api_factory.get_rest_assistant()
        url = web_utils.public_rest_url(
            path_url=CONSTANTS.ORDER_BOOK_PATH_URL.format(instrument_name=exchange_symbol),
            domain=self._domain,
        )

        data = await rest_assistant.execute_request(
            url=url,
            method=RESTMethod.GET,
            throttler_limit_id=CONSTANTS.ORDER_BOOK_PATH_URL,
            is_auth_required=False,
        )

        snapshot_timestamp: float = time.time()
        snapshot_msg: OrderBookMessage = self._parse_order_book_snapshot_message(
            raw_message=data,
            message_queue=None,
            trading_pair=trading_pair,
            timestamp=snapshot_timestamp,
        )
        return snapshot_msg

    async def _order_book_snapshot(self, trading_pair: str) -> OrderBookMessage:
        """
        Public method to get order book snapshot.
        """
        snapshot: OrderBookMessage = await self._request_order_book_snapshot(trading_pair)
        return snapshot

    async def _subscribe_channels(self, ws: WSAssistant):
        """
        Subscribes to the order book and trades channels for all trading pairs.
        """
        try:
            for trading_pair in self._trading_pairs:
                exchange_symbol = await self._connector.exchange_symbol_associated_to_pair(
                    trading_pair=trading_pair
                )
                instrument_id = self._connector._instrument_id_from_exchange_symbol(exchange_symbol)

                # Subscribe to orderbook channel
                orderbook_subscribe_request: WSJSONRequest = WSJSONRequest(
                    payload={
                        "op": "subscribe",
                        "data": [f"orderbook:{instrument_id}"]
                    }
                )
                await ws.send(orderbook_subscribe_request)

                # Subscribe to trades channel
                trades_subscribe_request: WSJSONRequest = WSJSONRequest(
                    payload={
                        "op": "subscribe",
                        "data": [f"trades:{instrument_id}"]
                    }
                )
                await ws.send(trades_subscribe_request)

                self.logger().info(
                    f"Subscribed to orderbook and trades channels for {trading_pair} "
                    f"(instrument_id: {instrument_id})"
                )

            self._last_ws_message_sent_timestamp = self._time()
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger().exception(
                "Unexpected error occurred subscribing to order book and trade channels..."
            )
            raise

    async def _connected_websocket_assistant(self) -> WSAssistant:
        """
        Creates a WebSocket connection to the Aevo WebSocket API.
        """
        ws: WSAssistant = await self._api_factory.get_ws_assistant()
        ws_url = CONSTANTS.WSS_PUBLIC_URL.get(self._domain, CONSTANTS.WSS_PUBLIC_URL[CONSTANTS.DEFAULT_DOMAIN])
        await ws.connect(
            ws_url=ws_url,
            ping_timeout=self._ping_interval,
        )
        return ws

    async def _process_websocket_messages(self, websocket_assistant: WSAssistant):
        """
        Process incoming WebSocket messages and route them to the appropriate message queue.
        """
        async for ws_response in websocket_assistant.iter_messages():
            data = ws_response.data
            if data is not None:
                channel = self._channel_originating_message(event_message=data)
                if channel is not None:
                    self._message_queue[channel].put_nowait(data)

    def _channel_originating_message(self, event_message: Dict[str, Any]) -> Optional[str]:
        """
        Determines the channel that originated the given message.
        """
        channel: Optional[str] = None

        if isinstance(event_message, dict):
            event_channel = event_message.get("channel", "")

            if "orderbook" in event_channel:
                channel = self._snapshot_messages_queue_key
                # Determine if it's a snapshot or diff
                data = event_message.get("data", {})
                msg_type = data.get("type", "")
                if msg_type == "snapshot":
                    channel = self._snapshot_messages_queue_key
                else:
                    channel = self._diff_messages_queue_key
            elif "trades" in event_channel:
                channel = self._trade_messages_queue_key

        return channel

    async def _parse_trade_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue):
        """
        Parses a trade message from the Aevo WebSocket and enqueues it.
        """
        try:
            channel = raw_message.get("channel", "")
            data = raw_message.get("data", {})

            # Extract instrument_id from channel (format: "trades:{instrument_id}")
            parts = channel.split(":")
            if len(parts) < 2:
                return

            instrument_id = parts[1]
            trading_pair = await self._connector.trading_pair_associated_to_exchange_symbol(
                symbol=self._connector._exchange_symbol_from_instrument_id(instrument_id)
            )

            trades = data if isinstance(data, list) else [data]

            for trade in trades:
                timestamp = float(trade.get("timestamp", time.time()))
                if timestamp > 1e12:
                    timestamp = timestamp / 1e6  # Convert microseconds to seconds

                trade_id = trade.get("trade_id", str(timestamp))
                price = float(trade.get("price", 0))
                amount = float(trade.get("amount", 0))
                side = trade.get("side", "").lower()

                trade_type = float(TradeType.BUY.value) if side == "buy" else float(TradeType.SELL.value)

                message_content = {
                    "trade_id": trade_id,
                    "trading_pair": trading_pair,
                    "trade_type": trade_type,
                    "amount": amount,
                    "price": price,
                }

                trade_message: Optional[OrderBookMessage] = OrderBookMessage(
                    message_type=OrderBookMessageType.TRADE,
                    content=message_content,
                    timestamp=timestamp,
                )
                message_queue.put_nowait(trade_message)

        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger().exception("Unexpected error when parsing trade message.")

    async def _parse_order_book_diff_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue):
        """
        Parses an order book diff (update) message from the Aevo WebSocket and enqueues it.
        """
        try:
            channel = raw_message.get("channel", "")
            data = raw_message.get("data", {})

            # Extract instrument_id from channel (format: "orderbook:{instrument_id}")
            parts = channel.split(":")
            if len(parts) < 2:
                return

            instrument_id = parts[1]
            exchange_symbol = self._connector._exchange_symbol_from_instrument_id(instrument_id)
            trading_pair = await self._connector.trading_pair_associated_to_exchange_symbol(
                symbol=exchange_symbol
            )

            timestamp = float(data.get("last_updated", time.time()))
            if timestamp > 1e12:
                timestamp = timestamp / 1e6

            update_id = int(data.get("checksum", timestamp * 1e6))

            bids = []
            asks = []

            raw_bids = data.get("bids", [])
            raw_asks = data.get("asks", [])

            for bid in raw_bids:
                if isinstance(bid, list) and len(bid) >= 2:
                    price = float(bid[0])
                    amount = float(bid[1])
                    bids.append(OrderBookRow(price, amount, update_id))

            for ask in raw_asks:
                if isinstance(ask, list) and len(ask) >= 2:
                    price = float(ask[0])
                    amount = float(ask[1])
                    asks.append(OrderBookRow(price, amount, update_id))

            order_book_message_content = {
                "trading_pair": trading_pair,
                "update_id": update_id,
                "bids": [(str(b.price), str(b.amount)) for b in bids],
                "asks": [(str(a.price), str(a.amount)) for a in asks],
            }

            diff_message: OrderBookMessage = OrderBookMessage(
                message_type=OrderBookMessageType.DIFF,
                content=order_book_message_content,
                timestamp=timestamp,
            )
            message_queue.put_nowait(diff_message)

        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger().exception("Unexpected error when parsing order book diff message.")

    def _parse_order_book_snapshot_message(
        self,
        raw_message: Dict[str, Any],
        message_queue: Optional[asyncio.Queue] = None,
        trading_pair: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> OrderBookMessage:
        """
        Parses an order book snapshot message from either REST or WebSocket.
        Returns an OrderBookMessage of SNAPSHOT type.
        """
        data = raw_message.get("data", raw_message) if "data" in raw_message else raw_message

        if timestamp is None:
            timestamp = float(data.get("last_updated", time.time()))
            if timestamp > 1e12:
                timestamp = timestamp / 1e6

        if trading_pair is None:
            channel = raw_message.get("channel", "")
            parts = channel.split(":")
            if len(parts) >= 2:
                instrument_id = parts[1]
                # We'll set trading_pair to instrument_id for now; caller should resolve
                trading_pair = instrument_id

        update_id = int(data.get("checksum", timestamp * 1e6))

        bids = []
        asks = []

        raw_bids = data.get("bids", [])
        raw_asks = data.get("asks", [])

        for bid in raw_bids:
            if isinstance(bid, list) and len(bid) >= 2:
                price = float(bid[0])
                amount = float(bid[1])
                bids.append((str(price), str(amount)))

        for ask in raw_asks:
            if isinstance(ask, list) and len(ask) >= 2:
                price = float(ask[0])
                amount = float(ask[1])
                asks.append((str(price), str(amount)))

        order_