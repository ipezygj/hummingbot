from decimal import Decimal


class BluefinAuth:
    def __init__(self, sui_address: str, secret_key: str):
        self.sui_address = sui_address
        self.secret_key = secret_key

    def get_auth_headers(self):
        """Technical implementation for Sui Move-based signing."""
        return {"X-BLUEFIN-SUI-ADDRESS": self.sui_address}
