import asyncio
import json
import re
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, patch

from aioresponses import aioresponses
from aioresponses.core import RequestCall

from hummingbot.connector.exchange.backpack import backpack_constants as CONSTANTS, backpack_web_utils as web_utils
from hummingbot.connector.exchange.backpack.backpack_exchange import BackpackExchange
from hummingbot.connector.test_support.exchange_connector_test import AbstractExchangeConnectorTests
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import get_new_client_order_id, get_new_numeric_client_order_id
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderState
from hummingbot.core.data_type.trade_fee import AddedToCostTradeFee, TokenAmount, TradeFeeBase
from hummingbot.core.event.events import MarketOrderFailureEvent, OrderFilledEvent


class BackpackExchangeTests(AbstractExchangeConnectorTests.ExchangeConnectorTests):
    @property
    def all_symbols_url(self):
        return web_utils.public_rest_url(path_url=CONSTANTS.EXCHANGE_INFO_PATH_URL, domain=self.exchange._domain)

    @property
    def latest_prices_url(self):
        url = web_utils.public_rest_url(path_url=CONSTANTS.TICKER_PRICE_CHANGE_PATH_URL, domain=self.exchange._domain)
        url = f"{url}?symbol={self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset)}"
        return url

    @property
    def network_status_url(self):
        url = web_utils.private_rest_url(CONSTANTS.PING_PATH_URL, domain=self.exchange._domain)
        return url

    @property
    def trading_rules_url(self):
        url = web_utils.private_rest_url(CONSTANTS.EXCHANGE_INFO_PATH_URL, domain=self.exchange._domain)
        return url

    @property
    def order_creation_url(self):
        url = web_utils.private_rest_url(CONSTANTS.ORDER_PATH_URL, domain=self.exchange._domain)
        return url

    @property
    def balance_url(self):
        url = web_utils.private_rest_url(CONSTANTS.BALANCE_PATH_URL, domain=self.exchange._domain)
        return url

    @property
    def all_symbols_request_mock_response(self):
        return {
            "baseSymbol": self.base_asset,
            "createdAt": "2025-01-21T06:34:54.691858",
            "filters": {
                "price": {
                    "borrowEntryFeeMaxMultiplier": None,
                    "borrowEntryFeeMinMultiplier": None,
                    "maxImpactMultiplier": "1.03",
                    "maxMultiplier": "1.25",
                    "maxPrice": None,
                    "meanMarkPriceBand": {
                        "maxMultiplier": "1.03",
                        "minMultiplier": "0.97"
                    },
                    "meanPremiumBand": None,
                    "minImpactMultiplier": "0.97",
                    "minMultiplier": "0.75",
                    "minPrice": "0.01",
                    "tickSize": "0.01"
                },
                "quantity": {
                    "maxQuantity": None,
                    "minQuantity": "0.01",
                    "stepSize": "0.01"
                }
            },
            "fundingInterval": None,
            "fundingRateLowerBound": None,
            "fundingRateUpperBound": None,
            "imfFunction": None,
            "marketType": "SPOT",
            "mmfFunction": None,
            "openInterestLimit": "0",
            "orderBookState": "Open",
            "positionLimitWeight": None,
            "quoteSymbol": self.quote_asset,
            "symbol": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
            "visible": True
        }

    @property
    def latest_prices_request_mock_response(self):
        return {
            "firstPrice": "0.8914",
            "high": "0.8914",
            "lastPrice": self.expected_latest_price,
            "low": "0.8769",
            "priceChange": "-0.0124",
            "priceChangePercent": "-0.013911",
            "quoteVolume": "831.1761",
            "symbol": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
            "trades": "11",
            "volume": "942"
        }

    @property
    def all_symbols_including_invalid_pair_mock_response(self) -> Tuple[str, Any]:
        valid_pair = self.all_symbols_request_mock_response
        invalid_pair = valid_pair.copy()
        invalid_pair["symbol"] = self.exchange_symbol_for_tokens("INVALID", "PAIR")
        invalid_pair["marketType"] = "PERP"
        response = [valid_pair, invalid_pair]
        return "INVALID-PAIR", response

    @property
    def network_status_request_successful_mock_response(self):
        return "pong"

    @property
    def trading_rules_request_mock_response(self):
        return self.all_symbols_request_mock_response

    @property
    def trading_rules_request_erroneous_mock_response(self):
        erroneous_trading_rule = self.all_symbols_request_mock_response.copy()
        del erroneous_trading_rule["filters"]
        return erroneous_trading_rule

    @property
    def order_creation_request_successful_mock_response(self):
        return {
            'clientId': 868620826,
            'createdAt': 1507725176595,
            'executedQuantity': '0',
            'executedQuoteQuantity': '0',
            'id': self.expected_exchange_order_id,
            'orderType': 'Limit',
            'postOnly': False,
            'price': '140.99',
            'quantity': '0.01',
            'reduceOnly': None,
            'relatedOrderId': None,
            'selfTradePrevention': 'RejectTaker',
            'side': 'Ask',
            'status': 'New',
            'stopLossLimitPrice': None,
            'stopLossTriggerBy': None,
            'stopLossTriggerPrice': None,
            'strategyId': None,
            'symbol': self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
            'takeProfitLimitPrice': None,
            'takeProfitTriggerBy': None,
            'takeProfitTriggerPrice': None,
            'timeInForce': 'GTC',
            'triggerBy': None,
            'triggerPrice': None,
            'triggerQuantity': None,
            'triggeredAt': None
        }

    @property
    def balance_request_mock_response_for_base_and_quote(self):
        return {
            self.base_asset: {
                'available': '0.232327918',
                'locked': '0',
                'staked': '0'
            },
            self.quote_asset: {
                'available': '15.3013672',
                'locked': '0',
                'staked': '0'
            }
        }

    @property
    def balance_request_mock_response_only_base(self):
        return self.balance_request_mock_response_for_base_and_quote[self.base_asset]

    @property
    def balance_event_websocket_update(self):
        return {}

    @property
    def expected_latest_price(self):
        return 9999.9

    @property
    def expected_supported_order_types(self):
        return [OrderType.LIMIT, OrderType.LIMIT_MAKER, OrderType.MARKET]

    @property
    def expected_trading_rule(self):
        filters = self.trading_rules_request_mock_response.get("filters")
        return TradingRule(
            trading_pair=self.trading_pair,
            min_order_size=Decimal(filters["quantity"]["minQuantity"]),
            min_price_increment=Decimal(filters["price"]["tickSize"]),
            min_base_amount_increment=Decimal(filters["quantity"]["stepSize"]),
            min_notional_size=Decimal(filters["quantity"]["minQuantity"])  # TODO
        )

    @property
    def expected_logged_error_for_erroneous_trading_rule(self):
        erroneous_rule = self.trading_rules_request_erroneous_mock_response[0]
        return f"Error parsing the trading pair rule {erroneous_rule}. Skipping."

    @property
    def expected_exchange_order_id(self):
        return 28

    @property
    def is_order_fill_http_update_included_in_status_update(self) -> bool:
        return True

    @property
    def is_order_fill_http_update_executed_during_websocket_order_event_processing(self) -> bool:
        return False

    @property
    def expected_partial_fill_price(self) -> Decimal:
        return Decimal(10500)

    @property
    def expected_partial_fill_amount(self) -> Decimal:
        return Decimal("0.5")

    @property
    def expected_fill_fee(self) -> TradeFeeBase:
        return AddedToCostTradeFee(
            percent_token=self.quote_asset,
            flat_fees=[TokenAmount(token=self.quote_asset, amount=Decimal("30"))])

    @property
    def expected_fill_trade_id(self) -> str:
        return str(30000)

    def exchange_symbol_for_tokens(self, base_token: str, quote_token: str) -> str:
        return f"{base_token}_{quote_token}"

    def create_exchange_instance(self):
        return BackpackExchange(
            backpack_api_key="testAPIKey",
            backpack_api_secret="testSecret",
            trading_pairs=[self.trading_pair],
        )

    def validate_auth_credentials_present(self, request_call: RequestCall):
        self._validate_auth_credentials_taking_parameters_from_argument(
            request_call_tuple=request_call,
            params=request_call.kwargs["params"] or request_call.kwargs["data"]
        )

    def validate_order_creation_request(self, order: InFlightOrder, request_call: RequestCall):
        request_data = dict(request_call.kwargs["data"])
        self.assertEqual(self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset), request_data["symbol"])
        self.assertEqual(order.trade_type.name.upper(), request_data["side"])
        self.assertEqual(BackpackExchange.backpack_order_type(OrderType.LIMIT), request_data["type"])
        self.assertEqual(Decimal("100"), Decimal(request_data["quantity"]))
        self.assertEqual(Decimal("10000"), Decimal(request_data["price"]))
        self.assertEqual(order.client_order_id, request_data["newClientOrderId"])

    def validate_order_cancelation_request(self, order: InFlightOrder, request_call: RequestCall):
        request_data = dict(request_call.kwargs["params"])
        self.assertEqual(self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
                         request_data["symbol"])
        self.assertEqual(order.client_order_id, request_data["origClientOrderId"])

    def validate_order_status_request(self, order: InFlightOrder, request_call: RequestCall):
        request_params = request_call.kwargs["params"]
        self.assertEqual(self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
                         request_params["symbol"])
        self.assertEqual(order.client_order_id, request_params["origClientOrderId"])

    def validate_trades_request(self, order: InFlightOrder, request_call: RequestCall):
        request_params = request_call.kwargs["params"]
        self.assertEqual(self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
                         request_params["symbol"])
        self.assertEqual(order.exchange_order_id, str(request_params["orderId"]))

    def configure_successful_cancelation_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None) -> str:
        url = web_utils.private_rest_url(CONSTANTS.ORDER_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        response = self._order_cancelation_request_successful_mock_response(order=order)
        mock_api.delete(regex_url, body=json.dumps(response), callback=callback)
        return url

    def configure_erroneous_cancelation_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None) -> str:
        url = web_utils.private_rest_url(CONSTANTS.ORDER_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        mock_api.delete(regex_url, status=400, callback=callback)
        return url

    def configure_order_not_found_error_cancelation_response(
        self, order: InFlightOrder, mock_api: aioresponses, callback: Optional[Callable] = lambda *args, **kwargs: None
    ) -> str:
        url = web_utils.private_rest_url(CONSTANTS.ORDER_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        response = {"code": -2011, "msg": "Unknown order sent."}
        mock_api.delete(regex_url, status=400, body=json.dumps(response), callback=callback)
        return url

    def configure_one_successful_one_erroneous_cancel_all_response(
            self,
            successful_order: InFlightOrder,
            erroneous_order: InFlightOrder,
            mock_api: aioresponses) -> List[str]:
        """
        :return: a list of all configured URLs for the cancelations
        """
        all_urls = []
        url = self.configure_successful_cancelation_response(order=successful_order, mock_api=mock_api)
        all_urls.append(url)
        url = self.configure_erroneous_cancelation_response(order=erroneous_order, mock_api=mock_api)
        all_urls.append(url)
        return all_urls

    def configure_completely_filled_order_status_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None) -> str:
        url = web_utils.private_rest_url(CONSTANTS.ORDER_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        response = self._order_status_request_completely_filled_mock_response(order=order)
        mock_api.get(regex_url, body=json.dumps(response), callback=callback)
        return url

    def configure_canceled_order_status_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None) -> str:
        url = web_utils.private_rest_url(CONSTANTS.ORDER_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        response = self._order_cancelation_request_successful_mock_response(order=order)
        mock_api.get(regex_url, body=json.dumps(response), callback=callback)
        return url

    def configure_erroneous_http_fill_trade_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None) -> str:
        url = web_utils.private_rest_url(path_url=CONSTANTS.MY_TRADES_PATH_URL)
        regex_url = re.compile(url + r"\?.*")
        mock_api.get(regex_url, status=400, callback=callback)
        return url

    def configure_open_order_status_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None) -> str:
        """
        :return: the URL configured
        """
        url = web_utils.private_rest_url(CONSTANTS.ORDER_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        response = self._order_status_request_open_mock_response(order=order)
        mock_api.get(regex_url, body=json.dumps(response), callback=callback)
        return url

    def configure_http_error_order_status_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None) -> str:
        url = web_utils.private_rest_url(CONSTANTS.ORDER_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        mock_api.get(regex_url, status=401, callback=callback)
        return url

    def configure_partially_filled_order_status_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None) -> str:
        url = web_utils.private_rest_url(CONSTANTS.ORDER_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        response = self._order_status_request_partially_filled_mock_response(order=order)
        mock_api.get(regex_url, body=json.dumps(response), callback=callback)
        return url

    def configure_order_not_found_error_order_status_response(
        self, order: InFlightOrder, mock_api: aioresponses, callback: Optional[Callable] = lambda *args, **kwargs: None
    ) -> List[str]:
        url = web_utils.private_rest_url(CONSTANTS.ORDER_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        response = {"code": -2013, "msg": "Order does not exist."}
        mock_api.get(regex_url, body=json.dumps(response), status=400, callback=callback)
        return [url]

    def configure_partial_fill_trade_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None) -> str:
        url = web_utils.private_rest_url(path_url=CONSTANTS.MY_TRADES_PATH_URL)
        regex_url = re.compile(url + r"\?.*")
        response = self._order_fills_request_partial_fill_mock_response(order=order)
        mock_api.get(regex_url, body=json.dumps(response), callback=callback)
        return url

    def configure_full_fill_trade_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None) -> str:
        url = web_utils.private_rest_url(path_url=CONSTANTS.MY_TRADES_PATH_URL)
        regex_url = re.compile(url + r"\?.*")
        response = self._order_fills_request_full_fill_mock_response(order=order)
        mock_api.get(regex_url, body=json.dumps(response), callback=callback)
        return url

    def order_event_for_new_order_websocket_update(self, order: InFlightOrder):
        return {
            "e": "orderAccepted",
            "E": 1694687692980000,
            "s": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
            "c": order.client_order_id,
            "S": self._get_side(order),
            "o": order.order_type.name.upper(),
            "f": "GTC",
            "q": str(order.amount),
            "Q": str(order.amount * order.price),
            "p": str(order.price),
            "P": "21",
            "B": "LastPrice",
            # "a": "30", # Only present if the order has a take-profit trigger price set
            # "b": "10", # Only present if the order has a stop loss trigger price set.
            "j": "30",
            "k": "10",
            # "d": "MarkPrice", # Only present if the order has a take profit trigger price set.
            # "g": "IndexPrice", # Only present if the order has a stop loss trigger price set.
            # "Y": "10", # Only present if the order is a trigger order.
            "X": "New",
            # "R": "PRICE_BAND", # Order expiry reason. Only present if the event is a orderExpired event.
            "i": order.exchange_order_id,
            # "t": 567, # Only present if the event is a orderFill event.
            # "l": "1.23", # Only present if the event is a orderFill event.
            "z": "321",
            "Z": "123",
            # "L": "20", # Only present if the event is a orderFill event.
            # "m": True, # Only present if the event is a orderFill event.
            # "n": "23", # Only present if the event is a orderFill event.
            # "N": "USD", # Only present if the event is a orderFill event.
            "V": "RejectTaker",
            "T": 1694687692989999,
            "O": "USER",
            "I": "1111343026156135",
            "H": 6023471188,
            "y": True,
        }

    def order_event_for_canceled_order_websocket_update(self, order: InFlightOrder):
        order_event = self.order_event_for_new_order_websocket_update(order)
        order_event["X"] = "Cancelled"
        order_event["e"] = "orderCancelled"
        return order_event

    def order_event_for_full_fill_websocket_update(self, order: InFlightOrder):
        order_event = self.order_event_for_new_order_websocket_update(order)
        order_event["X"] = "Filled"
        order_event["e"] = "orderFill"
        order_event["t"] = 378752121  # Trade ID
        order_event["l"] = str(order.average_executed_price)
        order_event["L"] = str(order.executed_amount_base)
        order_event["m"] = self._is_maker(order)
        order_event["n"] = str(self.expected_fill_fee.flat_fees[0].amount)
        order_event["N"] = self.expected_fill_fee.flat_fees[0].token
        order_event["Z"] = str(order.executed_amount_quote)
        return order_event

    def trade_event_for_full_fill_websocket_update(self, order: InFlightOrder):
        return None

    @aioresponses()
    @patch("hummingbot.connector.time_synchronizer.TimeSynchronizer._current_seconds_counter")
    def test_update_time_synchronizer_successfully(self, mock_api, seconds_counter_mock):
        request_sent_event = asyncio.Event()
        seconds_counter_mock.side_effect = [0, 0, 0]

        self.exchange._time_synchronizer.clear_time_offset_ms_samples()
        url = web_utils.public_rest_url(CONSTANTS.SERVER_TIME_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))

        response = 1640000003000

        mock_api.get(regex_url,
                     body=json.dumps(response),
                     callback=lambda *args, **kwargs: request_sent_event.set())

        self.async_run_with_timeout(self.exchange._update_time_synchronizer())

        self.assertEqual(response * 1e-3, self.exchange._time_synchronizer.time())

    @aioresponses()
    def test_update_time_synchronizer_failure_is_logged(self, mock_api):
        url = web_utils.public_rest_url(CONSTANTS.SERVER_TIME_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))

        mock_api.get(regex_url, status=500)

        self.async_run_with_timeout(self.exchange._update_time_synchronizer())

        self.assertTrue(self.is_logged("NETWORK", "Error getting server time."))

    @aioresponses()
    def test_update_time_synchronizer_raises_cancelled_error(self, mock_api):
        url = web_utils.public_rest_url(CONSTANTS.SERVER_TIME_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))

        mock_api.get(regex_url,
                     exception=asyncio.CancelledError)

        self.assertRaises(
            asyncio.CancelledError,
            self.async_run_with_timeout, self.exchange._update_time_synchronizer())

    @aioresponses()
    def test_update_order_fills_from_trades_triggers_filled_event(self, mock_api):
        self.exchange._set_current_timestamp(1640780000)
        self.exchange._last_poll_timestamp = (self.exchange.current_timestamp -
                                              self.exchange.UPDATE_ORDER_STATUS_MIN_INTERVAL - 1)

        self.exchange.start_tracking_order(
            order_id="OID1",
            exchange_order_id="100234",
            trading_pair=self.trading_pair,
            order_type=OrderType.LIMIT,
            trade_type=TradeType.BUY,
            price=Decimal("10000"),
            amount=Decimal("1"),
        )
        order = self.exchange.in_flight_orders["OID1"]

        url = web_utils.private_rest_url(CONSTANTS.MY_TRADES_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))

        trade_fill = {
            "symbol": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
            "id": 28457,
            "orderId": int(order.exchange_order_id),
            "orderListId": -1,
            "price": "9999",
            "qty": "1",
            "quoteQty": "48.000012",
            "commission": "10.10000000",
            "commissionAsset": self.quote_asset,
            "time": 1499865549590,
            "isBuyer": True,
            "isMaker": False,
            "isBestMatch": True
        }

        trade_fill_non_tracked_order = {
            "symbol": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
            "id": 30000,
            "orderId": 99999,
            "orderListId": -1,
            "price": "4.00000100",
            "qty": "12.00000000",
            "quoteQty": "48.000012",
            "commission": "10.10000000",
            "commissionAsset": "BNB",
            "time": 1499865549590,
            "isBuyer": True,
            "isMaker": False,
            "isBestMatch": True
        }

        mock_response = [trade_fill, trade_fill_non_tracked_order]
        mock_api.get(regex_url, body=json.dumps(mock_response))

        self.exchange.add_exchange_order_ids_from_market_recorder(
            {str(trade_fill_non_tracked_order["orderId"]): "OID99"})

        self.async_run_with_timeout(self.exchange._update_order_fills_from_trades())

        request = self._all_executed_requests(mock_api, url)[0]
        self.validate_auth_credentials_present(request)
        request_params = request.kwargs["params"]
        self.assertEqual(self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset), request_params["symbol"])

        fill_event: OrderFilledEvent = self.order_filled_logger.event_log[0]
        self.assertEqual(self.exchange.current_timestamp, fill_event.timestamp)
        self.assertEqual(order.client_order_id, fill_event.order_id)
        self.assertEqual(order.trading_pair, fill_event.trading_pair)
        self.assertEqual(order.trade_type, fill_event.trade_type)
        self.assertEqual(order.order_type, fill_event.order_type)
        self.assertEqual(Decimal(trade_fill["price"]), fill_event.price)
        self.assertEqual(Decimal(trade_fill["qty"]), fill_event.amount)
        self.assertEqual(0.0, fill_event.trade_fee.percent)
        self.assertEqual([TokenAmount(trade_fill["commissionAsset"], Decimal(trade_fill["commission"]))],
                         fill_event.trade_fee.flat_fees)

        fill_event: OrderFilledEvent = self.order_filled_logger.event_log[1]
        self.assertEqual(float(trade_fill_non_tracked_order["time"]) * 1e-3, fill_event.timestamp)
        self.assertEqual("OID99", fill_event.order_id)
        self.assertEqual(self.trading_pair, fill_event.trading_pair)
        self.assertEqual(TradeType.BUY, fill_event.trade_type)
        self.assertEqual(OrderType.LIMIT, fill_event.order_type)
        self.assertEqual(Decimal(trade_fill_non_tracked_order["price"]), fill_event.price)
        self.assertEqual(Decimal(trade_fill_non_tracked_order["qty"]), fill_event.amount)
        self.assertEqual(0.0, fill_event.trade_fee.percent)
        self.assertEqual([
            TokenAmount(
                trade_fill_non_tracked_order["commissionAsset"],
                Decimal(trade_fill_non_tracked_order["commission"]))],
            fill_event.trade_fee.flat_fees)
        self.assertTrue(self.is_logged(
            "INFO",
            f"Recreating missing trade in TradeFill: {trade_fill_non_tracked_order}"
        ))

    @aioresponses()
    def test_update_order_fills_request_parameters(self, mock_api):
        self.exchange._set_current_timestamp(0)
        self.exchange._last_poll_timestamp = -1

        url = web_utils.private_rest_url(CONSTANTS.MY_TRADES_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))

        mock_response = []
        mock_api.get(regex_url, body=json.dumps(mock_response))

        self.async_run_with_timeout(self.exchange._update_order_fills_from_trades())

        request = self._all_executed_requests(mock_api, url)[0]
        self.validate_auth_credentials_present(request)
        request_params = request.kwargs["params"]
        self.assertEqual(self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset), request_params["symbol"])
        self.assertNotIn("startTime", request_params)

        self.exchange._set_current_timestamp(1640780000)
        self.exchange._last_poll_timestamp = (self.exchange.current_timestamp -
                                              self.exchange.UPDATE_ORDER_STATUS_MIN_INTERVAL - 1)
        self.exchange._last_trades_poll_backpack_timestamp = 10
        self.async_run_with_timeout(self.exchange._update_order_fills_from_trades())

        request = self._all_executed_requests(mock_api, url)[1]
        self.validate_auth_credentials_present(request)
        request_params = request.kwargs["params"]
        self.assertEqual(self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset), request_params["symbol"])
        self.assertEqual(10 * 1e3, request_params["startTime"])

    @aioresponses()
    def test_update_order_fills_from_trades_with_repeated_fill_triggers_only_one_event(self, mock_api):
        self.exchange._set_current_timestamp(1640780000)
        self.exchange._last_poll_timestamp = (self.exchange.current_timestamp -
                                              self.exchange.UPDATE_ORDER_STATUS_MIN_INTERVAL - 1)

        url = web_utils.private_rest_url(CONSTANTS.MY_TRADES_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))

        trade_fill_non_tracked_order = {
            "symbol": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
            "id": 30000,
            "orderId": 99999,
            "orderListId": -1,
            "price": "4.00000100",
            "qty": "12.00000000",
            "quoteQty": "48.000012",
            "commission": "10.10000000",
            "commissionAsset": "BNB",
            "time": 1499865549590,
            "isBuyer": True,
            "isMaker": False,
            "isBestMatch": True
        }

        mock_response = [trade_fill_non_tracked_order, trade_fill_non_tracked_order]
        mock_api.get(regex_url, body=json.dumps(mock_response))

        self.exchange.add_exchange_order_ids_from_market_recorder(
            {str(trade_fill_non_tracked_order["orderId"]): "OID99"})

        self.async_run_with_timeout(self.exchange._update_order_fills_from_trades())

        request = self._all_executed_requests(mock_api, url)[0]
        self.validate_auth_credentials_present(request)
        request_params = request.kwargs["params"]
        self.assertEqual(self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset), request_params["symbol"])

        self.assertEqual(1, len(self.order_filled_logger.event_log))
        fill_event: OrderFilledEvent = self.order_filled_logger.event_log[0]
        self.assertEqual(float(trade_fill_non_tracked_order["time"]) * 1e-3, fill_event.timestamp)
        self.assertEqual("OID99", fill_event.order_id)
        self.assertEqual(self.trading_pair, fill_event.trading_pair)
        self.assertEqual(TradeType.BUY, fill_event.trade_type)
        self.assertEqual(OrderType.LIMIT, fill_event.order_type)
        self.assertEqual(Decimal(trade_fill_non_tracked_order["price"]), fill_event.price)
        self.assertEqual(Decimal(trade_fill_non_tracked_order["qty"]), fill_event.amount)
        self.assertEqual(0.0, fill_event.trade_fee.percent)
        self.assertEqual([
            TokenAmount(trade_fill_non_tracked_order["commissionAsset"],
                        Decimal(trade_fill_non_tracked_order["commission"]))],
            fill_event.trade_fee.flat_fees)
        self.assertTrue(self.is_logged(
            "INFO",
            f"Recreating missing trade in TradeFill: {trade_fill_non_tracked_order}"
        ))

    @aioresponses()
    def test_update_order_status_when_failed(self, mock_api):
        self.exchange._set_current_timestamp(1640780000)
        self.exchange._last_poll_timestamp = (self.exchange.current_timestamp -
                                              self.exchange.UPDATE_ORDER_STATUS_MIN_INTERVAL - 1)

        self.exchange.start_tracking_order(
            order_id="OID1",
            exchange_order_id="100234",
            trading_pair=self.trading_pair,
            order_type=OrderType.LIMIT,
            trade_type=TradeType.BUY,
            price=Decimal("10000"),
            amount=Decimal("1"),
        )
        order = self.exchange.in_flight_orders["OID1"]

        url = web_utils.private_rest_url(CONSTANTS.ORDER_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))

        order_status = {
            "symbol": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
            "orderId": int(order.exchange_order_id),
            "orderListId": -1,
            "clientOrderId": order.client_order_id,
            "price": "10000.0",
            "origQty": "1.0",
            "executedQty": "0.0",
            "cummulativeQuoteQty": "0.0",
            "status": "REJECTED",
            "timeInForce": "GTC",
            "type": "LIMIT",
            "side": "BUY",
            "stopPrice": "0.0",
            "icebergQty": "0.0",
            "time": 1499827319559,
            "updateTime": 1499827319559,
            "isWorking": True,
            "origQuoteOrderQty": "10000.000000"
        }

        mock_response = order_status
        mock_api.get(regex_url, body=json.dumps(mock_response))

        self.async_run_with_timeout(self.exchange._update_order_status())

        request = self._all_executed_requests(mock_api, url)[0]
        self.validate_auth_credentials_present(request)
        request_params = request.kwargs["params"]
        self.assertEqual(self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset), request_params["symbol"])
        self.assertEqual(order.client_order_id, request_params["origClientOrderId"])

        failure_event: MarketOrderFailureEvent = self.order_failure_logger.event_log[0]
        self.assertEqual(self.exchange.current_timestamp, failure_event.timestamp)
        self.assertEqual(order.client_order_id, failure_event.order_id)
        self.assertEqual(order.order_type, failure_event.order_type)
        self.assertNotIn(order.client_order_id, self.exchange.in_flight_orders)
        self.assertTrue(
            self.is_logged(
                "INFO",
                f"Order {order.client_order_id} has failed. Order Update: OrderUpdate(trading_pair='{self.trading_pair}',"
                f" update_timestamp={order_status['updateTime'] * 1e-3}, new_state={repr(OrderState.FAILED)}, "
                f"client_order_id='{order.client_order_id}', exchange_order_id='{order.exchange_order_id}', "
                "misc_updates=None)")
        )

    def test_user_stream_update_for_order_failure(self):
        self.exchange._set_current_timestamp(1640780000)
        self.exchange.start_tracking_order(
            order_id="OID1",
            exchange_order_id="100234",
            trading_pair=self.trading_pair,
            order_type=OrderType.LIMIT,
            trade_type=TradeType.BUY,
            price=Decimal("10000"),
            amount=Decimal("1"),
        )
        order = self.exchange.in_flight_orders["OID1"]

        event_message = {
            "e": "executionReport",
            "E": 1499405658658,
            "s": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
            "c": order.client_order_id,
            "S": "BUY",
            "o": "LIMIT",
            "f": "GTC",
            "q": "1.00000000",
            "p": "1000.00000000",
            "P": "0.00000000",
            "F": "0.00000000",
            "g": -1,
            "C": "",
            "x": "REJECTED",
            "X": "REJECTED",
            "r": "NONE",
            "i": int(order.exchange_order_id),
            "l": "0.00000000",
            "z": "0.00000000",
            "L": "0.00000000",
            "n": "0",
            "N": None,
            "T": 1499405658657,
            "t": 1,
            "I": 8641984,
            "w": True,
            "m": False,
            "M": False,
            "O": 1499405658657,
            "Z": "0.00000000",
            "Y": "0.00000000",
            "Q": "0.00000000"
        }

        mock_queue = AsyncMock()
        mock_queue.get.side_effect = [event_message, asyncio.CancelledError]
        self.exchange._user_stream_tracker._user_stream = mock_queue

        try:
            self.async_run_with_timeout(self.exchange._user_stream_event_listener())
        except asyncio.CancelledError:
            pass

        failure_event: MarketOrderFailureEvent = self.order_failure_logger.event_log[0]
        self.assertEqual(self.exchange.current_timestamp, failure_event.timestamp)
        self.assertEqual(order.client_order_id, failure_event.order_id)
        self.assertEqual(order.order_type, failure_event.order_type)
        self.assertNotIn(order.client_order_id, self.exchange.in_flight_orders)
        self.assertTrue(order.is_failure)
        self.assertTrue(order.is_done)

    @patch("hummingbot.connector.utils.get_tracking_nonce")
    def test_client_order_id_on_order(self, mocked_nonce):
        mocked_nonce.return_value = 7

        result = self.exchange.buy(
            trading_pair=self.trading_pair,
            amount=Decimal("1"),
            order_type=OrderType.LIMIT,
            price=Decimal("2"),
        )
        expected_client_order_id = get_new_numeric_client_order_id(
            nonce_creator=self.exchange._nonce_creator,
            max_id_bit_count=CONSTANTS.MAX_ORDER_ID_LEN
        )

        self.assertEqual(result, expected_client_order_id)

        result = self.exchange.sell(
            trading_pair=self.trading_pair,
            amount=Decimal("1"),
            order_type=OrderType.LIMIT,
            price=Decimal("2"),
        )
        expected_client_order_id = get_new_client_order_id(
            is_buy=False,
            trading_pair=self.trading_pair,
            hbot_order_id_prefix=CONSTANTS.HBOT_ORDER_ID_PREFIX,
            max_id_len=CONSTANTS.MAX_ORDER_ID_LEN,
        )

        self.assertEqual(result, expected_client_order_id)

    def test_time_synchronizer_related_request_error_detection(self):
        exception = IOError("Error executing request POST https://api.backpack.com/api/v3/order. HTTP status is 400. "
                            "Error: {'code':-1021,'msg':'Timestamp for this request is outside of the recvWindow.'}")
        self.assertTrue(self.exchange._is_request_exception_related_to_time_synchronizer(exception))

        exception = IOError("Error executing request POST https://api.backpack.com/api/v3/order. HTTP status is 400. "
                            "Error: {'code':-1021,'msg':'Timestamp for this request was 1000ms ahead of the server's "
                            "time.'}")
        self.assertTrue(self.exchange._is_request_exception_related_to_time_synchronizer(exception))

        exception = IOError("Error executing request POST https://api.backpack.com/api/v3/order. HTTP status is 400. "
                            "Error: {'code':-1022,'msg':'Timestamp for this request was 1000ms ahead of the server's "
                            "time.'}")
        self.assertFalse(self.exchange._is_request_exception_related_to_time_synchronizer(exception))

        exception = IOError("Error executing request POST https://api.backpack.com/api/v3/order. HTTP status is 400. "
                            "Error: {'code':-1021,'msg':'Other error.'}")
        self.assertFalse(self.exchange._is_request_exception_related_to_time_synchronizer(exception))

    @aioresponses()
    def test_place_order_manage_server_overloaded_error_unkown_order(self, mock_api):
        self.exchange._set_current_timestamp(1640780000)
        self.exchange._last_poll_timestamp = (self.exchange.current_timestamp -
                                              self.exchange.UPDATE_ORDER_STATUS_MIN_INTERVAL - 1)
        url = web_utils.private_rest_url(CONSTANTS.ORDER_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        mock_response = {"code": -1003, "msg": "Unknown error, please check your request or try again later."}
        mock_api.post(regex_url, body=json.dumps(mock_response), status=503)

        o_id, transact_time = self.async_run_with_timeout(self.exchange._place_order(
            order_id="test_order_id",
            trading_pair=self.trading_pair,
            amount=Decimal("1"),
            trade_type=TradeType.BUY,
            order_type=OrderType.LIMIT,
            price=Decimal("2"),
        ))
        self.assertEqual(o_id, "UNKNOWN")

    @aioresponses()
    def test_place_order_manage_server_overloaded_error_failure(self, mock_api):
        self.exchange._set_current_timestamp(1640780000)
        self.exchange._last_poll_timestamp = (self.exchange.current_timestamp -
                                              self.exchange.UPDATE_ORDER_STATUS_MIN_INTERVAL - 1)

        url = web_utils.private_rest_url(CONSTANTS.ORDER_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        mock_response = {"code": -1003, "msg": "Service Unavailable."}
        mock_api.post(regex_url, body=json.dumps(mock_response), status=503)

        self.assertRaises(
            IOError,
            self.async_run_with_timeout,
            self.exchange._place_order(
                order_id="test_order_id",
                trading_pair=self.trading_pair,
                amount=Decimal("1"),
                trade_type=TradeType.BUY,
                order_type=OrderType.LIMIT,
                price=Decimal("2"),
            ))

        mock_response = {"code": -1003, "msg": "Internal error; unable to process your request. Please try again."}
        mock_api.post(regex_url, body=json.dumps(mock_response), status=503)

        self.assertRaises(
            IOError,
            self.async_run_with_timeout,
            self.exchange._place_order(
                order_id="test_order_id",
                trading_pair=self.trading_pair,
                amount=Decimal("1"),
                trade_type=TradeType.BUY,
                order_type=OrderType.LIMIT,
                price=Decimal("2"),
            ))

    def test_format_trading_rules__min_notional_present(self):
        trading_rules = [{
            "symbol": "COINALPHAHBOT",
            "baseAssetPrecision": 8,
            "status": "TRADING",
            "quotePrecision": 8,
            "orderTypes": ["LIMIT", "MARKET"],
            "filters": [
                {
                    "filterType": "PRICE_FILTER",
                    "minPrice": "0.00000100",
                    "maxPrice": "100000.00000000",
                    "tickSize": "0.00000100"
                }, {
                    "filterType": "LOT_SIZE",
                    "minQty": "0.00100000",
                    "maxQty": "100000.00000000",
                    "stepSize": "0.00100000"
                }, {
                    "filterType": "MIN_NOTIONAL",
                    "minNotional": "0.00100000"
                }
            ],
            "permissionSets": [[
                "SPOT"
            ]]
        }]
        exchange_info = {"symbols": trading_rules}

        result = self.async_run_with_timeout(self.exchange._format_trading_rules(exchange_info))

        self.assertEqual(result[0].min_notional_size, Decimal("0.00100000"))

    def test_format_trading_rules__notional_but_no_min_notional_present(self):
        trading_rules = [{
            "symbol": "COINALPHAHBOT",
            "baseAssetPrecision": 8,
            "status": "TRADING",
            "quotePrecision": 8,
            "orderTypes": ["LIMIT", "MARKET"],
            "filters": [
                {
                    "filterType": "PRICE_FILTER",
                    "minPrice": "0.00000100",
                    "maxPrice": "100000.00000000",
                    "tickSize": "0.00000100"
                }, {
                    "filterType": "LOT_SIZE",
                    "minQty": "0.00100000",
                    "maxQty": "100000.00000000",
                    "stepSize": "0.00100000"
                }, {
                    "filterType": "NOTIONAL",
                    "minNotional": "10.00000000",
                    "applyMinToMarket": False,
                    "maxNotional": "10000.00000000",
                    "applyMaxToMarket": False,
                    "avgPriceMins": 5
                }
            ],
            "permissionSets": [[
                "SPOT"
            ]]
        }]
        exchange_info = {"symbols": trading_rules}

        result = self.async_run_with_timeout(self.exchange._format_trading_rules(exchange_info))

        self.assertEqual(result[0].min_notional_size, Decimal("10"))

    def _validate_auth_credentials_taking_parameters_from_argument(self,
                                                                   request_call_tuple: RequestCall,
                                                                   params: Dict[str, Any]):
        self.assertIn("timestamp", params)
        self.assertIn("window", params)
        request_headers = request_call_tuple.kwargs["headers"]
        self.assertIn("X-MBX-APIKEY", request_headers)
        self.assertIn("X-MBX-APIKEY", request_headers)
        self.assertIn("X-Timestamp", request_headers)
        self.assertIn("X-Window", request_headers)
        self.assertIn("X-Signature", request_headers)
        self.assertEqual("testAPIKey", request_headers["X-MBX-APIKEY"])

    def _order_status_request_open_mock_response(self, order: InFlightOrder) -> Any:
        return {
            "clientId": order.client_order_id,
            "createdAt": order.creation_timestamp,
            "executedQuantity": '0',
            "executedQuoteQuantity": '0',
            "id": '26919130763',
            "orderType": "Limit" if self._is_maker(order) else "Market",
            "postOnly": order.order_type == OrderType.LIMIT_MAKER,
            "price": str(order.price),
            "quantity": str(order.amount),
            "reduceOnly": None,
            "relatedOrderId": None,
            "selfTradePrevention": 'RejectTaker',
            "side": self._get_side(order),
            "status": 'New',
            "stopLossLimitPrice": None,
            "stopLossTriggerBy": None,
            "stopLossTriggerPrice": None,
            "strategyId": None,
            "symbol": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
            "takeProfitLimitPrice": None,
            "takeProfitTriggerBy": None,
            "takeProfitTriggerPrice": None,
            "timeInForce": 'GTC',
            "triggerBy": None,
            "triggerPrice": None,
            "triggerQuantity": None,
            "triggeredAt": None
        }

    def _order_cancelation_request_successful_mock_response(self, order: InFlightOrder) -> Any:
        order_cancelation_response = self._order_status_request_open_mock_response(order)
        order_cancelation_response["status"] = "Cancelled"
        return order_cancelation_response

    def _order_status_request_completely_filled_mock_response(self, order: InFlightOrder) -> Any:
        order_completely_filled_response = self._order_status_request_open_mock_response(order)
        order_completely_filled_response["executedQuantity"] = str(order.executed_amount_base)
        order_completely_filled_response["executedQuoteQuantity"] = str(order.executed_amount_quote)
        order_completely_filled_response["status"] = "Filled"
        return order_completely_filled_response

    def _order_status_request_partially_filled_mock_response(self, order: InFlightOrder) -> Any:
        order_partially_filled_response = self._order_status_request_open_mock_response(order)
        order_partially_filled_response["executedQuantity"] = str(self.expected_partial_fill_amount)
        executed_quote_quantity = str(self.expected_partial_fill_amount * self.expected_partial_fill_price)
        order_partially_filled_response["executedQuoteQuantity"] = executed_quote_quantity
        order_partially_filled_response["status"] = "PartiallyFilled"
        return order_partially_filled_response

    def _order_fill_template(self, order: InFlightOrder) -> Dict[str, Any]:
        return {
            "clientId": order.client_order_id,
            "fee": str(self.expected_fill_fee.flat_fees[0].amount),
            "feeSymbol": self.expected_fill_fee.flat_fees[0].token,
            "isMaker": self._is_maker(order),
            "orderId": order.exchange_order_id,
            "price": str(order.price),
            "quantity": str(order.amount),
            "side": self._get_side(order),
            "symbol": self.exchange_symbol_for_tokens(order.base_asset, order.quote_asset),
            "systemOrderType": None,
            "timestamp": 1499865549590,
            "tradeId": self.expected_fill_trade_id
        }

    def _order_fills_request_full_fill_mock_response(self, order: InFlightOrder):
        order_fill = self._order_fill_template(order)
        return [order_fill]

    def _order_fills_request_partial_fill_mock_response(self, order: InFlightOrder):
        partial_order_fill = self._order_fill_template(order)
        partial_order_fill["quantity"] = str(self.expected_partial_fill_amount)
        partial_order_fill["price"] = str(self.expected_partial_fill_price)
        return [partial_order_fill]

    @staticmethod
    def _is_maker(order: InFlightOrder):
        return order.order_type in [OrderType.LIMIT, OrderType.LIMIT_MAKER]

    @staticmethod
    def _get_side(order: InFlightOrder):
        return "Bid" if order.trade_type == TradeType.BUY else "Ask"
