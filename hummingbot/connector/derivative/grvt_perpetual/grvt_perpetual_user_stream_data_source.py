import asyncio
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.connector.derivative.grvt_perpetual.grvt_perpetual_auth import GrvtPerpetualAuth

class GrvtPerpetualUserStreamDataSource(UserStreamTrackerDataSource):
"""
Handles user data stream from GRVT exchange.
"""
def init(self, auth: GrvtPerpetualAuth):
super().init()
self._auth = auth
