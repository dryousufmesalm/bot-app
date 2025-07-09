from Strategy.strategy import Strategy
import threading
from Orders.order import order
from cycles.CT_cycle import cycle
from DB.db_engine import engine
from DB.ct_strategy.repositories.ct_repo import CTRepo
import asyncio
from Views.globals.app_logger import app_logger as logger


class CycleTrader(Strategy):
    """ CycleTrader strategy """

    def __init__(self, meta_trader, config, client, symbol, bot):
        self.meta_trader = meta_trader
        self.config = config
        self.client = client
        self.positions = {}
        self.orders = {}
        self.symbol = symbol
        self.bot = bot
        self.enable_recovery = False
        self.lot_sizes = [0.01, 0.02, 0.03, 0.04,
                          0.05, 0.06, 0.07, 0.08, 0.09, 0.10]
        self.margin = 10.8
        self.pips_step = 0
        self.slippage = 3
        self.sltp = "money"
        self.take_profit = 5
        self.zones = 500
        self.zone_forward = 1
        self.zone_forward2 = 1
        self.stop = False
        self.autotrade = False
        self.autotrade_threshold = 0
        self.max_cycles = 1
        self.local_api = CTRepo(engine=engine)
        self.settings = None
        self.last_cycle_price = self.meta_trader.get_ask(self.symbol)
        self.logger = logger
        self.hedges_numbers = None
        self.ADD_All_to_PNL = True
        self.autotrade_pips_restriction = 100
        # New auto candle close settings
        self.auto_candle_close = False
        self.candle_timeframe = "H1"
        self.hedge_sl = 100
        self.prevent_opposing_trades = True
        self.last_candle_time = None
        self.init_settings()

    def initialize(self, config, settings):
        """ Initialize the CycleTrader strategy """
        self.update_configs(config, settings)

        # # Try to load configuration from database
        # try:
        #     db_config = self.local_api.get_config(
        #         symbol=self.symbol,
        #         bot_id=self.bot.id,
        #         account_id=self.meta_trader.account_id
        #     )

        #     if db_config:
        #         # Convert database config to dictionary
        #         config_dict = {
        #             "enable_recovery": db_config.enable_recovery,
        #             "lot_sizes": db_config.lot_sizes,
        #             "pips_step": db_config.pips_step,
        #             "slippage": db_config.slippage,
        #             "sltp": db_config.sltp,
        #             "take_profit": db_config.take_profit,
        #             "zone_array": db_config.zones,
        #             "zone_forward": db_config.zone_forward,
        #             "zone_forward2": db_config.zone_forward2,
        #             "symbol": db_config.symbol,
        #             "max_cycles": db_config.max_cycles,
        #             "autotrade": db_config.autotrade,
        #             "autotrade_threshold": db_config.autotrade_threshold,
        #             "hedges_numbers": db_config.hedges_numbers,
        #             "buy_and_sell_add_to_pnl": db_config.buy_and_sell_add_to_pnl,
        #             "autotrade_pips_restriction": db_config.autotrade_pips_restriction,
        #             "auto_candle_close": db_config.auto_candle_close,
        #             "candle_timeframe": db_config.candle_timeframe,
        #             "hedge_sl": db_config.hedge_sl,
        #             "prevent_opposing_trades": db_config.prevent_opposing_trades
        #         }

        #         # Update config with database values
        #         self.update_configs(config_dict, settings)
        #         logger.info(
        #             f"Loaded configuration from database for {self.symbol}")
        #     else:
        #         # Create default configuration in database
        #         config_dict = {
        #             "symbol": self.symbol,
        #             "bot_id": self.bot.id,
        #             "account_id": self.meta_trader.account_id,
        #             "enable_recovery": self.enable_recovery,
        #             "lot_sizes": self.lot_sizes,
        #             "pips_step": self.pips_step,
        #             "slippage": self.slippage,
        #             "sltp": self.sltp,
        #             "take_profit": self.take_profit,
        #             "zones": self.zones,
        #             "zone_forward": self.zone_forward,
        #             "zone_forward2": self.zone_forward2,
        #             "max_cycles": self.max_cycles,
        #             "autotrade": self.autotrade,
        #             "autotrade_threshold": self.autotrade_threshold,
        #             "hedges_numbers": self.hedges_numbers,
        #             "buy_and_sell_add_to_pnl": self.ADD_All_to_PNL,
        #             "autotrade_pips_restriction": self.autotrade_pips_restriction,
        #             "auto_candle_close": self.auto_candle_close,
        #             "candle_timeframe": self.candle_timeframe,
        #             "hedge_sl": self.hedge_sl,
        #             "prevent_opposing_trades": self.prevent_opposing_trades
        #         }

        #         self.local_api.create_config(config_dict)
        # logger.info(
        #     f"Created default configuration in database for {self.symbol}")
        # except Exception as e:
        #     logger.error(f"Error loading configuration from database: {e}")
        # Continue with the configuration from parameter

    def init_settings(self):
        """ Initialize the settings for the CycleTrader strategy """
        try:
            self.enable_recovery = self.config.get("enable_recovery", False)
            self.lot_sizes = self.string_to_array(
                self.config.get("lot_sizes", "0.01"))
            self.pips_step = self.config.get("pips_step", 0)
            self.slippage = self.config.get("slippage", 3)
            self.sltp = self.config.get("sltp", "money")
            self.take_profit = self.config.get("take_profit", 5)
            self.zones = self.string_to_array(
                self.config.get('zone_array', "500"))
            self.zone_forward = self.config.get("zone_forward", 1)
            self.zone_forward2 = self.config.get("zone_forward2", 1)
            self.symbol = self.config.get('symbol', self.symbol)
            self.max_cycles = self.config.get("max_cycles", 1)
            self.autotrade = self.config.get("autotrade", False)
            self.autotrade_threshold = self.config.get(
                "autotrade_threshold", 0)
            self.hedges_numbers = self.config.get("hedges_numbers", 0)
            self.ADD_All_to_PNL = self.config.get(
                "buy_and_sell_add_to_pnl", True)
            self.autotrade_pips_restriction = self.config.get(
                "autotrade_pips_restriction", 100)

            # Initialize auto candle close settings
            self.auto_candle_close = self.config.get(
                "auto_candle_close", False)
            self.candle_timeframe = self.config.get("candle_timeframe", "H1")
            self.hedge_sl = self.config.get("hedge_sl", 100)
            self.prevent_opposing_trades = self.config.get(
                "prevent_opposing_trades", True)

            if self.settings and hasattr(self.settings, 'stopped'):
                self.stop = self.settings.stopped
            else:
                self.stop = False

            self.last_cycle_price = self.meta_trader.get_ask(self.symbol)

            # Log key settings for debugging
            logger.info(f"CycleTrader initialization for {self.symbol}:")
            logger.info(f"- auto_candle_close: {self.auto_candle_close}")
            logger.info(f"- candle_timeframe: {self.candle_timeframe}")
            logger.info(f"- hedge_sl: {self.hedge_sl}")
            logger.info(f"- zone_forward: {self.zone_forward}")
            logger.info(f"- zone_forward2: {self.zone_forward2}")

        except Exception as e:
            logger.error(f"Error initializing CycleTrader settings: {e}")
            # Set default values for critical parameters
            if not hasattr(self, 'zone_forward2') or self.zone_forward2 is None:
                self.zone_forward2 = 1

    def update_configs(self, config, settings):
        """
        This function updates the settings for the adaptive hedging strategy.

        Parameters:
        config (dict): The new configuration settings for the strategy.

        Returns:
        None
        """
        try:
            if config is not None:
                self.config = config
            if settings is not None:
                self.settings = settings

            self.init_settings()
            logger.info(f"CycleTrader configs updated for {self.symbol}")
        except Exception as e:
            logger.error(f"Error updating CycleTrader configs: {e}")
            # Ensure critical parameters have default values if update fails
            if not hasattr(self, 'zone_forward2') or self.zone_forward2 is None:
                self.zone_forward2 = 1

    async def handle_event(self, event):
        """
        This function handles incoming events for the adaptive hedging strategy.

        Parameters:
        event (dict): The event data.

        Returns:
        None
        """
        try:
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
                            await self.create_cycle(
                                order1, None, False, sent_by_admin, user_id, username, "BUY")
                        elif (price > 0):
                            ask = self.meta_trader.get_ask(self.symbol)
                            if (price > ask):
                                # buy stop
                                order1 = self.meta_trader.buy_stop(
                                    self.symbol, price, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "pending")
                                await self.create_cycle(order1, None, True, sent_by_admin, user_id, username, "BUY")
                            else:
                                order1 = self.meta_trader.buy_limit(
                                    self.symbol, price, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "pending")
                                await self.create_cycle(order1, None, True, sent_by_admin, user_id, username, "BUY")
                    elif cycle_type == 1:
                        if (price == 0):
                            order1 = self.meta_trader.sell(
                                self.symbol, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "initial")
                            await self.create_cycle(
                                order1, None, False, sent_by_admin, user_id, username, "SELL")
                        elif (price > 0):
                            bid = self.meta_trader.get_bid(self.symbol)
                            if (price < bid):
                                # sell stop
                                order1 = self.meta_trader.sell_stop(
                                    self.symbol, price, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "pending")
                                await self.create_cycle(
                                    order1, None, True, sent_by_admin, user_id, username, "SELL")
                            else:
                                order1 = self.meta_trader.sell_limit(
                                    self.symbol, price, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "pending")
                                await self.create_cycle(
                                    order1, None, True, sent_by_admin, user_id, username, "SELL")
                    elif cycle_type == 2:
                        if (price == 0):
                            order1 = self.meta_trader.buy(
                                self.symbol, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "initial")
                            order2 = self.meta_trader.sell(
                                self.symbol, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "initial")
                            await self.create_cycle(order1, order2, False, sent_by_admin, user_id, username, "BUY&SELL")
                        elif (price > 0):
                            ask = self.meta_trader.get_ask(self.symbol)
                            bid = self.meta_trader.get_bid(self.symbol)
                            if (price > ask):
                                # buy stop
                                order1 = self.meta_trader.buy_stop(
                                    self.symbol, price, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "pending")
                                # order2= self.meta_trader.sell_limit(self.symbol,price,self.lot_sizes[0],self.bot.magic,0, 0,"PIPS",self.slippage,"pending")
                                await self.create_cycle(order1, None, True, sent_by_admin, user_id, username, "BUY&SELL")
                            elif price < bid:
                                order1 = self.meta_trader.buy_limit(
                                    self.symbol, price, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "pending")
                                # order2= self.meta_trader.sell_stop(self.symbol,price,self.lot_sizes[0],self.bot.magic,0,0,"PIPS",self.slippage,"pending")
                                await self.create_cycle(order1, None, True, sent_by_admin, user_id, username, "BUY&SELL")
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
                self.client.update_CT_cycle_by_id(
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
                active_cycles = await self.get_all_active_cycles()
                for cycle_data in active_cycles:
                    cycle_obj = cycle(cycle_data, self.meta_trader, self, "db")
                    cycle_obj.close_cycle(
                        content["sent_by_admin"], content["user_id"], content["user_name"])
                    self.client.update_CT_cycle_by_id(
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
                    order_obj = order(
                        order_data, order_data.is_pending, self.meta_trader, self.local_api, "db")
                    order_obj.close_order()
            elif message == "close_pending_order":
                order_ticket = content["ticket"]
                order_data = self.local_api.get_order_by_ticket(order_ticket)
                order_obj = order(order_data, order_data.is_pending,
                                  self.meta_trader, self.local_api, "db")
                order_obj.close_order()
        except Exception as e:
            self.logger.error(f"Error handling event: {e}")
            data = {
                "title":  "Error handling event",
                "body":     "Error handling event {} for bot {} ({})".format(
                    e, self.bot.name, self.bot.id),
                "data":     {
                    "bot": self.bot.id,
                    "event": self.event.name,
                    "message": str(e),

                },
                "bot": self.bot.id,
                "level": "error",
                "subject": "test",
                "group": "test"
            }

            self.client.send_log(data)

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

    async def create_cycle(self, order1, order2, is_pending, sent_by_admin, user_id, username, cycle_type):
        """
        This function creates a cycle.

        Parameters:
        data (dict): The cycle data.

        Returns:
        None
        """
        try:
            lower_bound = float(order1[0].price_open) - float(
                self.zones[0]) * float(self.meta_trader.get_pips(self.symbol))
            upper_bound = float(order1[0].price_open) + float(
                self.zones[0]) * float(self.meta_trader.get_pips(self.symbol))
            upper_threshold = float(upper_bound) + float(
                self.zone_forward2 * float(self.meta_trader.get_pips(self.symbol)))
            lower_threshold = float(lower_bound) - float(
                self.zone_forward2 * float(self.meta_trader.get_pips(self.symbol)))
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
                "threshold": [],
                "cycle_id": "",
                "zone_index": 0,
                "threshold_upper": upper_threshold,
                "threshold_lower": lower_threshold,
            }
            New_cycle = cycle(data, self.meta_trader, self.bot)
            New_cycle.open_price = order1[0].price_open
            if order1:
                order_obj = order(
                    order1[0], is_pending, self.meta_trader, self.local_api, "mt5", "")
                order_obj.create_order()
                if is_pending:
                    New_cycle.add_pending_order(order1[0].ticket)
                else:
                    New_cycle.add_initial_order(order1[0].ticket)
            if order2 and order2 != -2:
                order_obj = order(
                    order2[0], is_pending, self.meta_trader, self.local_api, "mt5", "")
                order_obj.create_order()
                if is_pending:
                    New_cycle.add_pending_order(order2[0].ticket)
                else:
                    New_cycle.add_initial_order(order2[0].ticket)
            res = self.client.create_CT_cycle(New_cycle.to_remote_dict())
            New_cycle.cycle_id = str(res.id)
            New_cycle.create_cycle()
        except Exception as e:
            self.logger.error(f"Error creating cycle: {e}")

    async def get_all_active_cycles(self):
        """
        Get all active cycles.
        """
        try:
            cycles = self.local_api.get_active_cycles(self.bot.id)
            active_cycles = [
                cycle for cycle in cycles if cycle.is_closed is False]

            return active_cycles
        except Exception as e:
            self.logger.error(f"Error getting active cycles: {e}")

    async def open_new_cycle(self, active_cycles, cycles_Restrition):
        """
        Open new cycle automatically every threshold pips from the last cycle with limit max cycles.
        Only allows one buy cycle and one sell cycle per level.
        """
        try:
            if len(active_cycles) < self.max_cycles:
                ask = self.meta_trader.get_ask(self.symbol)
                bid = self.meta_trader.get_bid(self.symbol)
                pips = self.meta_trader.get_pips(self.symbol)
                up_price = self.last_cycle_price+self.autotrade_threshold*pips
                down_price = self.last_cycle_price-self.autotrade_threshold*pips

                # Check for existing buy/sell cycles at current level
                buy_exists_at_level = False
                sell_exists_at_level = False

                # Calculate a more appropriate level buffer based on the price scale
                # For high-value symbols like Bitcoin, we need a larger absolute buffer
                # Use 0.1% of the current price as a minimum buffer
                price_scale_buffer = self.autotrade_pips_restriction * pips

                self.logger.info(
                    f"Level buffer for {self.symbol}: {price_scale_buffer} (price: {ask}, pips: {pips})")

                # Check existing cycles to see if there's already a buy or sell at this level
                for cycle_data in active_cycles:
                    cycle_obj = cycle(cycle_data, self.meta_trader, self, "db")

                    # Check if the cycle is at current level using the adaptive buffer
                    is_at_up_level = abs(
                        cycle_obj.open_price - up_price) <= price_scale_buffer
                    is_at_down_level = abs(
                        cycle_obj.open_price - down_price) <= price_scale_buffer

                    # Also check if it's close to the current price level (for existing cycles)
                    is_at_current_level = False

                    # For BUY cycles, check against existing BUY cycles
                    if ask >= up_price and cycle_obj.cycle_type == "BUY":
                        is_at_current_level = abs(
                            cycle_obj.open_price - ask) <= price_scale_buffer

                    # For SELL cycles, check against existing SELL cycles
                    elif bid <= down_price and cycle_obj.cycle_type == "SELL":
                        is_at_current_level = abs(
                            cycle_obj.open_price - bid) <= price_scale_buffer

                    if is_at_up_level or is_at_down_level or is_at_current_level:
                        if cycle_obj.cycle_type == "BUY":
                            buy_exists_at_level = True
                            self.logger.info(
                                f"BUY cycle already exists at level: {cycle_obj.open_price}")
                        elif cycle_obj.cycle_type == "SELL":
                            sell_exists_at_level = True
                            self.logger.info(
                                f"SELL cycle already exists at level: {cycle_obj.open_price}")

                if ask >= up_price:
                    self.last_cycle_price = ask if ask >= up_price else bid if bid <= down_price else 0
                    # Check if autotrade is enabled AND restrictions pass AND no buy cycle exists at this level
                    if self.autotrade and (self.autotrade_pips_restriction == 0 or cycles_Restrition == False) and not buy_exists_at_level:
                        if self.stop is False:
                            order1 = self.meta_trader.buy(
                                self.symbol, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "initial")
                            await self.create_cycle(order1, None, False,
                                                    False, 0, "MetaTrader5", "BUY")
                            self.logger.info(
                                f"Opened new BUY cycle at price: {order1[0].price_open}")
                    elif buy_exists_at_level:
                        self.logger.info(
                            f"Skipped opening BUY cycle - already exists at this level")
                elif bid <= down_price:
                    self.last_cycle_price = ask if ask >= up_price else bid if bid <= down_price else 0
                    # Check if autotrade is enabled AND restrictions pass AND no sell cycle exists at this level
                    if self.autotrade and (self.autotrade_pips_restriction == 0 or cycles_Restrition == False) and not sell_exists_at_level:
                        if self.stop is False:
                            order1 = self.meta_trader.sell(
                                self.symbol, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "initial")
                            await self.create_cycle(order1, None, False,
                                                    False, 0, "MetaTrader5", "SELL")
                            self.logger.info(
                                f"Opened new SELL cycle at price: {order1[0].price_open}")
                    elif sell_exists_at_level:
                        self.logger.info(
                            f"Skipped opening SELL cycle - already exists at this level")
        except Exception as e:
            self.logger.error(f"Error opening new cycle: {e}")

    async def run(self):
        """
        This function runs the adaptive hedging strategy.

        Returns:
        None
        """
        while True:
            try:
                active_cycles = await self.get_all_active_cycles()
                New_cycles_Restrition = False

                # Only calculate restrictions if autotrade_pips_restriction is not 0
                if self.autotrade_pips_restriction != 0:
                    ask = self.meta_trader.get_ask(self.symbol)
                    bid = self.meta_trader.get_bid(self.symbol)
                    pips = self.meta_trader.get_pips(self.symbol)
                    up_price = bid+(self.autotrade_pips_restriction/2)*pips
                    down_price = bid-(self.autotrade_pips_restriction/2)*pips

                    for cycle_data in active_cycles:
                        cycle_obj = cycle(
                            cycle_data, self.meta_trader, self, "db")
                        if len(cycle_obj.orders) <= 2 and len(cycle_obj.closed) == 0 and len(cycle_obj.hedge) == 0:
                            if cycle_obj.open_price > 0:
                                if cycle_obj.open_price > down_price and cycle_obj.open_price < up_price:
                                    New_cycles_Restrition = True

                tasks = []
                for cycle_data in active_cycles:
                    cycle_obj = cycle(cycle_data, self.meta_trader, self, "db")
                    if not self.stop:
                        tasks.append(cycle_obj.manage_cycle_orders(
                            self.zone_forward, self.zone_forward2))
                    tasks.append(cycle_obj.update_cycle(self.client))
                    tasks.append(cycle_obj.close_cycle_on_takeprofit(
                        self.take_profit, self.client))

                tasks.append(self.open_new_cycle(
                    active_cycles, New_cycles_Restrition))

                # # Add candle trading check if enabled - create a separate task
                # if self.auto_candle_close and not self.stop:
                #     logger.debug(
                #         f"Adding candle trading check for {self.symbol}")
                #     # Run the check directly rather than just adding it to tasks
                #     await self.check_candle_trading()

                # If we have tasks, gather them
                if tasks:
                    await asyncio.gather(*tasks)

            except Exception as e:
                self.logger.error(f"Error in run loop: {e}")
                import traceback
                self.logger.error(traceback.format_exc())

            # Always sleep at the end to prevent CPU overload
            await asyncio.sleep(1)

    async def check_candle_trading(self):
        """Check for candle close events and execute trades

        This method monitors candle closes and executes trades based on
        the direction of the candle close. It also handles hedging.
        """
        try:
            # Get the last candle
            last_candle = self.meta_trader.get_last_candle(
                self.symbol, self.candle_timeframe)

            if last_candle is None:
                logger.debug(
                    f"No candle data available for {self.symbol} {self.candle_timeframe}")
                return

            # Check if this is a new candle since the last check
            candle_time = last_candle["time"]

            if self.last_candle_time is None or candle_time > self.last_candle_time:
                self.last_candle_time = candle_time

                # Check candle direction
                direction = self.meta_trader.check_candle_direction(
                    self.symbol, self.candle_timeframe)

                if direction:
                    logger.info(
                        f"New {self.candle_timeframe} candle closed {direction} for {self.symbol}")

                    try:
                        # Place the order based on candle direction
                        if direction == "UP":
                            # Place a buy order
                            order1 = self.meta_trader.buy(
                                self.symbol, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "initial")

                            # Calculate hedge level below entry
                            entry_price = order1[0].price_open
                            pip_value = self.meta_trader.get_pips(self.symbol)
                            hedge_price = entry_price - \
                                (self.hedge_sl * pip_value)

                            # # Place pending sell stop order as hedge
                            # hedge_order = self.meta_trader.sell_stop(
                            #     self.symbol, hedge_price, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "hedge")

                            # Create cycle with both orders
                            await self.create_cycle(
                                order1, None, False, False, 0, "MetaTrader5", "SELL")
                            logger.info(
                                f"Created UP cycle with hedge at {hedge_price}")

                        elif direction == "DOWN":
                            # Place a sell order
                            order1 = self.meta_trader.sell(
                                self.symbol, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "initial")

                            # Calculate hedge level above entry
                            entry_price = order1[0].price_open
                            pip_value = self.meta_trader.get_pips(self.symbol)
                            hedge_price = entry_price + \
                                (self.hedge_sl * pip_value)

                            # # Place pending buy stop order as hedge
                            # hedge_order = self.meta_trader.buy_stop(
                            #     self.symbol, hedge_price, self.lot_sizes[0], self.bot.magic, 0, 0, "PIPS", self.slippage, "hedge")

                            # Create cycle with both orders
                            await self.create_cycle(
                                order1, None, False, False, 0, "MetaTrader5", "BUY")
                            logger.info(
                                f"Created DOWN cycle with hedge at {hedge_price}")
                    except Exception as order_ex:
                        logger.error(
                            f"Error placing orders for {direction} candle: {order_ex}")
                        import traceback
                        logger.error(traceback.format_exc())
                else:
                    logger.debug(
                        f"No clear direction for candle on {self.symbol} {self.candle_timeframe}")

        except Exception as e:
            logger.error(f"Error in check_candle_trading: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def run_in_thread(self):
        """
        This function runs the adaptive hedging strategy in a separate thread.
        """
        try:
            def run_coroutine_in_thread(loop, coro):
                asyncio.set_event_loop(loop)
                loop.run_until_complete(coro)

            loop = asyncio.new_event_loop()
            thread = threading.Thread(
                target=run_coroutine_in_thread, args=(loop, self.run()), daemon=True)
            thread.start()
            self.logger.info("CycleTrader strategy running in thread")
        except Exception as e:
            self.logger.error(f"Error running in thread: {e}")
