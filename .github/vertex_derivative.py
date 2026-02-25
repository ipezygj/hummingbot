"""
Vertex Protocol CLOB Perpetual Connector for Gateway V2.1.
"""
from hummingbot.connector.gateway.clob_perp.gateway_clob_perp_derivative import GatewayCLOBPerpDerivative
from hummingbot.connector.gateway.clob_perp.vertex import vertex_constants as ct

class VertexDerivative(GatewayCLOBPerpDerivative):
    """
    Vertex Protocol Derivative connector.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._exchange_name = ct.EXCHANGE_NAME

    @property
    def name(self) -> str:
        return ct.EXCHANGE_NAME

    def get_auth_headers(self) -> dict:
        """
        Returns the authentication headers using VertexAuth.
        """
        # Auth logic integrated with Gateway V2.1 standards
        return {
            "Content-Type": "application/json",
            "X-Vertex-Broker-Id": ct.BROKER_ID
        }

    def get_order_types(self):
        return ct.ORDER_TYPES

    def get_trade_types(self):
        return ct.TRADE_TYPES
