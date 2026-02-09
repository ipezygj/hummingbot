import logging
from decimal import Decimal
from typing import Dict, Optional, Union

from hummingbot.connector.gateway.gateway_lp import AMMPoolInfo, CLMMPoolInfo
from hummingbot.core.data_type.common import TradeType
from hummingbot.core.data_type.trade_fee import AddedToCostTradeFee
from hummingbot.logger import HummingbotLogger
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase
from hummingbot.strategy_v2.executors.executor_base import ExecutorBase
from hummingbot.strategy_v2.executors.lp_executor.data_types import LPExecutorConfig, LPExecutorState, LPExecutorStates
from hummingbot.strategy_v2.models.base import RunnableStatus
from hummingbot.strategy_v2.models.executors import CloseType, TrackedOrder


class LPExecutor(ExecutorBase):
    """
    Executor for a single LP position lifecycle.

    - Opens position on start (direct await, no events)
    - Monitors and reports state (IN_RANGE, OUT_OF_RANGE)
    - Tracks out_of_range_since timestamp for rebalancing decisions
    - Closes position when stopped (unless keep_position=True)

    Rebalancing is handled by Controller (stops this executor, creates new one).

    Note: This executor directly awaits gateway operations instead of using
    the fire-and-forget pattern with events. This makes it work in environments
    without the Clock/tick mechanism (like hummingbot-api).
    """
    _logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(
        self,
        strategy: ScriptStrategyBase,
        config: LPExecutorConfig,
        update_interval: float = 1.0,
        max_retries: int = 3
    ):
        # Extract connector names from config for ExecutorBase
        connectors = [config.market.connector_name]
        super().__init__(strategy, connectors, config, update_interval)
        self.config: LPExecutorConfig = config
        self.lp_position_state = LPExecutorState()
        self._pool_info: Optional[Union[CLMMPoolInfo, AMMPoolInfo]] = None
        self._current_retries = 0
        self._max_retries = max_retries

    async def on_start(self):
        """Start executor - will create position in first control_task"""
        await super().on_start()

    async def control_task(self):
        """Main control loop - simple state machine with direct await operations"""
        current_time = self._strategy.current_timestamp

        # Fetch pool info (always needed for state updates)
        await self.update_pool_info()

        # Fetch position info when position exists to get current amounts
        if self.lp_position_state.position_address:
            await self._update_position_info()

        current_price = Decimal(str(self._pool_info.price)) if self._pool_info else None
        self.lp_position_state.update_state(current_price, current_time)

        match self.lp_position_state.state:
            case LPExecutorStates.NOT_ACTIVE:
                # Start opening position
                self.lp_position_state.state = LPExecutorStates.OPENING
                await self._create_position()

            case LPExecutorStates.OPENING:
                # Position creation in progress or retrying after failure
                await self._create_position()

            case LPExecutorStates.CLOSING:
                # Position close in progress or retrying after failure
                await self._close_position()

            case LPExecutorStates.IN_RANGE:
                # Position active and in range - just monitor
                pass

            case LPExecutorStates.OUT_OF_RANGE:
                # Position active but out of range
                # Auto-close if configured and duration exceeded
                if self.config.out_of_range_seconds_close is not None:
                    out_of_range_seconds = self.lp_position_state.get_out_of_range_seconds(current_time)
                    if out_of_range_seconds and out_of_range_seconds >= self.config.out_of_range_seconds_close:
                        self.logger().info(
                            f"Position out of range for {out_of_range_seconds}s >= {self.config.out_of_range_seconds_close}s, closing"
                        )
                        self.close_type = CloseType.EARLY_STOP
                        self.lp_position_state.state = LPExecutorStates.CLOSING

            case LPExecutorStates.COMPLETE:
                # Position closed - close_type already set by early_stop()
                self.stop()

    async def _update_position_info(self):
        """Fetch current position info from connector to update amounts and fees"""
        if not self.lp_position_state.position_address:
            return

        connector = self.connectors.get(self.config.market.connector_name)
        if connector is None:
            return

        try:
            position_info = await connector.get_position_info(
                trading_pair=self.config.market.trading_pair,
                position_address=self.lp_position_state.position_address
            )

            if position_info:
                # Update amounts and fees from live position data
                self.lp_position_state.base_amount = Decimal(str(position_info.base_token_amount))
                self.lp_position_state.quote_amount = Decimal(str(position_info.quote_token_amount))
                self.lp_position_state.base_fee = Decimal(str(position_info.base_fee_amount))
                self.lp_position_state.quote_fee = Decimal(str(position_info.quote_fee_amount))
                # Update price bounds from actual position (may differ slightly from config)
                self.lp_position_state.lower_price = Decimal(str(position_info.lower_price))
                self.lp_position_state.upper_price = Decimal(str(position_info.upper_price))
            else:
                self.logger().warning(f"get_position_info returned None for {self.lp_position_state.position_address}")
        except Exception as e:
            # Gateway returns HttpError with message patterns:
            # - "Position closed: {addr}" (404) - position was closed on-chain
            # - "Position not found: {addr}" (404) - position never existed
            # - "Position not found or closed: {addr}" (404) - combined check
            error_msg = str(e).lower()
            if "position closed" in error_msg:
                self.logger().info(
                    f"Position {self.lp_position_state.position_address} confirmed closed on-chain"
                )
                self.lp_position_state.state = LPExecutorStates.COMPLETE
                self.lp_position_state.active_close_order = None
                return
            elif "not found" in error_msg:
                self.logger().error(
                    f"Position {self.lp_position_state.position_address} not found - "
                    "position may never have been created. Check position tracking."
                )
                return
            self.logger().warning(f"Error fetching position info: {e}")

    async def _create_position(self):
        """
        Create position by directly awaiting the gateway operation.
        No events needed - result is available immediately after await.

        Uses the price bounds provided in config directly.
        """
        connector = self.connectors.get(self.config.market.connector_name)
        if connector is None:
            self.logger().error(f"Connector {self.config.market.connector_name} not found")
            return

        # Use config bounds directly
        lower_price = self.config.lower_price
        upper_price = self.config.upper_price
        mid_price = (lower_price + upper_price) / Decimal("2")

        self.logger().info(f"Creating position with bounds: [{lower_price:.6f} - {upper_price:.6f}]")

        # Generate order_id (same as add_liquidity does internally)
        order_id = connector.create_market_order_id(TradeType.RANGE, self.config.market.trading_pair)
        self.lp_position_state.active_open_order = TrackedOrder(order_id=order_id)

        try:
            # Directly await the async operation instead of fire-and-forget
            self.logger().info(f"Calling gateway to open position with order_id={order_id}")
            signature = await connector._clmm_add_liquidity(
                trade_type=TradeType.RANGE,
                order_id=order_id,
                trading_pair=self.config.market.trading_pair,
                price=float(mid_price),
                lower_price=float(lower_price),
                upper_price=float(upper_price),
                base_token_amount=float(self.config.base_amount),
                quote_token_amount=float(self.config.quote_amount),
                pool_address=self.config.pool_address,
                extra_params=self.config.extra_params,
            )
            # Note: If operation fails, connector now re-raises the exception
            # so it will be caught by the except block below with the actual error

            self.logger().info(f"Gateway returned signature={signature}")

            # Extract position_address from connector's metadata
            # Gateway response: {"signature": "...", "data": {"positionAddress": "...", ...}}
            metadata = connector._lp_orders_metadata.get(order_id, {})
            position_address = metadata.get("position_address", "")

            if not position_address:
                self.logger().error(f"No position_address in metadata: {metadata}")
                self._handle_create_failure(order_id, ValueError("Position creation failed - no position address in response"))
                return

            # Store position address and rent from transaction response
            self.lp_position_state.position_address = position_address
            self.lp_position_state.position_rent = metadata.get("position_rent", Decimal("0"))

            # Position is created - clear open order and reset retries
            self.lp_position_state.active_open_order = None
            self._current_retries = 0

            # Clean up connector metadata
            if order_id in connector._lp_orders_metadata:
                del connector._lp_orders_metadata[order_id]

            # Fetch full position info from chain to get actual amounts and bounds
            position_info = await connector.get_position_info(
                trading_pair=self.config.market.trading_pair,
                position_address=position_address
            )

            if position_info:
                self.lp_position_state.base_amount = Decimal(str(position_info.base_token_amount))
                self.lp_position_state.quote_amount = Decimal(str(position_info.quote_token_amount))
                self.lp_position_state.lower_price = Decimal(str(position_info.lower_price))
                self.lp_position_state.upper_price = Decimal(str(position_info.upper_price))
                self.lp_position_state.base_fee = Decimal(str(position_info.base_fee_amount))
                self.lp_position_state.quote_fee = Decimal(str(position_info.quote_fee_amount))

            self.logger().info(
                f"Position created: {position_address}, "
                f"rent: {self.lp_position_state.position_rent} SOL, "
                f"base: {self.lp_position_state.base_amount}, quote: {self.lp_position_state.quote_amount}, "
                f"bounds: [{self.lp_position_state.lower_price} - {self.lp_position_state.upper_price}]"
            )

            # Fetch pool info for current price
            await self.update_pool_info()
            current_price = Decimal(str(self._pool_info.price)) if self._pool_info else mid_price

            # Trigger event for database recording (lphistory command)
            connector._trigger_add_liquidity_event(
                order_id=order_id,
                exchange_order_id=signature,
                trading_pair=self.config.market.trading_pair,
                lower_price=self.lp_position_state.lower_price,
                upper_price=self.lp_position_state.upper_price,
                amount=self.lp_position_state.base_amount + self.lp_position_state.quote_amount / current_price,
                fee_tier=self.config.pool_address,
                creation_timestamp=self._strategy.current_timestamp,
                trade_fee=AddedToCostTradeFee(),
                position_address=position_address,
                base_amount=self.lp_position_state.base_amount,
                quote_amount=self.lp_position_state.quote_amount,
                mid_price=mid_price,
                position_rent=self.lp_position_state.position_rent,
            )

            # Update state immediately (don't wait for next tick)
            self.lp_position_state.update_state(current_price, self._strategy.current_timestamp)

        except Exception as e:
            self._handle_create_failure(order_id, e)

    def _handle_create_failure(self, order_id: str, error: Exception):
        """Handle position creation failure with retry logic."""
        self._current_retries += 1

        # Check if this is a timeout error (retryable)
        error_str = str(error)
        is_timeout = "TRANSACTION_TIMEOUT" in error_str

        if self._current_retries >= self._max_retries:
            self.logger().error(
                f"LP open failed after {self._max_retries} retries: {error}"
            )
            # Keep state as NOT_ACTIVE (prior state), just mark as failed and stop
            self.close_type = CloseType.FAILED
            self._status = RunnableStatus.SHUTTING_DOWN
            return

        if is_timeout:
            self.logger().warning(
                f"LP open timeout (retry {self._current_retries}/{self._max_retries}). "
                "Chain may be congested. Retrying..."
            )
        else:
            self.logger().warning(
                f"LP open failed (retry {self._current_retries}/{self._max_retries}): {error}"
            )

        # Clear open order to allow retry - state stays OPENING
        self.lp_position_state.active_open_order = None

    async def _close_position(self):
        """
        Close position by directly awaiting the gateway operation.
        No events needed - result is available immediately after await.
        """
        connector = self.connectors.get(self.config.market.connector_name)
        if connector is None:
            self.logger().error(f"Connector {self.config.market.connector_name} not found")
            return

        # Verify position still exists before trying to close (handles timeout-but-succeeded case)
        try:
            position_info = await connector.get_position_info(
                trading_pair=self.config.market.trading_pair,
                position_address=self.lp_position_state.position_address
            )
            if position_info is None:
                self.logger().info(
                    f"Position {self.lp_position_state.position_address} already closed - skipping close"
                )
                self.lp_position_state.state = LPExecutorStates.COMPLETE
                return
        except Exception as e:
            # Gateway returns HttpError with message patterns (see _update_position_info)
            error_msg = str(e).lower()
            if "position closed" in error_msg:
                self.logger().info(
                    f"Position {self.lp_position_state.position_address} already closed - skipping"
                )
                self.lp_position_state.state = LPExecutorStates.COMPLETE
                return
            elif "not found" in error_msg:
                self.logger().error(
                    f"Position {self.lp_position_state.position_address} not found - "
                    "marking complete to avoid retry loop"
                )
                self.lp_position_state.state = LPExecutorStates.COMPLETE
                return
            # Other errors - proceed with close attempt

        # Generate order_id for tracking
        order_id = connector.create_market_order_id(TradeType.RANGE, self.config.market.trading_pair)
        self.lp_position_state.active_close_order = TrackedOrder(order_id=order_id)

        try:
            # Directly await the async operation
            signature = await connector._clmm_close_position(
                trade_type=TradeType.RANGE,
                order_id=order_id,
                trading_pair=self.config.market.trading_pair,
                position_address=self.lp_position_state.position_address,
            )
            # Note: If operation fails, connector now re-raises the exception
            # so it will be caught by the except block below with the actual error

            self.logger().info(f"Position close confirmed, signature={signature}")

            # Success - extract close data from connector's metadata
            metadata = connector._lp_orders_metadata.get(order_id, {})
            self.lp_position_state.position_rent_refunded = metadata.get("position_rent_refunded", Decimal("0"))
            self.lp_position_state.base_amount = metadata.get("base_amount", Decimal("0"))
            self.lp_position_state.quote_amount = metadata.get("quote_amount", Decimal("0"))
            self.lp_position_state.base_fee = metadata.get("base_fee", Decimal("0"))
            self.lp_position_state.quote_fee = metadata.get("quote_fee", Decimal("0"))

            # Clean up connector metadata
            if order_id in connector._lp_orders_metadata:
                del connector._lp_orders_metadata[order_id]

            self.logger().info(
                f"Position closed: {self.lp_position_state.position_address}, "
                f"rent refunded: {self.lp_position_state.position_rent_refunded} SOL, "
                f"base: {self.lp_position_state.base_amount}, quote: {self.lp_position_state.quote_amount}, "
                f"fees: {self.lp_position_state.base_fee} base / {self.lp_position_state.quote_fee} quote"
            )

            # Trigger event for database recording (lphistory command)
            mid_price = (self.lp_position_state.lower_price + self.lp_position_state.upper_price) / Decimal("2")
            connector._trigger_remove_liquidity_event(
                order_id=order_id,
                exchange_order_id=signature,
                trading_pair=self.config.market.trading_pair,
                token_id="0",
                creation_timestamp=self._strategy.current_timestamp,
                trade_fee=AddedToCostTradeFee(),
                position_address=self.lp_position_state.position_address,
                lower_price=self.lp_position_state.lower_price,
                upper_price=self.lp_position_state.upper_price,
                mid_price=mid_price,
                base_amount=self.lp_position_state.base_amount,
                quote_amount=self.lp_position_state.quote_amount,
                base_fee=self.lp_position_state.base_fee,
                quote_fee=self.lp_position_state.quote_fee,
                position_rent_refunded=self.lp_position_state.position_rent_refunded,
            )

            self.lp_position_state.active_close_order = None
            self.lp_position_state.position_address = None
            self.lp_position_state.state = LPExecutorStates.COMPLETE
            self._current_retries = 0

        except Exception as e:
            self._handle_close_failure(order_id, e)

    def _handle_close_failure(self, order_id: str, error: Exception):
        """Handle position close failure with retry logic."""
        self._current_retries += 1

        # Check if this is a timeout error (retryable)
        error_str = str(error)
        is_timeout = "TRANSACTION_TIMEOUT" in error_str

        if self._current_retries >= self._max_retries:
            self.logger().error(
                f"LP close failed after {self._max_retries} retries: {error}"
            )
            # Keep prior state (IN_RANGE/OUT_OF_RANGE), just mark as failed and stop
            self.close_type = CloseType.FAILED
            self._status = RunnableStatus.SHUTTING_DOWN
            return

        if is_timeout:
            self.logger().warning(
                f"LP close timeout (retry {self._current_retries}/{self._max_retries}). "
                "Chain may be congested. Retrying..."
            )
        else:
            self.logger().warning(
                f"LP close failed (retry {self._current_retries}/{self._max_retries}): {error}"
            )

        # Clear active order - state stays CLOSING for retry in next control_task
        self.lp_position_state.active_close_order = None

    def early_stop(self, keep_position: bool = False):
        """Stop executor - transitions to CLOSING state, control_task handles the close"""
        self._status = RunnableStatus.SHUTTING_DOWN
        self.close_type = CloseType.POSITION_HOLD if keep_position or self.config.keep_position else CloseType.EARLY_STOP

        # Transition to CLOSING state if we have a position and not keeping it
        if not keep_position and not self.config.keep_position:
            if self.lp_position_state.state in [LPExecutorStates.IN_RANGE, LPExecutorStates.OUT_OF_RANGE]:
                self.lp_position_state.state = LPExecutorStates.CLOSING
            elif self.lp_position_state.state == LPExecutorStates.NOT_ACTIVE:
                # No position was created, just complete
                self.lp_position_state.state = LPExecutorStates.COMPLETE

    @property
    def filled_amount_quote(self) -> Decimal:
        """Returns total position value in quote currency (tokens + fees)"""
        if self._pool_info is None or self._pool_info.price == 0:
            return Decimal("0")
        current_price = Decimal(str(self._pool_info.price))

        # Total value = (base * price + quote) + (base_fee * price + quote_fee)
        token_value = (
            self.lp_position_state.base_amount * current_price +
            self.lp_position_state.quote_amount
        )
        fee_value = (
            self.lp_position_state.base_fee * current_price +
            self.lp_position_state.quote_fee
        )
        return token_value + fee_value

    def get_custom_info(self) -> Dict:
        """Report LP position state to controller"""
        price_float = float(self._pool_info.price) if self._pool_info else 0.0
        current_time = self._strategy.current_timestamp

        # Calculate total value in quote
        total_value = (
            float(self.lp_position_state.base_amount) * price_float +
            float(self.lp_position_state.quote_amount)
        )

        # Calculate fees earned in quote
        fees_earned = (
            float(self.lp_position_state.base_fee) * price_float +
            float(self.lp_position_state.quote_fee)
        )

        return {
            "side": self.config.side,
            "state": self.lp_position_state.state.value,
            "position_address": self.lp_position_state.position_address,
            "current_price": price_float if self._pool_info else None,
            "lower_price": float(self.lp_position_state.lower_price),
            "upper_price": float(self.lp_position_state.upper_price),
            "base_amount": float(self.lp_position_state.base_amount),
            "quote_amount": float(self.lp_position_state.quote_amount),
            "fees_earned_quote": fees_earned,
            "total_value_quote": total_value,
            "unrealized_pnl_quote": float(self.get_net_pnl_quote()),
            "position_rent": float(self.lp_position_state.position_rent),
            "position_rent_refunded": float(self.lp_position_state.position_rent_refunded),
            "out_of_range_seconds": self.lp_position_state.get_out_of_range_seconds(current_time),
        }

    # Required abstract methods from ExecutorBase
    async def validate_sufficient_balance(self):
        """Validate sufficient balance for LP position. ExecutorBase calls this in on_start()."""
        # LP connector handles balance validation during add_liquidity
        pass

    def get_net_pnl_quote(self) -> Decimal:
        """
        Returns net P&L in quote currency.

        P&L = (current_position_value + fees_earned) - initial_value

        Works for both open positions and closed positions (using final returned amounts).
        """
        if self._pool_info is None or self._pool_info.price == 0:
            return Decimal("0")
        current_price = Decimal(str(self._pool_info.price))

        # Initial value (from config)
        initial_value = (
            self.config.base_amount * current_price +
            self.config.quote_amount
        )

        # Current position value (tokens in position)
        current_value = (
            self.lp_position_state.base_amount * current_price +
            self.lp_position_state.quote_amount
        )

        # Fees earned (LP swap fees, not transaction costs)
        fees_earned = (
            self.lp_position_state.base_fee * current_price +
            self.lp_position_state.quote_fee
        )

        # P&L = current value + fees - initial value
        return current_value + fees_earned - initial_value

    def get_net_pnl_pct(self) -> Decimal:
        """Returns net P&L as percentage."""
        pnl_quote = self.get_net_pnl_quote()
        if pnl_quote == Decimal("0"):
            return Decimal("0")

        if self._pool_info is None or self._pool_info.price == 0:
            return Decimal("0")
        current_price = Decimal(str(self._pool_info.price))

        initial_value = (
            self.config.base_amount * current_price +
            self.config.quote_amount
        )

        if initial_value == Decimal("0"):
            return Decimal("0")

        return (pnl_quote / initial_value) * Decimal("100")

    def get_cum_fees_quote(self) -> Decimal:
        """
        Returns cumulative transaction costs in quote currency.

        NOTE: This is for transaction/gas costs, NOT LP fees earned.
        LP fees earned are included in get_net_pnl_quote() calculation.
        """
        return Decimal("0")

    async def update_pool_info(self):
        """Fetch and store current pool info"""
        connector = self.connectors.get(self.config.market.connector_name)
        if connector is None:
            return

        try:
            self._pool_info = await connector.get_pool_info_by_address(self.config.pool_address)
        except Exception as e:
            self.logger().warning(f"Error fetching pool info: {e}")
