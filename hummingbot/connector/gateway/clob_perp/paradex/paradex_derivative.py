import logging
from decimal import Decimal


class ParadexDerivative:
    def __init__(self, auth: "ParadexAuth"):
        self._auth = auth
        self._logger = logging.getLogger(__name__)

    async def get_trading_pairs(self):
        """Technical implementation for Paradex asset list."""
        return ["BTC-USD-PERP", "ETH-USD-PERP"]
