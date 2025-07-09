from sqlmodel import Field, SQLModel
from typing import Optional, List
from sqlmodel import Column, JSON


class CTConfig(SQLModel, table=True):
    """Configuration model for the CycleTrader strategy"""
    __tablename__ = "ct_config"

    id: int | None = Field(default=None, primary_key=True)
    symbol: str
    bot_id: int
    account_id: str

    # Basic settings
    enable_recovery: bool = Field(default=False)
    lot_sizes: List[float] = Field(
        default_factory=list, sa_column=Column(JSON))
    pips_step: int = Field(default=0)
    slippage: int = Field(default=3)
    sltp: str = Field(default="money")
    take_profit: float = Field(default=5)
    zones: List[int] = Field(default_factory=list, sa_column=Column(JSON))
    zone_forward: int = Field(default=1)
    zone_forward2: int = Field(default=1)
    max_cycles: int = Field(default=1)
    autotrade: bool = Field(default=False)
    autotrade_threshold: int = Field(default=0)
    hedges_numbers: int = Field(default=0)
    buy_and_sell_add_to_pnl: bool = Field(default=True)
    autotrade_pips_restriction: int = Field(default=100)

    # Auto candle close settings
    auto_candle_close: bool = Field(default=False)
    candle_timeframe: str = Field(default="H1")
    hedge_sl: int = Field(default=100)
    prevent_opposing_trades: bool = Field(default=True)

    class Config:
        arbitrary_types_allowed = True
