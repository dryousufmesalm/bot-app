from Strategy.strategy import Strategy
import threading
from Orders.order import order
from cycles.ACT_cycle import AdvancedCycle
from DB.db_engine import engine
from DB.ct_strategy.repositories.ct_repo import CTRepo
# ACTRepo removed - using in-memory operations
from Strategy.components import AdvancedOrderManager, DirectionController
from Strategy.components.multi_cycle_manager import MultiCycleManager
from Strategy.components.enhanced_zone_detection import EnhancedZoneDetection
from Strategy.components.enhanced_order_manager import EnhancedOrderManager
import asyncio
import datetime
import time
from Views.globals.app_logger import app_logger as logger
from typing import Dict
import json



class AdvancedCyclesTrader(Strategy):
    """ Advanced Cycles Trader strategy with multi-cycle zone-based reversal logic """

    def __init__(self, meta_trader, config, client, symbol, bot):
        self.meta_trader = meta_trader
        self.config = config
        self.client = client
        self.positions = {}
        self.orders = {}
        self.symbol = symbol
        
        # ACTRepo removed - using in-memory operations
        self.loss_tracker = {'total_accumulated_losses': 0.0, 'active_cycles_count': 0}
        # CRITICAL DEBUG: Check bot parameter
        if bot is None:
            logger.error("🚨 CRITICAL: Bot parameter is None during AdvancedCyclesTrader initialization!")
            raise ValueError("Bot parameter cannot be None")
        
        self.bot = bot
        logger.info(f"✅ Bot assigned to AdvancedCyclesTrader: ID={self.bot.id}, Name={getattr(self.bot, 'name', 'Unknown')}")
        
        # CRITICAL: Set the magic number on the MetaTrader instance
        if hasattr(self.bot, 'magic_number') and self.bot.magic_number:
            self.meta_trader.magic_number = self.bot.magic_number
            logger.info(f"✅ Magic number {self.bot.magic_number} set on MetaTrader instance")
        else:
            logger.warning("⚠️ Bot has no magic number - MetaTrader will use default")
        
        # Base CycleTrader properties
        self.cycles = {}
        self.active_cycles = []
        self.closed_cycles = []
        self.strategy_active = False
        self.monitoring_thread = None
        
        # Advanced Cycles Trader specific properties
        self.reversal_threshold_pips = float(config.get("reversal_threshold_pips", 300.0))  # 300 pips for zone switches
        self.order_interval_pips = float(config.get("order_interval_pips", 50.0))   # 50 pips between orders
        self.initial_order_stop_loss = float(config.get("initial_order_stop_loss", 300.0))
        self.cycle_interval = float(config.get("cycle_interval", 100.0))
        self.lot_size = float(config.get("lot_size", 0.01))
        self.take_profit_pips = float(config.get("take_profit_pips", 100.0))
        self.stop_loss_pips = float(config.get("stop_loss_pips", 50.0))
        self.max_active_cycles = int(config.get("max_active_cycles", 10))
        
        
        # MULTI-CYCLE SYSTEM INITIALIZATION
        # Replace single-cycle components with multi-cycle versions
        # CRITICAL FIX: Update config with new field names before passing to MultiCycleManager
        updated_config = config.copy() if isinstance(config, dict) else {}
        updated_config.update({
            "reversal_threshold_pips": self.reversal_threshold_pips,
            "order_interval_pips": self.order_interval_pips,
            "initial_order_stop_loss": self.initial_order_stop_loss,
            "cycle_interval": self.cycle_interval,
            "max_active_cycles": self.max_active_cycles
        })
        self.multi_cycle_manager = MultiCycleManager(meta_trader, bot, updated_config, client)
        self.enhanced_zone_engine = EnhancedZoneDetection(symbol, self.reversal_threshold_pips, self.order_interval_pips)
        self.enhanced_order_manager = EnhancedOrderManager(meta_trader, symbol, bot.magic_number)
        
        # Use enhanced zone engine as the main zone engine
        self.zone_engine = self.enhanced_zone_engine
        self.order_manager = AdvancedOrderManager(meta_trader, symbol, bot.magic_number)
        self.direction_controller = DirectionController(symbol)
        
    
        # API client for PocketBase operations
        self.api_client = client
        
        # CRITICAL: Ensure bot has access to API client for database operations
        if not hasattr(self.bot, 'api_client') or not self.bot.api_client:
            self.bot.api_client = client
            logger.info("API client assigned to bot for database operations")
        
        # Strategy state - MODIFIED FOR MULTI-CYCLE
        self.current_market_price = None
        self.last_candle_time = None
        self.loss_tracker = None
        
        # Trading state
        self.trading_active = False
        self.initial_threshold_breached = False
        self.zone_activated = False
        
        # Initialize direction controller with default direction
        # Set initial direction to BUY as default (can be changed by strategy logic)
        self.direction_controller.execute_direction_switch("BUY", "strategy_initialization")
        logger.info("Direction controller initialized with default BUY direction")
        
        # Event tracking to prevent duplicate processing
        self.processed_events = set()
        
        # Multi-cycle tracking
        self.last_cycle_creation_time = 0
        
        logger.info(f"AdvancedCyclesTrader initialized for {symbol} with MULTI-CYCLE MANAGEMENT")
        logger.info(f"Configuration: Threshold={self.reversal_threshold_pips}pips, "
                   f"Interval={self.order_interval_pips}pips, "
                   f"MaxCycles={self.max_active_cycles}")

    def initialize(self):
        """Initialize the Advanced Cycles Trader strategy (required by Strategy base class)"""
        try:
            # Initialize in-memory loss tracker
            # ACTRepo removed - using in-memory operations
            self.set_entry_price( self.meta_trader.get_bid(self.symbol) )
            logger.info("AdvancedCyclesTrader initialized successfully with multi-cycle support")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing AdvancedCyclesTrader: {e}")
            return False

    async def handle_event(self, event):
        """Handle trading events (required by Strategy base class)"""
        try:
            # CRITICAL: Check if strategy is initialized
            if not hasattr(self, 'strategy_active') or not self.strategy_active:
                if not self.initialize():
                    logger.error("Strategy not initialized and initialization failed")
                    return False
                self.start_strategy()
                logger.info("Strategy initialized and started")

            # Check for duplicate event processing
            event_id = getattr(event, 'id', str(hash(str(event))))
            if event_id in self.processed_events:
                logger.info(f"Event {event_id} already processed by strategy, skipping")
                return True
            
            # Mark event as processed
            self.processed_events.add(event_id)
            
            logger.info(f"AdvancedCyclesTrader handling event: {event}")
            
            # Check if event has action attribute (real event) or content (test event)
            if hasattr(event, 'action'):
                message = event.action
                content = event.content
            else:
                # For test events, look for message in content
                content = event.content if hasattr(event, 'content') else {}
                message = content.get("message", "unknown")
            
            if message == "open_order":
                await self._handle_open_order_event(content)
            elif message == "close_cycle":
                await self._handle_close_cycle_event(content)
            elif message == "close_order":
                await self._handle_close_order_event(content)
            elif message == "stop_bot":
                self.stop_strategy()
            elif message == "start_bot":
                self.start_strategy()
            else:
                logger.info(f"Unhandled event message: {message}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error handling event in AdvancedCyclesTrader: {e}")
            return False

    async def _handle_open_order_event(self, content):
        """Handle open_order event"""
        try:
            username = content.get("user_name", "system")
            sent_by_admin = content.get("sent_by_admin", False)
            user_id = content.get("user_id", "system")
            cycle_type = content.get('type', 0)  # 0=BUY, 1=SELL, 2=BUY&SELL
            price = content.get('price', 0)
            create_cycle_in_database = content.get('create_cycle_in_database', True)  # Default to True
            
            logger.info(f"Processing open_order: type={cycle_type}, price={price}, user={username}, create_in_db={create_cycle_in_database}")
            
            # Get current market prices
            current_bid = self.meta_trader.get_bid(self.symbol)
            current_ask = self.meta_trader.get_ask(self.symbol)
            
            if current_bid is None or current_ask is None:
                logger.error("Failed to get market prices")
                return False
            
    
            # Determine direction and place order
            if cycle_type == 0:  # BUY
                await self._place_buy_order(price, current_ask, username, sent_by_admin, user_id)
            elif cycle_type == 1:  # SELL
                await self._place_sell_order(price, current_bid, username, sent_by_admin, user_id)
            elif cycle_type == 2:  # BUY&SELL (dual orders)
                await self._place_dual_orders(price, current_bid, current_ask, username, sent_by_admin, user_id)
            else:
                logger.warning(f"Unknown cycle type: {cycle_type}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error handling open_order event: {e}")
            return False

    async def _place_buy_order(self, price, current_ask, username, sent_by_admin, user_id):
        """Place a BUY order"""
        try:
            lot_size = self.config.get("lot_size", 0.01)
            
            if price == 0:
                # Market order
                order_result = self.meta_trader.buy(
                    self.symbol, lot_size, self.bot.magic_number, 0, 0, "PIPS", 10, "initial"
                )
                logger.info(f"Placed market BUY order: {order_result}")
            elif price > current_ask:
                # Buy stop order
                order_result = self.meta_trader.buy_stop(
                    self.symbol, price, lot_size, self.bot.magic_number, 0, 0, "PIPS", 10, "initial"
                )
                logger.info(f"Placed BUY STOP order at {price}: {order_result}")
            else:
                # Buy limit order
                order_result = self.meta_trader.buy_limit(
                    self.symbol, price, lot_size, self.bot.magic_number, 0, 0, "PIPS", 10, "initial"
                )
                logger.info(f"Placed BUY LIMIT order at {price}: {order_result}")
            
            if order_result and len(order_result) > 0:
                # Set entry price and activate strategy
                entry_price = price if price > 0 else current_ask
                self.set_entry_price(entry_price)
                
                # Set direction and start trading session
                self.direction_controller.execute_direction_switch("BUY", "manual_order")
                self._start_trading_session("BUY", entry_price)
                
                # Create a new cycle
                await self._create_manual_cycle(order_result[0], "BUY", username, sent_by_admin, user_id)
                
                logger.info(f"BUY order placed successfully and ACT strategy activated")
            else:
                logger.error("Failed to place BUY order")
                
        except Exception as e:
            logger.error(f"Error placing BUY order: {e}")

    async def _place_sell_order(self, price, current_bid, username, sent_by_admin, user_id):
        """Place a SELL order"""
        try:
            lot_size = self.config.get("lot_size", 0.01)
            
            if price == 0:
                # Market order
                order_result = self.meta_trader.sell(
                    self.symbol, lot_size, self.bot.magic_number, 0, 0, "PIPS", 10, "initial"
                )
                logger.info(f"Placed market SELL order: {order_result}")
            elif price < current_bid:
                # Sell stop order
                order_result = self.meta_trader.sell_stop(
                    self.symbol, price, lot_size, self.bot.magic_number, 0, 0, "PIPS", 10, "initial"
                )
                logger.info(f"Placed SELL STOP order at {price}: {order_result}")
            else:
                # Sell limit order
                order_result = self.meta_trader.sell_limit(
                    self.symbol, price, lot_size, self.bot.magic_number, 0, 0, "PIPS", 10, "initial"
                )
                logger.info(f"Placed SELL LIMIT order at {price}: {order_result}")
            
            if order_result and len(order_result) > 0:
                # Set entry price and activate strategy
                entry_price = price if price > 0 else current_bid
                self.set_entry_price(entry_price)
                
                # Set direction and start trading session
                self.direction_controller.execute_direction_switch("SELL", "manual_order")
                self._start_trading_session("SELL", entry_price)
                
                # Create a new cycle
                await self._create_manual_cycle(order_result[0], "SELL", username, sent_by_admin, user_id)
                
                logger.info(f"SELL order placed successfully and ACT strategy activated")
            else:
                logger.error("Failed to place SELL order")
                
        except Exception as e:
            logger.error(f"Error placing SELL order: {e}")

    async def _place_dual_orders(self, price, current_bid, current_ask, username, sent_by_admin, user_id):
        """Place dual BUY and SELL orders"""
        try:
            # For now, just place a BUY order and let the strategy handle direction switching
            # This can be enhanced later for true dual-order functionality
            await self._place_buy_order(price, current_ask, username, sent_by_admin, user_id)
            
        except Exception as e:
            logger.error(f"Error placing dual orders: {e}")

    async def _create_manual_cycle(self, order_data, direction, username, sent_by_admin, user_id):
        """Create a cycle from a manually placed order"""
        try:
            # Calculate stop loss and take profit based on config
            entry_price = order_data.price_open
            stop_loss_pips = self.config.get("stop_loss_pips", 50.0)
            take_profit_pips = self.config.get("take_profit_pips", 100.0)
            
            pip_value = self._get_pip_value()
            
            if direction == "BUY":
                stop_loss = entry_price - (stop_loss_pips / pip_value)
                take_profit = entry_price + (take_profit_pips / pip_value)
            else:  # SELL
                stop_loss = entry_price + (stop_loss_pips / pip_value)
                take_profit = entry_price - (take_profit_pips / pip_value)
            
            # Create new cycle using existing method
            cycle_id = self._create_new_cycle(direction, entry_price, stop_loss, take_profit)
            
            if cycle_id and self.current_cycle:
                # Add the initial order to the cycle (pass complete order data)
                logger.info(f"🎯 Adding initial order {order_data.ticket} to new manual cycle {cycle_id}")
                # Create order data from MT5 position
                order_data = {
                        'ticket': order_data.ticket,
                        'volume': getattr(order_data, 'volume', 0.01),
                        'price_open': getattr(order_data, 'price_open', 0.0),
                        'profit': getattr(order_data, 'profit', 0.0),
                        'swap': getattr(order_data, 'swap', 0.0),
                        'commission': getattr(order_data, 'commission', 0.0),
                        'sl': getattr(order_data, 'sl', 0.0),
                        'tp': getattr(order_data, 'tp', 0.0),
                        'margin': getattr(order_data, 'margin', 0.0),
                        'type': getattr(order_data, 'type', 0),  # 0=BUY, 1=SELL
                        'comment': getattr(order_data, 'comment', '')  # Store the comment for future reference
                    }
                    
                self.current_cycle.add_order(order_data)
                
                # CRITICAL FIX: Check for any missed orders after initial creation
                self.current_cycle._check_and_add_missing_orders()
                
                # Debug cycle status after adding order
                self.current_cycle.debug_order_status()
                
                # NEW: Mark this cycle as created via event and set timestamp
                self.current_cycle.created_via_event = True
                self.current_cycle.creation_time = time.time()
                
                # NEW: Set global timestamp for last event-created cycle
                self.last_event_cycle_time = time.time()
                
                logger.info(f"Manual cycle created: {cycle_id} with initial order {order_data.ticket}")
                logger.info(f"Total active cycles: {len(self.active_cycles)}")
            else:
                logger.warning(f"❌ Failed to create manual cycle - cycle_id: {cycle_id}, current_cycle: {self.current_cycle is not None}")
            
        except Exception as e:
            logger.error(f"Error creating manual cycle: {e}")

    async def _handle_close_cycle_event(self, content):
        """Handle close_cycle event with comprehensive enhanced status updates"""
        try:
            cycle_id = content.get('id') or content.get('cycle_id')
            username = content.get("user_name", "system")
            
            # Create event notification data for compatibility
            event_data = {
                "uuid": f"close_cycle_{int(time.time() * 1000)}",
                "type": "close_cycle",
                "bot_id": str(self.bot.id),
                "user_name": username,
                "timestamp": time.time(),
                "status": "in_progress",
                "cycle_id": cycle_id,
                "details": {
                    "action": "close_cycle",
                    "requested_by": username,
                    "cycle_id": cycle_id
                }
            }
            
            logger.info(f"🔄 Handling close cycle event: ID={cycle_id}, User={username}")
            
            # Check if it's a "close_all" request
            if cycle_id and cycle_id.lower() == 'all':
                result = await self._close_all_cycles_enhanced(username, event_data)
                return result
            
            # ✅ USE ENHANCED CYCLE CLOSING WITH COMPREHENSIVE STATUS UPDATES
            enhanced_content = {
                'cycle_id': cycle_id,
                'user_name': username,
                'method': 'manual_close'
            }
            
            result = await self._handle_close_cycle_event_enhanced(enhanced_content)
            
            # Update event data for compatibility
            event_data["status"] = "completed" if result else "failed"
            if result:
                event_data["details"]["enhanced_close"] = True
                event_data["details"]["status_updated"] = "active_to_inactive"
                event_data["details"]["database_updated"] = True
            
            logger.info(f"✅ Enhanced cycle closing {'completed' if result else 'failed'}: {cycle_id}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error handling close_cycle event: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return False

    async def _close_all_cycles(self, username):
        """Close all active cycles"""
        try:
            logger.info(f"🔄 Closing all cycles requested by {username}")
            
            if not self.active_cycles:
                logger.info("No active cycles to close")
                return True
            
            cycles_to_close = self.active_cycles.copy()
            closed_count = 0
            
            for cycle in cycles_to_close:
                try:
                    logger.info(f"Closing cycle {cycle.id}")
                    cycle.close_cycle(f"close_all_by_{username}")
                    self.active_cycles.remove(cycle)
                    self.closed_cycles.append(cycle)
                    closed_count += 1
                    logger.info(f"✅ Cycle {cycle.id} closed")
                except Exception as e:
                    logger.error(f"Error closing cycle {cycle.id}: {e}")
            
            # Also try to close all cycles in database for this bot
            try:
                if hasattr(self.bot, 'api_client') and self.bot.api_client:
                    api_client = self.bot.api_client
                    db_result = api_client.close_all_cycles_by_bot(str(self.bot.id))
                    if db_result:
                        logger.info("✅ All database cycles closed")
                    else:
                        logger.warning("⚠️ Failed to close some database cycles")
            except Exception as db_error:
                logger.error(f"Error closing database cycles: {db_error}")
            
            logger.info(f"✅ Closed {closed_count} cycles in memory")
            return True
            
        except Exception as e:
            logger.error(f"Error closing all cycles: {e}")
            return False

    async def _sync_cycles_from_database(self):
        """Sync active cycles from database to memory with improved detection"""
        try:
            # CRITICAL DEBUG: Check bot state before sync
            if self.bot is None:
                logger.error("🚨 CRITICAL: Bot is None during cycle sync! Cannot proceed with database operations")
                return
            
            logger.info(f"🔄 Starting cycle sync for bot: ID={self.bot.id}, Name={getattr(self.bot, 'name', 'Unknown')}")
            
            # Get all active cycles from database for this bot
            if hasattr(self.bot, 'api_client') and self.bot.api_client:
                api_client = self.bot.api_client
                
                try:
                    logger.debug(f"Requesting ACT cycles for account {self.bot.account}")
                    
                    # Get all active cycles for this bot
                    cycles_response = api_client.get_active_ACT_cycles(
                        bot_id=str(self.bot.id)
                    )
                    
                    # CRITICAL FIX: Handle both list responses and responses with 'items' attribute
                    if cycles_response:
                        # Determine cycles based on response type
                        if hasattr(cycles_response, 'items'):
                            # Response has 'items' attribute
                            cycles = cycles_response.items
                        elif isinstance(cycles_response, list):
                            # Response is a list
                            cycles = cycles_response
                        else:
                            # Unknown response type
                            logger.error(f"❌ Unknown response type from get_active_ACT_cycles: {type(cycles_response)}")
                            return
                            
                        total_cycles = len(cycles)
                        logger.info(f"Found {total_cycles} total ACT cycles in PocketBase")
                        
                        active_cycles_count = 0
                        closed_cycles_count = 0
                        
                        # Process each cycle
                        for cycle_record in cycles:
                            try:
                                # Skip closed cycles
                                if getattr(cycle_record, 'is_closed', False):
                                    closed_cycles_count += 1
                                    continue
                                
                                logger.debug(f"ACT cycle {cycle_record.id} is active - including")
                                active_cycles_count += 1
                                
                                # Convert PocketBase record to cycle data
                                cycle_data = self._convert_pocketbase_to_cycle_data(cycle_record)
                                
                                # Find existing cycle or create new one
                                existing_cycle = None
                                for cycle in self.active_cycles:
                                    if cycle.id == cycle_data.get('id'):
                                        existing_cycle = cycle
                                        break
                                
                                if existing_cycle:
                                    # Update existing cycle with data from database
                                    # This would require a cycle.update_from_data() method
                                    pass
                                else:
                                    # Create new cycle from database data
                                    try:
                                        logger.debug(f"Found bot {self.bot.id} for cycle {cycle_data.get('id')}")
                                        
                                        # Import here to avoid circular imports
                                        from cycles.ACT_cycle import AdvancedCycle
                                        
                                        # Create new cycle instance
                                        new_cycle = AdvancedCycle(
                                            cycle_data=cycle_data,
                                            meta_trader=self.meta_trader,
                                            bot=self.bot
                                        )
                                        
                                        # # CRITICAL: Set as current cycle (for now, just use the most recent one)
                                        # if not self.current_cycle:
                                        #     self.current_cycle = new_cycle
                                            
                                        #     # CRITICAL: Restart trading session for loaded cycle
                                        #     if new_cycle.current_direction and new_cycle.current_direction != "HOLD":
                                        #         logger.info(f"🔄 Restarting trading session for loaded cycle: {new_cycle.id}")
                                                
                                        #         # Set direction in controller
                                        #         self.direction_controller.execute_direction_switch(
                                        #             new_cycle.current_direction, "cycle_resume"
                                        #         )
                                                
                                        #         # Set entry price if available
                                        #         if hasattr(new_cycle, 'entry_price') and new_cycle.entry_price:
                                        #             self.set_entry_price(new_cycle.entry_price)
                                        #         elif hasattr(new_cycle, 'zone_base_price') and new_cycle.zone_base_price:
                                        #             self.set_entry_price(new_cycle.zone_base_price)
                                                
                                        #         # Restart trading session with cycle parameters
                                        #         current_price = self.meta_trader.get_ask(self.symbol) if hasattr(self.meta_trader, 'get_ask') else new_cycle.entry_price
                                        #         self._start_trading_session(new_cycle.current_direction, current_price)
                                                
                                        #         # Set flags to indicate resumed state
                                        #         if hasattr(new_cycle, 'zone_activated') and new_cycle.zone_activated:
                                        #             self.zone_activated = True
                                        #         if hasattr(new_cycle, 'initial_threshold_breached') and new_cycle.initial_threshold_breached:
                                        #             self.initial_threshold_breached = True
                                                    
                                        #         logger.info(f"✅ Trading session resumed for cycle {new_cycle.id} - Direction: {new_cycle.current_direction}")
                                        
                                        # Add to active cycles list
                                        self.active_cycles.append(new_cycle)
                                        
                                        # Add to multi-cycle manager if available
                                        if hasattr(self, 'multi_cycle_manager'):
                                            self.multi_cycle_manager.add_cycle(new_cycle)
                                            
                                        logger.info(f"✅ Synced cycle {new_cycle.id} from database (Direction: {new_cycle.current_direction})")
                                            
                                    except Exception as cycle_error:
                                        logger.error(f"Error creating cycle from database: {cycle_error}")
                            
                            except Exception as record_error:
                                logger.error(f"Error processing cycle record: {record_error}")
                        
                        # CRITICAL: Verify sync between main active_cycles and multi_cycle_manager
                        if hasattr(self, 'multi_cycle_manager'):
                            main_cycle_ids = {c.id for c in self.active_cycles}
                            manager_cycle_ids = set(self.multi_cycle_manager.active_cycles.keys())
                            
                            # Log sync status
                            logger.info(f"Cycle sync status - Main: {len(main_cycle_ids)} cycles, Manager: {len(manager_cycle_ids)} cycles")
                            
                            # Identify cycles missing from manager
                            missing_in_manager = main_cycle_ids - manager_cycle_ids
                            if missing_in_manager:
                                logger.warning(f"Found {len(missing_in_manager)} cycles missing from multi-cycle manager")
                                for cycle_id in missing_in_manager:
                                    cycle = next((c for c in self.active_cycles if c.id == cycle_id), None)
                                    if cycle:
                                        logger.info(f"🔄 Adding missing cycle {cycle_id} to multi-cycle manager")
                                        self.multi_cycle_manager.add_cycle(cycle)
                        
                        logger.info(f"ACT cycles summary: {active_cycles_count} active, {closed_cycles_count} closed")
                        logger.info(f"✅ Cycle sync completed - {len(self.active_cycles)} cycles loaded")
                    else:
                        logger.info("No ACT cycles found in database")
                    
                except Exception as api_error:
                    logger.error(f"API error during cycle sync: {api_error}")
            else:
                logger.error("Bot has no API client, cannot sync cycles from database")
                
        except Exception as e:
            logger.error(f"Error syncing cycles from database: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")

    async def _close_cycle_in_database(self, cycle_id, username):
        """Close cycle directly in database"""
        try:
            if hasattr(self.bot, 'api_client') and self.bot.api_client:
                api_client = self.bot.api_client
                
                # Update cycle in database to closed status
                update_data = {
                    "is_closed": True,
                    "closed_by": username,
                    "closed_at": datetime.datetime.now().isoformat()
                }
                
                result = api_client.update_ACT_cycle_by_id(cycle_id, update_data)
                if result:
                    logger.info(f"✅ Cycle {cycle_id} closed in database by {username}")
                    return True
                else:
                    logger.error(f"❌ Failed to close cycle {cycle_id} in database")
                    return False
            else:
                logger.error("No API client available for database operations")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to close cycle {cycle_id} in database")
            return False

    async def _send_close_cycle_event_to_pocketbase(self, event_data):
        """Send close cycle event notification to PocketBase"""
        try:
            if hasattr(self.bot, 'api_client') and self.bot.api_client:
                api_client = self.bot.api_client
                
                # Create event record in PocketBase
                event_record_data = {
                    "uuid": event_data["uuid"],
                    "content": event_data["content"],
                    "bot_id": event_data["bot_id"],
                    "user_name": event_data["user_name"],
                    "timestamp": datetime.datetime.now().isoformat(),
                    "status": event_data["status"],
                    "data": json.dumps(event_data["details"]),
                }
                
                # Try to create event in Events collection
                try:
                    result = api_client.client.collection("Events").create(event_record_data)
                    logger.info(f"✅ Close cycle event sent to PocketBase: {event_data['uuid']}")
                    return True
                except Exception as create_error:
                    logger.warning(f"⚠️ Could not create event in Events collection: {create_error}")
                    # Fallback: log the event locally
                    logger.info(f"📝 Close cycle event (local): {json.dumps(event_data, indent=2)}")
                    return False
            else:
                logger.warning("No API client available for event notification")
                return False
                
        except Exception as e:
            logger.error(f"Error sending close cycle event to PocketBase: {e}")
            return False

    async def _close_all_cycles_enhanced(self, username, event_data):
        """Enhanced close all cycles with comprehensive status updates and database synchronization"""
        try:
            logger.info(f"🔄 Enhanced close all cycles requested by {username}")
            
            if not self.active_cycles:
                logger.info("No active cycles to close")
                event_data["details"]["message"] = "No active cycles to close"
                return True
            
            cycles_to_close = self.active_cycles.copy()
            closed_count = 0
            total_orders_closed = 0
            total_orders_failed = 0
            
            # Update event data with cycle count
            event_data["details"]["total_cycles"] = len(cycles_to_close)
            
            for cycle in cycles_to_close:
                try:
                    logger.info(f"🔄 Enhanced closing cycle {cycle.id}")
                    
                    # ✅ USE ENHANCED CYCLE CLOSING FOR EACH CYCLE
                    enhanced_content = {
                        'cycle_id': cycle.id,
                        'user_name': username,
                        'method': f'close_all_by_{username}'
                    }
                    
                    result = await self._handle_close_cycle_event_enhanced(enhanced_content)
                    
                    if result:
                        closed_count += 1
                        logger.info(f"✅ Cycle {cycle.id} enhanced closing completed")
                    else:
                        logger.error(f"❌ Cycle {cycle.id} enhanced closing failed")
                        
                except Exception as e:
                    logger.error(f"Error in enhanced closing of cycle {getattr(cycle, 'id', 'unknown')}: {e}")
            
            # Also try to close all cycles in database for this bot
            try:
                if hasattr(self.bot, 'api_client') and self.bot.api_client:
                    api_client = self.bot.api_client
                    db_result = api_client.close_all_cycles_by_bot(str(self.bot.id))
                    if db_result:
                        logger.info("✅ All database cycles closed")
                    else:
                        logger.warning("⚠️ Failed to close some database cycles")
            except Exception as db_error:
                logger.error(f"Error closing database cycles: {db_error}")
            
            # Update bot configuration after closing all cycles
            await self._update_bot_config_on_cycle_close("all", username)
            
            # Update event data with results
            event_data["details"].update({
                "cycles_closed": closed_count,
                "total_orders_closed": total_orders_closed,
                "close_all_completed": True,
                "enhanced_close_used": True,
                "status_updates": "active_to_inactive",
                "database_synchronized": True
            })
            
            logger.info(f"✅ Enhanced close all complete: {closed_count} cycles closed with comprehensive status updates")
            return True
            
        except Exception as e:
            logger.error(f"Error in enhanced close all cycles: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            event_data["details"]["error"] = str(e)
            return False

    async def _close_all_cycle_orders(self, cycle):
        """Close all MetaTrader orders for a specific cycle"""
        try:
            orders_closed = 0
            
            if not hasattr(cycle, 'active_orders') or not cycle.active_orders:
                logger.info(f"No orders found for cycle {cycle.id}")
                return orders_closed
            
            logger.info(f"🔄 Closing {len(cycle.active_orders)} orders for cycle {cycle.id}")
            
            for order in cycle.active_orders:
                try:
                    # Get order ticket/ID
                    order_ticket =order['ticket']
                    
                    if order_ticket:
                        # Check if order is still open in MetaTrader
                        if hasattr(self.meta_trader, 'get_position_by_ticket') and self.meta_trader.get_position_by_ticket(order_ticket):
                            # Close the order/position
                            close_result = self.meta_trader.close_position(order)
                            if close_result:
                                orders_closed += 1
                                logger.info(f"✅ Closed order {order_ticket} for cycle {cycle.id}")
                            else:
                                logger.warning(f"⚠️ Failed to close order {order_ticket} for cycle {cycle.id}")
                        else:
                            logger.info(f"📝 Order {order_ticket} already closed or not found in MetaTrader")
                    else:
                        logger.warning(f"⚠️ Order has no ticket/ID: {order}")
                        
                except Exception as order_error:
                    logger.error(f"Error closing individual order: {order_error}")
                    continue
            
            logger.info(f"✅ Closed {orders_closed} orders for cycle {cycle.id}")
            return orders_closed
            
        except Exception as e:
            logger.error(f"Error closing orders for cycle {getattr(cycle, 'id', 'unknown')}: {e}")
            return 0

    async def _close_all_cycle_orders_enhanced(self, cycle, closing_method="manual", username="system"):
        """Enhanced order closing with comprehensive status updates"""
        try:
            import datetime
            
            orders_closed = 0
            orders_failed = 0
            closing_timestamp = datetime.datetime.utcnow()
            
            if not hasattr(cycle, 'active_orders') or not cycle.active_orders:
                logger.info(f"No active orders found for cycle {cycle.cycle_id}")
                return {"orders_closed": 0, "orders_failed": 0, "failed_orders": []}
            
            logger.info(f"🔄 Enhanced closing of {len(cycle.active_orders)} orders for cycle {cycle.cycle_id}")
            
            failed_orders = []
            orders_to_move = []
            
            for order in cycle.active_orders:
                try:
                    order_ticket = order.get('ticket')
                    
                    if not order_ticket:
                        logger.warning(f"⚠️ Order has no ticket/ID: {order}")
                        orders_failed += 1
                        continue
                    
                    # Close order in MetaTrader
                    close_result = self._close_order_in_mt5(order_ticket, order)
                    
                    if close_result:
                        # ✅ SUCCESS: Update order status to inactive
                        order.update({
                            "status": "inactive",          # ← KEY REQUIREMENT
                            "is_active": False,
                            "is_closed": True,
                            "close_time": closing_timestamp.isoformat(),
                            "close_reason": closing_method,
                            "closed_by": username,
                            "closing_method": {            # ← KEY REQUIREMENT
                                "type": closing_method,
                                "user": username,
                                "timestamp": closing_timestamp.isoformat(),
                                "method_details": f"Order closed via {closing_method}"
                            }
                        })
                        
                        # Add to orders to move to completed
                        orders_to_move.append(order)
                        orders_closed += 1
                        
                        logger.info(f"✅ Order {order_ticket} status updated to inactive")
                        
                    else:
                        # ❌ FAILED: Mark as failed but still update status
                        order.update({
                            "status": "close_failed",
                            "is_active": False,  # Still mark as inactive even if close failed
                            "close_attempt_time": closing_timestamp.isoformat(),
                            "close_failure_reason": "MetaTrader close failed"
                        })
                        failed_orders.append(order)
                        orders_failed += 1
                        
                except Exception as e:
                    logger.error(f"Error closing order {order.get('ticket')}: {e}")
                    failed_orders.append(order)
                    orders_failed += 1
            
            # Move successfully closed orders to completed_orders
            for order in orders_to_move:
                cycle.completed_orders.append(order)
            
            # Clear active orders (they're all moved to completed or failed)
            cycle.active_orders.clear()
            
            logger.info(f"✅ Enhanced order closing complete: {orders_closed} closed, {orders_failed} failed")
            
            return {
                "orders_closed": orders_closed, 
                "orders_failed": orders_failed,
                "failed_orders": failed_orders
            }
            
        except Exception as e:
            logger.error(f"Error in enhanced order closing: {e}")
            return {"error": str(e), "orders_closed": 0, "orders_failed": 0}

    def _close_order_in_mt5(self, order_ticket, order_data):
        """Helper method to close individual order in MetaTrader"""
        try:
            # Check if order is still open in MetaTrader
            if hasattr(self.meta_trader, 'get_position_by_ticket'):
                position = self.meta_trader.get_position_by_ticket(order_ticket)
                if position:
                    # Close the position
                    close_result = self.meta_trader.close_position(order_data)
                    return bool(close_result)
                else:
                    # Order already closed or not found
                    logger.info(f"📝 Order {order_ticket} already closed or not found in MetaTrader")
                    return True  # Consider as successfully closed
            else:
                logger.warning("MetaTrader close_position method not available")
                return False
                
        except Exception as e:
            logger.error(f"Error closing order {order_ticket} in MT5: {e}")
            return False

    async def _update_cycle_status_on_close(self, cycle, closing_method, username="system"):
        """Update cycle status from active to inactive with full tracking"""
        try:
            import datetime
            
            closing_timestamp = datetime.datetime.utcnow()
            
            # ✅ UPDATE CYCLE STATUS - KEY REQUIREMENTS
            cycle.is_active = False              # ← Active to Inactive
            cycle.is_closed = True
            cycle.status = "inactive"            # ← KEY REQUIREMENT
            cycle.close_time = closing_timestamp
            cycle.close_reason = closing_method
            cycle.closed_by = username
            
            # ✅ SET CLOSING METHOD - KEY REQUIREMENT  
            cycle.closing_method = {
                "type": closing_method,          # ← KEY REQUIREMENT
                "user": username,
                "timestamp": closing_timestamp.isoformat(),
                "details": f"Cycle closed via {closing_method}",
                "final_profit": getattr(cycle, 'total_profit', 0.0) or 0.0,
                "total_orders": len(getattr(cycle, 'completed_orders', [])),
                "duration_minutes": self._calculate_cycle_duration(cycle)
            }
            
            # Calculate final statistics
            if hasattr(cycle, '_calculate_final_statistics'):
                cycle._calculate_final_statistics()
            
            logger.info(f"✅ Cycle {cycle.id} status updated: active → inactive")
            logger.info(f"✅ Closing method set: {closing_method} by {username}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating cycle status: {e}")
            return False

    def _calculate_cycle_duration(self, cycle):
        """Calculate cycle duration in minutes"""
        try:
            if hasattr(cycle, 'start_time') and hasattr(cycle, 'close_time'):
                if cycle.start_time and cycle.close_time:
                    duration = cycle.close_time - cycle.start_time
                    return duration.total_seconds() / 60
            return 0
        except Exception as e:
            logger.error(f"Error calculating cycle duration: {e}")
            return 0

    async def _update_database_on_cycle_close(self, cycle, closing_details):
        """Update cycle in database when closing"""
        try:
            if not hasattr(self.bot, 'api_client') or not self.bot.api_client:
                logger.error("No API client available for database update")
                return False
                
            api_client = self.bot.api_client
            
            # Prepare update data
            update_data = {
                "is_closed": True,
                "closed_by": closing_details.get("username", "system"),
                "closed_at": datetime.datetime.now().isoformat(),
                "closing_method": closing_details.get("closing_method", "manual"),
                "orders_closed": closing_details.get("orders_closed", 0),
                "orders_failed": closing_details.get("orders_failed", 0)
            }
            
            # ✅ UPDATE CYCLE IN DATABASE
            if hasattr(cycle, 'cycle_id') and cycle.cycle_id:
                result = api_client.update_ACT_cycle_by_id(cycle.cycle_id, update_data)
                if result:
                    logger.info(f"✅ Database updated: Cycle {cycle.id} status → inactive")
                    logger.info(f"✅ Database updated: Closing method → {cycle.close_reason}")
                    return True
                else:
                    logger.error(f"❌ Failed to update cycle {cycle.id} in database")
                    return False
            else:
                logger.error(f"❌ Cycle {cycle.id} has no database ID")
                return False
                
        except Exception as e:
            logger.error(f"Error updating database on cycle close: {e}")
            return False

    def _find_cycle_by_id(self, cycle_id):
        """Helper method to find cycle by ID in active cycles"""
        try:
            for cycle in self.active_cycles:
                if hasattr(cycle, 'cycle_id') and cycle.cycle_id == cycle_id:
                    return cycle
            return None
        except Exception as e:
            logger.error(f"Error finding cycle {cycle_id}: {e}")
            return None

    async def _handle_close_cycle_event_enhanced(self, content):
        """Enhanced cycle closing with comprehensive status and database updates"""
        try:
            cycle_id = content.get('cycle_id')
            username = content.get("user_name", "system")
            closing_method = content.get("method", "manual_close")
            
            if not cycle_id:
                logger.error("No cycle_id provided in close cycle event")
                return False
            
            # Find the cycle
            cycle = self._find_cycle_by_id(cycle_id)
            if not cycle:
                logger.error(f"Cycle {cycle_id} not found in active cycles")
                
                # Try to close the cycle directly in the database if it exists there
                try:
                    logger.info(f"🔄 Attempting to close cycle {cycle_id} directly in database")
                    result = await self._close_cycle_in_database_enhanced(cycle_id, username)
                    return result
                except Exception as db_error:
                    logger.error(f"Failed to close cycle in database: {db_error}")
                    return False
            
            logger.info(f"🔄 Starting enhanced close process for cycle {cycle_id}")
            
            # ✅ STEP 1: Close all orders with status updates
            close_result = await self._close_all_cycle_orders_enhanced(
                cycle, closing_method, username
            )
            
            if "error" in close_result:
                logger.error(f"❌ Error in enhanced order closing: {close_result['error']}")
                return False
            
            # ✅ STEP 2: Update cycle status (active → inactive)
            status_updated = await self._update_cycle_status_on_close(
                cycle, closing_method, username
            )
            
            # ✅ STEP 3: Update database with all changes
            db_updated = await self._update_database_on_cycle_close(cycle, {
                "username": username,
                "closing_method": closing_method,
                "orders_closed": close_result.get("orders_closed", 0),
                "orders_failed": close_result.get("orders_failed", 0)
            })
            
            # ✅ STEP 4: Remove from active cycles
            if cycle in self.active_cycles:
                self.active_cycles.remove(cycle)
                self.closed_cycles.append(cycle)
            
            # ✅ STEP 5: Update bot configuration
            await self._update_bot_config_on_cycle_close(cycle_id, username)
            
            # ✅ FINAL VERIFICATION
            if status_updated and db_updated:
                logger.info(f"✅ COMPLETE: Cycle {cycle_id} successfully closed")
                logger.info(f"   - Orders closed: {close_result.get('orders_closed', 0)}")
                logger.info(f"   - Orders failed: {close_result.get('orders_failed', 0)}")
                logger.info(f"   - Cycle status: active → inactive")
                logger.info(f"   - Closing method: {closing_method}")
                logger.info(f"   - Database updated: ✅")
                return True
            else:
                logger.error(f"❌ INCOMPLETE: Cycle {cycle_id} close process had errors")
                logger.error(f"   - Status updated: {status_updated}")
                logger.error(f"   - Database updated: {db_updated}")
                return False
                
        except Exception as e:
            logger.error(f"Error in enhanced cycle closing: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return False

    async def _update_bot_config_on_cycle_close(self, cycle_id, username):
        """Update bot configuration when cycles are closed"""
        try:
            if hasattr(self.bot, 'api_client') and self.bot.api_client:
                api_client = self.bot.api_client
                
                # Get current bot configuration
                current_bot = api_client.get_account_bots_by_id(self.bot.id)
                if current_bot and len(current_bot) > 0:
                    bot_data = current_bot[0]
                    
                    # Update bot settings to reflect cycle closure
                    updated_settings = getattr(bot_data, 'settings', {})
                    if not isinstance(updated_settings, dict):
                        updated_settings = {}
                    
                    # Add cycle closure information
                    updated_settings.update({
                        "last_cycle_closed": cycle_id,
                        "last_cycle_closed_by": username,
                        "last_cycle_closed_at": datetime.datetime.now().isoformat(),
                        "active_cycles_count": len(self.active_cycles),
                        "closed_cycles_count": len(self.closed_cycles)
                    })
                    
                    # If all cycles are closed, consider stopping the bot
                    if len(self.active_cycles) == 0:
                        updated_settings["all_cycles_closed"] = True
                        logger.info(f"🛑 All cycles closed for bot {self.bot.id}")
                    
                    # Update bot in database
                    update_data = {"settings": updated_settings}
                    result = api_client.client.collection("bots").update(self.bot.id, update_data)
                    
                    if result:
                        logger.info(f"✅ Bot configuration updated for cycle closure: {cycle_id}")
                        return True
                    else:
                        logger.warning(f"⚠️ Failed to update bot configuration")
                        return False
                else:
                    logger.warning(f"⚠️ Bot {self.bot.id} not found for configuration update")
                    return False
            else:
                logger.warning("No API client available for bot configuration update")
                return False
                
        except Exception as e:
            logger.error(f"Error updating bot configuration on cycle close: {e}")
            return False

    async def _close_cycle_in_database_enhanced(self, cycle_id, username):
        """Enhanced close cycle directly in database with comprehensive tracking"""
        try:
            if hasattr(self.bot, 'api_client') and self.bot.api_client:
                api_client = self.bot.api_client
                
                # First, try to get the cycle to verify it exists
                try:
                    existing_cycles = api_client.get_ACT_cycle_by_id(cycle_id)
                    if not existing_cycles or len(existing_cycles) == 0:
                        logger.warning(f"⚠️ Cycle {cycle_id} not found in database")
                        return False
                except Exception as get_error:
                    logger.error(f"Error checking cycle existence: {get_error}")
                    return False
                
                # Update cycle in database to closed status
                update_data = {
                    "is_closed": True,
                    "closed_by": username,
                    "closed_at": datetime.datetime.now().isoformat(),
                    "closure_method": "database_direct"
                }
                
                result = api_client.update_ACT_cycle_by_id(cycle_id, update_data)
                if result:
                    logger.info(f"✅ Cycle {cycle_id} closed in database by {username}")
                    
                    # Also try to close any associated orders in the database
                    await self._close_cycle_orders_in_database(cycle_id)
                    
                    return True
                else:
                    logger.error(f"❌ Failed to close cycle {cycle_id} in database")
                    return False
            else:
                logger.error("No API client available for database operations")
                return False
                
        except Exception as e:
            logger.error(f"❌ Enhanced database close failed for cycle {cycle_id}: {e}")
            return False

    async def _close_cycle_orders_in_database(self, cycle_id):
        """Close orders associated with a cycle in the database"""
        try:
            if hasattr(self.bot, 'api_client') and self.bot.api_client:
                api_client = self.bot.api_client
                
                # This would need to be implemented based on your order tracking system
                # For now, just log the action
                logger.info(f"📝 Attempting to close orders for cycle {cycle_id} in database")
                
                # If you have an orders collection that tracks cycle relationships,
                # you would update those records here
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error closing cycle orders in database: {e}")
            return False

    async def _handle_close_order_event(self, content):
        """Handle close_order event"""
        try:
            ticket = content.get('ticket')
            cycle_id = content.get('cycle_id')
            username = content.get("user_name", "system")
            
            if not ticket:
                logger.error("No ticket provided in close_order event")
                return False
                
            logger.info(f"Processing close_order for ticket {ticket} by {username}")
            
            # Find the order in MT5 positions
            positions = self.meta_trader.get_positions()
            if not positions:
                logger.warning("No positions found in MT5")
                return False

            order_to_close = None
            for position in positions:
                if str(position.ticket) == str(ticket):
                    order_to_close = position
                    break
            
            if not order_to_close:
                logger.warning(f"Order with ticket {ticket} not found in MT5 positions")
                return False

            # Close the order using MT5
            try:
                close_result = self.meta_trader.close_order(order_to_close, 30)
                if close_result:
                    logger.info(f"✅ Order {ticket} closed successfully")
                    
                    # IMMEDIATELY PLACE REPLACEMENT ORDER IN OPPOSITE DIRECTION
                    if self.order_manager and self.trading_active:
                        replacement_ticket = self.order_manager.handle_order_close(str(ticket), "manual_close")
                        if replacement_ticket:
                            logger.info(f"🔄 Replacement order placed: {replacement_ticket}")
                            
                            # Add to current cycle if exists
                            if self.current_cycle:
                                self.current_cycle.add_order(replacement_ticket)
                        else:
                            logger.warning("Failed to place replacement order")
                    
                    # Update the cycle if cycle_id is provided
                    if cycle_id and self.current_cycle and self.current_cycle.id == cycle_id:
                        # Force update the cycle to reflect the closed order
                        self.current_cycle._check_and_add_missing_orders()
                        self.current_cycle.debug_order_status()
                        logger.info(f"Updated cycle {cycle_id} after closing order {ticket}")
                    
                    return True
                else:
                    logger.error(f"❌ Failed to close order {ticket}")
                    return False
                
            except Exception as close_error:
                logger.error(f"Error closing order {ticket}: {close_error}")
                return False
                
        except Exception as e:
            logger.error(f"Error handling close_order event: {e}")
            return False

    def start_strategy(self):
        """Start the Advanced Cycles Trader strategy"""
        try:
            if self.strategy_active:
                logger.warning("Strategy already active")
                return True
            
            # Initialize in-memory loss tracker
            # ACTRepo removed - using in-memory operations
            
            # if not self.loss_tracker:
            #     logger.error("Failed to initialize loss tracker")
            #     return False
            
            # Sync existing cycles from database - FIXED: Use safer approach to handle event loops
            try:
                # Check if we're already in an event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        logger.info("Event loop already running, skipping immediate sync")
                        # Schedule the sync for later when we're in the event loop
                        asyncio.create_task(self._schedule_sync_cycles())
                    else:
                        # We have a loop but it's not running
                        loop.run_until_complete(self._sync_cycles_from_database())
                except RuntimeError:
                    # No event loop in this thread, create one
                    logger.info("Creating new event loop for cycle sync")
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self._sync_cycles_from_database())
                    # Don't close the loop as it might be needed later
            except Exception as sync_error:
                logger.warning(f"Failed to sync cycles from database: {sync_error}")
            
            # Start monitoring thread
            self.strategy_active = True
            self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
            self.monitoring_thread.start()
            
            logger.info("AdvancedCyclesTrader strategy started")
            return True
            
        except Exception as e:
            logger.error(f"Error starting strategy: {e}")
            return False
            
    async def _schedule_sync_cycles(self):
        """Helper method to schedule cycle sync when already in an event loop"""
        try:
            logger.info("Scheduled cycle sync running")
            await self._sync_cycles_from_database()
            logger.info("Scheduled cycle sync completed")
        except Exception as e:
            logger.error(f"Error in scheduled cycle sync: {e}")
            
    def stop_strategy(self):
        """Stop the Advanced Cycles Trader strategy"""
        try:
            self.strategy_active = False
            self.trading_active = False
            
            # Stop order placement
            self.order_manager.stop_continuous_placement()
            
            # Close any open cycles
            for cycle in self.active_cycles:
                try:
                    cycle.close_cycle("strategy_stopped")
                except Exception as e:
                    logger.error(f"Error closing cycle {cycle.id}: {e}")
            
            logger.info("AdvancedCyclesTrader strategy stopped")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping strategy: {e}")
            return False

    def _monitoring_loop(self):
        """Main monitoring loop for the strategy"""
        try:
            while self.strategy_active:
                try:
                    # Get current market data
                    market_data = self._get_market_data()
                    
                    if not market_data:
                        time.sleep(1)
                        continue
                    
                    self.current_market_price = market_data["current_price"]
                    
                    # Process strategy logic
                    self._process_strategy_logic(market_data)
                    
                    # Update active cycles - FIXED: Use synchronous version
                    self._update_active_cycles_sync()
                    
                    # Monitor order management
                    self._monitor_order_management(market_data)
                    
                    # Sleep for 1 second before next iteration
                    time.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Error in monitoring loop: {e}")
                    time.sleep(5)  # Wait longer on error
                    
        except Exception as e:
            logger.error(f"Fatal error in monitoring loop: {e}")
            self.strategy_active = False

    def _update_active_cycles_sync(self):
        """Synchronous version of _update_active_cycles to avoid coroutine issues"""
        try:
            if not self.active_cycles:
                return
            
            # Get current market price
            current_price = self.meta_trader.get_bid(self.symbol)
            
            # Update each active cycle
            for cycle in self.active_cycles[:]:  # Create a copy of the list to avoid modification during iteration
                try:
                    # Check for initial order stop loss
                    if self._check_initial_order_stop_loss(cycle, current_price):
                        logger.warning(f"Stop loss hit for cycle {cycle.id} - skipping update in sync context")
                        continue
                    
                    # Update cycle status and orders
                    cycle.update_cycle_status()
                    
                    # CRITICAL: Check for missing orders in each cycle
                    cycle._check_and_add_missing_orders()
                    
                    # Update cycle in database
                    cycle._update_cycle_in_database()
                    
                except Exception as e:
                    logger.error(f"Error updating cycle {cycle.id}: {e}")
            
            # ENHANCED: Global missing order detection and organization - Skip async call
            logger.debug("Skipping async missing order detection in sync context")
            
        except Exception as e:
            logger.error(f"Error updating active cycles: {e}")

    async def _update_active_cycles(self):
        """Update all active cycles and handle missing orders"""
        try:
            if not self.active_cycles:
                return
            
            # Get current market price
            current_price = self.meta_trader.get_bid(self.symbol)
            
            # Update each active cycle
            for cycle in self.active_cycles[:]:  # Create a copy of the list to avoid modification during iteration
                try:
                    # Check for initial order stop loss
                    if self._check_initial_order_stop_loss(cycle, current_price):
                        await self._close_initial_order_stop_loss(cycle, current_price)
                        continue
                    
                    # Update cycle status and orders
                    cycle.update_cycle_status()
                    
                    # CRITICAL: Check for missing orders in each cycle
                    cycle._check_and_add_missing_orders()
                    
                    # Update cycle in database
                    cycle._update_cycle_in_database()
                    
                except Exception as e:
                    logger.error(f"Error updating cycle {cycle.id}: {e}")
            
            # ENHANCED: Global missing order detection and organization
            await self._detect_and_organize_missing_orders()
            
        except Exception as e:
            logger.error(f"Error updating active cycles: {e}")

    def _process_strategy_logic(self, market_data):
        """Process the main strategy logic"""
        try:
            current_price = market_data["current_price"]
            candle_data = market_data.get("candle", {})
            
            # Step 1: Check for initial threshold breach
            if not self.initial_threshold_breached and self.entry_price:
                # Use enhanced zone detection's detect_zone_breach method
                breach_result = self.zone_engine.detect_zone_breach(current_price, self.entry_price)
                if breach_result.get("breach_detected", False):
                    self._handle_threshold_breach(current_price, candle_data)
            
            # Step 2: Monitor active zone
            if self.zone_activated:
                self._monitor_active_zone(current_price, candle_data)
            
            # Step 3: Manage continuous order placement
            if self.trading_active:
                self._manage_continuous_orders(current_price, candle_data)
            
            # Step 4: Check for direction switches
            self._check_direction_switches(current_price, candle_data)
            
        except Exception as e:
            logger.error(f"Error processing strategy logic: {e}")

    def _handle_threshold_breach(self, current_price, candle_data):
        """Handle initial threshold breach with zone-based trading"""
        try:
            if not self.initial_threshold_breached:
                logger.info("🎯 Initial threshold breach detected")
                
                # Get current market data
                current_bid = candle_data.get("bid", current_price)
                current_ask = candle_data.get("ask", current_price)
                
                # Determine direction based on price movement
                direction = "BUY" if current_price > self.entry_price else "SELL"
                
                # Generate unique zone ID
                zone_id = f"zone_{int(time.time())}"
                
                # Place initial order
                order_ticket = None
                if direction == "BUY":
                    order_result = self.meta_trader.place_buy_order(
                        symbol=self.symbol,
                        volume=self.lot_size,
                        price=current_ask,
                        stop_loss=0.0,
                        take_profit=0.0,
                        comment="ini1",
                        
                    )
                    if order_result and order_result['order']:
                        order_ticket = order_result['order']['ticket']
                else:  # SELL
                    order_result = self.meta_trader.place_sell_order(
                        symbol=self.symbol,
                        volume=self.lot_size,
                        price=current_bid,
                        stop_loss=0.0,
                        take_profit=0.0,
                        comment="ini1",
                    )
                    if order_result and order_result['order']:
                        order_ticket = order_result['order']['ticket']
                
                if order_ticket:
                    logger.info(f"✅ Initial order placed: Ticket={order_ticket}")
                    
                    # Get order data from MT5
                    order_data = self.meta_trader.get_position_by_ticket(order_ticket)
                    if not order_data:
                        logger.error("❌ Failed to get order data from MT5")
                        return
                    # Create manual cycle with the order (schedule as task)
                    try:
                        # Get or create event loop
                        self._create_manual_cycle(
                            order_data=order_data,
                            direction=direction,
                            username="system",
                            sent_by_admin=False,
                            user_id="system"
                        )
                        
                    except Exception as e:
                        logger.error(f"Failed to schedule manual cycle creation: {e}")
                        import traceback
                        logger.error(f"Traceback: {traceback.format_exc()}")
                    
                    # Update strategy state
                    self.initial_threshold_breached = True
                    self.zone_activated = True
                    
                    # Update loss tracking
                    self._update_loss_tracking(order_ticket, "initial_threshold_breach")
                    
                    logger.info("✅ Initial threshold breach handled successfully")
                    
                else:
                    logger.warning("❌ Failed to place initial order for threshold breach")
                    
        except Exception as e:
            logger.error(f"Error handling threshold breach: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")

    def _should_create_new_cycle_every_candle(self, current_time: float) -> bool:
        """
        Check if a new cycle should be created for this candle (multi-cycle logic)
        
        Args:
            current_time: Current timestamp
            
        Returns:
            bool: True if new cycle should be created
        """
        # Disable creating cycles on every candle - cycles are now created on threshold breaches
        return False

    def _monitor_active_zone(self, current_price, candle_data):
        """Monitor the active zone for price level completion"""
        try:
            # Get active zones from enhanced zone detection
            active_zones = self.zone_engine.get_active_zones()
            if not active_zones:
                return
            
            current_direction = self.direction_controller.get_current_direction()
            
            if current_direction:
                # Check each active zone for state changes
                for zone in active_zones:
                    zone_id = zone.get('zone_id')
                    if not zone_id:
                        continue
                    
                    # Update zone state with current price
                    zone_update = self.zone_engine.detect_zone_breach(
                        current_price,
                        zone.get('base_price', current_price),
                        threshold_pips=zone.get('threshold_pips', self.reversal_threshold_pips)
                    )
                    
                    # Check if zone state changed
                    if zone_update.get('previous_state') != zone_update.get('zone_state'):
                        logger.info(f"Zone {zone_id} state changed: {zone_update.get('previous_state')} -> {zone_update.get('zone_state')}")
                
                # Check if we should continue orders based on zone states
                continue_orders = any(zone.get('zone_state') in ['monitoring', 'breached'] for zone in active_zones)
                
                if not continue_orders:
                    logger.info("No active zones in monitoring or breached state - deactivating zone")
                    # Clean up old zones
                    self.zone_engine.cleanup_old_zones()
                    self.zone_activated = False
            
        except Exception as e:
            logger.error(f"Error monitoring active zone: {e}")

    def _manage_continuous_orders(self, current_price, candle_data):
        """MULTI-CYCLE MANAGEMENT: Create and manage multiple cycles simultaneously"""
        try:
            if not self.trading_active:
                return
            
            # If we still don't have cycles, return early
            if not self.active_cycles:
                return
    
            current_time = datetime.datetime.utcnow()
            timestamp = time.time()
            
            # MANAGE ALL ACTIVE CYCLES
            management_results = self.multi_cycle_manager.manage_all_cycles(current_price, candle_data, self.active_cycles)
            
            if management_results.get("error"):
                logger.error(f"Multi-cycle management error: {management_results['error']}")
            else:
                logger.debug(f"Multi-cycle management: {management_results['cycles_processed']} cycles, "
                           f"{management_results['orders_placed']} orders placed")
            
            # ZONE BREACH DETECTION AND REVERSAL CYCLES
            self._check_zone_breaches_and_reversals(current_price, candle_data)
            
            # Log multi-cycle statistics
            total_orders_placed = management_results.get('orders_placed', 0)
            if total_orders_placed > 0:
                logger.info(f"📊 Multi-cycle summary: {len(self.active_cycles)} active cycles, "
                           f"{total_orders_placed} orders placed this candle")
            
        except Exception as e:
            logger.error(f"Error in multi-cycle management: {e}")


    def _check_zone_breaches_and_reversals(self, current_price: float, candle_data: Dict):
        """
        Check for zone breaches and handle direction reversals
        
        Args:
            current_price: Current market price
            candle_data: Current candle information
        """
        try:
            active_cycles = self.multi_cycle_manager.get_all_active_cycles()
            
            # Track if we created any new cycles in this check
            new_cycle_created = False
            current_time = time.time()
            
            # Process existing cycles for zone breaches
            for cycle in active_cycles:
                try:
                    # Skip closed cycles
                    if getattr(cycle, 'is_closed', False):
                        continue
                    
                    # Check for zone breaches using enhanced zone detection
                    breach_result = self.zone_engine.detect_zone_breach(
                        current_price,
                        getattr(cycle, 'entry_price', current_price),
                        threshold_pips=self.reversal_threshold_pips
                    )
                    
                    cycle_id = getattr(cycle, 'cycle_id', 'unknown')
                    cycle_direction = getattr(cycle, 'current_direction', 'BUY')
                    
                    # Update reversal monitor if it exists
                    if hasattr(self.zone_engine, 'update_reversal_monitor'):
                        reversal_update = self.zone_engine.update_reversal_monitor(cycle_id, current_price)
                        if reversal_update and reversal_update.get("reversal_triggered", False):
                            breach_result["reversal_info"] = {
                                "should_create_reversal": True,
                                "reversal_direction": "SELL" if cycle_direction == "BUY" else "BUY",
                                "reversal_price": current_price
                            }
                    
                    if breach_result.get("breach_detected"):
                        logger.info(f"Zone breach detected for cycle {cycle_id}: {breach_result}")
                        
                        # Check if reversal should be handled
                        reversal_info = breach_result.get("reversal_info", {})
                        if reversal_info.get("should_create_reversal"):
                            reversal_direction = reversal_info.get("reversal_direction", "BUY")
                            reversal_price = reversal_info.get("reversal_price", current_price)
                            
                            if self._should_create_reversal_cycle(current_price, reversal_price, reversal_direction):
                                # Instead of creating a new cycle, switch direction and close existing orders
                                logger.info(f"🔄 Direction reversal detected: {cycle_direction} -> {reversal_direction}")
                                
                                # Close existing orders for the current direction
                                closed_orders = self._close_orders_for_direction_switch(cycle_direction)
                                logger.info(f"Closed {closed_orders} orders for direction reversal")
                                
                                # Execute the direction switch
                                switch_success = self.direction_controller.execute_direction_switch(
                                    reversal_direction, 
                                    "zone_breach_reversal"
                                )
                                
                                if switch_success:
                                    logger.info(f"✅ Direction switched to {reversal_direction} due to zone breach")
                                    
                                    # Reset the last cycle creation time to allow immediate order placement in the new direction
                                    self.last_cycle_creation_time = time.time() - self.order_interval_pips
                                    
                                    # Place an immediate order in the new direction
                                    order_ticket = self.enhanced_order_manager.place_order(
                                        current_price=current_price,
                                        direction=reversal_direction,
                                        lot_size=self.lot_size,
                                        cycle_id="zone_reversal"
                                    )
                                    
                                    if order_ticket:
                                        logger.info(f"🎯 Reversal order {order_ticket} placed ({reversal_direction})")
                                        
                                        # Update loss tracker
                                        self._update_loss_tracking(order_ticket, f"zone_reversal_{reversal_direction}")
                                else:
                                    logger.warning(f"❌ Direction switch to {reversal_direction} was blocked or failed")
                    
                except Exception as e:
                    logger.error(f"Error checking zone breach for cycle {getattr(cycle, 'id', 'unknown')}: {e}")
            
            # Log summary if we created any new cycles
            if new_cycle_created:
                logger.info(f"📊 Zone detection summary: Created new cycles at {self.order_interval_pips}-pip interval")
                    
        except Exception as e:
            logger.error(f"Error in zone breach and reversal checking: {e}")

    def _check_direction_switches(self, current_price: float, candle_data: Dict):
        """
        Check for direction switches based on market conditions and zone analysis
        
        Args:
            current_price: Current market price
            candle_data: Current candle information
        """
        try:
            # Only check direction switches if zone is activated and trading is active
            if not self.zone_activated or not self.trading_active:
                return
            
            # Get active zones from enhanced zone detection
            active_zones = self.zone_engine.get_active_zones()
            if not active_zones:
                logger.debug("No active zones available for direction switch analysis")
                return
            
            # Use the first active zone's base price for analysis
            zone_base_price = active_zones[0].get('base_price')
            if not zone_base_price:
                logger.debug("No zone base price available for direction switch analysis")
                return
            
            # Prepare market data for direction controller
            market_data = {
                "current_price": current_price,
                "zone_price": zone_base_price,
                "candle": candle_data
            }
            
            # Get direction recommendation from controller
            recommendation = self.direction_controller.get_direction_recommendation(
                zone_base_price, candle_data, current_price
            )
            
            # Check if direction switch is recommended
            if recommendation.get("should_switch", False):
                recommended_direction = recommendation.get("recommended_direction", "HOLD")
                
                if recommended_direction != "HOLD":
                    current_direction = self.direction_controller.get_current_direction()
                    
                    # Only switch if the recommended direction is different
                    if recommended_direction != current_direction:
                        logger.info(f"Direction switch recommended: {current_direction} -> {recommended_direction}")
                        logger.info(f"Switch reason: Market analysis, strength: {recommendation.get('strength', 'unknown')}")
                        
                        # Close existing orders for the current direction
                        closed_orders = self._close_orders_for_direction_switch(current_direction)
                        logger.info(f"Closed {closed_orders} orders for direction switch")
                        
                        # Execute the direction switch
                        switch_success = self.direction_controller.execute_direction_switch(
                            recommended_direction, 
                            "market_analysis"
                        )
                        
                        if switch_success:
                            logger.info(f"✅ Direction switched successfully to {recommended_direction}")
                            
                            # Reset the last cycle creation time to allow immediate order placement in the new direction
                            self.last_cycle_creation_time = time.time() - self.order_interval_pips
                            
                            # Place an immediate order in the new direction
                            order_ticket = self.enhanced_order_manager.place_order(
                                current_price=current_price,
                                direction=recommended_direction,
                                lot_size=self.lot_size,
                                cycle_id="direction_switch"
                            )
                            
                            if order_ticket:
                                logger.info(f"🎯 Direction switch order {order_ticket} placed ({recommended_direction})")
                                
                                # Update loss tracker
                                self._update_loss_tracking(order_ticket, f"direction_switch_{recommended_direction}")
                            
                            # Log direction switch statistics
                            direction_stats = self.direction_controller.get_direction_statistics()
                            logger.info(f"Direction switch stats: {direction_stats.get('total_switches', 0)} total switches")
                        else:
                            logger.warning(f"❌ Direction switch to {recommended_direction} was blocked or failed")
                    else:
                        logger.debug(f"Direction switch not needed - already in {recommended_direction} direction")
                else:
                    logger.debug("Direction switch recommended but direction is HOLD - no action taken")
            else:
                logger.debug("No direction switch recommended based on current market conditions")
            
            # Update direction controller with latest market data
            self.direction_controller.update_direction_from_market_data(market_data)
            
        except Exception as e:
            logger.error(f"Error checking direction switches: {e}")
            
    def _close_orders_for_direction_switch(self, current_direction: str) -> int:
        """
        Close all orders for the current direction when switching directions
        
        Args:
            current_direction: Current trading direction (BUY or SELL)
            
        Returns:
            int: Number of orders closed
        """
        try:
            closed_count = 0
            
            # Get all active orders for the current direction
            if current_direction == "BUY":
                orders_to_close = self.meta_trader.get_buy_orders(self.symbol, self.bot.magic_number)
            else:
                orders_to_close = self.meta_trader.get_sell_orders(self.symbol, self.bot.magic_number)
            
            # Close each order
            for order in orders_to_close:
                order_ticket = order.get("ticket", 0)
                if order_ticket > 0:
                    close_result = self.meta_trader.close_order(order_ticket)
                    if close_result:
                        logger.info(f"Closed order {order_ticket} for direction switch")
                        closed_count += 1
                    else:
                        logger.warning(f"Failed to close order {order_ticket} for direction switch")
            
            logger.info(f"Closed {closed_count} orders for direction switch from {current_direction}")
            return closed_count
            
        except Exception as e:
            logger.error(f"Error closing orders for direction switch: {e}")
            return 0

    def _should_create_reversal_cycle(self, current_price: float, reversal_price: float, direction: str) -> bool:
        """
        Determine if a reversal cycle should be created based on price conditions
        
        Args:
            current_price: Current market price
            reversal_price: Calculated reversal trigger price
            direction: Original cycle direction
            
        Returns:
            bool: True if reversal cycle should be created
        """
        try:
            if direction == "BUY":
                # For BUY cycles, create SELL reversal when price drops below reversal price
                return current_price <= reversal_price
            else:  # SELL
                # For SELL cycles, create BUY reversal when price rises above reversal price
                return current_price >= reversal_price
            
        except Exception as e:
            logger.error(f"Error determining reversal cycle creation: {e}")
            return False
    
    def get_multi_cycle_statistics(self) -> Dict:
        """
        Get comprehensive multi-cycle statistics
        
        Returns:
            Dict: Multi-cycle system statistics
        """
        try:
            manager_stats = self.multi_cycle_manager.get_manager_statistics()
            zone_stats = self.enhanced_zone_engine.get_detection_statistics()
            order_stats = self.enhanced_order_manager.get_manager_statistics()
            
            return {
                "multi_cycle_manager": manager_stats,
                "enhanced_zone_detection": zone_stats,
                "enhanced_order_manager": order_stats,
                "system_overview": {
                    "total_active_cycles": manager_stats.get("total_cycles", 0),
                    "open_cycles": manager_stats.get("open_cycles", 0),
                    "zone_breaches": zone_stats.get("zone_breach_count", 0),
                    "order_success_rate": order_stats.get("diagnostics", {}).get("success_rate", 0),
                    "last_cycle_creation": self.last_cycle_creation_time,
                    "cycle_creation_interval": self.cycle_creation_interval
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting multi-cycle statistics: {e}")
            return {"error": str(e)}

    async def _detect_and_organize_missing_orders(self):
        """Comprehensive missing order detection and organization system"""
        try:
            if not hasattr(self.meta_trader, 'get_all_positions'):
                logger.warning("MetaTrader does not support position checking")
                return
            
            # Get all MT5 positions with our magic number
            mt5_positions = self.meta_trader.get_all_positions()
            if not mt5_positions:
                logger.debug("No MT5 positions found for missing order detection")
                return
            
            # Filter positions by magic number and symbol
            relevant_positions = []
            for pos in mt5_positions:
                if (hasattr(pos, 'magic') and pos.magic == self.bot.magic_number and 
                    hasattr(pos, 'symbol') and pos.symbol == self.symbol):
                    # CRITICAL FIX: Check comment for cycle association
                    comment = getattr(pos, 'comment', '')
                    if comment:
                        # Only add positions that have comments indicating they belong to a specific cycle
                        relevant_positions.append(pos)
                    else:
                        # For positions without comments, check if they were created during any cycle's lifetime
                        pos_time = getattr(pos, 'time_setup', 0)
                        if pos_time > 0:
                            for cycle in self.active_cycles:
                                if hasattr(cycle, 'start_time') and cycle.start_time and pos_time >= cycle.start_time.timestamp():
                                    relevant_positions.append(pos)
                                    break
            
            if not relevant_positions:
                logger.debug(f"No relevant MT5 positions found (magic: {self.bot.magic_number}, symbol: {self.symbol})")
                return
            
            # Get all order tickets currently tracked in cycles
            tracked_tickets = set()
            for cycle in self.active_cycles:
                for order in cycle.active_orders + cycle.completed_orders:
                    ticket = order.get('ticket', 0)
                    if ticket:
                        tracked_tickets.add(int(ticket))
            
            # Find missing orders (in MT5 but not tracked in cycles)
            missing_orders = []
            for pos in relevant_positions:
                ticket = getattr(pos, 'ticket', 0)
                if ticket and int(ticket) not in tracked_tickets:
                    missing_orders.append(pos)
            
            if not missing_orders:
                logger.debug("No missing orders detected")
                return
            
            logger.warning(f"🔍 Found {len(missing_orders)} missing orders in MT5 that aren't tracked in cycles")
            
            # Organize missing orders by potential cycle association
            organized_orders = self._organize_missing_orders(missing_orders)
            
            # Process organized orders
            await self._process_organized_missing_orders(organized_orders)
            
        except Exception as e:
            logger.error(f"Error in missing order detection and organization: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")

    def _organize_missing_orders(self, missing_orders):
        """
        Organize missing orders into categories for processing
        
        Args:
            missing_orders: List of MT5 position objects that aren't tracked in cycles
            
        Returns:
            Dict: Organized orders with keys:
                - existing_cycle_candidates: Orders that can be added to existing cycles
                - new_cycle_candidates: Orders that need new cycles
                - orphaned_orders: Orders that can't be easily categorized
        """
        try:
            organized = {
                'existing_cycle_candidates': [],
                'new_cycle_candidates': [],
                'orphaned_orders': []
            }
            
            if not missing_orders:
                return organized
            
            logger.info(f"🔍 Organizing {len(missing_orders)} missing orders")
            
            for pos in missing_orders:
                try:
                    # Determine order direction
                    order_type = getattr(pos, 'type', 0)
                    direction = "BUY" if order_type == 0 else "SELL"
                    
                    # Get order details
                    ticket = getattr(pos, 'ticket', 0)
                    price_open = getattr(pos, 'price_open', 0.0)
                    
                    logger.debug(f"Processing missing order {ticket}: {direction} at {price_open}")
                    
                    # Try to find a suitable existing cycle
                    suitable_cycle = self._find_suitable_cycle_for_order(pos, direction, price_open)
                    
                    if suitable_cycle:
                        # Add to existing cycle candidates
                        organized['existing_cycle_candidates'].append({
                            'position': pos,
                            'cycle': suitable_cycle,
                            'direction': direction
                        })
                        logger.debug(f"Order {ticket} matched to existing cycle {suitable_cycle.id}")
                    else:
                        # Check if this order should create a new cycle or be orphaned
                        if self._should_create_cycle_for_order(pos, direction, price_open):
                            # Add to new cycle candidates
                            organized['new_cycle_candidates'].append({
                                'position': pos,
                                'direction': direction
                            })
                            logger.debug(f"Order {ticket} marked for new cycle creation")
                        else:
                            # Add to orphaned orders
                            organized['orphaned_orders'].append({
                                'position': pos,
                                'direction': direction
                            })
                            logger.debug(f"Order {ticket} marked as orphaned")
                
                except Exception as e:
                    logger.error(f"Error organizing missing order {getattr(pos, 'ticket', 'unknown')}: {e}")
                    # Default to orphaned if we can't categorize
                    organized['orphaned_orders'].append({
                        'position': pos,
                        'direction': 'UNKNOWN'
                    })
            
            # Log organization summary
            logger.info(f"📊 Organization results:")
            logger.info(f"   - Existing cycle candidates: {len(organized['existing_cycle_candidates'])}")
            logger.info(f"   - New cycle candidates: {len(organized['new_cycle_candidates'])}")
            logger.info(f"   - Orphaned orders: {len(organized['orphaned_orders'])}")
            
            return organized
            
        except Exception as e:
            logger.error(f"Error organizing missing orders: {e}")
            # Return safe default structure
            return {
                'existing_cycle_candidates': [],
                'new_cycle_candidates': [],
                'orphaned_orders': [{'position': pos, 'direction': 'UNKNOWN'} for pos in missing_orders]
            }

    def _find_suitable_cycle_for_order(self, pos, direction, price_open):
        """
        Find an existing cycle that could accommodate this missing order
        
        Args:
            pos: MT5 position object
            direction: Order direction (BUY/SELL)
            price_open: Order opening price
            
        Returns:
            AdvancedCycle or None: Suitable cycle if found
        """
        try:
            if not self.active_cycles:
                return None
            
            # Look for cycles with matching direction first
            matching_direction_cycles = [
                cycle for cycle in self.active_cycles 
                if getattr(cycle, 'direction', '') == direction and not getattr(cycle, 'is_closed', False)
            ]
            
            if not matching_direction_cycles:
                return None
            
            # Calculate price tolerance (50 pips by default)
            pip_value = self._get_pip_value()
            price_tolerance = 50.0 / pip_value  # 50 pips tolerance
            
            # Find the closest cycle by price
            best_cycle = None
            best_distance = float('inf')
            
            for cycle in matching_direction_cycles:
                try:
                    cycle_entry_price = getattr(cycle, 'entry_price', 0.0)
                    if cycle_entry_price == 0.0:
                        continue
                    
                    price_distance = abs(price_open - cycle_entry_price)
                    
                    # Check if within tolerance
                    if price_distance <= price_tolerance and price_distance < best_distance:
                        best_cycle = cycle
                        best_distance = price_distance
                
                except Exception as e:
                    logger.error(f"Error checking cycle {getattr(cycle, 'id', 'unknown')}: {e}")
                    continue
            
            if best_cycle:
                logger.debug(f"Found suitable cycle {best_cycle.id} for order (distance: {best_distance * pip_value:.1f} pips)")
            
            return best_cycle
            
        except Exception as e:
            logger.error(f"Error finding suitable cycle: {e}")
            return None

    def _should_create_cycle_for_order(self, pos, direction, price_open):
        """
        Determine if a new cycle should be created for this missing order
        
        Args:
            pos: MT5 position object
            direction: Order direction (BUY/SELL)
            price_open: Order opening price
            
        Returns:
            bool: True if new cycle should be created
        """
        try:
            # Check if we're under the maximum cycle limit
            if hasattr(self, 'multi_cycle_manager') and self.multi_cycle_manager:
                max_cycles = getattr(self.multi_cycle_manager, 'max_active_cycles', 10)
                current_cycles = len(self.active_cycles)
                
                if current_cycles >= max_cycles:
                    logger.debug(f"Max cycles limit reached ({current_cycles}/{max_cycles})")
                    return False
            
            # Check order volume - only create cycles for significant orders
            volume = getattr(pos, 'volume', 0.0)
            min_volume = self.config.get('min_volume_for_cycle', 0.01)
            
            if volume < min_volume:
                logger.debug(f"Order volume {volume} below minimum {min_volume}")
                return False
            
            # Check order age - don't create cycles for very old orders
            try:
                import datetime
                order_time = getattr(pos, 'time', 0)
                if order_time:
                    # Convert MT5 time to datetime
                    order_datetime = datetime.datetime.fromtimestamp(order_time)
                    current_time = datetime.datetime.now()
                    age_hours = (current_time - order_datetime).total_seconds() / 3600
                    
                    max_age_hours = self.config.get('max_order_age_for_cycle', 24)  # 24 hours default
                    if age_hours > max_age_hours:
                        logger.debug(f"Order too old ({age_hours:.1f}h > {max_age_hours}h)")
                        return False
            except Exception:
                # If we can't determine age, assume it's acceptable
                pass
            
            # Default: create cycle for orders that pass basic checks
            return True
            
        except Exception as e:
            logger.error(f"Error determining if cycle should be created: {e}")
            return False

    async def _process_organized_missing_orders(self, organized_orders):
        """Process organized missing orders and take appropriate actions"""
        try:
            # Process existing cycle candidates first
            for candidate in organized_orders['existing_cycle_candidates']:
                try:
                    pos = candidate['position']
                    cycle = candidate['cycle']
                    direction = candidate['direction']
                    
                    logger.info(f"🔄 Adding missing order {pos.ticket} to existing cycle {cycle.id}")
                    
                    # Create order data from MT5 position
                    order_data = {
                        'ticket': pos.ticket,
                        'volume': getattr(pos, 'volume', 0.01),
                        'price_open': getattr(pos, 'price_open', 0.0),
                        'profit': getattr(pos, 'profit', 0.0),
                        'swap': getattr(pos, 'swap', 0.0),
                        'commission': getattr(pos, 'commission', 0.0),
                        'sl': getattr(pos, 'sl', 0.0),
                        'tp': getattr(pos, 'tp', 0.0),
                        'margin': getattr(pos, 'margin', 0.0),
                        'type': getattr(pos, 'type', 0)
                    }
                    
                    # Add order to cycle
                    success = cycle.add_order(order_data)
                    if success:
                        logger.info(f"✅ Successfully added missing order {pos.ticket} to cycle {cycle.id}")
                        
                        # Update cycle in database
                        cycle._update_cycle_in_database()
                    else:
                        logger.error(f"❌ Failed to add missing order {pos.ticket} to cycle {cycle.id}")
                        
                except Exception as e:
                    logger.error(f"Error processing existing cycle candidate: {e}")
            
            # Process new cycle candidates
            for candidate in organized_orders['new_cycle_candidates']:
                try:
                    pos = candidate['position']
                    direction = candidate['direction']
                    
                    logger.info(f"🆕 Creating new cycle for missing order {pos.ticket}")
                    
                    # Create order data
                    order_data = {
                        'ticket': pos.ticket,
                        'volume': getattr(pos, 'volume', 0.01),
                        'price_open': getattr(pos, 'price_open', 0.0),
                        'profit': getattr(pos, 'profit', 0.0),
                        'swap': getattr(pos, 'swap', 0.0),
                        'commission': getattr(pos, 'commission', 0.0),
                        'sl': getattr(pos, 'sl', 0.0),
                        'tp': getattr(pos, 'tp', 0.0),
                        'margin': getattr(pos, 'margin', 0.0),
                        'type': getattr(pos, 'type', 0)
                    }
                    
                    # Create new cycle for this order
                    await self._create_cycle_for_missing_order(order_data, direction)
                    
                except Exception as e:
                    logger.error(f"Error processing new cycle candidate: {e}")
            
            # Process orphaned orders
            if organized_orders['orphaned_orders']:
                logger.warning(f"⚠️ Found {len(organized_orders['orphaned_orders'])} orphaned orders:")
                for orphan in organized_orders['orphaned_orders']:
                    pos = orphan['position']
                    logger.warning(f"   - Order {pos.ticket}: {orphan['direction']} at {getattr(pos, 'price_open', 0.0)}")
                
                # Create a recovery cycle for orphaned orders
                await self._create_recovery_cycle_for_orphaned_orders(organized_orders['orphaned_orders'])
            
        except Exception as e:
            logger.error(f"Error processing organized missing orders: {e}")

    async def _create_cycle_for_missing_order(self, order_data, direction):
        """Create a new cycle for a missing order"""
        try:
            # Calculate stop loss and take profit based on config
            entry_price = order_data['price_open']
            stop_loss_pips = self.config.get("stop_loss_pips", 50.0)
            take_profit_pips = self.config.get("take_profit_pips", 100.0)
            
            pip_value = self._get_pip_value()
            
            if direction == "BUY":
                stop_loss = entry_price - (stop_loss_pips / pip_value)
                take_profit = entry_price + (take_profit_pips / pip_value)
            else:  # SELL
                stop_loss = entry_price + (stop_loss_pips / pip_value)
                take_profit = entry_price - (take_profit_pips / pip_value)
            
            # Create new cycle
            cycle_id = self._create_new_cycle(direction, entry_price, stop_loss, take_profit)
            
            if cycle_id and self.current_cycle:
                # Add the missing order to the cycle
                logger.info(f"🎯 Adding missing order {order_data['ticket']} to new recovery cycle {cycle_id}")
                self.current_cycle.add_order(order_data)
                
                # Update cycle in database
                self.current_cycle._update_cycle_in_database()
                
                logger.info(f"✅ Recovery cycle created: {cycle_id} with missing order {order_data['ticket']}")
            else:
                logger.error(f"❌ Failed to create recovery cycle for missing order {order_data['ticket']}")
            
        except Exception as e:
            logger.error(f"Error creating cycle for missing order: {e}")

    async def _create_recovery_cycle_for_orphaned_orders(self, orphaned_orders):
        """Create a recovery cycle for orphaned orders that don't match existing cycles"""
        try:
            if not orphaned_orders:
                return
            
            logger.info(f"🆘 Creating recovery cycle for {len(orphaned_orders)} orphaned orders")
            
            # Use the first orphaned order as the base
            first_orphan = orphaned_orders[0]
            pos = first_orphan['position']
            direction = first_orphan['direction']
            
            # Create order data
            order_data = {
                'ticket': pos.ticket,
                'volume': getattr(pos, 'volume', 0.01),
                'price_open': getattr(pos, 'price_open', 0.0),
                'profit': getattr(pos, 'profit', 0.0),
                'swap': getattr(pos, 'swap', 0.0),
                'commission': getattr(pos, 'commission', 0.0),
                'sl': getattr(pos, 'sl', 0.0),
                'tp': getattr(pos, 'tp', 0.0),
                'margin': getattr(pos, 'margin', 0.0),
                'type': getattr(pos, 'type', 0)
            }
            
            # Create recovery cycle
            await self._create_cycle_for_missing_order(order_data, direction)
            
            # Add remaining orphaned orders to the same recovery cycle
            if self.current_cycle:
                for orphan in orphaned_orders[1:]:
                    try:
                        pos = orphan['position']
                        orphan_order_data = {
                            'ticket': pos.ticket,
                            'volume': getattr(pos, 'volume', 0.01),
                            'price_open': getattr(pos, 'price_open', 0.0),
                            'profit': getattr(pos, 'profit', 0.0),
                            'swap': getattr(pos, 'swap', 0.0),
                            'commission': getattr(pos, 'commission', 0.0),
                            'sl': getattr(pos, 'sl', 0.0),
                            'tp': getattr(pos, 'tp', 0.0),
                            'margin': getattr(pos, 'margin', 0.0),
                            'type': getattr(pos, 'type', 0)
                        }
                        
                        self.current_cycle.add_order(orphan_order_data)
                        logger.info(f"✅ Added orphaned order {pos.ticket} to recovery cycle")
                        
                    except Exception as e:
                        logger.error(f"Error adding orphaned order {pos.ticket}: {e}")
                
                # Update recovery cycle in database
                self.current_cycle._update_cycle_in_database()
                logger.info(f"✅ Recovery cycle created with {len(orphaned_orders)} orphaned orders")
            
        except Exception as e:
            logger.error(f"Error creating recovery cycle for orphaned orders: {e}")

    def _force_sync_all_cycles_with_mt5(self):
        """Force synchronization of all cycles with MT5 orders"""
        try:
            logger.info("🔄 Force syncing all cycles with MT5 orders")
            
            # Update all active cycles
            self._update_active_cycles()
            
            # Perform comprehensive missing order detection
            self._detect_and_organize_missing_orders()
            
            # Log final status
            total_orders = sum(len(cycle.active_orders) + len(cycle.completed_orders) for cycle in self.active_cycles)
            logger.info(f"✅ Force sync completed - {len(self.active_cycles)} active cycles, {total_orders} total orders")
            
        except Exception as e:
            logger.error(f"Error in force sync: {e}")

    def _get_market_data(self):
        """Get current market data"""
        try:
            # Get current market price
            current_price = None
            if hasattr(self.meta_trader, 'get_ask'):
                current_price = self.meta_trader.get_ask(self.symbol)
            elif hasattr(self.meta_trader, 'get_price'):
                current_price = self.meta_trader.get_price(self.symbol)
            
            if current_price is None:
                logger.warning("Failed to get current market price")
                return None
                
            # Handle NumPy array case - this is likely causing the error
            if hasattr(current_price, 'size') and current_price.size > 1:
                # If it's a NumPy array with multiple values, take the first one
                current_price = float(current_price[0])
            
            # Get candle data
            candle_data = {}
            if hasattr(self.meta_trader, 'get_candles'):
                candles = self.meta_trader.get_candles(self.symbol, 1, 10)
                
                # Handle structured NumPy array case
                if candles is not None:
                    # Check if it's a NumPy structured array (with named fields)
                    if hasattr(candles, 'dtype') and hasattr(candles.dtype, 'names') and candles.dtype.names:
                        if len(candles) > 0:
                            # Extract the first candle from structured array
                            candle = candles[0]
                            candle_data = {
                                "open": float(candle['open']),
                                "high": float(candle['high']),
                                "low": float(candle['low']),
                                "close": float(candle['close']),
                                "time": int(candle['time']) if 'time' in candle.dtype.names else None,
                                "tick_volume": int(candle['tick_volume']) if 'tick_volume' in candle.dtype.names else None
                            }
                    # Regular object case
                    elif len(candles) > 0:
                        candle = candles[0]
                        candle_data = {
                            "open": float(candle.open) if hasattr(candle.open, 'size') else float(candle.open),
                            "high": float(candle.high) if hasattr(candle.high, 'size') else float(candle.high),
                            "low": float(candle.low) if hasattr(candle.low, 'size') else float(candle.low),
                            "close": float(candle.close) if hasattr(candle.close, 'size') else float(candle.close),
                            "time": candle.time
                        }
            
            # Get positions
            positions = []
            if hasattr(self.meta_trader, 'get_positions'):
                positions = self.meta_trader.get_positions()
            elif hasattr(self.meta_trader, 'get_all_positions'):
                positions = self.meta_trader.get_all_positions()
            
            return {
                "current_price": current_price,
                "candle": candle_data,  # Changed from candle_data for consistency
                "positions": positions,
                "timestamp": datetime.datetime.utcnow()
            }
            
        except Exception as e:
            logger.error(f"Error getting market data: {e}")
            return None

    def _get_pip_value(self):
        """Get pip value for the current symbol"""
        if "JPY" in self.symbol:
            return 100.0  # 0.01 = 1 pip for JPY pairs
        elif "XAU" in self.symbol or "GOLD" in self.symbol.upper():
            return 100.0  # 0.01 = 1 pip for gold
        elif "BTC" in self.symbol or "ETH" in self.symbol:
            return 1.0    # 1.0 = 1 pip for crypto
        else:
            return 10000.0  # 0.0001 = 1 pip for major currency pairs

    def _monitor_order_management(self, market_data):
        """Monitor and manage orders across all active cycles"""
        try:
            if not market_data:
                logger.warning("No market data available for order management")
                return
                
            current_price = market_data.get("current_price")
            if not current_price:
                logger.warning("No current price available for order management")
                return
                
            # Count active cycles and orders for logging
            active_cycle_count = len(self.active_cycles)
            total_orders = sum(len(cycle.active_orders) for cycle in self.active_cycles)
            
            # Skip if no active cycles
            if active_cycle_count == 0:
                logger.debug(f"Multi-cycle management: {active_cycle_count} cycles, {total_orders} orders placed")
                return
                
            # Update each cycle with live data
            for cycle in self.active_cycles:
                try:
                    # Update orders with live data
                    cycle.update_orders_with_live_data()
                    
                    # Check if cycle should be closed
                    if hasattr(cycle, '_should_close_cycle') and cycle._should_close_cycle():
                        logger.info(f"Cycle {cycle.id} should be closed based on conditions")
                        cycle.close_cycle("auto_conditions_met")
                        self.closed_cycles.append(cycle)
                        self.active_cycles.remove(cycle)
                        continue
                        
                    # Update cycle status
                    if hasattr(cycle, 'update_cycle_status'):
                        cycle.update_cycle_status()
                        
                    # CRITICAL: Run advanced zone order management
                    if hasattr(cycle, 'manage_advanced_zone_orders'):
                        try:
                            # Create event loop for async call
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            
                            # Run manage_advanced_zone_orders
                            loop.run_until_complete(cycle.manage_advanced_zone_orders(
                                zone_threshold_pips=self.reversal_threshold_pips,
                                order_interval_pips=self.order_interval_pips,
                                batch_stop_loss_pips=self.initial_order_stop_loss
                            ))
                            
                            loop.close()
                            
                        except Exception as e:
                            logger.error(f"Error in manage_advanced_zone_orders for cycle {cycle.cycle_id}: {e}")
                        
                    # Check for batch stop loss
                    if hasattr(cycle, 'check_batch_stop_loss') and cycle.check_batch_stop_loss(current_price):
                        logger.warning(f"Batch stop loss triggered for cycle {cycle.id}")
                        
                    # Update cycle in database
                    if hasattr(cycle, '_update_cycle_in_database'):
                        cycle._update_cycle_in_database()
                        
                except Exception as e:
                    logger.error(f"Error monitoring cycle {cycle.id}: {e}")
            
            # Log multi-cycle management status
            updated_active_cycle_count = len(self.active_cycles)
            updated_total_orders = sum(len(cycle.active_orders) for cycle in self.active_cycles)
            
            logger.debug(f"Multi-cycle management: {updated_active_cycle_count} cycles, {updated_total_orders} orders placed")
            
        except Exception as e:
            logger.error(f"Error in order management: {e}")

    def set_entry_price(self, price):
        """Set the entry price for threshold monitoring"""
        self.entry_price = price
        logger.info(f"Entry price set to {price}")

    def _start_trading_session(self, direction, entry_price):
        """Start a new trading session with the specified direction and entry price"""
        try:
            # Set the entry price for threshold monitoring
            self.set_entry_price(entry_price)
            
            # Activate the strategy if not already active
            if not self.strategy_active:
                self.start_strategy()
            
            # Enable trading
            self.trading_active = True
            
            # Set initial direction
            if hasattr(self, 'direction_controller') and self.direction_controller:
                self.direction_controller.execute_direction_switch(direction, "manual_session_start")
            
            # Initialize zone monitoring
            self.zone_activated = False
            self.initial_threshold_breached = False
            
            logger.info(f"🎯 Trading session started: {direction} at {entry_price}")
            logger.info(f"   Strategy active: {self.strategy_active}")
            logger.info(f"   Trading active: {self.trading_active}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error starting trading session: {e}")
            return False

    def _create_new_cycle(self, direction, entry_price, stop_loss, take_profit):
        """Create a new cycle with the specified parameters"""
        try:
            # Import the cycle class
            from cycles.ACT_cycle import AdvancedCycle
            
            # Create cycle data
            cycle_data = {
                'bot_id': str(self.bot.id),
                'symbol': self.symbol,
                'direction': direction,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'is_active': True,
                'is_closed': False,
                'created': datetime.datetime.utcnow(),
                'updated': datetime.datetime.utcnow()
            }
            
            # Create the cycle object
            new_cycle = AdvancedCycle(cycle_data, self.meta_trader, self.bot)
            
            # Create in database first to get cycle_id
            if not new_cycle._create_cycle_in_database():
                logger.error("Failed to create cycle in database")
                return None
            
            # Add to active cycles
            self.active_cycles.append(new_cycle)
            
            # Set as current cycle (for backward compatibility)
            self.current_cycle = new_cycle
            
            logger.info(f"🎯 Created new ACT cycle: {new_cycle.cycle_id}")
            logger.info(f"   Direction: {direction}")
            logger.info(f"   Entry: {entry_price}")
            logger.info(f"   Stop Loss: {stop_loss}")
            logger.info(f"   Take Profit: {take_profit}")
            
            return new_cycle.cycle_id
            
        except Exception as e:
            logger.error(f"Error creating new cycle: {e}")
            return None

    def get_strategy_statistics(self):
        """Get comprehensive strategy statistics"""
        try:
            # Use enhanced zone detection's get_detection_statistics method
            zone_stats = self.zone_engine.get_detection_statistics()
            order_stats = self.order_manager.get_order_statistics()
            direction_stats = self.direction_controller.get_direction_statistics()
            
            # ACTRepo removed - using in-memory operations
            loss_stats = self.loss_tracker if hasattr(self, 'loss_tracker') and self.loss_tracker else {}
            
            return {
                "strategy_active": self.strategy_active,
                "trading_active": self.trading_active,
                "zone_activated": self.zone_activated,
                "threshold_breached": self.initial_threshold_breached,
                "active_cycles": len(self.active_cycles),
                "closed_cycles": len(self.closed_cycles),
                "current_price": self.current_market_price,
                "entry_price": self.entry_price,
                "zone_statistics": zone_stats,
                "order_statistics": order_stats,
                "direction_statistics": direction_stats,
                "loss_statistics": loss_stats
            }
            
        except Exception as e:
            logger.error(f"Error getting strategy statistics: {e}")
            return {"error": str(e)}

    def reset_strategy(self):
        """Reset strategy state (use with caution)"""
        try:
            # Stop strategy first
            self.stop_strategy()
            
            # Reset components - clean up old zones for enhanced zone detection
            self.zone_engine.cleanup_old_zones(0)  # 0 means remove all zones
            self.direction_controller.reset_direction_state()
            
            # Reset strategy state
            self.initial_threshold_breached = False
            self.zone_activated = False
            self.trading_active = False
            self.current_cycle = None
            self.entry_price = None
            
            # Clear cycles
            self.active_cycles.clear()
            self.closed_cycles.clear()
            
            # ADDED: Reset validation backoff state
            if hasattr(self, '_validation_failures'):
                delattr(self, '_validation_failures')
            if hasattr(self, '_validation_backoff_start'):
                delattr(self, '_validation_backoff_start')
            if hasattr(self, '_trading_resume_time'):
                delattr(self, '_trading_resume_time')
            
            logger.info("Strategy state reset")
            return True
            
        except Exception as e:
            logger.error(f"Error resetting strategy: {e}")
            return False

    def reset_validation_backoff(self):
        """Reset validation backoff mechanism manually"""
        try:
            if hasattr(self, '_validation_failures'):
                old_count = len(self._validation_failures)
                delattr(self, '_validation_failures')
                logger.info(f"Cleared {old_count} validation failures")
            
            if hasattr(self, '_validation_backoff_start'):
                delattr(self, '_validation_backoff_start')
                logger.info("Reset validation backoff start time")
            
            if hasattr(self, '_trading_resume_time'):
                delattr(self, '_trading_resume_time')
                logger.info("Cleared trading resume time")
            
            # Re-enable trading if it was disabled due to validation failures
            if not self.trading_active and self.strategy_active:
                self.trading_active = True
                logger.info("Re-enabled trading after validation backoff reset")
            
            logger.info("✅ Validation backoff mechanism reset successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error resetting validation backoff: {e}")
            return False

    async def run_in_thread(self):
        """
        This function runs the Advanced Cycles Trader strategy in a separate thread.
        Now properly handles asyncio event loops.
        """
        try:
            def run_coroutine_in_thread(coro):
                # Create a new event loop for this thread
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    # Run the coroutine in this thread's event loop
                    new_loop.run_until_complete(coro)
                except Exception as e:
                    logger.error(f"Error in thread event loop: {e}")
                finally:
                    # Clean up
                    new_loop.close()
                    logger.info("Thread event loop closed")

            # Create and start thread with its own event loop
            thread = threading.Thread(
                target=run_coroutine_in_thread, args=(self.run(),), daemon=True)
            thread.start()
            logger.info("AdvancedCyclesTrader strategy running in thread with dedicated event loop")
            return thread
            
        except Exception as e:
            logger.error(f"Error running AdvancedCyclesTrader in thread: {e}")
            return None

    async def run(self):
        """
        Main run loop for the Advanced Cycles Trader strategy.
        This method contains the core trading logic.
        """
        try:
            # Start the strategy if not already started
            if not self.strategy_active:
                self.start_strategy()
            
            # while self.strategy_active:
            #     try:
            #         # Get current market data
            #         market_data = self._get_market_data()
                    
            #         if not market_data:
            #             await asyncio.sleep(1)
            #             continue
                    
            #         self.current_market_price = market_data["current_price"]
                    
            #         # Process strategy logic
            #         self._process_strategy_logic(market_data)
                    
            #         # Update active cycles - FIXED: Use await with async method
            #         await self._update_active_cycles()
                    
            #         # Monitor order management
            #         self._monitor_order_management(market_data)
                    
            #         # Sleep for 1 second before next iteration
            #         await asyncio.sleep(1)
                    
            #     except Exception as e:
            #         logger.error(f"Error in ACT run loop: {e}")
            #         await asyncio.sleep(5)  # Wait longer on error
                    
        except Exception as e:
            logger.error(f"Fatal error in ACT run loop: {e}")
            self.strategy_active = False

    def _convert_pocketbase_to_cycle_data(self, cycle_record):
        """Convert PocketBase cycle record to cycle initialization data"""
        try:
            return {
                'id': cycle_record.id,
                'source': 'pocketbase',  # CRITICAL FIX: Mark source as PocketBase
                'symbol': getattr(cycle_record, 'symbol', self.symbol),
                'direction': getattr(cycle_record, 'direction', 'BUY'),
                'current_direction': getattr(cycle_record, 'current_direction', 'BUY'),
                'entry_price': float(getattr(cycle_record, 'entry_price', 0.0)),
                'zone_base_price': float(getattr(cycle_record, 'zone_base_price', 0.0)),
                'initial_threshold_price': float(getattr(cycle_record, 'initial_threshold_price', 0.0)),
                'lot_size': float(getattr(cycle_record, 'lot_size', 0.01)),
                'reversal_threshold_pips': float(getattr(cycle_record, 'reversal_threshold_pips', self.reversal_threshold_pips)),
                'order_interval_pips': float(getattr(cycle_record, 'order_interval_pips', self.order_interval_pips)),
                'initial_order_stop_loss': float(getattr(cycle_record, 'initial_order_stop_loss', self.initial_order_stop_loss)),
                'cycle_interval': float(getattr(cycle_record, 'cycle_interval', self.cycle_interval)),
                'stop_loss': float(getattr(cycle_record, 'stop_loss', 0.0)),
                'take_profit': float(getattr(cycle_record, 'take_profit', 0.0)),
                'zone_activated': bool(getattr(cycle_record, 'zone_activated', False)),
                'initial_threshold_breached': bool(getattr(cycle_record, 'initial_threshold_breached', False)),
                'direction_switched': bool(getattr(cycle_record, 'direction_switched', False)),
                'direction_switches': int(getattr(cycle_record, 'direction_switches', 0)),
                'zone_based_losses': float(getattr(cycle_record, 'zone_based_losses', 0.0)),
                'batch_stop_loss_triggers': int(getattr(cycle_record, 'batch_stop_loss_triggers', 0)),
                'active_orders': getattr(cycle_record, 'active_orders', []),
                'completed_orders': getattr(cycle_record, 'completed_orders', []),
                'next_order_index': int(getattr(cycle_record, 'next_order_index', 1)),
                'done_price_levels': getattr(cycle_record, 'done_price_levels', []),
                'last_order_time': getattr(cycle_record, 'last_order_time', None),
                'last_order_price': float(getattr(cycle_record, 'last_order_price', 0.0)),
                'current_batch_id': getattr(cycle_record, 'current_batch_id', None),
                'status': getattr(cycle_record, 'status', 'active'),
                'is_closed': bool(getattr(cycle_record, 'is_closed', False)),
                # Required CT_cycles compatibility fields
                'lower_bound': float(getattr(cycle_record, 'stop_loss', 0.0)),
                'upper_bound': float(getattr(cycle_record, 'take_profit', 0.0)),
                'is_pending': False,
                'lot_idx': 0,
                'total_volume': float(getattr(cycle_record, 'total_volume', 0.0)),
                'total_profit': float(getattr(cycle_record, 'total_profit', 0.0)),
                'zone_index': 0,
                'bot': str(self.bot.id) if hasattr(self.bot, 'id') else "ACT_Bot",
                'account': str(getattr(self.bot, 'account', 'Default')),
                'threshold_lower': float(getattr(cycle_record, 'stop_loss', 0.0)),
                'threshold_upper': float(getattr(cycle_record, 'take_profit', 0.0)),
                'base_threshold_lower': float(getattr(cycle_record, 'stop_loss', 0.0)),
                'base_threshold_upper': float(getattr(cycle_record, 'take_profit', 0.0)),
                'collectionId': getattr(cycle_record, 'collectionId', 'advanced_cycles_trader_cycles')  # CRITICAL FIX: Include collection ID
            }
        except Exception as e:
            logger.error(f"Error converting PocketBase record to cycle data: {e}")
            return {}

    async def _force_sync_cycles_from_db(self):
        """
        Force synchronization of cycles from database to both memory stores
        This is a critical recovery method when cycles exist in DB but not in memory
        """
        try:
            logger.info("🔄 FORCE SYNC: Attempting to recover cycles from database")
            
            # First, check if we have active cycles in memory but not in manager
            if self.active_cycles and hasattr(self, 'multi_cycle_manager'):
                if len(self.multi_cycle_manager.active_cycles) == 0:
                    logger.warning("🚨 Active cycles exist in memory but not in multi-cycle manager - fixing...")
                    for cycle in self.active_cycles:
                        self.multi_cycle_manager.add_cycle(cycle)
                    logger.info(f"✅ Added {len(self.active_cycles)} cycles to multi-cycle manager")
                    return True
            
            # If no active cycles in memory, try to fetch from database
            if not self.active_cycles and hasattr(self.bot, 'api_client') and self.bot.api_client:
                api_client = self.bot.api_client
                
                try:
                    logger.info(f"🔍 Searching for active cycles in database for bot {self.bot.id}")
                    cycles_response = api_client.get_active_ACT_cycles(
                        bot_id=str(self.bot.id)
                    )
                    
                    # CRITICAL FIX: Handle both list responses and responses with 'items' attribute
                    if cycles_response:
                        # Determine cycle count based on response type
                        if hasattr(cycles_response, 'items'):
                            # Response has 'items' attribute
                            cycles = cycles_response.items
                            cycle_count = len(cycles)
                        elif isinstance(cycles_response, list):
                            # Response is a list
                            cycles = cycles_response
                            cycle_count = len(cycles)
                        else:
                            # Unknown response type
                            logger.error(f"❌ FORCE SYNC: Unknown response type: {type(cycles_response)}")
                            return False
                            
                        logger.info(f"🔄 FORCE SYNC: Found {cycle_count} active cycles in database")
                        
                        if cycle_count > 0:
                            # Use the existing sync method to load cycles
                            await self._sync_cycles_from_database()
                            
                            # Verify the sync was successful
                            if self.active_cycles:
                                logger.info(f"✅ FORCE SYNC: Successfully recovered {len(self.active_cycles)} cycles")
                                
                                # Verify multi-cycle manager sync
                                if hasattr(self, 'multi_cycle_manager'):
                                    manager_count = len(self.multi_cycle_manager.active_cycles)
                                    logger.info(f"✅ Multi-cycle manager now has {manager_count} cycles")
                                    
                                return True
                            else:
                                logger.error("❌ FORCE SYNC: Failed to load cycles into memory")
                        else:
                            logger.info("ℹ️ No active cycles found in database during force sync")
                    else:
                        logger.info("ℹ️ No active cycles found in database during force sync")
                        
                except Exception as api_error:
                    logger.error(f"❌ FORCE SYNC: API error during cycle recovery: {api_error}")
            
            return False
                
        except Exception as e:
            logger.error(f"❌ FORCE SYNC: Error during force sync: {e}")
            return False

    def _update_loss_tracking(self, order_ticket, source_tag=""):
        """Update loss tracking with order information"""
        try:
            if not self.loss_tracker:
                logger.error("Loss tracker not initialized")
                return False
                
            # Update order tracking in loss tracker
            self.loss_tracker.last_order_ticket = order_ticket
            self.loss_tracker.last_order_source = source_tag
            
            # Update counts based on source
            if source_tag == "initial_order":
                self.loss_tracker.initial_orders_placed += 1
            elif source_tag == "interval_order":
                self.loss_tracker.interval_orders_placed += 1
            elif source_tag == "reversal_order":
                self.loss_tracker.reversal_orders_placed += 1
                
            self.loss_tracker.total_orders_placed += 1
            
            # ACTRepo removed - using in-memory operations
            logger.debug(f"Loss tracking updated for order {order_ticket}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating loss tracking: {e}")
            return False
            
    async def update_bot_config(self, config_updates):
        """
        Update bot configuration during runtime
        
        Args:
            config_updates (dict): Dictionary of configuration parameters to update
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not config_updates or not isinstance(config_updates, dict):
                logger.error("Invalid configuration updates provided")
                return False
                
            logger.info(f"Updating bot configuration with: {config_updates}")
            
            # 1. Update local configuration properties
            updated = False
            for key, value in config_updates.items():
                if hasattr(self, key):
                    old_value = getattr(self, key)
                    setattr(self, key, value)
                    logger.info(f"Updated {key}: {old_value} -> {value}")
                    updated = True
                else:
                    logger.warning(f"Configuration parameter '{key}' not found")
            
            # 2. Apply changes to strategy components
            if "reversal_threshold_pips" in config_updates or "order_interval_pips" in config_updates:
                zone_threshold = config_updates.get("reversal_threshold_pips", self.reversal_threshold_pips)
                order_interval = config_updates.get("order_interval_pips", self.order_interval_pips)
                
                # Update zone detection engine
                if hasattr(self, "enhanced_zone_engine"):
                    self.enhanced_zone_engine = EnhancedZoneDetection(
                        self.symbol,
                        zone_threshold,
                        order_interval
                    )
                    logger.info(f"Updated zone detection engine with new thresholds")
            
            return updated
            
        except Exception as e:
            logger.error(f"Error updating bot configuration: {e}")
            return False

    async def _initialize_strategy_configuration(self, config):
        """
        Initialize or update strategy configuration
        
        Args:
            config (dict): Configuration parameters
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not config or not isinstance(config, dict):
                logger.error("Invalid configuration provided")
                return False
            
            # Update configuration
            await self.update_bot_config(config)
            
            # Re-initialize components with new configuration
            updated_config = config.copy()
            updated_config.update({
                "reversal_threshold_pips": self.reversal_threshold_pips,
                "order_interval_pips": self.order_interval_pips,
                "initial_order_stop_loss": self.initial_order_stop_loss,
                "cycle_interval": self.cycle_interval,
                "max_active_cycles": self.max_active_cycles
            })
            
            # Update multi-cycle manager
            if hasattr(self, 'multi_cycle_manager'):
                self.multi_cycle_manager = MultiCycleManager(
                    self.meta_trader,
                    self.bot,
                    updated_config,
                    self.api_client
                )
            
            # Update zone detection engine
            if hasattr(self, 'enhanced_zone_engine'):
                self.enhanced_zone_engine = EnhancedZoneDetection(
                    self.symbol,
                    self.reversal_threshold_pips,
                    self.order_interval_pips
                )
            
            logger.info("Strategy configuration initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing strategy configuration: {e}")
            return False

    def _check_initial_order_stop_loss(self, cycle, current_price):
        """
        Check if the initial order in a cycle has hit its stop loss level
        
        Args:
            cycle: The cycle to check
            current_price: Current market price
            
        Returns:
            bool: True if stop loss is hit, False otherwise
        """
        try:
            if not cycle or not cycle.orders:
                return False
                
            # Get the initial order (first order in the cycle)
            initial_order = next((order for order in cycle.orders if order.get('comment', '').startswith('ini')), None)
            if not initial_order:
                return False
                
            # Get order details
            order_type = initial_order.get('type', '')  # 0 for buy, 1 for sell
            open_price = float(initial_order.get('price_open', 0))
            
            # Calculate stop loss level
            stop_loss_pips = float(cycle.initial_order_stop_loss)
            pip_value = self._get_pip_value()
            stop_loss_points = stop_loss_pips * pip_value
            
            # Check if price has hit stop loss level
            if order_type == 0:  # BUY
                stop_loss_level = open_price - stop_loss_points
                return current_price <= stop_loss_level
            else:  # SELL
                stop_loss_level = open_price + stop_loss_points
                return current_price >= stop_loss_level
                
        except Exception as e:
            logger.error(f"Error checking initial order stop loss: {e}")
            return False
            
    async def _close_initial_order_stop_loss(self, cycle, current_price):
        """
        Close the initial order and its cycle when stop loss is hit
        
        Args:
            cycle: The cycle containing the initial order
            current_price: Current market price
        """
        try:
            if not cycle or not cycle.orders:
                return
                
            # Get the initial order
            initial_order = next((order for order in cycle.orders if order.get('comment', '').startswith('ini')), None)
            if not initial_order:
                return
                
            logger.info(f"🔴 Initial order stop loss hit for cycle {cycle.id}")
            
            # Close the order in MT5
            order_ticket = initial_order.get('ticket')
            if order_ticket:
                close_result = self._close_order_in_mt5(order_ticket, initial_order)
                if close_result:
                    logger.info(f"✅ Closed initial order {order_ticket} at stop loss")
                else:
                    logger.error(f"❌ Failed to close initial order {order_ticket}")
                    return
            
            # Update cycle status
            await self._update_cycle_status_on_close(
                cycle=cycle,
                closing_method="stop_loss",
                username="system"
            )
            
            # Close cycle in database
            await self._close_cycle_in_database_enhanced(
                cycle_id=cycle.id,
                username="system"
            )
            
            # Remove cycle from active management
            if cycle in self.active_cycles:
                self.active_cycles.remove(cycle)
                logger.info(f"Cycle {cycle.id} removed from active management due to stop loss")
                
        except Exception as e:
            logger.error(f"Error closing initial order on stop loss: {e}")