import base64
import json
from collections import OrderedDict
from typing import Any, Dict

from cryptography.hazmat.primitives.asymmetric import ed25519

from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest, WSRequest


class BackpackAuth(AuthBase):
    def __init__(self, api_key: str, secret_key: str, time_provider: TimeSynchronizer):
        self.api_key = api_key
        self.secret_key = secret_key
        self.time_provider = time_provider

    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        """
        Adds the server time and the signature to the request, required for authenticated interactions. It also adds
        the required parameter in the request header.
        :param request: the request to be configured for authenticated interaction
        """
        if request.method == RESTMethod.POST:
            request.data = self.add_auth_to_params(params=json.loads(request.data))
        else:
            request.params = self.add_auth_to_params(params=request.params)

        headers = {}
        if request.headers is not None:
            headers.update(request.headers)
        headers.update(self.header_for_authentication())
        request.headers = headers

        return request

    async def ws_authenticate(self, request: WSRequest) -> WSRequest:
        """
        This method is intended to configure a websocket request to be authenticated. Backpack does not use this
        functionality
        """
        return request  # pass-through

    def add_auth_to_params(self,
                           params: Dict[str, Any]):
        timestamp = int(self.time_provider.time() * 1e3)

        request_params = OrderedDict(params or {})
        request_params["timestamp"] = timestamp

        signature = self._generate_signature(params=request_params)
        request_params["signature"] = signature

        return request_params

    def header_for_authentication(self) -> Dict[str, str]:
        return {
            "X-Timestamp": str(self.time_provider.time()),
            "X-Window": "5000",
            "X-API-Key": self.api_key,
            "X-Signature": self._generate_signature()
        }

    def _generate_signature(self, params: Dict[str, Any]) -> str:
        message = "&".join(
            f"{k}={params[k]}" for k in sorted(params)
        ).encode("utf-8")

        seed = base64.b64decode(self.secret_key)
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(seed)

        signature = private_key.sign(message)

        return base64.b64encode(signature).decode()
