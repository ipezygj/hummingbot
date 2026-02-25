import time
from decimal import Decimal


class DYDXAuth:
    def __init__(self, stark_key: str, api_key: str):
        self.stark_key = stark_key
        self.api_key = api_key

    def get_auth_headers(self):
        """Technical implementation for Starkware/Cosmos auth."""
        return {"DYDX-STARK-KEY": self.stark_key}
