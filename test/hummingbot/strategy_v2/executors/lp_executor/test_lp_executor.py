from decimal import Decimal
from test.isolated_asyncio_wrapper_test_case import IsolatedAsyncioWrapperTestCase
from test.logger_mixin_for_test import LoggerMixinForTest
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

from hummingbot.strategy.script_strategy_base import ScriptStrategyBase
from hummingbot.strategy_v2.executors.data_types import ConnectorPair
from hummingbot.strategy_v2.executors.lp_executor.data_types import LPExecutorConfig, LPExecutorStates
from hummingbot.strategy_v2.executors.lp_executor.lp_executor import LPExecutor
from hummingbot.strategy_v2.models.base import RunnableStatus
from hummingbot.strategy_v2.models.executors import CloseType


class TestLPExecutor(IsolatedAsyncioWrapperTestCase, LoggerMixinForTest):
    def setUp(self) -> None:
        super().setUp()
        self.strategy = self.create_mock_strategy()
        self.update_interval = 0.5

    @staticmethod
    def create_mock_strategy():
        market = MagicMock()
        market_info = MagicMock()
        market_info.market = market

        strategy = MagicMock(spec=ScriptStrategyBase)
        type(strategy).market_info = PropertyMock(return_value=market_info)
        type(strategy).trading_pair = PropertyMock(return_value="SOL-USDC")
        type(strategy).current_timestamp = PropertyMock(return_value=1234567890.0)

        connector = MagicMock()
        connector.create_market_order_id.return_value = "order-123"
        connector._lp_orders_metadata = {}

        strategy.connectors = {
            "meteora/clmm": connector,
        }
        strategy.notify_hb_app_with_timestamp = MagicMock()
        return strategy

    def get_default_config(self) -> LPExecutorConfig:
        return LPExecutorConfig(
            id="test-lp-1",
            timestamp=1234567890,
            market=ConnectorPair(connector_name="meteora/clmm", trading_pair="SOL-USDC"),
            pool_address="pool123",
            lower_price=Decimal("95"),
            upper_price=Decimal("105"),
            base_amount=Decimal("1.0"),
            quote_amount=Decimal("100"),
        )

    def get_executor(self, config: LPExecutorConfig = None) -> LPExecutor:
        if config is None:
            config = self.get_default_config()
        executor = LPExecutor(self.strategy, config, self.update_interval)
        self.set_loggers(loggers=[executor.logger()])
        return executor

    def test_executor_initialization(self):
        """Test executor initializes with correct state"""
        executor = self.get_executor()
        self.assertEqual(executor.config.market.connector_name, "meteora/clmm")
        self.assertEqual(executor.config.market.trading_pair, "SOL-USDC")
        self.assertEqual(executor.lp_position_state.state, LPExecutorStates.NOT_ACTIVE)
        self.assertIsNone(executor._pool_info)
        self.assertEqual(executor._max_retries, 10)
        self.assertEqual(executor._current_retries, 0)
        self.assertFalse(executor._max_retries_reached)

    def test_executor_custom_max_retries(self):
        """Test executor with custom max_retries"""
        config = self.get_default_config()
        executor = LPExecutor(self.strategy, config, self.update_interval, max_retries=5)
        self.assertEqual(executor._max_retries, 5)

    def test_logger(self):
        """Test logger returns properly"""
        executor = self.get_executor()
        logger = executor.logger()
        self.assertIsNotNone(logger)
        # Call again to test caching
        logger2 = executor.logger()
        self.assertEqual(logger, logger2)

    async def test_on_start(self):
        """Test on_start calls super"""
        executor = self.get_executor()
        with patch.object(executor.__class__.__bases__[0], 'on_start', new_callable=AsyncMock) as mock_super:
            await executor.on_start()
            mock_super.assert_called_once()

    def test_early_stop_with_keep_position_false(self):
        """Test early_stop transitions to CLOSING when position exists"""
        executor = self.get_executor()
        executor.lp_position_state.state = LPExecutorStates.IN_RANGE
        executor.lp_position_state.position_address = "pos123"

        executor.early_stop(keep_position=False)

        self.assertEqual(executor._status, RunnableStatus.SHUTTING_DOWN)
        self.assertEqual(executor.close_type, CloseType.EARLY_STOP)
        self.assertEqual(executor.lp_position_state.state, LPExecutorStates.CLOSING)

    def test_early_stop_with_keep_position_true(self):
        """Test early_stop with keep_position=True doesn't close position"""
        executor = self.get_executor()
        executor.lp_position_state.state = LPExecutorStates.IN_RANGE

        executor.early_stop(keep_position=True)

        self.assertEqual(executor._status, RunnableStatus.SHUTTING_DOWN)
        self.assertEqual(executor.close_type, CloseType.POSITION_HOLD)
        # State should not change to CLOSING
        self.assertEqual(executor.lp_position_state.state, LPExecutorStates.IN_RANGE)

    def test_early_stop_with_config_keep_position(self):
        """Test early_stop respects config.keep_position"""
        config = self.get_default_config()
        config.keep_position = True
        executor = self.get_executor(config)
        executor.lp_position_state.state = LPExecutorStates.IN_RANGE

        executor.early_stop()

        self.assertEqual(executor.close_type, CloseType.POSITION_HOLD)

    def test_early_stop_from_out_of_range(self):
        """Test early_stop from OUT_OF_RANGE state"""
        executor = self.get_executor()
        executor.lp_position_state.state = LPExecutorStates.OUT_OF_RANGE
        executor.lp_position_state.position_address = "pos123"

        executor.early_stop()

        self.assertEqual(executor.lp_position_state.state, LPExecutorStates.CLOSING)

    def test_early_stop_from_not_active(self):
        """Test early_stop from NOT_ACTIVE goes to COMPLETE"""
        executor = self.get_executor()
        executor.lp_position_state.state = LPExecutorStates.NOT_ACTIVE

        executor.early_stop()

        self.assertEqual(executor.lp_position_state.state, LPExecutorStates.COMPLETE)

    def test_filled_amount_quote_no_pool_info(self):
        """Test filled_amount_quote returns 0 when no pool info"""
        executor = self.get_executor()
        self.assertEqual(executor.filled_amount_quote, Decimal("0"))

    def test_filled_amount_quote_with_pool_info(self):
        """Test filled_amount_quote calculates correctly"""
        executor = self.get_executor()
        executor._pool_info = MagicMock()
        executor._pool_info.price = 100.0
        executor.lp_position_state.base_amount = Decimal("2.0")
        executor.lp_position_state.quote_amount = Decimal("50")
        executor.lp_position_state.base_fee = Decimal("0.01")
        executor.lp_position_state.quote_fee = Decimal("1.0")

        # Total = (2.0 * 100 + 50) + (0.01 * 100 + 1.0) = 250 + 2 = 252
        self.assertEqual(executor.filled_amount_quote, Decimal("252"))

    def test_get_net_pnl_quote_no_pool_info(self):
        """Test get_net_pnl_quote returns 0 when no pool info"""
        executor = self.get_executor()
        self.assertEqual(executor.get_net_pnl_quote(), Decimal("0"))

    def test_get_net_pnl_quote_with_values(self):
        """Test get_net_pnl_quote calculates correctly"""
        executor = self.get_executor()
        executor._pool_info = MagicMock()
        executor._pool_info.price = 100.0

        # Config: base=1.0, quote=100 -> initial = 1.0*100 + 100 = 200
        # Current: base=1.1, quote=90, base_fee=0.01, quote_fee=1
        executor.lp_position_state.base_amount = Decimal("1.1")
        executor.lp_position_state.quote_amount = Decimal("90")
        executor.lp_position_state.base_fee = Decimal("0.01")
        executor.lp_position_state.quote_fee = Decimal("1.0")

        # Current = 1.1*100 + 90 = 200
        # Fees = 0.01*100 + 1 = 2
        # PnL = 200 + 2 - 200 = 2
        self.assertEqual(executor.get_net_pnl_quote(), Decimal("2"))

    def test_get_net_pnl_pct_zero_pnl(self):
        """Test get_net_pnl_pct returns 0 when pnl is 0"""
        executor = self.get_executor()
        self.assertEqual(executor.get_net_pnl_pct(), Decimal("0"))

    def test_get_net_pnl_pct_with_values(self):
        """Test get_net_pnl_pct calculates correctly"""
        executor = self.get_executor()
        executor._pool_info = MagicMock()
        executor._pool_info.price = 100.0

        executor.lp_position_state.base_amount = Decimal("1.1")
        executor.lp_position_state.quote_amount = Decimal("90")
        executor.lp_position_state.base_fee = Decimal("0.01")
        executor.lp_position_state.quote_fee = Decimal("1.0")

        # Initial = 200, PnL = 2
        # Pct = (2 / 200) * 100 = 1%
        self.assertEqual(executor.get_net_pnl_pct(), Decimal("1"))

    def test_get_cum_fees_quote(self):
        """Test get_cum_fees_quote returns 0 (tx fees not tracked)"""
        executor = self.get_executor()
        self.assertEqual(executor.get_cum_fees_quote(), Decimal("0"))

    async def test_validate_sufficient_balance(self):
        """Test validate_sufficient_balance passes (handled by connector)"""
        executor = self.get_executor()
        # Should not raise
        await executor.validate_sufficient_balance()

    def test_get_custom_info_no_pool_info(self):
        """Test get_custom_info without pool info"""
        executor = self.get_executor()
        info = executor.get_custom_info()

        self.assertEqual(info["side"], 0)
        self.assertEqual(info["state"], "NOT_ACTIVE")
        self.assertIsNone(info["position_address"])
        self.assertIsNone(info["current_price"])
        self.assertEqual(info["lower_price"], 0.0)
        self.assertEqual(info["upper_price"], 0.0)
        self.assertFalse(info["max_retries_reached"])

    def test_get_custom_info_with_position(self):
        """Test get_custom_info with position"""
        executor = self.get_executor()
        executor._pool_info = MagicMock()
        executor._pool_info.price = 100.0
        executor.lp_position_state.state = LPExecutorStates.IN_RANGE
        executor.lp_position_state.position_address = "pos123"
        executor.lp_position_state.lower_price = Decimal("95")
        executor.lp_position_state.upper_price = Decimal("105")
        executor.lp_position_state.base_amount = Decimal("1.0")
        executor.lp_position_state.quote_amount = Decimal("100")
        executor.lp_position_state.base_fee = Decimal("0.01")
        executor.lp_position_state.quote_fee = Decimal("1.0")
        executor.lp_position_state.position_rent = Decimal("0.002")

        info = executor.get_custom_info()

        self.assertEqual(info["side"], 0)
        self.assertEqual(info["state"], "IN_RANGE")
        self.assertEqual(info["position_address"], "pos123")
        self.assertEqual(info["current_price"], 100.0)
        self.assertEqual(info["lower_price"], 95.0)
        self.assertEqual(info["upper_price"], 105.0)
        self.assertEqual(info["base_amount"], 1.0)
        self.assertEqual(info["quote_amount"], 100.0)
        self.assertEqual(info["position_rent"], 0.002)

    async def test_update_pool_info_success(self):
        """Test update_pool_info fetches pool info"""
        executor = self.get_executor()
        mock_pool_info = MagicMock()
        mock_pool_info.address = "pool123"
        mock_pool_info.price = 100.0

        connector = self.strategy.connectors["meteora/clmm"]
        connector.get_pool_info_by_address = AsyncMock(return_value=mock_pool_info)

        await executor.update_pool_info()

        self.assertEqual(executor._pool_info, mock_pool_info)
        connector.get_pool_info_by_address.assert_called_once_with("pool123")

    async def test_update_pool_info_error(self):
        """Test update_pool_info handles errors gracefully"""
        executor = self.get_executor()
        connector = self.strategy.connectors["meteora/clmm"]
        connector.get_pool_info_by_address = AsyncMock(side_effect=Exception("Network error"))

        await executor.update_pool_info()

        self.assertIsNone(executor._pool_info)

    async def test_update_pool_info_no_connector(self):
        """Test update_pool_info with missing connector"""
        executor = self.get_executor()
        self.strategy.connectors = {}

        await executor.update_pool_info()

        self.assertIsNone(executor._pool_info)

    def test_handle_create_failure_increment_retries(self):
        """Test _handle_create_failure increments retry counter"""
        executor = self.get_executor()
        executor._current_retries = 0

        executor._handle_create_failure(Exception("Test error"))

        self.assertEqual(executor._current_retries, 1)
        self.assertFalse(executor._max_retries_reached)

    def test_handle_create_failure_max_retries(self):
        """Test _handle_create_failure sets max_retries_reached"""
        executor = self.get_executor()
        executor._current_retries = 9  # Will become 10

        executor._handle_create_failure(Exception("Test error"))

        self.assertEqual(executor._current_retries, 10)
        self.assertTrue(executor._max_retries_reached)

    def test_handle_create_failure_timeout_message(self):
        """Test _handle_create_failure logs timeout appropriately"""
        executor = self.get_executor()
        executor._handle_create_failure(Exception("TRANSACTION_TIMEOUT: tx not confirmed"))
        self.assertEqual(executor._current_retries, 1)

    def test_handle_close_failure_increment_retries(self):
        """Test _handle_close_failure increments retry counter"""
        executor = self.get_executor()
        executor._current_retries = 0

        executor._handle_close_failure(Exception("Test error"))

        self.assertEqual(executor._current_retries, 1)
        self.assertFalse(executor._max_retries_reached)

    def test_handle_close_failure_max_retries(self):
        """Test _handle_close_failure sets max_retries_reached"""
        executor = self.get_executor()
        executor._current_retries = 9
        executor.lp_position_state.position_address = "pos123"

        executor._handle_close_failure(Exception("Test error"))

        self.assertTrue(executor._max_retries_reached)

    async def test_control_task_not_active_starts_opening(self):
        """Test control_task transitions from NOT_ACTIVE to OPENING"""
        executor = self.get_executor()
        executor._status = RunnableStatus.RUNNING

        mock_pool_info = MagicMock()
        mock_pool_info.price = 100.0
        connector = self.strategy.connectors["meteora/clmm"]
        connector.get_pool_info_by_address = AsyncMock(return_value=mock_pool_info)
        connector._clmm_add_liquidity = AsyncMock(side_effect=Exception("Test - prevent actual creation"))

        with patch.object(executor, '_create_position', new_callable=AsyncMock):
            await executor.control_task()

        self.assertEqual(executor.lp_position_state.state, LPExecutorStates.OPENING)

    async def test_control_task_complete_stops_executor(self):
        """Test control_task stops executor when COMPLETE"""
        executor = self.get_executor()
        executor._status = RunnableStatus.RUNNING
        executor.lp_position_state.state = LPExecutorStates.COMPLETE

        mock_pool_info = MagicMock()
        mock_pool_info.price = 100.0
        connector = self.strategy.connectors["meteora/clmm"]
        connector.get_pool_info_by_address = AsyncMock(return_value=mock_pool_info)

        with patch.object(executor, 'stop') as mock_stop:
            await executor.control_task()
            mock_stop.assert_called_once()

    async def test_control_task_out_of_range_auto_close(self):
        """Test control_task auto-closes when out of range too long"""
        config = self.get_default_config()
        config.auto_close_out_of_range_seconds = 60
        executor = self.get_executor(config)
        executor._status = RunnableStatus.RUNNING
        executor.lp_position_state.state = LPExecutorStates.OUT_OF_RANGE
        executor.lp_position_state.position_address = "pos123"
        executor.lp_position_state._out_of_range_since = 1234567800.0  # 90 seconds ago

        mock_pool_info = MagicMock()
        mock_pool_info.price = 110.0  # Out of range
        connector = self.strategy.connectors["meteora/clmm"]
        connector.get_pool_info_by_address = AsyncMock(return_value=mock_pool_info)
        connector.get_position_info = AsyncMock(return_value=None)

        await executor.control_task()

        self.assertEqual(executor.lp_position_state.state, LPExecutorStates.CLOSING)
        self.assertEqual(executor.close_type, CloseType.EARLY_STOP)

    async def test_update_position_info_success(self):
        """Test _update_position_info updates state from position data"""
        executor = self.get_executor()
        executor.lp_position_state.position_address = "pos123"

        mock_position = MagicMock()
        mock_position.base_token_amount = 1.5
        mock_position.quote_token_amount = 150.0
        mock_position.base_fee_amount = 0.02
        mock_position.quote_fee_amount = 2.0
        mock_position.lower_price = 94.0
        mock_position.upper_price = 106.0

        connector = self.strategy.connectors["meteora/clmm"]
        connector.get_position_info = AsyncMock(return_value=mock_position)

        await executor._update_position_info()

        self.assertEqual(executor.lp_position_state.base_amount, Decimal("1.5"))
        self.assertEqual(executor.lp_position_state.quote_amount, Decimal("150.0"))
        self.assertEqual(executor.lp_position_state.base_fee, Decimal("0.02"))
        self.assertEqual(executor.lp_position_state.quote_fee, Decimal("2.0"))

    async def test_update_position_info_position_closed(self):
        """Test _update_position_info handles closed position"""
        executor = self.get_executor()
        executor.lp_position_state.position_address = "pos123"

        connector = self.strategy.connectors["meteora/clmm"]
        connector.get_position_info = AsyncMock(side_effect=Exception("Position closed: pos123"))
        connector.create_market_order_id = MagicMock(return_value="order-123")
        connector._trigger_remove_liquidity_event = MagicMock()

        await executor._update_position_info()

        self.assertEqual(executor.lp_position_state.state, LPExecutorStates.COMPLETE)

    async def test_update_position_info_no_position_address(self):
        """Test _update_position_info returns early when no position"""
        executor = self.get_executor()
        executor.lp_position_state.position_address = None

        connector = self.strategy.connectors["meteora/clmm"]
        connector.get_position_info = AsyncMock()

        await executor._update_position_info()

        connector.get_position_info.assert_not_called()
