from typing import List
from pydantic import Field

from hummingbot.core.data_type.common import MarketDict
from hummingbot.strategy_v2.controllers import ControllerBase, ControllerConfigBase
from hummingbot.strategy_v2.models.executor_actions import ExecutorAction


class MarketStatusControllerConfig(ControllerConfigBase):
    controller_name: str = "examples.market_status_controller"
    exchanges: list = Field(default=["binance_paper_trade", "kucoin_paper_trade", "gate_io_paper_trade"])
    trading_pairs: list = Field(default=["ETH-USDT", "BTC-USDT", "POL-USDT", "AVAX-USDT", "WLD-USDT", "DOGE-USDT", "SHIB-USDT", "XRP-USDT", "SOL-USDT"])

    def update_markets(self, markets: MarketDict) -> MarketDict:
        # Add all combinations of exchanges and trading pairs
        for exchange in self.exchanges:
            markets[exchange] = markets.get(exchange, set()) | set(self.trading_pairs)
        return markets


class MarketStatusController(ControllerBase):
    def __init__(self, config: MarketStatusControllerConfig, *args, **kwargs):
        super().__init__(config, *args, **kwargs)
        self.config = config

    async def update_processed_data(self):
        market_status_data = {}
        if self.ready_to_trade:
            try:
                market_status_df = self.get_market_status_df_with_depth()
                market_status_data = {
                    "market_status_df": market_status_df,
                    "ready_to_trade": True
                }
            except Exception as e:
                self.logger().error(f"Error getting market status: {e}")
                market_status_data = {
                    "error": str(e),
                    "ready_to_trade": False
                }
        else:
            market_status_data = {"ready_to_trade": False}
        
        self.processed_data = market_status_data

    def determine_executor_actions(self) -> list[ExecutorAction]:
        # This controller is for monitoring only, no trading actions
        return []

    def to_format_status(self) -> List[str]:
        if not self.ready_to_trade:
            return ["Market connectors are not ready."]
        
        lines = []
        lines.extend(["", "  Market Status Data Frame:"])
        
        try:
            market_status_df = self.get_market_status_df_with_depth()
            lines.extend(["    " + line for line in market_status_df.to_string(index=False).split("\n")])
        except Exception as e:
            lines.extend([f"    Error: {str(e)}"])
        
        return lines

    def get_market_status_df_with_depth(self):
        market_status_df = self.market_status_data_frame(self.get_market_trading_pair_tuples())
        market_status_df["Exchange"] = market_status_df.apply(lambda x: x["Exchange"].strip("PaperTrade") + "paper_trade", axis=1)
        market_status_df["Volume (+1%)"] = market_status_df.apply(lambda x: self.get_volume_for_percentage_from_mid_price(x, 0.01), axis=1)
        market_status_df["Volume (-1%)"] = market_status_df.apply(lambda x: self.get_volume_for_percentage_from_mid_price(x, -0.01), axis=1)
        market_status_df.sort_values(by=["Market"], inplace=True)
        return market_status_df

    def get_volume_for_percentage_from_mid_price(self, row, percentage):
        price = row["Mid Price"] * (1 + percentage)
        is_buy = percentage > 0
        result = self.connectors[row["Exchange"]].get_volume_for_price(row["Market"], is_buy, price)
        return result.result_volume