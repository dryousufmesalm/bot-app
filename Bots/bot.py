import threading
import time
import logging
from Strategy.AdaptiveHedging import AdaptiveHedging
from Strategy.CycleTrader import CycleTrader
from Strategy.AdvancedCyclesTrader_Organized import AdvancedCyclesTrader
from Strategy.StockTrader import StockTrader
from Strategy.MoveGuard import MoveGuard
import asyncio


class Bot:
    def __init__(self, client, account, meta_trader, bot_id):
        self.id = bot_id
        self.account = None
        self.strategy_name = None
        self.symbol = None
        self.symbol_name = None
        self.magic = None
        self.configs = None
        self.client = client
        self.account = account
        self.meta_trader = meta_trader
        self.strategy = None
        self.settings = None
        self.name = None

    def initialize(self):
        """ Initialize the bot """
        # get bot from the API
        try:
            bot_started = self.get_bot_settings()
            if bot_started is None:
                print(f"Failed to initialize bot {bot_started.name}")
                return False
            if bot_started:
                # Initialize the strategy
                self.init_strategy()
                self.update_configs()

            return True
        except (ConnectionError, TimeoutError) as e:
            print(f"Failed to initialize bot due to network issue: {e}")
            return False
        except ValueError as e:
            print(f"Failed to initialize bot due to value error: {e}")
            return False
        except KeyError as e:
            print(f"Failed to initialize bot due to missing key: {e}")
            return False
        except Exception as e:
            print(f"Failed to initialize bot: {e}")
            return False

    def init_strategy(self):
        """ Initialize the strategy """
        try:
            if self.strategy_name == "Tony AH Recovery":
                self.strategy = AdaptiveHedging(
                    self.meta_trader, self.configs, self.client, self.symbol_name, self)
                self.strategy.initialize(self.configs, self.settings)
            elif self.strategy_name == "Cycles Trader":
                self.strategy = CycleTrader(
                    self.meta_trader, self.configs, self.client, self.symbol_name, self)
                self.strategy.initialize(self.configs, self.settings)
            elif self.strategy_name == "Advanced Cycles Trader":
                self.strategy = AdvancedCyclesTrader(
                    self.meta_trader, self.configs, self.client, self.symbol_name, self)
                # Check if initialize method is async and handle appropriately
                try:
                    result = self.strategy.initialize()
                    if hasattr(result, '__await__'):
                        # It's a coroutine, we need to run it in an event loop
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                asyncio.create_task(result)
                            else:
                                loop.run_until_complete(result)
                        except RuntimeError:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            loop.run_until_complete(result)
                except Exception as init_error:
                    print(f"Failed to initialize Advanced Cycles Trader: {init_error}")
            elif self.strategy_name == "MoveGuard":
                self.strategy = MoveGuard(
                    self.meta_trader, self.configs, self.client, self.symbol_name, self)
                # Check if initialize method is async and handle appropriately
                try:
                    result = self.strategy.initialize()
                    if hasattr(result, '__await__'):
                        # It's a coroutine, we need to run it in an event loop
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                asyncio.create_task(result)
                            else:
                                loop.run_until_complete(result)
                        except RuntimeError:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            loop.run_until_complete(result)
                except Exception as init_error:
                    print(f"Failed to initialize MoveGuard: {init_error}")
            elif self.strategy_name == "Stock Trader":
                self.strategy = StockTrader(
                    self.meta_trader, self.configs, self.client)
                self.strategy.initialize(self.configs, self.settings)
            else:
                print(f"Unknown strategy: {self.strategy_name}")
        except Exception as e:
            print(f"Failed to initialize strategy: {e}")

    def update_configs(self):
        """ Update the bot's settings """
        try:
            if self.strategy_name == "Tony AH Recovery":
                self.strategy.update_configs(self.configs, self.settings)
            elif self.strategy_name == "Cycles Trader":
                self.strategy.update_configs(self.configs, self.settings)
            elif self.strategy_name == "Advanced Cycles Trader":
                # Use the new update_bot_config method
                if hasattr(self.strategy, "_initialize_strategy_configuration"):
                    try:
                        # Call the method directly since it's not async
                        self.strategy._initialize_strategy_configuration(self.configs)
                        print(f"Successfully updated Advanced Cycles Trader configuration")
                    except Exception as e:
                        print(f"Failed to update Advanced Cycles Trader configuration: {e}")
                else:
                    print(f"Advanced Cycles Trader does not support dynamic configuration updates")
            elif self.strategy_name == "MoveGuard":
                # Use the new update_bot_config method
                if hasattr(self.strategy, "_initialize_strategy_configuration"):
                    try:
                        # Call the method directly since it's not async
                        self.strategy._initialize_strategy_configuration(self.configs)
                        print(f"Successfully updated MoveGuard configuration")
                        
                        # Update bot symbol if it changed
                        if 'symbol' in self.configs and self.configs['symbol'] != self.symbol:
                            old_symbol = self.symbol
                            self.symbol = self.configs['symbol']
                            print(f"✅ Bot symbol updated from {old_symbol} to {self.symbol}")
                    except Exception as e:
                        print(f"Failed to update MoveGuard configuration: {e}")
                else:
                    print(f"MoveGuard does not support dynamic configuration updates")
            elif self.strategy_name == "StockTrader":
                self.strategy.update_configs(self.configs, self.settings)
            else:
                print(f"Unknown strategy: {self.strategy_name}")
        except Exception as e:
            print(f"Failed to update configs: {e}")

    def get_bot_settings(self):
        """ Get the bot's settings """
        bot = self.client.get_account_bots_by_id(self.id)[0]
        if not bot:
            print(f"Bot {self.id} not found.")
            return False
        # Initialize the bot
        strategy = self.client.get_strategy_by_id(bot.strategy)[0]
        self.strategy_name = strategy.name
        self.magic = bot.magic_number
        self.magic_number = bot.magic_number  # Add magic_number attribute for ACT strategy
        self.configs = bot.bot_configs
        self.settings = bot.settings
        
        # Handle missing 'symbol' key in bot_configs
        try:
            self.symbol_name = bot.bot_configs["symbol"]
        except KeyError:
            # If symbol is not in bot_configs, try to get it from bot.symbol
            if hasattr(bot, 'symbol') and bot.symbol:
                self.symbol_name = bot.symbol
                print(f"Using symbol from bot.symbol: {self.symbol_name}")
            else:
                # Set a default symbol or raise an error
                print("Warning: No symbol found in bot configuration")
                self.symbol_name = "EURUSD"  # Default fallback
                print(f"Using default symbol: {self.symbol_name}")
        
        self.symbol = bot.symbol
        self.name = bot.name

        return bot

    async def handle_event(self, event):
        """ Handle the incoming event """
        if self.strategy:
            await self.route_to_strategy(event)
            logging.info("Got event: %s", event)
        else:
            logging.error("Strategy not initialized for bot %s", self.id)

    async def route_to_strategy(self, event):
        """ Route the event to the strategy """
        if self.strategy:
            logging.info("Route to strategy")
            await self.strategy.handle_event(event)
        else:
            logging.error("Strategy not initialized for bot %s", self.id)

    async def run(self):
        """ Run the bot """
        if self.strategy is None:
            # Try re-initializing the strategy if it's None
            logging.info(
                f"Strategy is None for bot {self.id}. Attempting to reinitialize...")
            self.init_strategy()

        if self.strategy is not None:
            # Run the strategy
            logging.info(f"Running strategy for bot {self.id}")
            await self.strategy.run_in_thread()
        else:
            logging.error(
                f"Cannot run bot {self.id} - strategy initialization failed")
