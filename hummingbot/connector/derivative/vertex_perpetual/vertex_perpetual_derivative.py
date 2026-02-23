

"""Vertex Perpetual Derivative Connector for Hummingbot."""

import asyncio
import logging
import time
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from bidict import bidict

from hummingbot.connector.constants import s_decimal_NaN, s_decimal_0
from hummingbot.connector.derivative.position import Position
from hummingbot.connector.derivative.vertex_perpetual import (
    vertex_perpetual_constants as CONSTANTS,
    vertex_perpetual_utils as utils,
    vertex_perpetual_web_utils as web_utils,
)
from hummingbot.connector.derivative.vertex_perpetual.vertex_perpetual_api_order_book_data_source import (
    VertexPerpetualAPIOrderBookDataSource,
)
from hummingbot.connector.derivative.vertex_perpetual.vertex_perpetual_auth import (
    VertexPerpetualAuth,
)
from hummingbot.connector.derivative.vertex_perpetual.vertex_perpetual_user_stream_data_source import (
    VertexPerpetualAPIUserStreamDataSource,
)
from hummingbot.connector.perpetual_derivative_py_base import PerpetualDerivativePyBase
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import combine_to_hb_trading_pair, get_new_numeric_client_order_id
from hummingbot.core.api_throttler.data_types import RateLimit
from hummingbot.core.data_type.cancellation_result import CancellationResult
from hummingbot.core.data_type.common import OrderType, PositionAction, PositionMode, PositionSide, TradeType
from hummingbot.core.data_type.funding_info import FundingInfo, FundingInfoUpdate
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderState, OrderUpdate, TradeUpdate
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.trade_fee import TokenAmount, TradeFeeBase, TradeFeeSchema, AddedToCostTradeFee
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.event.events import (
    AccountEvent,
    FundingPaymentCompletedEvent,
    MarketEvent,
    PositionModeChangeEvent,
)
from hummingbot.core.network_iterator import NetworkStatus
from hummingbot.core.utils.async_utils import safe_ensure_future, safe_gather
from hummingbot.core.utils.estimate_fee import build_trade_fee
from hummingbot.core.utils.tracking_nonce import NonceCreator
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.logger import HummingbotLogger

if not hasattr(CONSTANTS, "SIDE_BUY"):
    CONSTANTS.SIDE_BUY = "buy"
    CONSTANTS.SIDE_SELL = "sell"

bpm_logger = None


class VertexPerpetualDerivative(PerpetualDerivativePyBase):
    """
    Vertex Perpetual Derivative connector implementing EIP-712 order signing,
    position tracking, and integration with Vertex Protocol on Arbitrum.
    """

    web_utils = web_utils

    SHORT_POLL_INTERVAL = 5.0
    LONG_POLL_INTERVAL = 120.0
    UPDATE_ORDER_STATUS_MIN_INTERVAL = 10.0
    TICK_INTERVAL_LIMIT = 60.0

    def __init__(
        self,
        client_config_map: "ClientConfigAdapter",
        vertex_perpetual_secret_key: str,
        vertex_perpetual_sender_address: str,
        trading_pairs: Optional[List[str]] = None,
        trading_required: bool = True,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        self._vertex_perpetual_secret_key = vertex_perpetual_secret_key
        self._vertex_perpetual_sender_address = vertex_perpetual_sender_address
        self._trading_pairs = trading_pairs or []
        self._trading_required = trading_required
        self._domain = domain
        self._last_trade_history_timestamp = None
        self._position_mode = PositionMode.ONEWAY
        self._trading_pair_to_product_id: Dict[str, int] = {}
        self._product_id_to_trading_pair: Dict[int, str] = {}
        self._nonce_creator = NonceCreator.for_microseconds()
        self._last_funding_fee_payment_ts: Dict[str, float] = defaultdict(lambda: 0)
        self._account_positions: Dict[str, Position] = {}
        self._subaccount: Optional[str] = None
        self._chain_id: int = CONSTANTS.CHAIN_ID.get(domain, 42161)

        super().__init__(client_config_map)

    @classmethod
    def logger(cls) -> HummingbotLogger:
        global bpm_logger
        if bpm_logger is None:
            bpm_logger = logging.getLogger(__name__)
        return bpm_logger

    @property
    def name(self) -> str:
        return CONSTANTS.EXCHANGE_NAME

    @property
    def authenticator(self) -> VertexPerpetualAuth:
        return VertexPerpetualAuth(
            secret_key=self._vertex_perpetual_secret_key,
            sender_address=self._vertex_perpetual_sender_address,
            domain=self._domain,
        )

    @property
    def rate_limits_rules(self) -> List[RateLimit]:
        return CONSTANTS.RATE_LIMITS

    @property
    def domain(self) -> str:
        return self._domain

    @property
    def client_order_id_max_length(self) -> int:
        return CONSTANTS.MAX_ORDER_ID_LEN

    @property
    def client_order_id_prefix(self) -> str:
        return CONSTANTS.HBOT_ORDER_ID_PREFIX

    @property
    def trading_rules_request_path(self) -> str:
        return CONSTANTS.EXCHANGE_INFO_PATH_URL

    @property
    def trading_pairs_request_path(self) -> str:
        return CONSTANTS.EXCHANGE_INFO_PATH_URL

    @property
    def check_network_request_path(self) -> str:
        return CONSTANTS.PING_PATH_URL

    @property
    def trading_pairs(self) -> List[str]:
        return self._trading_pairs

    @property
    def is_cancel_request_in_exchange_synchronous(self) -> bool:
        return True

    @property
    def is_trading_required(self) -> bool:
        return self._trading_required

    @property
    def funding_fee_poll_interval(self) -> int:
        return 600

    def supported_order_types(self) -> List[OrderType]:
        return [OrderType.LIMIT, OrderType.LIMIT_MAKER, OrderType.MARKET]

    def supported_position_modes(self) -> List[PositionMode]:
        return [PositionMode.ONEWAY]

    def _is_request_exception_related_to_time_synchronizer(self, request_exception: Exception) -> bool:
        return False

    def _is_order_not_found_during_status_update_error(self, status_update_exception: Exception) -> bool:
        error_msg = str(status_update_exception).lower()
        return "order not found" in error_msg or "not exist" in error_msg

    def _is_order_not_found_during_cancelation_error(self, cancelation_exception: Exception) -> bool:
        error_msg = str(cancelation_exception).lower()
        return "order not found" in error_msg or "not exist" in error_msg

    async def _make_trading_rules_request(self) -> Any:
        exchange_info = await self._api_get(
            path_url=self.trading_rules_request_path,
            params={},
        )
        return exchange_info

    async def _make_trading_pairs_request(self) -> Any:
        exchange_info = await self._api_get(
            path_url=self.trading_pairs_request_path,
            params={},
        )
        return exchange_info

    def _create_web_assistants_factory(self) -> WebAssistantsFactory:
        return web_utils.build_api_factory(
            throttler=self._throttler,
            auth=self._auth,
        )

    def _create_order_book_data_source(self) -> OrderBookTrackerDataSource:
        return VertexPerpetualAPIOrderBookDataSource(
            trading_pairs=self._trading_pairs,
            connector=self,
            domain=self._domain,
            api_factory=self._web_assistants_factory,
            throttler=self._throttler,
        )

    def _create_user_stream_data_source(self) -> UserStreamTrackerDataSource:
        return VertexPerpetualAPIUserStreamDataSource(
            auth=self._auth,
            trading_pairs=self._trading_pairs,
            connector=self,
            domain=self._domain,
            api_factory=self._web_assistants_factory,
            throttler=self._throttler,
        )

    def _get_fee(
        self,
        base_currency: str,
        quote_currency: str,
        order_type: OrderType,
        order_side: TradeType,
        amount: Decimal,
        price: Decimal = s_decimal_0,
        is_maker: Optional[bool] = None,
    ) -> AddedToCostTradeFee:
        is_maker = is_maker or (order_type is OrderType.LIMIT_MAKER)
        fee = build_trade_fee(
            self.name,
            is_maker,
            base_currency=base_currency,
            quote_currency=quote_currency,
            order_type=order_type,
            order_side=order_side,
            amount=amount,
            price=price,
        )
        return fee

    async def _update_trading_fees(self):
        """Vertex fees are determined per-trade; no global update needed."""
        pass

    def buy(
        self,
        trading_pair: str,
        amount: Decimal,
        order_type: OrderType = OrderType.LIMIT,
        price: Decimal = s_decimal_NaN,
        **kwargs,
    ) -> str:
        order_id = self._create_client_order_id(TradeType.BUY, trading_pair)
        safe_ensure_future(
            self._create_order(
                trade_type=TradeType.BUY,
                order_id=order_id,
                trading_pair=trading_pair,
                amount=amount,
                order_type=order_type,
                price=price,
                position_action=kwargs.get("position_action", PositionAction.OPEN),
            )
        )
        return order_id

    def sell(
        self,
        trading_pair: str,
        amount: Decimal,
        order_type: OrderType = OrderType.LIMIT,
        price: Decimal = s_decimal_NaN,
        **kwargs,
    ) -> str:
        order_id = self._create_client_order_id(TradeType.SELL, trading_pair)
        safe_ensure_future(
            self._create_order(
                trade_type=TradeType.SELL,
                order_id=order_id,
                trading_pair=trading_pair,
                amount=amount,
                order_type=order_type,
                price=price,
                position_action=kwargs.get("position_action", PositionAction.CLOSE),
            )
        )
        return order_id

    def _create_client_order_id(self, trade_type: TradeType, trading_pair: str) -> str:
        nonce = get_new_numeric_client_order_id(
            nonce_creator=self._nonce_creator,
            max_id_len=self.client_order_id_max_length,
        )
        return f"{self.client_order_id_prefix}{nonce}"

    def _get_product_id(self, trading_pair: str) -> int:
        if trading_pair in self._trading_pair_to_product_id:
            return self._trading_pair_to_product_id[trading_pair]
        base, quote = trading_pair.split("-")
        product_id = utils.trading_pair_to_product_id(trading_pair)
        self._trading_pair_to_product_id[trading_pair] = product_id
        self._product_id_to_trading_pair[product_id] = trading_pair
        return product_id

    def _get_trading_pair_from_product_id(self, product_id: int) -> Optional[str]:
        return self._product_id_to_trading_pair.get(product_id)

    async def _place_order(
        self,
        order_id: str,
        trading_pair: str,
        amount: Decimal,
        trade_type: TradeType,
        order_type: OrderType,
        price: Decimal,
        position_action: PositionAction = PositionAction.NIL,
        **kwargs,
    ) -> Tuple[str, float]:
        """
        Place an order on Vertex Protocol using EIP-712 signed messages.
        """
        product_id = self._get_product_id(trading_pair)
        sender = self._auth.get_sender_address()
        subaccount = self._auth.get_subaccount()

        # Convert amount to Vertex's x18 format (18 decimal places)
        amount_x18 = self._to_x18(amount)
        if trade_type == TradeType.SELL:
            amount_x18 = -amount_x18

        # Convert price to x18 format
        price_x18 = self._to_x18(price) if price != s_decimal_NaN else self._to_x18(Decimal("0"))

        # Build the order expiration
        # Vertex uses expiration as a combined field: (expiration_time << 1) | reduce_only_flag
        expiration_time = int(time.time()) + CONSTANTS.ORDER_EXPIRATION_SECONDS
        reduce_only = 1 if position_action == PositionAction.CLOSE else 0
        expiration = (expiration_time << 1) | reduce_only

        # Generate nonce for the order
        nonce = self._nonce_creator.get_tracking_nonce()

        # Determine order type flags for Vertex
        order_type_flag = self._get_vertex_order_type(order_type)

        # Build the order struct for EIP-712 signing
        order = {
            "sender": subaccount,
            "priceX18": str(price_x18),
            "amount": str(amount_x18),
            "expiration": str(expiration),
            "nonce": str(nonce),
        }

        # Sign the order using EIP-712
        signature = self._auth.sign_order(
            order=order,
            product_id=product_id,
            chain_id=self._chain_id,
        )

        # Build the place order request
        place_order_request = {
            "place_order": {
                "product_id": product_id,
                "order": {
                    "sender": subaccount,
                    "priceX18": str(price_x18),
                    "amount": str(amount_x18),
                    "expiration": str(expiration),
                    "nonce": str(nonce),
                },
                "signature": signature,
                "id": int(nonce),
            }
        }

        if order_type_flag: