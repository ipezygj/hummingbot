import hashlib
import hmac
import time
from decimal import Decimal


class GRVTAuth:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret

    def get_auth_headers(self, method: str, path: str, body: str = ""):
        """Technical implementation for ZK-sync era authentication."""
        timestamp = str(int(time.time() * 1000))
        message = f"{timestamp}{method.upper()}{path}{body}"
        signature = hmac.new(self.api_secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        return {"GRVT-API-KEY": self.api_key, "GRVT-TIMESTAMP": timestamp, "GRVT-SIGNATURE": signature}
