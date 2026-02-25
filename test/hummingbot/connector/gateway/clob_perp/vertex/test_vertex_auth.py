import unittest
from decimal import Decimal

from hummingbot.connector.gateway.clob_perp.vertex.vertex_auth import VertexAuth


class TestVertexAuth(unittest.TestCase):
    def setUp(self):
        self.auth = VertexAuth("0x123", "secret_key")

    def test_scale_price(self):
        """Technical test implementation."""
        price = Decimal("1.5")
        scaled = self.auth.scale_price(price)
        self.assertEqual(scaled, int(1.5 * 1e18))


if __name__ == "__main__":
    unittest.main()
