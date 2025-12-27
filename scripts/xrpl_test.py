import logging
import os
import time
from datetime import datetime
from decimal import Decimal
from typing import Dict, List

from pydantic import Field

from hummingbot.client.config.config_data_types import BaseClientModel
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.core.data_type.common import OrderType, PriceType, TradeType
from hummingbot.core.data_type.order_candidate import OrderCandidate
from hummingbot.core.event.events import OrderFilledEvent
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase


class TestXRPLConfig(BaseClientModel):
    script_file_name: str = os.path.basename(__file__)
    exchange: str = Field("xrpl")
    trading_pair: str = Field("XRP-RLUSD")
    order_refresh_time: int = Field(60, description="Time in seconds to refresh the orders")


class TestXRPLStrategy(ScriptStrategyBase):
    create_timestamp = 0
    price_source = PriceType.MidPrice

    @classmethod
    def init_markets(cls, config: TestXRPLConfig):
        cls.markets = {config.exchange: {config.trading_pair}}
        cls.price_source = PriceType.MidPrice

    def __init__(self, connectors: Dict[str, ConnectorBase], config: TestXRPLConfig):
        super().__init__(connectors)
        self.config = config

        # Simple tracking for test purposes
        self.start_time = time.time()
        self.fill_events: List[Dict] = []

        # Order statistics
        self.total_fills = 0
        self.buy_fills = 0
        self.sell_fills = 0
        self.limit_fills = 0
        self.market_fills = 0

    def on_tick(self):
        if self.create_timestamp <= self.current_timestamp:
            self.cancel_all_orders()
            proposal = self.create_proposal_market(
                order_count=1,
                order_amount=Decimal("0.01"),
                order_side="BUY",
            )
            self.place_orders(self.adjust_proposal_to_budget(proposal))

            proposal = self.create_proposal_market(
                order_count=1,
                order_amount=Decimal("0.01"),
                order_side="SELL",
            )
            self.place_orders(self.adjust_proposal_to_budget(proposal))

            # proposal = self.create_proposal_limit(
            #     order_levels=50,
            #     order_level_spread=50,
            #     order_amount=Decimal("0.1"),
            # )
            # self.place_orders(self.adjust_proposal_to_budget(proposal))

            self.create_timestamp = self.config.order_refresh_time + self.current_timestamp

    def create_proposal_limit(
        self,
        order_levels: int = 1,
        order_level_spread: int = 50,
        order_amount: Decimal = Decimal("10"),
    ) -> List[OrderCandidate]:
        """
        Create limit orders on both sides of the order book.

        Args:
            order_levels: Number of order levels per side (e.g., 3 means 3 buy + 3 sell orders)
            order_level_spread: Gap between order levels in basis points (bps). 100 bps = 1%
            order_amount: Amount per order level in base token
        """
        connector = self.connectors[self.config.exchange]
        mid_price = connector.get_price_by_type(self.config.trading_pair, self.price_source)

        if mid_price is None or mid_price <= 0:
            self.log_with_clock(logging.WARNING, "Could not get mid price, skipping order creation")
            return []

        orders: List[OrderCandidate] = []
        spread_decimal = Decimal(order_level_spread) / Decimal("10000")  # Convert bps to decimal

        for level in range(1, order_levels + 1):
            # Calculate price offset for this level
            level_spread = spread_decimal * level

            # Buy order (below mid price)
            buy_price = mid_price * (Decimal("1") - level_spread)
            orders.append(
                OrderCandidate(
                    trading_pair=self.config.trading_pair,
                    is_maker=True,
                    order_type=OrderType.LIMIT,
                    order_side=TradeType.BUY,
                    amount=order_amount,
                    price=buy_price,
                )
            )

            # Sell order (above mid price)
            sell_price = mid_price * (Decimal("1") + level_spread)
            orders.append(
                OrderCandidate(
                    trading_pair=self.config.trading_pair,
                    is_maker=True,
                    order_type=OrderType.LIMIT,
                    order_side=TradeType.SELL,
                    amount=order_amount,
                    price=sell_price,
                )
            )

        self.log_with_clock(
            logging.INFO,
            f"Creating {order_levels} limit order levels per side | "
            f"Spread: {order_level_spread} bps | Amount: {order_amount} | "
            f"Total orders: {len(orders)}",
        )

        return orders

    def create_proposal_market(
        self,
        order_count: int = 1,
        order_amount: Decimal = Decimal("10"),
        order_side: str = "BUY",
    ) -> List[OrderCandidate]:
        """
        Create market orders.

        Args:
            order_count: Number of market orders to create
            order_amount: Amount per market order in base token
            order_side: Side for market orders: 'BUY' or 'SELL'
        """
        trade_side = TradeType.BUY if order_side.upper() == "BUY" else TradeType.SELL

        orders: List[OrderCandidate] = []
        for _ in range(order_count):
            orders.append(
                OrderCandidate(
                    trading_pair=self.config.trading_pair,
                    is_maker=False,
                    order_type=OrderType.MARKET,
                    order_side=trade_side,
                    amount=order_amount,
                    price=Decimal("0"),  # Market orders don't need price
                )
            )

        self.log_with_clock(
            logging.INFO, f"Creating {order_count} MARKET {order_side} orders | Amount: {order_amount} each"
        )

        return orders

    def adjust_proposal_to_budget(self, proposal: List[OrderCandidate]) -> List[OrderCandidate]:
        proposal_adjusted = self.connectors[self.config.exchange].budget_checker.adjust_candidates(
            proposal, all_or_none=True
        )
        return proposal_adjusted

    def place_orders(self, proposal: List[OrderCandidate]) -> None:
        for order in proposal:
            self.place_order(connector_name=self.config.exchange, order=order)

    def place_order(self, connector_name: str, order: OrderCandidate):
        if order.order_side == TradeType.SELL:
            self.sell(
                connector_name=connector_name,
                trading_pair=order.trading_pair,
                amount=order.amount,
                order_type=order.order_type,
                price=order.price,
            )
        elif order.order_side == TradeType.BUY:
            self.buy(
                connector_name=connector_name,
                trading_pair=order.trading_pair,
                amount=order.amount,
                order_type=order.order_type,
                price=order.price,
            )

    def cancel_all_orders(self):
        for order in self.get_active_orders(connector_name=self.config.exchange):
            self.cancel(self.config.exchange, order.trading_pair, order.client_order_id)

    def did_fill_order(self, event: OrderFilledEvent):
        """Track filled orders for testing."""
        if event.trading_pair != self.config.trading_pair:
            return

        # Update counters
        self.total_fills += 1
        if event.trade_type == TradeType.BUY:
            self.buy_fills += 1
        else:
            self.sell_fills += 1

        if event.order_type == OrderType.LIMIT:
            self.limit_fills += 1
        else:
            self.market_fills += 1

        # Record fill event
        fill_record = {
            "timestamp": time.time(),
            "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "order_id": event.order_id,
            "trade_type": event.trade_type.name,
            "order_type": event.order_type.name,
            "price": event.price,
            "amount": event.amount,
            "quote_volume": event.price * event.amount,
        }
        self.fill_events.append(fill_record)

        # Log the fill event
        msg = (
            f"FILL #{self.total_fills}: {event.trade_type.name} {event.order_type.name} | "
            f"Amount: {event.amount:.6f} @ Price: {event.price:.6f} | "
            f"Quote: {event.price * event.amount:.4f} | "
            f"Order ID: {event.order_id[:8]}..."
        )
        self.log_with_clock(logging.INFO, msg)
        self.notify_hb_app_with_timestamp(msg)

    def format_status(self) -> str:
        """Returns simplified status for testing."""
        if not self.ready_to_trade:
            return "Market connectors are not ready."

        lines = []

        # ============ Balances ============
        lines.extend(["", "  Balances:"])
        balance_df = self.get_balance_df()
        lines.extend(["    " + line for line in balance_df.to_string(index=False).split("\n")])

        # ============ Active Orders ============
        try:
            orders_df = self.active_orders_df()
            lines.extend(["", "  Active Orders:"])
            lines.extend(["    " + line for line in orders_df.to_string(index=False).split("\n")])
        except ValueError:
            lines.extend(["", "  No active orders."])

        # ============ Test Duration ============
        elapsed_seconds = time.time() - self.start_time
        lines.extend(["", "  ═══════════════════════════════════════"])
        lines.extend(["  Test Duration:"])
        lines.append(f"    Elapsed: {elapsed_seconds:.1f} seconds ({elapsed_seconds / 60:.2f} minutes)")

        # ============ Fill Statistics ============
        lines.extend(["", "  ═══════════════════════════════════════"])
        lines.extend(["  Fill Statistics:"])
        lines.append(f"    Total Fills:   {self.total_fills}")
        lines.append(f"    By Side:       BUY: {self.buy_fills} | SELL: {self.sell_fills}")
        lines.append(f"    By Type:       LIMIT: {self.limit_fills} | MARKET: {self.market_fills}")

        # ============ Fill Events (All) ============
        if self.fill_events:
            lines.extend(["", "  ═══════════════════════════════════════"])
            lines.extend(["  Fill Events:"])
            for i, fill in enumerate(self.fill_events, 1):
                lines.append(
                    f"    #{i} [{fill['datetime']}] {fill['trade_type']} {fill['order_type']}: "
                    f"{fill['amount']:.6f} @ {fill['price']:.6f} = {fill['quote_volume']:.4f}"
                )
        else:
            lines.extend(["", "  No fills yet."])

        lines.append("")
        return "\n".join(lines)
