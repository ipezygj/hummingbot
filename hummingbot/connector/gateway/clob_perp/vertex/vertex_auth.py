from decimal import Decimal


class VertexAuth:
    def __init__(self, wallet_address: str, private_key: str):
        self.wallet_address = wallet_address
        self.private_key = private_key

    def scale_price(self, price: Decimal) -> int:
        """Technical implementation."""
        return int(price * Decimal("1e18"))
