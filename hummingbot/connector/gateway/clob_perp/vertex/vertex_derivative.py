import logging
from decimal import Decimal


class VertexDerivative:
    def __init__(self):
        """Technical implementation."""
        self._logger = logging.getLogger(__name__)

    async def get_balances(self):
        """Technical implementation."""
        return {"USDC": Decimal("0.0")}
