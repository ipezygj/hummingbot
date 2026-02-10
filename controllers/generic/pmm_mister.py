from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple, Union

from pydantic import Field, field_validator
from pydantic_core.core_schema import ValidationInfo

from hummingbot.core.data_type.common import MarketDict, OrderType, PositionMode, PriceType, TradeType
from hummingbot.strategy_v2.controllers.controller_base import ControllerBase, ControllerConfigBase
from hummingbot.strategy_v2.utils.common import parse_comma_separated_list, parse_enum_value
from hummingbot.strategy_v2.executors.data_types import ConnectorPair
from hummingbot.strategy_v2.executors.position_executor.data_types import PositionExecutorConfig, TripleBarrierConfig
from hummingbot.strategy_v2.models.executor_actions import CreateExecutorAction, ExecutorAction, StopExecutorAction


class PMMisterConfig(ControllerConfigBase):
    """
    Advanced PMM (Pure Market Making) controller with sophisticated position management.
    Features hanging executors, price distance requirements, and breakeven awareness.
    """
    controller_type: str = "generic"
    controller_name: str = "pmm_mister"
    connector_name: str = Field(default="binance")
    trading_pair: str = Field(default="BTC-FDUSD")
    portfolio_allocation: Decimal = Field(default=Decimal("0.05"), json_schema_extra={"is_updatable": True})
    target_base_pct: Decimal = Field(default=Decimal("0.2"), json_schema_extra={"is_updatable": True})
    min_base_pct: Decimal = Field(default=Decimal("0.1"), json_schema_extra={"is_updatable": True})
    max_base_pct: Decimal = Field(default=Decimal("0.4"), json_schema_extra={"is_updatable": True})
    buy_spreads: List[float] = Field(default="0.01,0.02", json_schema_extra={"is_updatable": True})
    sell_spreads: List[float] = Field(default="0.01,0.02", json_schema_extra={"is_updatable": True})
    buy_amounts_pct: Union[List[Decimal], None] = Field(default="1,2", json_schema_extra={"is_updatable": True})
    sell_amounts_pct: Union[List[Decimal], None] = Field(default="1,2", json_schema_extra={"is_updatable": True})
    executor_refresh_time: int = Field(default=30, json_schema_extra={"is_updatable": True})

    # Enhanced timing parameters
    buy_cooldown_time: int = Field(default=15, json_schema_extra={"is_updatable": True})
    sell_cooldown_time: int = Field(default=15, json_schema_extra={"is_updatable": True})
    buy_position_effectivization_time: int = Field(default=60, json_schema_extra={"is_updatable": True})
    sell_position_effectivization_time: int = Field(default=60, json_schema_extra={"is_updatable": True})

    # Price distance requirements
    min_buy_price_distance_pct: Decimal = Field(default=Decimal("0.005"), json_schema_extra={"is_updatable": True})
    min_sell_price_distance_pct: Decimal = Field(default=Decimal("0.005"), json_schema_extra={"is_updatable": True})

    leverage: int = Field(default=20, json_schema_extra={"is_updatable": True})
    position_mode: PositionMode = Field(default="HEDGE")
    take_profit: Optional[Decimal] = Field(default=Decimal("0.0001"), gt=0, json_schema_extra={"is_updatable": True})
    take_profit_order_type: Optional[OrderType] = Field(default="LIMIT_MAKER", json_schema_extra={"is_updatable": True})
    max_active_executors_by_level: Optional[int] = Field(default=1, json_schema_extra={"is_updatable": True})
    tick_mode: bool = Field(default=False, json_schema_extra={"is_updatable": True})
    position_profit_protection: bool = Field(default=False, json_schema_extra={"is_updatable": True})
    max_skew: Decimal = Field(default=Decimal("0.2"), json_schema_extra={"is_updatable": True})
    global_take_profit: Decimal = Field(default=Decimal("0.03"), json_schema_extra={"is_updatable": True})
    global_stop_loss: Decimal = Field(default=Decimal("0.05"), json_schema_extra={"is_updatable": True})

    @field_validator("take_profit", mode="before")
    @classmethod
    def validate_target(cls, v):
        if isinstance(v, str):
            if v == "":
                return None
            return Decimal(v)
        return v

    @field_validator('take_profit_order_type', mode="before")
    @classmethod
    def validate_order_type(cls, v) -> OrderType:
        if v is None:
            return OrderType.MARKET
        return parse_enum_value(OrderType, v, "take_profit_order_type")

    @field_validator('buy_spreads', 'sell_spreads', mode="before")
    @classmethod
    def parse_spreads(cls, v):
        return parse_comma_separated_list(v, "spreads")

    @field_validator('buy_amounts_pct', 'sell_amounts_pct', mode="before")
    @classmethod
    def parse_and_validate_amounts(cls, v, validation_info: ValidationInfo):
        field_name = validation_info.field_name
        if v is None or v == "":
            spread_field = field_name.replace('amounts_pct', 'spreads')
            return [1 for _ in validation_info.data[spread_field]]
        parsed = parse_comma_separated_list(v, field_name)
        if isinstance(parsed, list) and len(parsed) != len(validation_info.data[field_name.replace('amounts_pct', 'spreads')]):
            raise ValueError(
                f"The number of {field_name} must match the number of {field_name.replace('amounts_pct', 'spreads')}.")
        return parsed

    @field_validator('position_mode', mode="before")
    @classmethod
    def validate_position_mode(cls, v) -> PositionMode:
        return parse_enum_value(PositionMode, v, "position_mode")

    @property
    def triple_barrier_config(self) -> TripleBarrierConfig:
        return TripleBarrierConfig(
            take_profit=self.take_profit,
            trailing_stop=None,
            open_order_type=OrderType.LIMIT_MAKER,
            take_profit_order_type=self.take_profit_order_type,
            stop_loss_order_type=OrderType.MARKET,
            time_limit_order_type=OrderType.MARKET
        )

    def get_cooldown_time(self, trade_type: TradeType) -> int:
        """Get cooldown time for specific trade type"""
        return self.buy_cooldown_time if trade_type == TradeType.BUY else self.sell_cooldown_time

    def get_position_effectivization_time(self, trade_type: TradeType) -> int:
        """Get position effectivization time for specific trade type"""
        return self.buy_position_effectivization_time if trade_type == TradeType.BUY else self.sell_position_effectivization_time

    def update_parameters(self, trade_type: TradeType, new_spreads: Union[List[float], str],
                          new_amounts_pct: Optional[Union[List[int], str]] = None):
        spreads_field = 'buy_spreads' if trade_type == TradeType.BUY else 'sell_spreads'
        amounts_pct_field = 'buy_amounts_pct' if trade_type == TradeType.BUY else 'sell_amounts_pct'

        setattr(self, spreads_field, self.parse_spreads(new_spreads))
        if new_amounts_pct is not None:
            setattr(self, amounts_pct_field,
                    self.parse_and_validate_amounts(new_amounts_pct, self.__dict__, self.__fields__[amounts_pct_field]))
        else:
            setattr(self, amounts_pct_field, [1 for _ in getattr(self, spreads_field)])

    def get_spreads_and_amounts_in_quote(self, trade_type: TradeType) -> Tuple[List[float], List[float]]:
        buy_amounts_pct = getattr(self, 'buy_amounts_pct')
        sell_amounts_pct = getattr(self, 'sell_amounts_pct')

        total_pct = sum(buy_amounts_pct) + sum(sell_amounts_pct)

        if trade_type == TradeType.BUY:
            normalized_amounts_pct = [amt_pct / total_pct for amt_pct in buy_amounts_pct]
        else:
            normalized_amounts_pct = [amt_pct / total_pct for amt_pct in sell_amounts_pct]

        spreads = getattr(self, f'{trade_type.name.lower()}_spreads')
        return spreads, [amt_pct * self.total_amount_quote * self.portfolio_allocation for amt_pct in normalized_amounts_pct]

    def update_markets(self, markets: MarketDict) -> MarketDict:
        return markets.add_or_update(self.connector_name, self.trading_pair)


class PMMister(ControllerBase):
    """
    Advanced PMM (Pure Market Making) controller with sophisticated position management.
    Features:
    - Hanging executors system for better position control
    - Price distance requirements to prevent over-accumulation
    - Breakeven awareness for dynamic parameter adjustment
    - Separate buy/sell cooldown and effectivization times
    """

    def __init__(self, config: PMMisterConfig, *args, **kwargs):
        super().__init__(config, *args, **kwargs)
        self.config = config
        self.market_data_provider.initialize_rate_sources(
            [ConnectorPair(connector_name=config.connector_name, trading_pair=config.trading_pair)]
        )

    def determine_executor_actions(self) -> List[ExecutorAction]:
        """
        Determine actions based on the current state with advanced position management.
        """
        actions = []

        # Create new executors
        actions.extend(self.create_actions_proposal())

        # Stop executors (refresh and early stop)
        actions.extend(self.stop_actions_proposal())

        return actions

    def should_effectivize_executor(self, executor_info, current_time: int) -> bool:
        """Check if a hanging executor should be effectivized"""
        level_id = executor_info.custom_info.get("level_id", "")
        fill_time = executor_info.custom_info["open_order_last_update"]
        if not level_id or not fill_time:
            return False

        trade_type = self.get_trade_type_from_level_id(level_id)
        effectivization_time = self.config.get_position_effectivization_time(trade_type)

        return current_time - fill_time >= effectivization_time

    def create_actions_proposal(self) -> List[ExecutorAction]:
        """
        Create actions proposal with advanced position management logic.
        """
        create_actions = []

        # Get levels to execute with advanced logic
        levels_to_execute = self.get_levels_to_execute()

        # Check for global TP/SL first
        global_tpsl_action = self.check_global_take_profit_stop_loss()
        if global_tpsl_action:
            create_actions.append(global_tpsl_action)
            return create_actions
            
        # Pre-calculate spreads and amounts
        buy_spreads, buy_amounts_quote = self.config.get_spreads_and_amounts_in_quote(TradeType.BUY)
        sell_spreads, sell_amounts_quote = self.config.get_spreads_and_amounts_in_quote(TradeType.SELL)
        reference_price = Decimal(self.processed_data["reference_price"])
        
        # Use pre-calculated skew factors from processed_data
        buy_skew = self.processed_data["buy_skew"]
        sell_skew = self.processed_data["sell_skew"]

        # Create executors for each level
        for level_id in levels_to_execute:
            trade_type = self.get_trade_type_from_level_id(level_id)
            level = self.get_level_from_level_id(level_id)

            if trade_type == TradeType.BUY:
                spread_in_pct = Decimal(buy_spreads[level]) * Decimal(self.processed_data["spread_multiplier"])
                amount_quote = Decimal(buy_amounts_quote[level])
            else:
                spread_in_pct = Decimal(sell_spreads[level]) * Decimal(self.processed_data["spread_multiplier"])
                amount_quote = Decimal(sell_amounts_quote[level])

            # Apply skew to amount calculation
            skew = buy_skew if trade_type == TradeType.BUY else sell_skew
            
            # Calculate price and amount
            side_multiplier = Decimal("-1") if trade_type == TradeType.BUY else Decimal("1")
            price = reference_price * (Decimal("1") + side_multiplier * spread_in_pct)
            amount = self.market_data_provider.quantize_order_amount(
                self.config.connector_name,
                self.config.trading_pair,
                (amount_quote / price) * skew
            )

            if amount == Decimal("0"):
                self.logger().warning(f"The amount of the level {level_id} is 0. Skipping.")
                continue

            # Position profit protection: don't place sell orders below breakeven
            if self.config.position_profit_protection and trade_type == TradeType.SELL:
                breakeven_price = self.processed_data.get("breakeven_price")
                if breakeven_price is not None and breakeven_price > 0 and price < breakeven_price:
                    self.logger().info(f"Skipping {level_id}: sell price {price:.4f} < breakeven {breakeven_price:.4f}")
                    continue

            executor_config = self.get_executor_config(level_id, price, amount)
            if executor_config is not None:
                create_actions.append(CreateExecutorAction(
                    controller_id=self.config.id,
                    executor_config=executor_config
                ))

        return create_actions

    def get_levels_to_execute(self) -> List[str]:
        """
        Get levels to execute with advanced hanging executor logic using the analyzer.
        """
        current_time = self.market_data_provider.time()

        # Analyze all levels to understand executor states
        all_levels_analysis = self.analyze_all_levels()

        # Get working levels (active or hanging with cooldown)
        working_levels_ids = []

        for analysis in all_levels_analysis:
            level_id = analysis["level_id"]
            trade_type = self.get_trade_type_from_level_id(level_id)
            is_buy = level_id.startswith("buy")
            current_price = Decimal(self.processed_data["reference_price"])
            
            # Enhanced price distance logic - check both current price and existing order distances
            price_distance_violated = False
            if is_buy and analysis["max_price"]:
                # For buy orders, ensure they're not too close to current price
                distance_from_current = (current_price - analysis["max_price"]) / current_price
                if distance_from_current < self.config.min_buy_price_distance_pct:
                    price_distance_violated = True
            elif not is_buy and analysis["min_price"]:
                # For sell orders, ensure they're not too close to current price
                distance_from_current = (analysis["min_price"] - current_price) / current_price
                if distance_from_current < self.config.min_sell_price_distance_pct:
                    price_distance_violated = True
            
            # Level is working if:
            # - it has active executors not trading
            # - it has too many active executors for the level
            # - it has a cooldown that is still active
            # - price distance requirements are violated
            if (analysis["active_executors_not_trading"] or
                    analysis["total_active_executors"] >= self.config.max_active_executors_by_level or
                    (analysis["open_order_last_update"] and current_time - analysis["open_order_last_update"] < self.config.get_cooldown_time(trade_type)) or
                    price_distance_violated):
                working_levels_ids.append(level_id)
                continue
        return self.get_not_active_levels_ids(working_levels_ids)

    def stop_actions_proposal(self) -> List[ExecutorAction]:
        """
        Create stop actions with enhanced refresh logic.
        """
        stop_actions = []
        stop_actions.extend(self.executors_to_refresh())
        stop_actions.extend(self.process_hanging_executors())
        return stop_actions

    def executors_to_refresh(self) -> List[ExecutorAction]:
        """Refresh executors that have been active too long"""
        executors_to_refresh = self.filter_executors(
            executors=self.executors_info,
            filter_func=lambda x: (
                not x.is_trading and x.is_active and
                self.market_data_provider.time() - x.timestamp > self.config.executor_refresh_time
            )
        )
        return [StopExecutorAction(
            controller_id=self.config.id,
            keep_position=True,
            executor_id=executor.id
        ) for executor in executors_to_refresh]

    def process_hanging_executors(self) -> List[ExecutorAction]:
        """Process hanging executors and effectivize them when appropriate"""
        current_time = self.market_data_provider.time()
        actions = []

        # Find hanging executors that should be effectivized
        executors_to_effectivize = self.filter_executors(
            executors=self.executors_info,
            filter_func=lambda x: (
                x.is_trading and
                self.should_effectivize_executor(x, current_time)
            )
        )
        
        # Also check for hanging executors that are too far from current price
        current_price = Decimal(self.processed_data["reference_price"])
        executors_too_far = self.filter_executors(
            executors=self.executors_info,
            filter_func=lambda x: (
                x.is_trading and
                hasattr(x.config, 'entry_price') and
                self._is_executor_too_far_from_price(x, current_price)
            )
        )
        
        # Combine both lists, avoiding duplicates
        all_executors_to_stop = list(set(executors_to_effectivize + executors_too_far))
        
        return [StopExecutorAction(
            controller_id=self.config.id,
            keep_position=True,
            executor_id=executor.id
        ) for executor in all_executors_to_stop]

    async def update_processed_data(self):
        """
        Update processed data with enhanced breakeven tracking.
        """
        reference_price = self.market_data_provider.get_price_by_type(
            self.config.connector_name, self.config.trading_pair, PriceType.MidPrice
        )

        position_held = next((position for position in self.positions_held if
                              (position.trading_pair == self.config.trading_pair) &
                              (position.connector_name == self.config.connector_name)), None)

        target_position = self.config.total_amount_quote * self.config.target_base_pct

        if position_held is not None:
            position_amount = position_held.amount
            current_base_pct = position_held.amount_quote / self.config.total_amount_quote
            deviation = (target_position - position_held.amount_quote) / target_position
            unrealized_pnl_pct = position_held.unrealized_pnl_quote / position_held.amount_quote if position_held.amount_quote != 0 else Decimal(
                "0")
            breakeven_price = position_held.breakeven_price
        else:
            position_amount = 0
            current_base_pct = 0
            deviation = 1
            unrealized_pnl_pct = 0
            breakeven_price = None

        if self.config.tick_mode:
            spread_multiplier = (self.market_data_provider.get_trading_rules(self.config.connector_name,
                                                                             self.config.trading_pair).min_price_increment / reference_price)
        else:
            spread_multiplier = Decimal("1")

        # Calculate skew factors for position balancing
        min_pct = self.config.min_base_pct
        max_pct = self.config.max_base_pct
        
        if max_pct > min_pct:
            # Calculate skew factors (0.2 to 1.0) based on position deviation
            buy_skew = (max_pct - current_base_pct) / (max_pct - min_pct)
            sell_skew = (current_base_pct - min_pct) / (max_pct - min_pct)
            # Apply minimum skew to prevent orders from becoming too small
            buy_skew = max(min(buy_skew, Decimal("1.0")), self.config.max_skew)
            sell_skew = max(min(sell_skew, Decimal("1.0")), self.config.max_skew)
        else:
            buy_skew = sell_skew = Decimal("1.0")

        self.processed_data = {
            "reference_price": Decimal(reference_price),
            "spread_multiplier": spread_multiplier,
            "deviation": deviation,
            "current_base_pct": current_base_pct,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "position_amount": position_amount,
            "breakeven_price": breakeven_price,
            "buy_skew": buy_skew,
            "sell_skew": sell_skew
        }

    def get_executor_config(self, level_id: str, price: Decimal, amount: Decimal):
        """Get executor config for a given level"""
        trade_type = self.get_trade_type_from_level_id(level_id)
        return PositionExecutorConfig(
            timestamp=self.market_data_provider.time(),
            level_id=level_id,
            connector_name=self.config.connector_name,
            trading_pair=self.config.trading_pair,
            entry_price=price,
            amount=amount,
            triple_barrier_config=self.config.triple_barrier_config,
            leverage=self.config.leverage,
            side=trade_type,
        )

    def get_level_id_from_side(self, trade_type: TradeType, level: int) -> str:
        """Get level ID based on trade type and level"""
        return f"{trade_type.name.lower()}_{level}"

    def get_trade_type_from_level_id(self, level_id: str) -> TradeType:
        return TradeType.BUY if level_id.startswith("buy") else TradeType.SELL

    def get_level_from_level_id(self, level_id: str) -> int:
        return int(level_id.split('_')[1])

    def get_not_active_levels_ids(self, active_levels_ids: List[str]) -> List[str]:
        """Get levels that should be executed based on position constraints"""
        buy_ids_missing = [
            self.get_level_id_from_side(TradeType.BUY, level)
            for level in range(len(self.config.buy_spreads))
            if self.get_level_id_from_side(TradeType.BUY, level) not in active_levels_ids
        ]
        sell_ids_missing = [
            self.get_level_id_from_side(TradeType.SELL, level)
            for level in range(len(self.config.sell_spreads))
            if self.get_level_id_from_side(TradeType.SELL, level) not in active_levels_ids
        ]

        current_pct = self.processed_data["current_base_pct"]

        if current_pct < self.config.min_base_pct:
            return buy_ids_missing
        elif current_pct > self.config.max_base_pct:
            return sell_ids_missing

        # Position profit protection: filter based on breakeven
        if self.config.position_profit_protection:
            breakeven_price = self.processed_data.get("breakeven_price")
            reference_price = self.processed_data["reference_price"]
            target_pct = self.config.target_base_pct

            if breakeven_price is not None and breakeven_price > 0:
                if current_pct < target_pct and reference_price < breakeven_price:
                    return buy_ids_missing  # Don't sell at a loss when underweight
                elif current_pct > target_pct and reference_price > breakeven_price:
                    return sell_ids_missing  # Don't buy more when overweight and in profit

        return buy_ids_missing + sell_ids_missing

    def analyze_all_levels(self) -> List[Dict]:
        """Analyze executors for all levels."""
        level_ids: Set[str] = {e.custom_info.get("level_id") for e in self.executors_info if "level_id" in e.custom_info}
        return [self._analyze_by_level_id(level_id) for level_id in level_ids]

    def _analyze_by_level_id(self, level_id: str) -> Dict:
        """Analyze executors for a specific level ID."""
        filtered_executors = [e for e in self.executors_info if e.custom_info.get("level_id") == level_id and e.is_active]

        active_not_trading = [e for e in filtered_executors if e.is_active and not e.is_trading]
        active_trading = [e for e in filtered_executors if e.is_active and e.is_trading]

        open_order_last_updates = [
            e.custom_info.get("open_order_last_update") for e in filtered_executors
            if "open_order_last_update" in e.custom_info and e.custom_info["open_order_last_update"] is not None
        ]
        latest_open_order_update = max(open_order_last_updates) if open_order_last_updates else None

        prices = [e.config.entry_price for e in filtered_executors if hasattr(e.config, 'entry_price')]

        return {
            "level_id": level_id,
            "active_executors_not_trading": active_not_trading,
            "active_executors_trading": active_trading,
            "total_active_executors": len(active_not_trading) + len(active_trading),
            "open_order_last_update": latest_open_order_update,
            "min_price": min(prices) if prices else None,
            "max_price": max(prices) if prices else None,
        }

    def to_format_status(self) -> List[str]:
        """
        Enhanced status display with comprehensive information and visualizations.
        """
        from decimal import Decimal
        from itertools import zip_longest

        status = []

        # Get all required data
        base_pct = self.processed_data.get('current_base_pct', Decimal("0"))
        min_pct = self.config.min_base_pct
        max_pct = self.config.max_base_pct
        target_pct = self.config.target_base_pct
        pnl = self.processed_data.get('unrealized_pnl_pct', Decimal('0'))
        breakeven = self.processed_data.get('breakeven_price')
        current_price = self.processed_data['reference_price']
        buy_skew = self.processed_data.get('buy_skew', Decimal("1.0"))
        sell_skew = self.processed_data.get('sell_skew', Decimal("1.0"))

        # Layout dimensions
        outer_width = 100
        inner_width = outer_width - 4
        half_width = (inner_width) // 2 - 1
        bar_width = inner_width - 15

        # Header
        status.append("╒" + "═" * inner_width + "╕")
        
        header_line = (
            f"{self.config.connector_name}:{self.config.trading_pair}  "
            f"Price: {current_price:.2f}  "
            f"Alloc: {self.config.portfolio_allocation:.1%}  "
            f"Spread Mult: {self.processed_data['spread_multiplier']:.4f}"
        )
        status.append(f"│ {header_line:<{inner_width}} │")

        # Position and PnL sections
        status.append(f"├{'─' * half_width}┬{'─' * half_width}┤")
        status.append(f"│ {'POSITION STATUS':<{half_width - 2}} │ {'PROFIT & LOSS':<{half_width - 2}} │")
        status.append(f"├{'─' * half_width}┼{'─' * half_width}┤")

        # Position data
        skew = base_pct - target_pct
        skew_pct = skew / target_pct if target_pct != 0 else Decimal('0')
        position_info = [
            f"Current: {base_pct:.2%}",
            f"Target: {target_pct:.2%}",
            f"Min/Max: {min_pct:.2%}/{max_pct:.2%}",
            f"Skew: {skew_pct:+.2%} (max {self.config.max_skew:.2%})"
        ]

        # PnL data
        breakeven_str = f"{breakeven:.2f}" if breakeven is not None else "N/A"
        pnl_sign = "+" if pnl >= 0 else ""
        pnl_info = [
            f"Unrealized: {pnl_sign}{pnl:.2%}",
            f"Take Profit: {self.config.global_take_profit:.2%}",
            f"Stop Loss: {-self.config.global_stop_loss:.2%}",
            f"Breakeven: {breakeven_str}"
        ]

        # Display position and PnL info side by side
        for pos_line, pnl_line in zip_longest(position_info, pnl_info, fillvalue=""):
            status.append(f"│ {pos_line:<{half_width - 2}} │ {pnl_line:<{half_width - 2}} │")

        # Visualizations
        status.append(f"├{'─' * inner_width}┤")
        status.append(f"│ {'VISUALIZATIONS':<{inner_width}} │")
        status.append(f"├{'─' * inner_width}┤")

        # Position bar
        filled_width = int(base_pct * bar_width)
        min_pos = int(min_pct * bar_width)
        max_pos = int(max_pct * bar_width)
        target_pos = int(target_pct * bar_width)

        position_bar = ""
        for i in range(bar_width):
            if i == filled_width:
                position_bar += "◆"  # Current position
            elif i == min_pos:
                position_bar += "┃"  # Min threshold
            elif i == max_pos:
                position_bar += "┃"  # Max threshold
            elif i == target_pos:
                position_bar += "┇"  # Target threshold
            elif i < filled_width:
                position_bar += "█"  # Filled area
            else:
                position_bar += "░"  # Empty area

        status.append(f"│ Position: [{position_bar}] │")

        # Skew visualization
        skew_bar_width = bar_width
        center = skew_bar_width // 2
        skew_pos = center + int(skew_pct * center * 2)
        skew_pos = max(0, min(skew_bar_width - 1, skew_pos))

        skew_bar = ""
        for i in range(skew_bar_width):
            if i == center:
                skew_bar += "┃"  # Center line
            elif i == skew_pos:
                skew_bar += "⬤"  # Current skew
            else:
                skew_bar += "─"  # Empty line

        status.append(f"│ Skew:     [{skew_bar}] │")

        # PnL visualization
        pnl_bar_width = bar_width
        center = pnl_bar_width // 2
        max_range = max(abs(self.config.global_take_profit), abs(self.config.global_stop_loss), abs(pnl)) * Decimal("1.2")
        if max_range > 0:
            scale = (pnl_bar_width // 2) / max_range
            pnl_pos = center + int(pnl * scale)
            take_profit_pos = center + int(self.config.global_take_profit * scale)
            stop_loss_pos = center + int(-self.config.global_stop_loss * scale)

            pnl_pos = max(0, min(pnl_bar_width - 1, pnl_pos))
            take_profit_pos = max(0, min(pnl_bar_width - 1, take_profit_pos))
            stop_loss_pos = max(0, min(pnl_bar_width - 1, stop_loss_pos))

            pnl_bar = ""
            for i in range(pnl_bar_width):
                if i == center:
                    pnl_bar += "│"  # Center line
                elif i == pnl_pos:
                    pnl_bar += "⬤"  # Current PnL
                elif i == take_profit_pos:
                    pnl_bar += "T"  # Take profit line
                elif i == stop_loss_pos:
                    pnl_bar += "S"  # Stop loss line
                elif (pnl >= 0 and center <= i < pnl_pos) or (pnl < 0 and pnl_pos < i <= center):
                    pnl_bar += "█" if pnl >= 0 else "▓"
                else:
                    pnl_bar += "─"
        else:
            pnl_bar = "─" * pnl_bar_width

        status.append(f"│ PnL:      [{pnl_bar}] │")

        # Executors section
        status.append(f"├{'─' * half_width}┬{'─' * half_width}┤")
        status.append(f"│ {'EXECUTORS & SKEW':<{half_width - 2}} │ {'HANGING EXECUTORS':<{half_width - 2}} │")
        status.append(f"├{'─' * half_width}┼{'─' * half_width}┤")

        # Count active executors
        active_buy = sum(1 for info in self.executors_info
                         if info.is_active and self.get_trade_type_from_level_id(info.custom_info.get("level_id", "")) == TradeType.BUY)
        active_sell = sum(1 for info in self.executors_info
                          if info.is_active and self.get_trade_type_from_level_id(info.custom_info.get("level_id", "")) == TradeType.SELL)
        hanging_count = sum(1 for info in self.executors_info if info.is_active and info.is_trading)
        
        executor_info = [
            f"Active Buy: {active_buy} (skew: {buy_skew:.2f})",
            f"Active Sell: {active_sell} (skew: {sell_skew:.2f})",
            f"Total Active: {active_buy + active_sell}",
            f"Position Protection: {'ON' if self.config.position_profit_protection else 'OFF'}"
        ]

        # Hanging executor details
        current_time = self.market_data_provider.time()
        hanging_info = [f"Hanging Executors: {hanging_count}"]
        
        if hanging_count > 0:
            hanging_executors = [e for e in self.executors_info if e.is_active and e.is_trading][:3]  # Show top 3
            for executor in hanging_executors:
                level_id = executor.custom_info.get("level_id", "unknown")
                age = current_time - executor.timestamp
                trade_type = "BUY" if level_id.startswith("buy") else "SELL"
                hanging_info.append(f"{level_id} ({trade_type}): {int(age)}s")

        # Display executor info side by side
        for exec_line, hang_line in zip_longest(executor_info, hanging_info, fillvalue=""):
            status.append(f"│ {exec_line:<{half_width - 2}} │ {hang_line:<{half_width - 2}} │")

        # Bottom border
        status.append(f"╘{'═' * inner_width}╛")

        return status
    
    def _is_executor_too_far_from_price(self, executor_info, current_price: Decimal) -> bool:
        """Check if hanging executor is too far from current price and should be stopped"""
        if not hasattr(executor_info.config, 'entry_price'):
            return False
            
        entry_price = executor_info.config.entry_price
        level_id = executor_info.custom_info.get("level_id", "")
        
        if not level_id:
            return False
            
        is_buy = level_id.startswith("buy")
        
        # Calculate price distance
        if is_buy:
            # For buy orders, stop if they're above current price (inverted)
            if entry_price >= current_price:
                return True
            distance = (current_price - entry_price) / current_price
            max_distance = Decimal("0.05")  # 5% maximum distance
        else:
            # For sell orders, stop if they're below current price
            if entry_price <= current_price:
                return True
            distance = (entry_price - current_price) / current_price
            max_distance = Decimal("0.05")  # 5% maximum distance
            
        return distance > max_distance
    
    def check_global_take_profit_stop_loss(self) -> Optional[ExecutorAction]:
        """Check if global TP/SL should be triggered"""
        # Check if a global TP/SL executor already exists
        global_executor_exists = any(
            executor.is_active and
            executor.custom_info.get("level_id") == "global_tp_sl"
            for executor in self.executors_info
        )
        
        if global_executor_exists:
            return None
            
        current_base_pct = self.processed_data["current_base_pct"]
        unrealized_pnl_pct = self.processed_data.get("unrealized_pnl_pct", Decimal("0"))
        
        # Only trigger if we have a significant position and meet TP/SL criteria
        if (current_base_pct > self.config.target_base_pct and
            (unrealized_pnl_pct > self.config.global_take_profit or
             unrealized_pnl_pct < -self.config.global_stop_loss)):
            
            from hummingbot.strategy_v2.executors.order_executor.data_types import OrderExecutorConfig, ExecutionStrategy
            
            return CreateExecutorAction(
                controller_id=self.config.id,
                executor_config=OrderExecutorConfig(
                    timestamp=self.market_data_provider.time(),
                    connector_name=self.config.connector_name,
                    trading_pair=self.config.trading_pair,
                    side=TradeType.SELL,
                    amount=self.processed_data["position_amount"],
                    execution_strategy=ExecutionStrategy.MARKET,
                    price=self.processed_data["reference_price"],
                    level_id="global_tp_sl"
                )
            )
        return None
