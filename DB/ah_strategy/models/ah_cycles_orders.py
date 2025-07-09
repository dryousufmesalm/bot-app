from sqlmodel import Field, SQLModel, Relationship, or_, col, select, create_engine,Session
from datetime import datetime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .ah_cycles import AHCycle

class AhCyclesOrders(SQLModel, table=True):
    __tablename__ = "ah_cycles_orders"
    id : int | None= Field(default=None, primary_key=True)
    cycle: "AHCycle" = Relationship(back_populates="orders")
    cycle_id: int | None= Field(default=None, foreign_key="ah_cycles.id")
    ticket: int = Field(unique=True, index=True)
    comment: str
    commission: int
    is_pending: bool
    kind: str
    magic_number: int
    open_price: int
    open_time: str
    profit: int
    tp: int
    sl: int
    swap: int
    symbol: str
    type: int
    volume: int
    is_closed: bool
    trailing_steps: int
    account: str|None = Field(default=None)
