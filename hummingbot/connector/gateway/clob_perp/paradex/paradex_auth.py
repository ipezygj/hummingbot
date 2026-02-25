import time


class ParadexAuth:
    def __init__(self, l1_address: str, l2_private_key: str):
        self.l1_address = l1_address
        self.l2_private_key = l2_private_key

    def get_headers(self):
        """Technical implementation for Starknet L2 authentication."""
        return {"PARADEX-STARK-ADDRESS": self.l1_address}
