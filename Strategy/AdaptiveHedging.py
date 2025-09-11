from Strategy.strategy import Strategy
from Orders.order import order
from cycles.AH_cycle import cycle
import threading
from DB.db_engine import engine
from DB.ah_strategy.repositories.ah_repo import AHRepo
import time
import asyncio
from Views.globals.app_logger import app_logger as logger


class AdaptiveHedging(Strategy):
    def __init__(self, meta_trader, config, client, symbol, bot):
        self.meta_trader = meta_trader
        self.config = config
        self.client = client
        self.positions = {}
        self.orders = {}
        self.symbol = symbol
        self.bot = bot
        self.disable_new_cycle_recovery = False
        self.enable_recovery = False
        self.lot_sizes = [0.01, 0.02, 0.03, 0.04,
                          0.05, 0.06, 0.07, 0.08, 0.09, 0.10]
        self.margin = 10.8
        self.max_recovery = 2
        self.max_recovery_direction = "opposite"
        self.pips_step = 0
        self.slippage = 3
        self.sltp = "money"
        self.take_profit = 5
        self.zones = 500
        self.zone_forward = 1
        self.stop = False
        self.local_api = AHRepo(engine=engine)
        self.settings = None
        self.init_settings()
        self.logger = logger

    def init_settings(self):
        """
        This function initializes the settings for the adaptive hedging strategy."""
        self.disable_new_cycle_recovery = self.config["disable_new_cycle_recovery"]
        self.enable_recovery = self.config["enable_recovery"]
        self.lot_sizes = self.string_to_array(self.config["lot_sizes"])
        self.margin = self.config["margin"]
        self.max_recovery = self.config["max_recovery"]
        self.max_recovery_direction = self.config["max_recovery_direction"]
        self.pips_step = self.config["pips_step"]
        self.slippage = self.config["slippage"]
        self.sltp = self.config["sltp"]
        self.take_profit = self.config["take_profit"]
        self.zones = self.string_to_array(self.config['zone_array'])
        self.zone_forward = self.config["zone_forward"]
        self.symbol = self.config['symbol']

        if self.settings and hasattr(self.settings, 'stopped'):
            self.stop = self.settings.stopped
        else:
            self.stop = False

    def update_configs(self, config, settings):
        """
        This function updates the settings for the adaptive hedging strategy.

        Parameters:
        config (dict): The new configuration settings for the strategy.

        Returns:
        None
        """
        self.config = config
        self.settings = settings
        self.init_settings()
        
        # Update magic number in PocketBase if it has changed
        self._update_magic_number_if_needed(config)

    def _update_magic_number_if_needed(self, cfg):
        """Update magic number in PocketBase if it has changed"""
        try:
            if 'magic_number' in cfg and cfg['magic_number'] != self.bot.magic:
                # Update magic number in PocketBase
                if hasattr(self.client, 'update_bot_magic_number'):
                    result = self.client.update_bot_magic_number(self.bot.id, cfg['magic_number'])
                    if result:
                        self.bot.magic = cfg['magic_number']
                        logger.info(f"✅ Magic number updated to {cfg['magic_number']} in PocketBase")
                    else:
                        logger.error(f"❌ Failed to update magic number in PocketBase")
                else:
                    logger.warning(f"⚠️ Client does not support update_bot_magic_number method")
        except Exception as e:
            logger.error(f"❌ Error updating magic number: {str(e)}")

    async def handle_event(self, event):
        """
        This function handles incoming events for the adaptive hedging strategy.

        Parameters:
        event (dict): The event data.

        Returns:
        None
        """
        print(f"Got event: {event}")
        content = event.content
        message = content["message"]
        if (message == "open_order"):
            username = content["user_name"]
            sent_by_admin = content["sent_by_admin"]
            user_id = content["user_id"]
            cycle_type = content['type']
            price = content['price']
            # wait_for_candle = content['wait_for_candle_to_close']
            # username= content['user_name']

            if (self.stop == False):
                if (cycle_type == 0):
                    if (price == 0):
                        order1 = self.meta_trader.buy(
                            self.symbol, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "initial")
                        self.create_cycle(
                            order1, None, False, sent_by_admin, user_id, username, "BUY")
                    elif (price > 0):
                        ask = self.meta_trader.get_ask(self.symbol)
                        if (price > ask):
                            # buy stop
                            order1 = self.meta_trader.buy_stop(
                                self.symbol, price, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "pending")
                            self.create_cycle(
                                order1, None, True, sent_by_admin, user_id, username, "BUY")
                        else:
                            order1 = self.meta_trader.buy_limit(
                                self.symbol, price, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "pending")
                            self.create_cycle(
                                order1, None, True, sent_by_admin, user_id, username, "BUY")
                elif cycle_type == 1:
                    if (price == 0):
                        order1 = self.meta_trader.sell(
                            self.symbol, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "initial")
                        self.create_cycle(
                            order1, None, False, sent_by_admin, user_id, username, "SELL")
                    elif (price > 0):
                        bid = self.meta_trader.get_bid(self.symbol)
                        if (price < bid):
                            # sell stop
                            order1 = self.meta_trader.sell_stop(
                                self.symbol, price, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "pending")
                            self.create_cycle(
                                order1, None, True, sent_by_admin, user_id, username, "SELL")
                        else:
                            order1 = self.meta_trader.sell_limit(
                                self.symbol, price, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "pending")
                            self.create_cycle(
                                order1, None, True, sent_by_admin, user_id, username, "SELL")
                elif cycle_type == 2:
                    if (price == 0):
                        order1 = self.meta_trader.buy(
                            self.symbol, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "initial")
                        order2 = self.meta_trader.sell(
                            self.symbol, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "initial")
                        self.create_cycle(
                            order1, order2, False, sent_by_admin, user_id, username, "BUY&SELL")
                    elif (price > 0):
                        ask = self.meta_trader.get_ask(self.symbol)
                        bid = self.meta_trader.get_bid(self.symbol)
                        if (price > ask):
                            # buy stop
                            order1 = self.meta_trader.buy_stop(
                                self.symbol, price, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "pending")
                            # order2= self.meta_trader.sell_limit(self.symbol,price,self.lot_sizes[0],self.bot.magic,0,0,"PIPS",self.slippage,"pending")
                            self.create_cycle(
                                order1, None, True, sent_by_admin, user_id, username, "BUY&SELL")
                        elif price < bid:
                            order1 = self.meta_trader.buy_limit(
                                self.symbol, price, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "pending")
                            # order2= self.meta_trader.sell_stop(self.symbol,price,self.lot_sizes[0],self.bot.magic,0,0,"PIPS",self.slippage,"pending")
                            self.create_cycle(
                                order1, None, True, sent_by_admin, user_id, username, "BUY&SELL")
            # close cycle
        elif message == "close_cycle":
            username = content["user_name"]
            sent_by_admin = content["sent_by_admin"]
            user_id = content["user_id"]
            cycle_id = content['id']
            cycle_data = self.local_api.get_cycle_by_id(cycle_id)
            selected_cycle = cycle(
                cycle_data, self.meta_trader, self.meta_trader, "db")
            selected_cycle.close_cycle(sent_by_admin, user_id, username)
            self.client.update_AH_cycle_by_id(
                selected_cycle.cycle_id, selected_cycle.to_remote_dict())
        elif message == "update_order_configs":
            order_ticket = content["ticket"]
            sl = content['updated']['sl']
            tp = content['updated']['tp']
            ts = content['updated']['trailing_steps']
            order_data = self.local_api.get_order_by_ticket(order_ticket)
            order_obj = order(order_data, order_data.is_pending,
                              self.meta_trader, self.local_api, "db")
            order_obj.update_order_configs(sl, tp, ts)
            order_obj.update_order()
        elif message == "close_order":
            order_ticket = content["ticket"]
            order_data = self.local_api.get_order_by_ticket(order_ticket)
            order_obj = order(order_data, order_data.is_pending,
                              self.meta_trader, self.local_api, "db")
            order_obj.close_order()
        elif message == "close_all_cycles":
            active_cycles = self.get_all_active_cycles()
            for cycle_data in active_cycles:
                cycle_obj = cycle(cycle_data, self.meta_trader, self, "db")
                cycle_obj.close_cycle(
                    content["sent_by_admin"], content["user_id"], content["user_name"])
                self.client.update_AH_cycle_by_id(
                    cycle_obj.cycle_id, cycle_obj.to_remote_dict())
        elif message == "stop_bot":
            self.stop = True
            self.client.set_bot_stopped(event.bot)
        elif message == "start_bot":
            self.stop = False
            self.client.set_bot_running(event.bot)
        elif message == "close_all_pending_orders":
            orders = self.local_api.get_open_pending_orders()
            for order_data in orders:
                if order_data.is_pending == False:
                    continue
                order_obj = order(order_data, order_data.is_pending,
                                  self.meta_trader, self.local_api, "db")
                order_obj.close_order()
        elif message == "close_pending_order":
            order_ticket = content["ticket"]
            order_data = self.local_api.get_order_by_ticket(order_ticket)
            order_obj = order(order_data, order_data.is_pending,
                              self.meta_trader, self.local_api, "db")
            order_obj.close_order()

    def initialize(self, config, settings):
        """
        This function initializes the adaptive hedging strategy.

        Parameters:
        None

        Returns:
        None
        """
        self.update_configs(config, settings)

    def string_to_array(self, string):
        """
        This function converts a string to an array.

        Parameters:
        string (str): The string to convert.

        Returns:
        list: The converted array.
        """
        if string == "":
            return []
        float_array = [float(value.strip()) for value in string.split(",")]
        return float_array

    def create_cycle(self, order1, order2, is_pending, sent_by_admin, user_id, username, cycle_type):
        """
        This function creates a cycle.

        Parameters:
        data (dict): The cycle data.

        Returns:
        None
        """
        lower_bound = float(order1[0].price_open) - float(self.zones[0]) * \
            float(self.meta_trader.get_pips(self.symbol))
        upper_bound = float(order1[0].price_open) + float(self.zones[0]) * \
            float(self.meta_trader.get_pips(self.symbol))

        data = {
            "account": self.bot.account.id,
            "bot": self.bot.id,
            "is_closed": False,
            "symbol": order1[0].symbol,
            "closing_method": {},
            "opened_by": {
                "sent_by_admin": sent_by_admin,
                "status": "Opened by User",
                "user_id": user_id,
                "user_name": username,
            },
            "lot_idx": 0,
            "status": "initial",
            "cycle_type": cycle_type,
            "lower_bound": round(lower_bound, 2),
            "upper_bound": round(upper_bound, 2),
            "is_pending": is_pending,
            "type": "initial",
            "total_volume": round(0, 2),
            "total_profit": round(0, 2),
            "initial": [],
            "hedge": [],
            "pending": [],
            "closed": [],
            "recovery": [],
            "max_recovery": [],
            "cycle_id": "",
            "zone_index": 0,

        }

        New_cycle = cycle(data, self.meta_trader, self.bot)

        if order1:
            order_obj = order(order1[0], is_pending,
                              self.meta_trader, self.local_api, "mt5", "")
            order_obj.create_order()
            if is_pending:
                New_cycle.add_pending_order(order1[0].ticket)
            else:
                New_cycle.add_initial_order(order1[0].ticket)

        if order2 and order2 != -2:
            order_obj = order(order2[0], is_pending,
                              self.meta_trader, self.local_api, "mt5", "")
            order_obj.create_order()
            if is_pending:
                New_cycle.add_pending_order(order2[0].ticket)
            else:
                New_cycle.add_initial_order(order2[0].ticket)
        res = self.client.create_AH_cycle(New_cycle.to_remote_dict())
        New_cycle.cycle_id = str(res.id)
        New_cycle.create_cycle()

    # get all active  cycles
    async def get_all_active_cycles(self):
        try:
            cycles = self.local_api.get_active_cycles(self.bot.id)
            active_cycles = [
                cycle for cycle in cycles if cycle.is_closed is False]
            return active_cycles
        except Exception as e:
            self.logger.error(f"Error getting active cycles: {e}")
    # Cycles  Manager

    async def run(self):
        """
        This function runs the adaptive hedging strategy.

        Parameters:
        None

        Returns:
        None
        """
        while True:
            try:
                active_cycles = await self.get_all_active_cycles()
                tasks = []

                for cycle_data in active_cycles:
                    cycle_obj = cycle(cycle_data, self.meta_trader, self, "db")
                    if self.stop is False:
                        tasks.append(cycle_obj.manage_cycle_orders())
                    tasks.append(cycle_obj.update_cycle(self.client))
                    tasks.append(cycle_obj.close_cycle_on_takeprofit(
                        self.take_profit, self.client))

                await asyncio.gather(*tasks)
            except Exception as e:
                self.logger.error(
                    f"Error running adaptive hedging strategy: {e}")
            await asyncio.sleep(1)

    async def run_in_thread(self):
        try:
            def run_coroutine_in_thread(loop, coro):
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(coro)

            loop = asyncio.new_event_loop()
            thread = threading.Thread(
                target=run_coroutine_in_thread, args=(loop, self.run()), daemon=True)
            thread.start()
            self.logger.info("adaptive hedging strategy running in thread")
        except Exception as e:
            self.logger.error(f"Error running in thread: {e}")