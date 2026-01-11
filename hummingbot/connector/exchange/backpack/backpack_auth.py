import base64
import json
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives.asymmetric import ed25519

import hummingbot.connector.exchange.backpack.backpack_constants as CONSTANTS
from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest, WSRequest


class BackpackAuth(AuthBase):
    DEFAULT_WINDOW_MS = 5000

    def __init__(self, api_key: str, secret_key: str, time_provider: TimeSynchronizer):
        self.api_key = api_key
        self.secret_key = secret_key
        self.time_provider = time_provider

    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        headers = dict(request.headers or {})

        # actually this instruction is passed through headers to avoid modifying the base class, then is popped
        instruction = headers.pop("instruction", None)

        sign_params = self._get_signable_params(request)

        timestamp_ms = int(self.time_provider.time() * 1e3)
        window_ms = self.DEFAULT_WINDOW_MS

        signature = self.generate_signature(params=sign_params,
                                            timestamp_ms=timestamp_ms, window_ms=window_ms,
                                            instruction=instruction)

        headers.update({
            "X-Timestamp": str(timestamp_ms),
            "X-Window": str(window_ms),
            "X-API-Key": self.api_key,
            "X-Signature": signature,
            "X-BROKER-ID": str(CONSTANTS.BROKER_ID)
        })
        request.headers = headers

        return request

    async def ws_authenticate(self, request: WSRequest) -> WSRequest:
        return request  # pass-through

    def _get_signable_params(self, request: RESTRequest) -> Dict[str, Any]:
        """
        Backpack: sign the request BODY (for POST/DELETE with body) OR QUERY params.
        Do NOT include timestamp/window/signature here (those are appended separately).
        """
        if request.method in [RESTMethod.POST, RESTMethod.DELETE] and request.data:
            return json.loads(request.data)
        return dict(request.params or {})

    def generate_signature(
        self,
        params: Dict[str, Any],
        timestamp_ms: int,
        window_ms: int,
        instruction: Optional[str] = None,
    ) -> str:
        params_message = "&".join(
            f"{k}={params[k]}" for k in sorted(params)
        )

        sign_str = ""
        if instruction:
            sign_str = f"instruction={instruction}"
        if params_message:
            sign_str = f"{sign_str}&{params_message}" if sign_str else params_message

        sign_str += f"{'&' if len(sign_str) > 0 else ''}timestamp={timestamp_ms}&window={window_ms}"

        seed = base64.b64decode(self.secret_key)
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(seed)
        signature_bytes = private_key.sign(sign_str.encode("utf-8"))
        return base64.b64encode(signature_bytes).decode("utf-8")
