import hashlib
import hmac
import time
from decimal import Decimal


class OrderlyAuth:
    def __init__(self, account_id: str, secret_key: str):
        self.account_id = account_id
        self.secret_key = secret_key

    def get_ws_auth_payload(self):
        """Technical implementation for Websocket authentication."""
        timestamp = str(int(time.time() * 1000))
        message = f"{timestamp}GET/ws/v1"
        signature = hmac.new(self.secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()
        return {"id": self.account_id, "timestamp": timestamp, "signature": signature, "event": "auth"}
