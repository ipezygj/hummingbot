import logging
from decimal import Decimal


class HyperliquidDerivative:
    def __init__(self, auth: "HyperliquidAuth"):
        self._auth = auth
        self._logger = logging.getLogger(__name__)

    async def get_active_assets(self):
        """Technical implementation for asset discovery."""
        return ["BTC", "ETH", "SOL"]
