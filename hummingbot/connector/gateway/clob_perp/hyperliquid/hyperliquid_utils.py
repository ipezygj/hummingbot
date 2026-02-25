from decimal import Decimal
from typing import Any, Dict

def convert_to_exchange_trading_pair(hb_trading_pair: str) -> str:
    """Converts ETH-USDC to ETH."""
    return hb_trading_pair.split("-")[0]

def convert_from_exchange_trading_pair(ex_trading_pair: str) -> str:
    """Converts ETH back to ETH-USDC (Hyperliquid default)."""
    return f"{ex_trading_pair}-USDC"

def get_price_increment(trading_pair: str) -> Decimal:
    return Decimal("0.0001")