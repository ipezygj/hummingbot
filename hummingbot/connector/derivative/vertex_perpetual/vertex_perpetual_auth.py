import time
from typing import Any, Dict, Optional
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

from hummingbot.connector.derivative.vertex_perpetual.vertex_perpetual_constants import VERTEX_CHAIN_ID
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTRequest, WSRequest


class VertexPerpetualAuth(AuthBase):
    def __init__(self, vertex_arbitrum_address: str, vertex_arbitrum_private_key: str):
        self._vertex_arbitrum_address = vertex_arbitrum_address
        self._vertex_arbitrum_private_key = vertex_arbitrum_private_key
        self._chain_id = VERTEX_CHAIN_ID

    @property
    def vertex_arbitrum_address(self) -> str:
        return self._vertex_arbitrum_address

    @property
    def vertex_arbitrum_private_key(self) -> str:
        return self._vertex_arbitrum_private_key

    def sign_message(self, message: str) -> str:
        msg = encode_defunct(text=message)
        signed = Account.sign_message(msg, private_key=self._vertex_arbitrum_private_key)
        return signed.signature.hex()

    def get_expiration_time(self, expiration_seconds: int = 90) -> int:
        return int(time.time()) + expiration_seconds

    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        return request

    async def ws_authenticate(self, request: WSRequest) -> WSRequest:
        return request

    def get_referral_code(self) -> Optional[str]:
        return None

    def generate_auth_dict(self, expiration_seconds: int = 90) -> Dict[str, Any]:
        expiration = self.get_expiration_time(expiration_seconds)
        message = f"{self._vertex_arbitrum_address}{expiration}"
        signature = self.sign_message(message)
        return {
            "address": self._vertex_arbitrum_address,
            "expiration": expiration,
            "signature": signature,
        }