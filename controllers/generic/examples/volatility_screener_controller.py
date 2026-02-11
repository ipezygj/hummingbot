import pandas as pd
import pandas_ta as ta

from pydantic import Field
from typing import Dict, List

from hummingbot.client.ui.interface_utils import format_df_for_printout
from hummingbot.core.data_type.common import MarketDict
from hummingbot.data_feed.candles_feed.candles_factory import CandlesFactory
from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
from hummingbot.strategy_v2.controllers import ControllerBase, ControllerConfigBase
from hummingbot.strategy_v2.models.executor_actions import ExecutorAction


class VolatilityScreenerControllerConfig(ControllerConfigBase):
    controller_name: str = "examples.volatility_screener_controller"
    exchange: str = Field(default="binance_perpetual")
    trading_pairs: List[str] = Field(default=["BTC-USDT", "ETH-USDT", "BNB-USDT", "NEO-USDT"])
    intervals: List[str] = Field(default=["3m"])
    max_records: int = Field(default=1000)
    volatility_interval: int = Field(default=200)
    top_n: int = Field(default=20)
    report_interval: int = Field(default=60 * 60 * 6)  # 6 hours
    columns_to_show: List[str] = Field(default=["trading_pair", "bbands_width_pct", "bbands_percentage", "natr"])
    sort_values_by: List[str] = Field(default=["natr", "bbands_width_pct", "bbands_percentage"])

    def update_markets(self, markets: MarketDict) -> MarketDict:
        # For screener strategies, we don't typically need to add trading pairs to markets
        # since we're only consuming data (candles), not placing orders
        return markets


class VolatilityScreenerController(ControllerBase):
    def __init__(self, config: VolatilityScreenerControllerConfig, *args, **kwargs):
        super().__init__(config, *args, **kwargs)
        self.config = config
        self.last_time_reported = 0
        
        # Initialize candles for all trading pair/interval combinations
        combinations = [(trading_pair, interval) for trading_pair in config.trading_pairs for interval in config.intervals]
        self.candles = {f"{combination[0]}_{combination[1]}": None for combination in combinations}
        
        # Initialize candle feeds
        for combination in combinations:
            candle = CandlesFactory.get_candle(
                CandlesConfig(connector=config.exchange, trading_pair=combination[0], interval=combination[1], max_records=self.config.max_records)
            )
            candle.start()
            self.candles[f"{combination[0]}_{combination[1]}"] = candle

    async def update_processed_data(self):
        current_time = self.market_data_provider.time()
        
        # Check if all candles are ready
        all_ready = all(candle.ready for candle in self.candles.values())
        
        volatility_data = {
            "all_candles_ready": all_ready,
            "candles_status": {}
        }
        
        # Get status of each candle feed
        for trading_pair_interval, candle in self.candles.items():
            volatility_data["candles_status"][trading_pair_interval] = {
                "ready": candle.ready,
                "missing_records": candle._candles.maxlen - len(candle._candles) if not candle.ready else 0
            }
        
        # Generate report if conditions are met
        if all_ready and (current_time - self.last_time_reported > self.config.report_interval):
            self.last_time_reported = current_time
            try:
                market_analysis = self.get_market_analysis()
                formatted_analysis = self.get_formatted_market_analysis()
                
                volatility_data.update({
                    "market_analysis": market_analysis,
                    "formatted_analysis": formatted_analysis,
                    "last_report_time": current_time
                })
                
                # Notify the main application
                if hasattr(self, 'notify_hb_app'):
                    self.notify_hb_app(formatted_analysis)
                else:
                    self.logger().info("Volatility Report:\n" + formatted_analysis)
                    
            except Exception as e:
                self.logger().error(f"Error generating market analysis: {e}")
                volatility_data["analysis_error"] = str(e)
        
        self.processed_data = volatility_data

    def determine_executor_actions(self) -> list[ExecutorAction]:
        # This controller is for screening/monitoring only, no trading actions
        return []

    def format_status(self) -> str:
        if not hasattr(self, 'processed_data') or not self.processed_data:
            return "Volatility Screener initializing..."
        
        if self.processed_data["all_candles_ready"]:
            lines = []
            lines.extend(["", "VOLATILITY SCREENER"])
            lines.extend(["=" * 60])
            lines.extend([f"Configuration:"])
            lines.extend([f"  Volatility Interval: {self.config.volatility_interval}"])
            lines.extend([f"  Report Interval: {self.config.report_interval / 3600:.1f} hours"])
            lines.extend([f"  Top N: {self.config.top_n}"])
            lines.extend(["", "Volatility Metrics:", ""])
            
            try:
                formatted_analysis = self.get_formatted_market_analysis()
                lines.extend([formatted_analysis])
            except Exception as e:
                lines.extend([f"Error generating analysis: {e}"])
            
            # Show time until next report
            if self.last_time_reported > 0:
                time_until_next = max(0, self.last_time_reported + self.config.report_interval - self.market_data_provider.time())
                lines.extend([f"\nNext report in: {time_until_next / 3600:.1f} hours"])
            
            return "\n".join(lines)
        else:
            lines = ["Candles not ready yet!"]
            for trading_pair_interval, status in self.processed_data["candles_status"].items():
                if not status["ready"]:
                    lines.append(f"  {trading_pair_interval}: Missing {status['missing_records']} records")
                else:
                    lines.append(f"  {trading_pair_interval}: Ready ✅")
            return "\n".join(lines)

    def get_formatted_market_analysis(self):
        volatility_metrics_df = self.get_market_analysis()
        sorted_df = volatility_metrics_df[self.config.columns_to_show].sort_values(
            by=self.config.sort_values_by, ascending=False
        ).head(self.config.top_n)
        
        return format_df_for_printout(sorted_df, table_format="psql")

    def get_market_analysis(self):
        market_metrics = {}
        
        for trading_pair_interval, candle in self.candles.items():
            df = candle.candles_df.copy()
            df["trading_pair"] = trading_pair_interval.split("_")[0]
            df["interval"] = trading_pair_interval.split("_")[1]
            
            # Adding volatility metrics
            df["volatility"] = df["close"].pct_change().rolling(self.config.volatility_interval).std()
            df["volatility_pct"] = df["volatility"] / df["close"]
            df["volatility_pct_mean"] = df["volatility_pct"].rolling(self.config.volatility_interval).mean()

            # Adding bbands metrics
            df.ta.bbands(length=self.config.volatility_interval, append=True)
            df["bbands_width_pct"] = df[f"BBB_{self.config.volatility_interval}_2.0"]
            df["bbands_width_pct_mean"] = df["bbands_width_pct"].rolling(self.config.volatility_interval).mean()
            df["bbands_percentage"] = df[f"BBP_{self.config.volatility_interval}_2.0"]
            df["natr"] = ta.natr(df["high"], df["low"], df["close"], length=self.config.volatility_interval)
            
            market_metrics[trading_pair_interval] = df.iloc[-1]
        
        volatility_metrics_df = pd.DataFrame(market_metrics).T
        return volatility_metrics_df

    async def stop(self):
        """Clean shutdown of all candle feeds"""
        for candle in self.candles.values():
            if candle:
                candle.stop()
        await super().stop()