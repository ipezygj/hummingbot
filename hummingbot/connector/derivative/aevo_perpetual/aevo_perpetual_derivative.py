

"""
Aevo Perpetual Derivative Connector for Hummingbot V2

This module implements the main AevoPerpetualDerivative class that provides
perpetual futures trading functionality on the Aevo exchange.

Reference: https://docs.aevo.xyz/
"""

import asyncio
import logging
import time
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from bidict import bidict

from hummingbot.connector.constants import s_decimal_NaN, s_decimal_0
from hummingbot.connector.derivative.aevo_perpetual import (
    aevo_perpetual_constants as CONSTANTS,
    aevo_perpetual_utils as utils,
    aevo_perpetual_web_utils as web_utils,
)
from hummingbot.connector.derivative.aevo_perpetual.aevo_perpetual_api_order_book_data_source import (
    AevoPerpetualAPIOrderBookDataSource,
)
from hummingbot.connector.derivative.aevo_perpetual.aevo_perpetual_auth import AevoPerpetualAuth
from hummingbot.connector.derivative.aevo_perpetual.aevo_perpetual_user_stream_data_source import (
    AevoPerpetualAPIUserStreamDataSource,
)
from hummingbot.connector.derivative.position import Position
from hummingbot.connector.perpetual_derivative_py_base import PerpetualDerivativePyBase
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import combine_to_hb_trading_pair, get_new_numeric_client_order_id
from hummingbot.core.api_throttler.data_types import RateLimit
from hummingbot.core.data_type.cancellation_result import CancellationResult
from hummingbot.core.data_type.common import OrderType, PositionAction, PositionMode, PositionSide, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderState, OrderUpdate, TradeUpdate
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.trade_fee import (
    AddedToCostTradeFee,
    TokenAmount,
    TradeFeeBase,
)
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.network_iterator import NetworkStatus
from hummingbot.core.utils.async_utils import safe_ensure_future, safe_gather
from hummingbot.core.utils.estimate_fee import build_trade_fee
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.client.config.config_helpers import ClientConfigAdapter

s_logger = None


class AevoPerpetualDerivative(PerpetualDerivativePyBase):
    """
    AevoPerpetualDerivative connects with Aevo exchange and provides order book pricing,
    user account tracking and trading functionality for perpetual futures.
    """

    web_utils = web_utils

    def __init__(
        self,
        client_config_map: "ClientConfigAdapter",
        aevo_api_key: str,
        aevo_api_secret: str,
        aevo_signing_key: str = "",
        trading_pairs: Optional[List[str]] = None,
        trading_required: bool = True,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        self._aevo_api_key = aevo_api_key
        self._aevo_api_secret = aevo_api_secret
        self._aevo_signing_key = aevo_signing_key
        self._trading_pairs = trading_pairs or []
        self._trading_required = trading_required
        self._domain = domain

        self._last_trade_history_timestamp: Optional[float] = None
        self._position_mode: Optional[PositionMode] = None
        self._trading_pair_instrument_id_map: Optional[bidict] = None
        self._token_id_map: Dict[str, int] = {}
        self._instrument_info_map: Dict[str, Dict[str, Any]] = {}

        super().__init__(client_config_map)

    @classmethod
    def logger(cls) -> HummingbotLogger:
        global s_logger
        if s_logger is None:
            s_logger = logging.getLogger(__name__)
        return s_logger

    @property
    def name(self) -> str:
        return CONSTANTS.EXCHANGE_NAME

    @property
    def authenticator(self) -> AevoPerpetualAuth:
        return AevoPerpetualAuth(
            api_key=self._aevo_api_key,
            api_secret=self._aevo_api_secret,
            signing_key=self._aevo_signing_key,
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
        return CONSTANTS.MARKETS_PATH_URL

    @property
    def trading_pairs_request_path(self) -> str:
        return CONSTANTS.MARKETS_PATH_URL

    @property
    def check_network_request_path(self) -> str:
        return CONSTANTS.SERVER_TIME_PATH_URL

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
        return 120

    def supported_order_types(self) -> List[OrderType]:
        return [OrderType.LIMIT, OrderType.LIMIT_MAKER, OrderType.MARKET]

    def supported_position_modes(self) -> List[PositionMode]:
        return [PositionMode.ONEWAY]

    def _is_request_exception_related_to_time_synchronizer(self, request_exception: Exception) -> bool:
        error_description = str(request_exception)
        is_time_synchronizer_related = (
            "timestamp" in error_description.lower()
            or "recvwindow" in error_description.lower()
        )
        return is_time_synchronizer_related

    def _is_order_not_found_during_status_update_error(self, status_update_exception: Exception) -> bool:
        return "order not found" in str(status_update_exception).lower()

    def _is_order_not_found_during_cancelation_error(self, cancelation_exception: Exception) -> bool:
        return "order not found" in str(cancelation_exception).lower()

    def _create_web_assistants_factory(self) -> WebAssistantsFactory:
        return web_utils.build_api_factory(
            throttler=self._throttler,
            auth=self._auth,
        )

    def _create_order_book_data_source(self) -> OrderBookTrackerDataSource:
        return AevoPerpetualAPIOrderBookDataSource(
            trading_pairs=self._trading_pairs,
            connector=self,
            api_factory=self._web_assistants_factory,
            domain=self._domain,
        )

    def _create_user_stream_data_source(self) -> UserStreamTrackerDataSource:
        return AevoPerpetualAPIUserStreamDataSource(
            auth=self._auth,
            trading_pairs=self._trading_pairs,
            connector=self,
            api_factory=self._web_assistants_factory,
            domain=self._domain,
        )

    def _get_fee(
        self,
        base_currency: str,
        quote_currency: str,
        order_type: OrderType,
        order_side: TradeType,
        position_action: PositionAction,
        amount: Decimal,
        price: Decimal = s_decimal_0,
        is_maker: Optional[bool] = None,
    ) -> TradeFeeBase:
        is_maker = is_maker or (order_type is OrderType.LIMIT_MAKER)
        fee = build_trade_fee(
            exchange=self.name,
            is_maker=is_maker,
            order_side=order_side,
            order_type=order_type,
            amount=amount,
            price=price,
            base_currency=base_currency,
            quote_currency=quote_currency,
            hbot_order_type=order_type,
            position_action=position_action,
        )
        return fee

    async def _update_trading_fees(self):
        """
        Aevo uses standard maker/taker fee structure. Fees are retrieved from account info.
        """
        pass

    async def _status_polling_loop_fetch_updates(self):
        await safe_gather(
            self._update_order_status(),
            self._update_balances(),
            self._update_positions(),
        )

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
        Places an order on Aevo via POST /orders.

        :param order_id: The client order ID
        :param trading_pair: The trading pair (e.g., "ETH-USDC")
        :param amount: The order amount
        :param trade_type: BUY or SELL
        :param order_type: LIMIT, LIMIT_MAKER, or MARKET
        :param price: The order price
        :param position_action: OPEN or CLOSE
        :return: Tuple of (exchange_order_id, timestamp)
        """
        instrument_id = await self.exchange_symbol_associated_to_pair(trading_pair)

        side = "buy" if trade_type == TradeType.BUY else "sell"

        # Build the order payload
        order_params: Dict[str, Any] = {
            "instrument": int(instrument_id),
            "maker": self._auth.get_account_address(),
            "is_buy": trade_type == TradeType.BUY,
            "amount": str(utils.convert_to_exchange_amount(amount, trading_pair)),
            "limit_price": str(utils.convert_to_exchange_price(price, trading_pair)),
            "salt": get_new_numeric_client_order_id(
                nonce_creator=self._nonce_creator,
                max_id_len=CONSTANTS.MAX_ORDER_ID_LEN,
            ),
            "timestamp": int(time.time()),
        }

        # Set time in force based on order type
        if order_type == OrderType.LIMIT_MAKER:
            order_params["post_only"] = True
            order_params["time_in_force"] = "GTC"
        elif order_type == OrderType.MARKET:
            order_params["time_in_force"] = "IOC"
            # For market orders, use a very high/low limit price
            if trade_type == TradeType.BUY:
                order_params["limit_price"] = str(
                    utils.convert_to_exchange_price(price * Decimal("1.05"), trading_pair)
                )
            else:
                order_params["limit_price"] = str(
                    utils.convert_to_exchange_price(price * Decimal("0.95"), trading_pair)
                )
        else:
            order_params["time_in_force"] = "GTC"

        # Handle reduce_only for closing positions
        if position_action == PositionAction.CLOSE:
            order_params["reduce_only"] = True

        # Sign the order if signing key is available
        if self._aevo_signing_key:
            order_params["signature"] = self._auth.sign_order(order_params)

        # Tag client order id
        order_params["client_order_id"] = order_id

        exchange_order_id, transact_time = await self._api_post(
            path_url=CONSTANTS.CREATE_ORDER_PATH_URL,
            data=order_params,
            is_auth_required=True,
        )

        return str(exchange_order_id), float(transact_time)

    async def _place_cancel(self, order_id: str, tracked_order: InFlightOrder) -> bool:
        """
        Cancels an order on Aevo via DELETE /orders/{order_id}.

        :param order_id: The client order ID
        :param tracked_order: The tracked in-flight order
        :return: True if cancellation was successful
        """
        exchange_order_id = await tracked_order.get_exchange_order_id()

        cancel_result = await self._api_delete(
            path_url=CONSTANTS.CANCEL_ORDER_PATH_URL.format(order_id=exchange_order_id),
            is_auth_required=True,
        )

        if cancel_result is None:
            # A successful cancellation on Aevo may return empty
            return True

        return True

    async def _api_post(
        self,
        path_url: str,
        data: Optional[Dict[str, Any]] = None,
        is_auth_required: bool = False,
        **kwargs,
    ) -> Tuple[str, float]:
        """
        Sends a POST request to create an order.
        Returns (exchange_order_id, transaction_timestamp)
        """
        rest_assistant = await self._web_assistants_factory.get_rest_assistant()

        url = web_utils.get_rest_url_for_endpoint(
            endpoint=path_url,
            domain=self._domain,
        )

        request_result = await rest_assistant.execute_request(
            url=url,
            throttler_limit_id=CONSTANTS.CREATE_ORDER_PATH_URL,
            data=data,
            method=RESTMethod.POST,
            is_auth_required=is_auth_required,
        )

        exchange_order_id = str(request_result.get("order_id", ""))
        transact_time = float(request_result.get("timestamp", time.time()))

        return exchange_order_id, transact_time

    async def _api_delete(
        self,
        path_url: str,
        is_auth_required: bool = False,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """
        Sends a DELETE request to cancel an order.
        """
        rest_assistant = await self._web_assistants_factory.get_rest_assistant()

        url = web_utils.get_rest_url_for_endpoint(
            endpoint=path_url,
            domain=self._domain,
        )

        request_result = await rest_assistant.execute_request(
            url=url,
            throttler_limit_id=CONSTANTS.CANCEL_ORDER_PATH_URL,
            method=RESTMethod.DELETE,
            is_auth_required=is_auth_required,
        )

        return request_result

    async def _format_trading_rules(self, exchange_info_dict: Dict[str, Any]) -> List[TradingRule]:
        """
        Parses exchange info response to create TradingRule instances.
        """
        trading_rules = []