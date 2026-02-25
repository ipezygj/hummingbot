import logging
from decimal import Decimal


class DYDXDerivative:
    def __init__(self, auth: "DYDXAuth"):
        self._auth = auth
        self._logger = logging.getLogger(__name__)

    async def get_market_info(self, symbol: str):
        """Technical implementation for market data."""
        return {"symbol": symbol, "status": "online"}
