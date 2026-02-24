from decimal import Decimal
from typing import Optional
from pydantic import BaseModel
from hummingbot.core.data_type.common import TradeType

class ExecutorDecision(BaseModel):
"""
Tämä malli määrittelee strategian tekemän päätöksen.
"""
executor_id: str
trading_pair: str
trade_type: TradeType
amount: Decimal
price: Optional[Decimal] = None
reason: str
is_active: bool = True
