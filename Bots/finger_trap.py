from aiomql import Strategy, ForexSymbol, TimeFrame, Tracker, OrderType, Sessions, Trader, ScalpTrader

from Orders.order import order
from cycles.AH_cycle import cycle
from DB.db_engine import engine
from DB.ah_strategy.repositories.ah_repo import AHRepo
import time
import asyncio

class FingerTrap(Strategy):
    ttf: TimeFrame  # time frame for the strategy
    tcc: int  # how many candles to consider
    tracker: Tracker  # tracker to keep track of strategy state
    interval: TimeFrame  # intervals to check for entry and exit signals
    timeout: int  # timeout after placing an order in seconds
    disable_new_cycle_recovery : bool
    enable_recovery : bool
    lot_sizes : list[float]
    margin : float
    max_recovery : int
    max_recovery_direction : str
    pips_step : int
    slippage : int
    sltp : str
    take_profit : int
    zones : int
    zone_forward : int
    stop : bool
    def __init__(self, *, symbol: ForexSymbol, params: dict | None = None, trader: Trader = None,
                 sessions: Sessions = None, name: str = "AH Strategy",remote_api=None): 
        super().__init__(symbol=symbol, params=params, sessions=sessions, name=name)
        self.tracker = Tracker(snooze=self.interval.seconds)
        self.trader = trader or ScalpTrader(symbol=self.symbol)
        self.local_api = AHRepo(engine=engine)
        self.remote_api =   remote_api

    async def find_entry(self):
        # get the candles

        # check for entry signals in the current candle
        self.tracker.update(order_type=OrderType.BUY, snooze=self.timeout)

    async def trade(self):
        active_cycles = await self.get_all_active_cycles()
        tasks = []
        for cycle_data in active_cycles:
            cycle_obj = cycle(cycle_data, self.trader, self, "db")
            if self.stop is False:
                tasks.append(cycle_obj.manage_cycle_orders())
            tasks.append(cycle_obj.update_cycle(self.client))
            tasks.append(cycle_obj.close_cycle_on_takeprofit(self.take_profit, self.client))
        
        await asyncio.gather(*tasks)
    
    async  def get_all_active_cycles(self):
        cycles = self.local_api.get_active_cycles(self.bot.account.id)
        if cycles is None:
            return []
        active_cycles = [cycle for cycle in cycles if cycle.account ==
                         self.bot.account.id and cycle.bot == self.bot.id]
        return active_cycles
    # Cycles  Manager
