
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder
from hummingbot.connector.derivative.derivative_base import DerivativeBase
from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_auth import GrvtPerpetualAuth

class GrvtPerpetualDerivative(DerivativeBase):
def init(self, auth: GrvtPerpetualAuth, trading_pairs: List[str]):
super().init()
self._auth = auth
self._trading_pairs = trading_pairs
