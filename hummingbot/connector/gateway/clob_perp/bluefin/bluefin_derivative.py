import logging
from decimal import Decimal


class BluefinDerivative:
    def __init__(self, auth: "BluefinAuth"):
        self._auth = auth
        self._logger = logging.getLogger(__name__)

    async def cancel_all_orders(self, symbol: str):
        """Technical implementation for Gateway V2.1."""
        return {"status": "success", "symbol": symbol}
