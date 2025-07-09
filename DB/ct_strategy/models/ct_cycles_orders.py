from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .ct_cycles import CTCycle
from sqlmodel import Field, SQLModel, Relationship, or_, col, select, create_engine, Session
from typing import Optional
from datetime import datetime


class CtCyclesOrders (SQLModel, table=True):
    __tablename__ = 'ct_cycles_orders'
    id: int | None = Field(default=None, primary_key=True)
    cycle: "CTCycle" = Relationship(back_populates="orders")
    cycle_id: int | None = Field(foreign_key="ct_cycles.id")
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
    account: str | None = Field(default=None)
    # hedged: bool
