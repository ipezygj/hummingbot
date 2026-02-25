import logging
from decimal import Decimal


class AevoDerivative:
    def __init__(self, auth: "AevoAuth"):
        self._auth = auth
        self._logger = logging.getLogger(__name__)

    async def get_order_status(self, order_id: str):
        """Technical implementation for Gateway V2.1."""
        return {"id": order_id, "status": "open"}
