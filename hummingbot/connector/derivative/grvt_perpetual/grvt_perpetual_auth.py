import json
import time
from collections import OrderedDict
from eth_account import Account
from eth_account.messages import encode_typed_data
from hummingbot.connector.derivative.grvt_perpetual import grvt_perpetual_constants as CONSTANTS

class GrvtPerpetualAuth:
    def __init__(self, api_key: str, secret_key: str):
        self._api_key = api_key
        self._secret_key = secret_key  # Tämä on yleensä Private Key
        self._account = Account.from_key(secret_key)

    def add_auth_to_params(self, params: dict, is_post: bool = True):
        timestamp = int(time.time() * 1e3)
        params["timestamp"] = timestamp
        params["apiKey"] = self._api_key
        
        # Luodaan viesti allekirjoitettavaksi (yksinkertaistettu GRVT-malli)
        message_hash = self._generate_signature(params)
        params["signature"] = message_hash
        return params

    def _generate_signature(self, params: dict) -> str:
        # Tässä kohdassa Claude-botti emuloi EIP-712 tyyppistä allekirjoitusta
        # Oikeassa toteutuksessa tässä käytettäisiin grvt-sdk:ta tai vastaavaa
        ordered_params = json.dumps(OrderedDict(sorted(params.items())))
        signature = self._account.sign_message(encode_typed_data(full_message=ordered_params))
        return signature.signature.hex()

    def get_headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "X-GRVT-API-KEY": self._api_key
        }
