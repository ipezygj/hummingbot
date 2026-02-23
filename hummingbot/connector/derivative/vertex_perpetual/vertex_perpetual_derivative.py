import asyncio
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from hummingbot.connector.derivative.vertex_perpetual import (
    vertex_perpetual_constants as CONSTANTS,
    vertex_perpetual_web_utils as web_utils,
)
from hummingbot.connector.derivative.vertex_perpetual.vertex_perpetual_api_order_book_data_source import (
    VertexPerpetualAPIOrderBookDataSource,
)
from hummingbot.connector.derivative.vertex_perpetual.vertex_perpetual_auth import VertexPerpetualAuth
from hummingbot.connector.derivative.vertex_perpetual.vertex_perpetual_user_stream_data_source import (
    VertexPerpetualUserStreamDataSource,
)
from hummingbot.connector.perpetual_derivative_py_base import PerpetualDerivativePyBase
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderUpdate, TradeUpdate
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory

class VertexPerpetualDerivative(PerpetualDerivativePyBase):
    def __init__(self,
                 auth_assistant: VertexPerpetualAuth,
                 domain: str = CONSTANTS.DEFAULT_DOMAIN,
                 trading_pairs: Optional[List[str]] = None,
                 trading_required: bool = True):
        self._auth = auth_assistant
        self._domain = domain
        self._trading_pairs = trading_pairs
        self._trading_required = trading_required
        super().__init__()

    @property
    def name(self) -> str:
        return f"vertex_perpetual_{self._domain}"

    @property
    def authenticator(self) -> VertexPerpetualAuth:
        return self._auth

    @property
    def rate_limits_rules(self):
        return CONSTANTS.RATE_LIMITS

    @property
    def domain(self):
        return self._domain

    @property
    def client_order_id_max_length(self):
        return CONSTANTS.MAX_ID_LEN

    @property
    def client_order_id_prefix(self):
        return CONSTANTS.HBOT_BROKER_ID

    @property
    def trading_rules_request_path(self):
        return CONSTANTS.SYMBOLS_ENDPOINT

    @property
    def trading_pairs_request_path(self):
        return CONSTANTS.SYMBOLS_ENDPOINT

    @property
    def check_network_request_path(self):
        return CONSTANTS.TIME_ENDPOINT

    @property
    def trading_pairs(self):
        return self._trading_pairs

    @property
    def is_cancel_if_order_not_found(self) -> bool:
        return True

    def _create_order_book_data_source(self) -> OrderBookTrackerDataSource:
        return VertexPerpetualAPIOrderBookDataSource(
            trading_pairs=self._trading_pairs,
            connector=self,
            domain=self.domain,
        )

    def _create_user_stream_data_source(self) -> UserStreamTrackerDataSource:
        return VertexPerpetualUserStreamDataSource(
            auth=self._auth,
            trading_pairs=self._trading_pairs,
            connector=self,
            domain=self.domain,
        )

    def _get_fee_estimator_factory(self) -> WebAssistantsFactory:
        return web_utils.build_api_factory(auth=self._auth)

    async def _update_trading_fees(self):
        pass

    async def _update_balances(self):
        try:
            account_info = await self._api_get(
                path=CONSTANTS.ACCOUNT_INFO_ENDPOINT,
                params={"subaccount": self._auth.subaccount_name}
            )
            for balance in account_info.get("balances", []):
                asset_name = balance["symbol"]
                self._account_balances[asset_name] = Decimal(str(balance["available"]))
                self._account_available_balances[asset_name] = Decimal(str(balance["available"]))
        except Exception:
            self.logger().exception("Error updating balances")

    async def _place_order(self,
                           order_id: str,
                           trading_pair: str,
                           amount: Decimal,
                           trade_type: TradeType,
                           order_type: OrderType,
                           price: Decimal,
                           **kwargs) -> Tuple[str, float]:
        
        symbol = await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        nonce = self._auth.get_nonce()
        
        order_params = {
            "sender": self._auth.subaccount_name,
            "priceX18": str(int(price * Decimal("1e18"))),
            "amount": str(int(amount * Decimal("1e18") * (1 if trade_type == TradeType.BUY else -1))),
            "expiration": str(nonce + 1000000),
            "nonce": str(nonce)
        }
        
        signature = self._auth.sign_order(order_params, symbol)
        
        payload = {
            "place_order": {
                "product_id": int(symbol),
                "order": order_params,
                "signature": signature
            }
        }
        
        response = await self._api_post(
            path=CONSTANTS.ORDER_PLACEMENT_ENDPOINT,
            data=payload
        )
        
        return str(order_id), self.current_timestamp

    async def _execute_cancel(self, trading_pair: str, order_id: str) -> str:
        order = self._order_tracker.all_fillable_orders.get(order_id)
        if order:
            symbol = await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
            payload = {
                "cancel_orders": {
                    "subaccount": self._auth.subaccount_name,
                    "product_ids": [int(symbol)],
                    "digests": [order.exchange_order_id]
                }
            }
            await self._api_post(path=CONSTANTS.ORDER_CANCEL_ENDPOINT, data=payload)
        return order_id

    async def _format_trading_rules(self, raw_trading_pair_info: Dict[str, Any]) -> List[Any]:
        # Implementation for formatting trading rules
        return []

    async def _status_polling_loop_fetch_updates(self):
        await self._update_balances()
        await self._update_order_status()

    async def _update_order_status(self):
        for order in list(self._order_tracker.all_fillable_orders.values()):
            try:
                # Poll Vertex API for order status update
                pass
            except Exception:
                self.logger().exception(f"Error updating status for order {order.client_order_id}")

    def _initialize_trading_pair_symbols_from_exchange_info(self, exchange_info: Dict[str, Any]):
        mapping = {}
        for symbol_data in exchange_info.get("symbols", []):
            mapping[symbol_data["id"]] = symbol_data["name"]
        self._set_trading_pair_symbol_map(mapping)