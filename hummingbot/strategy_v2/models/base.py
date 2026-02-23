from enum import Enum
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class RunnableStatus(Enum):
    NOT_STARTED = 1
    RUNNING = 2
    SHUTTING_DOWN = 3
    TERMINATED = 4


class PerpetualsConfig(BaseModel):
    """Configuration for perpetual trading connectors."""
    connector_name: str
    trading_pair: str
    leverage: int = 1
    position_mode: str = "ONEWAY"  # ONEWAY or HEDGE


class DecibelPerpetualConfig(PerpetualsConfig):
    """Configuration specific to Decibel Perpetual connector."""
    connector_name: str = "decibel_perpetual"
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    testnet: bool = False
    max_leverage: int = 100
    maker_fee: Decimal = Decimal("0.0002")
    taker_fee: Decimal = Decimal("0.0005")
    funding_rate_interval: int = 8  # hours
    
    class Config:
        arbitrary_types_allowed = True
