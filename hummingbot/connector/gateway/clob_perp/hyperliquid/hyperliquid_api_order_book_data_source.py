import asyncio
from typing import Any, Dict, List, Optional
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.connector.gateway.clob_perp.hyperliquid import hyperliquid_constants as constants

class HyperliquidAPIOrderBookDataSource:
    def __init__(self, trading_pairs: List[str]):
        self._trading_pairs = trading_pairs

    async def get_new_order_book(self, trading_pair: str) -> OrderBook:
        return OrderBook()

    async def listen_for_order_book_snapshots(self, ev_loop: asyncio.AbstractEventLoop, output: asyncio.Queue):
        pass