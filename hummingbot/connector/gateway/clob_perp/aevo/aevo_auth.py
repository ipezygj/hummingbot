import time

from eth_account import Account
from eth_account.messages import encode_defunct


class AevoAuth:
    def __init__(self, signing_key: str):
        self.account = Account.from_key(signing_key)

    def sign_request(self, method: str, path: str, body: str = ""):
        """Technical implementation for Aevo L2 signing."""
        timestamp = str(int(time.time() * 1000))
        message = f"{method}{path}{body}{timestamp}"
        signature = self.account.sign_message(encode_defunct(text=message))
        return signature.signature.hex()
