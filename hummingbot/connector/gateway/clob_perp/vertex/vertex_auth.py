import time
from typing import Any, Dict
from decimal import Decimal

class VertexAuth:
    def __init__(self, wallet_address: str, private_key: str):
        self.wallet_address = wallet_address
        self.private_key = private_key

    def get_subaccount_identifier(self, name: str = default) -> str:
        return f"{self.wallet_address}{name}"

    def scale_price(self, price: Decimal) -> int:
        return int(price * Decimal(1000000000000000000))

    def scale_amount(self, amount: Decimal) -> int:
        return int(amount * Decimal(1000000))