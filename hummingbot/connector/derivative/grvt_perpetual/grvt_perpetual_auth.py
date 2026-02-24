import hmac
import hashlib
import time
from typing import Any, Dict
from hummingbot.core.web_assistant.auth import AuthBase

class GrvtPerpetualAuth(AuthBase):
    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key

    async def rest_authenticate(self, request: Any) -> Any:
        timestamp = str(int(time.time() * 1000))
        method = request.method.upper()
        path = request.url.split(".io")[-1]
        
        body = ""
        if request.data:
            body = request.data
            
        auth_dict = self.generate_auth_dict(method, path, body, timestamp)
        request.headers.update(auth_dict)
        return request

    def generate_auth_dict(self, method: str, path: str, body: str, timestamp: str) -> Dict[str, str]:
        message = timestamp + method + path + body
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        return {
            "GRVT-API-KEY": self.api_key,
            "GRVT-TIMESTAMP": timestamp,
            "GRVT-SIGNATURE": signature
        }
