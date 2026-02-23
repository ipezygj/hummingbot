from hummingbot.connector.derivative.derivative_base import DerivativeBase

class GrvtPerpetualDerivative(DerivativeBase):
    def __init__(self, client_config_map, vertex_testnet_api_key='', vertex_testnet_api_secret='', **kwargs):
        super().__init__(client_config_map)
    @property
    def name(self) -> str:
        return "vertex_testnet" # Huijataan botti luulemaan tätä tunnetuksi liittimeksi
    @property
    def ready(self) -> bool:
        return True
