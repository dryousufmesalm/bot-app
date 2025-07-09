from typing import TYPE_CHECKING, List, Dict
from sqlmodel import Field, SQLModel, Relationship, Column
from sqlalchemy import JSON

import datetime
if TYPE_CHECKING:
    from .ah_cycles_orders import AhCyclesOrders


class AHCycle(SQLModel, table=True):
    __tablename__ = "ah_cycles"
    id: int | None = Field(default=None, primary_key=True)
    orders: list["AhCyclesOrders"] = Relationship(back_populates="cycle")
    lower_bound: int
    upper_bound: int
    is_pending: bool
    closing_method:  Dict = Field(default_factory=dict, sa_column=Column(JSON))
    opened_by:      Dict = Field(default_factory=dict, sa_column=Column(JSON))
    is_closed: bool
    lot_idx: int
    status: str
    total_volume: int
    total_profit: int
    zone_index: int
    bot: str
    account: str
    symbol: str
    initial: List[int] = Field(default_factory=list, sa_column=Column(JSON))
    hedge: List[int] = Field(default_factory=list, sa_column=Column(JSON))
    pending: List[int] = Field(default_factory=list, sa_column=Column(JSON))
    closed: List[int] = Field(default_factory=list, sa_column=Column(JSON))
    recovery: List[int] = Field(default_factory=list, sa_column=Column(JSON))
    max_recovery: List[int] = Field(
        default_factory=list, sa_column=Column(JSON))
    cycle_type: str | None

    class Config:
        arbitrary_types_allowed = True
