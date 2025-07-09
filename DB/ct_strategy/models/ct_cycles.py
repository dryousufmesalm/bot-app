from sqlmodel import Field, SQLModel, Relationship
from typing import TYPE_CHECKING, Dict, List
if TYPE_CHECKING:
    from .ct_cycles_orders import CtCyclesOrders
from sqlmodel import Column, JSON


class CTCycle(SQLModel, table=True):
    __tablename__ = "ct_cycles"
    id: int | None = Field(default=None, primary_key=True)
    orders: List["CtCyclesOrders"] = Relationship(back_populates="cycle")
    lower_bound: float
    upper_bound: float
    is_pending: bool
    is_closed: bool
    closing_method:  Dict = Field(default_factory=dict, sa_column=Column(JSON))
    opened_by: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    lot_idx: int
    status: str
    total_volume: float
    total_profit: float
    zone_index: int
    bot: str
    account: str
    symbol: str
    threshold_lower: float
    threshold_upper: float
    base_threshold_lower: float
    base_threshold_upper: float
    initial: List[int] = Field(default_factory=list, sa_column=Column(JSON))
    hedge: List[int] = Field(default_factory=list, sa_column=Column(JSON))
    pending: List[int] = Field(default_factory=list, sa_column=Column(JSON))
    closed: List[int] = Field(default_factory=list, sa_column=Column(JSON))
    recovery: List[int] = Field(default_factory=list, sa_column=Column(JSON))
    threshold: List[int] = Field(default_factory=list, sa_column=Column(JSON))
    cycle_type: str | None
    done_price_levels: List[Dict] = Field(
        default_factory=list, sa_column=Column(JSON))
    current_direction: str = Field(default="BUY")
    initial_threshold_price: float = Field(default=0.0)
    direction_switched: bool = Field(default=False)
    next_order_index: int = Field(default=0)

    class Config:
        arbitrary_types_allowed = True
