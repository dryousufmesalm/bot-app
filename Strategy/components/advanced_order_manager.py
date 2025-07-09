import datetime
import asyncio
from typing import Dict, List, Optional, Tuple
from Orders.order import order
from Views.globals.app_logger import app_logger as logger


class AdvancedOrderManager:
    """Advanced order manager for continuous order placement and batch management"""
    
    def __init__(self, meta_trader, symbol: str, magic_number: int):
        self.meta_trader = meta_trader
        self.symbol = symbol
        self.magic_number = magic_number
        self.order_sequence = []  # Track order sequence
        self.batch_orders = {}  # Track order batches
        self.order_interval_pips = 50.0  # 50-pip intervals
        self.max_orders_per_batch = 10  # Maximum orders per batch
        self.order_placement_active = False
        self.current_direction = None
        self.last_order_time = None
        self.candle_interval = 60  # 1-minute candles (in seconds)
        
        logger.info(f"AdvancedOrderManager initialized for {symbol} - Magic: {magic_number}")

    def start_continuous_placement(self, direction: str, entry_price: float, 
                                 lot_size: float, stop_loss: float, take_profit: float) -> bool:
        """Start continuous order placement every candle"""
        try:
            self.order_placement_active = True
            self.current_direction = direction
            
            # Create initial batch
            batch_id = self._create_new_batch(direction, entry_price, lot_size, stop_loss, take_profit)
            
            if batch_id:
                logger.info(f"Started continuous order placement - Direction: {direction}, Batch: {batch_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error starting continuous placement: {e}")
            return False

    def place_next_order(self, current_price: float, candle_close_time: datetime.datetime) -> Optional[str]:
        """Place the next order in the sequence - EVERY CANDLE"""
        try:
            # if not self.order_placement_active or not self.current_direction:
            #     return None
            
            # PLACE ORDER EVERY CANDLE - no timing restrictions
            logger.info(f"Placing order for new candle at {candle_close_time}")
            
            # Get the next order price
            order_count = len([o for o in self.order_sequence if o["direction"] == self.current_direction]) + 1
            next_price = self._calculate_next_order_price(current_price, order_count)
            
            # Get current batch information
            current_batch = self._get_current_batch()
            if not current_batch:
                logger.error("No active batch found for order placement")
                return None
            
            # Create the order with NO SL/TP
            order_ticket = self._create_market_order(
                price=next_price,
                lot_size=current_batch["lot_size"],
                stop_loss=0,  # NO STOP LOSS
                take_profit=0,  # NO TAKE PROFIT
                direction=self.current_direction
            )
            
            if order_ticket:
                # Add to sequence and batch
                self._add_order_to_sequence(order_ticket, next_price, candle_close_time)
                self._add_order_to_batch(current_batch["batch_id"], order_ticket)
                
                self.last_order_time = candle_close_time
                
                logger.info(f"Order placed: {order_ticket} at {next_price} ({self.current_direction}) - NO SL/TP")
                return order_ticket
            
            return None
            
        except Exception as e:
            logger.error(f"Error placing next order: {e}")
            return None

    def manage_batch_stop_loss(self, batch_id: str, current_price: float) -> bool:
        """Manage stop loss for the entire batch (300 pips from last order)"""
        try:
            if batch_id not in self.batch_orders:
                return False
            
            batch = self.batch_orders[batch_id]
            
            # Get the last order in the batch
            if not batch["orders"]:
                return False
            
            last_order = batch["orders"][-1]
            last_order_price = last_order["price"]
            
            # Calculate batch stop loss (300 pips from last order)
            pip_value = self._get_pip_value()
            batch_sl_distance = 300.0  # 300 pips as specified
            
            if self.current_direction == "BUY":
                batch_sl_price = last_order_price - (batch_sl_distance / pip_value)
                sl_triggered = current_price <= batch_sl_price
            else:  # SELL
                batch_sl_price = last_order_price + (batch_sl_distance / pip_value)
                sl_triggered = current_price >= batch_sl_price
            
            if sl_triggered:
                logger.info(f"Batch SL triggered for {batch_id} at {current_price} (SL: {batch_sl_price})")
                return self._execute_batch_stop_loss(batch_id)
            
            return False
            
        except Exception as e:
            logger.error(f"Error managing batch stop loss: {e}")
            return False

    def switch_direction(self, new_direction: str, current_price: float) -> bool:
        """Switch trading direction and start new batch"""
        try:
            if new_direction == self.current_direction:
                return True  # No change needed
            
            # Close current batch
            current_batch = self._get_current_batch()
            if current_batch:
                self._close_batch(current_batch["batch_id"])
            
            # Start new batch in opposite direction
            self.current_direction = new_direction
            self.order_sequence.clear()  # Reset sequence for new direction
            
            # Create new batch with same parameters but opposite direction
            if current_batch:
                new_batch_id = self._create_new_batch(
                    direction=new_direction,
                    entry_price=current_price,
                    lot_size=current_batch["lot_size"],
                    stop_loss=current_batch["stop_loss"],
                    take_profit=current_batch["take_profit"]
                )
                
                if new_batch_id:
                    logger.info(f"Direction switched to {new_direction}, new batch: {new_batch_id}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error switching direction: {e}")
            return False

    def stop_continuous_placement(self) -> bool:
        """Stop continuous order placement"""
        try:
            self.order_placement_active = False
            
            # Close all active batches
            for batch_id in list(self.batch_orders.keys()):
                if self.batch_orders[batch_id]["active"]:
                    self._close_batch(batch_id)
            
            logger.info("Continuous order placement stopped")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping continuous placement: {e}")
            return False

    def get_order_statistics(self) -> Dict:
        """Get comprehensive order statistics"""
        try:
            total_orders = len(self.order_sequence)
            active_batches = sum(1 for batch in self.batch_orders.values() if batch["active"])
            total_batches = len(self.batch_orders)
            
            return {
                "total_orders_placed": total_orders,
                "active_batches": active_batches,
                "total_batches": total_batches,
                "current_direction": self.current_direction,
                "placement_active": self.order_placement_active,
                "last_order_time": self.last_order_time,
                "order_interval_pips": self.order_interval_pips
            }
            
        except Exception as e:
            logger.error(f"Error getting order statistics: {e}")
            return {}

    def validate_order_placement(self, price: float, direction: str) -> bool:
        """Validate that an order placement is legitimate"""
        try:
            # Check if we have sufficient margin
            if not self._check_margin_requirements():
                logger.warning("Insufficient margin for order placement")
                return False
            
            # Check if price is within reasonable range
            if not self._validate_price_range(price):
                logger.warning(f"Price {price} outside valid range")
                return False
            
            # Check if direction is valid
            if direction not in ["BUY", "SELL"]:
                logger.warning(f"Invalid direction: {direction}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating order placement: {e}")
            return False

    # Private helper methods

    def _create_new_batch(self, direction: str, entry_price: float, lot_size: float, 
                         stop_loss: float, take_profit: float) -> Optional[str]:
        """Create a new order batch"""
        try:
            batch_id = f"{self.symbol}_{direction}_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            
            self.batch_orders[batch_id] = {
                "batch_id": batch_id,
                "direction": direction,
                "entry_price": entry_price,
                "lot_size": lot_size,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "orders": [],
                "active": True,
                "created_time": datetime.datetime.utcnow()
            }
            
            logger.info(f"New batch created: {batch_id}")
            return batch_id
            
        except Exception as e:
            logger.error(f"Error creating new batch: {e}")
            return None

    def _get_current_batch(self) -> Optional[Dict]:
        """Get the current active batch"""
        try:
            for batch in self.batch_orders.values():
                if batch["active"] and batch["direction"] == self.current_direction:
                    return batch
            return None
            
        except Exception as e:
            logger.error(f"Error getting current batch: {e}")
            return None

    def _should_place_order_now(self, candle_close_time: datetime.datetime) -> bool:
        """Check if it's time to place the next order based on timing"""
        try:
            if not self.last_order_time:
                return True  # First order
            
            # Use real-time interval instead of candle interval for more responsive trading
            # Check if enough time has passed (minimum 30 seconds between orders)
            time_diff = (candle_close_time - self.last_order_time).total_seconds()
            min_interval = 30  # 30 seconds minimum between orders
            
            should_place = time_diff >= min_interval
            
            if not should_place:
                logger.debug(f"Order timing: {time_diff:.1f}s elapsed, need {min_interval}s minimum")
            
            return should_place
            
        except Exception as e:
            logger.error(f"Error checking order timing: {e}")
            return False

    def _calculate_next_order_price(self, current_price: float, order_count: int) -> float:
        """Calculate the next order price based on 50-pip intervals"""
        try:
            pip_value = self._get_pip_value()
            
            if self.current_direction == "BUY":
                # For BUY orders, place orders at higher prices
                next_price = current_price + (self.order_interval_pips * order_count / pip_value)
            else:  # SELL
                # For SELL orders, place orders at lower prices
                next_price = current_price - (self.order_interval_pips * order_count / pip_value)
            
            return round(next_price, 5)  # Round to 5 decimal places
            
        except Exception as e:
            logger.error(f"Error calculating next order price: {e}")
            return current_price

    def _create_market_order(self, price: float, lot_size: float, stop_loss: float, 
                           take_profit: float, direction: str) -> Optional[str]:
        """Create a market order using MetaTrader with enhanced validation"""
        try:
            # Verify MetaTrader object has required methods
            if not hasattr(self.meta_trader, 'order_send'):
                logger.error("MetaTrader object missing 'order_send' method")
                return None
            
            # Pre-validate order parameters to prevent error 10016
            if not self._validate_order_parameters(price, lot_size, 0, 0, direction):  # No SL/TP
                logger.error("Order parameter validation failed")
                return None
            
            # Get current market price for order validation
            current_price = self._get_current_market_price()
            if not current_price:
                logger.warning("Cannot get current market price - using provided price as fallback")
                # Use the provided price as fallback instead of failing
                current_price = price
            
            # For market orders, use current market price instead of specified price
            # This prevents error 10016 (invalid price)
            if direction == "BUY":
                market_price = current_price + (10 / self._get_pip_value())  # Add 1 pip spread buffer
            else:  # SELL
                market_price = current_price - (10 / self._get_pip_value())  # Subtract 1 pip spread buffer
            
            # Convert direction to MT5 order type
            order_type = 0 if direction == "BUY" else 1  # 0 = BUY, 1 = SELL
            
            # Create order request with NO STOP LOSS OR TAKE PROFIT
            order_request = {
                "action": 1,  # TRADE_ACTION_DEAL
                "symbol": self.symbol,
                "volume": round(lot_size, 2),  # Round to 2 decimal places
                "type": order_type,
                "price": round(market_price, 5),  # Use market price, rounded to 5 decimals
                "sl": 0,  # NO STOP LOSS
                "tp": 0,  # NO TAKE PROFIT
                "magic": self.magic_number,
                "comment": f"ACT_{direction}_{datetime.datetime.utcnow().strftime('%H%M%S')}",
                "type_time": 0,  # ORDER_TIME_GTC
                "type_filling": 1,  # ORDER_FILLING_IOC (Immediate or Cancel) - more reliable than FOK
            }
            
            # Log order request for debugging
            logger.debug(f"Sending order request: {order_request}")
            
            # Send order to MT5 with enhanced error handling and diagnostics
            try:
                result = self.meta_trader.order_send(order_request)
                logger.debug(f"Order result: {result}")
                
                # Enhanced None result handling with diagnostics
                if result is None:
                    logger.error("❌ Order failed: No response from MetaTrader")
                    # Run diagnostics only when there's a failure
                    self._diagnose_trading_conditions()
                    self._handle_order_send_none_result()
                    return None
                    
            except AttributeError as e:
                logger.error(f"MetaTrader order_send method not available: {e}")
                return None
            except Exception as e:
                logger.error(f"Error calling order_send: {e}")
                return None
            
            # Handle different result types
            if result is None:
                logger.error("Order failed: No response from MetaTrader")
                return None
            
            # Check if result has retcode attribute
            if hasattr(result, 'retcode'):
                if result.retcode == 10009:  # TRADE_RETCODE_DONE
                    order_id = getattr(result, 'order', None)
                    if order_id:
                        logger.info(f"✅ Order created successfully (NO SL/TP): {order_id}")
                        return str(order_id)
                    else:
                        logger.error("Order result missing order ID")
                        return None
                else:
                    logger.error(f"Order failed with retcode: {result.retcode}")
                    return None
            else:
                # Handle case where result doesn't have retcode
                logger.error(f"Order result format unexpected: {type(result)}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating market order: {e}")
            return None

    def _add_order_to_sequence(self, ticket: str, price: float, time: datetime.datetime):
        """Add order to the sequence tracking"""
        try:
            self.order_sequence.append({
                "ticket": ticket,
                "price": price,
                "time": time,
                "direction": self.current_direction
            })
            
        except Exception as e:
            logger.error(f"Error adding order to sequence: {e}")

    def _add_order_to_batch(self, batch_id: str, ticket: str):
        """Add order to the batch tracking"""
        try:
            if batch_id in self.batch_orders:
                order_info = {
                    "ticket": ticket,
                    "price": self.order_sequence[-1]["price"] if self.order_sequence else 0,
                    "time": datetime.datetime.utcnow()
                }
                self.batch_orders[batch_id]["orders"].append(order_info)
                
        except Exception as e:
            logger.error(f"Error adding order to batch: {e}")

    def handle_order_close(self, closed_ticket: str, close_reason: str = "unknown") -> Optional[str]:
        """Handle order close event - immediately place new order in opposite direction"""
        try:
            logger.info(f"Handling order close: {closed_ticket}, reason: {close_reason}")
            
            # Find the closed order in our tracking
            closed_order = None
            for order in self.order_sequence:
                if order["ticket"] == closed_ticket:
                    closed_order = order
                    break
            
            if not closed_order:
                logger.warning(f"Closed order {closed_ticket} not found in sequence")
                return None
            
            # Determine opposite direction
            old_direction = closed_order["direction"]
            new_direction = "SELL" if old_direction == "BUY" else "BUY"
            
            logger.info(f"Order {closed_ticket} closed ({old_direction}) → Placing {new_direction}")
            
            # Switch direction
            self.current_direction = new_direction
            
            # Get current market price
            current_price = self._get_current_market_price()
            if not current_price:
                logger.error("Cannot get current price for replacement order")
                return None
            
            # Get current batch info
            current_batch = self._get_current_batch()
            if not current_batch:
                logger.error("No active batch for replacement order")
                return None
            
            # Calculate next order price in new direction (50 pips away)
            pip_value = self._get_pip_value()
            if new_direction == "BUY":
                next_price = current_price + (50.0 / pip_value)
            else:  # SELL
                next_price = current_price - (50.0 / pip_value)
            
            # Create replacement order immediately
            replacement_ticket = self._create_market_order(
                price=next_price,
                lot_size=current_batch["lot_size"],
                stop_loss=0,  # NO STOP LOSS
                take_profit=0,  # NO TAKE PROFIT
                direction=new_direction
            )
            
            if replacement_ticket:
                # Add to sequence
                self._add_order_to_sequence(replacement_ticket, next_price, datetime.datetime.utcnow())
                self._add_order_to_batch(current_batch["batch_id"], replacement_ticket)
                
                logger.info(f"Replacement order placed: {replacement_ticket} at {next_price} ({new_direction})")
                return replacement_ticket
            
            return None
            
        except Exception as e:
            logger.error(f"Error handling order close: {e}")
            return None

    def _execute_batch_stop_loss(self, batch_id: str) -> bool:
        """Execute stop loss for entire batch"""
        try:
            if batch_id not in self.batch_orders:
                return False
            
            batch = self.batch_orders[batch_id]
            
            # Close all orders in the batch
            for order_info in batch["orders"]:
                try:
                    self._close_order(order_info["ticket"])
                except Exception as e:
                    logger.error(f"Error closing order {order_info['ticket']}: {e}")
            
            # Mark batch as closed
            batch["active"] = False
            batch["closed_time"] = datetime.datetime.utcnow()
            batch["closed_reason"] = "batch_stop_loss"
            
            logger.info(f"Batch {batch_id} stop loss executed")
            return True
            
        except Exception as e:
            logger.error(f"Error executing batch stop loss: {e}")
            return False

    def _close_batch(self, batch_id: str) -> bool:
        """Close a batch (mark as inactive)"""
        try:
            if batch_id in self.batch_orders:
                self.batch_orders[batch_id]["active"] = False
                self.batch_orders[batch_id]["closed_time"] = datetime.datetime.utcnow()
                logger.info(f"Batch {batch_id} closed")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error closing batch: {e}")
            return False

    def _close_order(self, ticket: str) -> bool:
        """Close a specific order"""
        try:
            # Get position info
            position = self.meta_trader.get_position_by_ticket(ticket)
            
            if not position:
                logger.warning(f"Position {ticket} not found")
                return False
            
            # Create close request
            close_request = {
                "action": 1,  # TRADE_ACTION_DEAL
                "symbol": self.symbol,
                "volume": position[0].volume,
                "type": 1 if position[0].type == 0 else 0,  # Opposite type
                "position": int(ticket),
                "magic": self.magic_number,
                "comment": f"ACT_CLOSE_{datetime.datetime.utcnow().strftime('%H%M%S')}",
            }
            
            # Send close request
            result = self.meta_trader.order_send(close_request)
            
            if result and result.retcode == 10009:
                logger.info(f"Order {ticket} closed successfully")
                return True
            else:
                logger.error(f"Failed to close order {ticket}: {result.retcode if result else 'No response'}")
                return False
                
        except Exception as e:
            logger.error(f"Error closing order {ticket}: {e}")
            return False

    def _get_pip_value(self) -> float:
        """Get pip value for the symbol"""
        if "JPY" in self.symbol:
            return 100.0  # 0.01 = 1 pip for JPY pairs
        elif "XAU" in self.symbol or "GOLD" in self.symbol.upper():
            return 100.0  # 0.01 = 1 pip for gold
        elif "BTC" in self.symbol or "ETH" in self.symbol:
            return 1.0    # 1.0 = 1 pip for crypto
        else:
            return 10000.0  # 0.0001 = 1 pip for major currency pairs

    def _check_margin_requirements(self) -> bool:
        """Check if there's sufficient margin for order placement"""
        try:
            # Get account info
            account_info = self.meta_trader.get_account_info()
            
            if not account_info:
                return False
            
            # Simple margin check (can be enhanced)
            # account_info is a dict, so access with keys
            free_margin = account_info.get('margin_free', 0)
            margin_level = account_info.get('margin_level', 0)
            
            # Require at least 200% margin level and some free margin
            return margin_level > 200 and free_margin > 100
            
        except Exception as e:
            logger.error(f"Error checking margin requirements: {e}")
            return False

    def _validate_price_range(self, price: float) -> bool:
        """Validate that price is within reasonable range"""
        try:
            # Get current market price - use multiple approaches for robustness
            tick = None
            
            # Try symbol_info_tick method first
            if hasattr(self.meta_trader, 'symbol_info_tick'):
                tick = self.meta_trader.symbol_info_tick(self.symbol)
            
            # Fallback to individual bid/ask methods if symbol_info_tick fails
            if not tick:
                try:
                    bid = self.meta_trader.get_bid(self.symbol)
                    ask = self.meta_trader.get_ask(self.symbol)
                    
                    if bid and ask:
                        # Create a tick-like object
                        class MockTick:
                            def __init__(self, bid, ask):
                                self.bid = bid
                                self.ask = ask
                        tick = MockTick(bid, ask)
                except Exception as e:
                    logger.warning(f"Fallback price retrieval failed: {e}")
            
            if not tick:
                logger.warning("Could not retrieve market prices for validation - allowing order")
                return True  # Allow order if we can't get price data
            
            current_price = (tick.bid + tick.ask) / 2
            
            # Check if price is within reasonable range - make this more tolerant
            pip_value = self._get_pip_value()
            
            # Use different max distances based on symbol type
            if "XAU" in self.symbol or "GOLD" in self.symbol.upper():
                max_distance = 5000.0  # 5000 pips for gold (more volatile)
            elif "BTC" in self.symbol or "ETH" in self.symbol:
                max_distance = 10000.0  # 10000 pips for crypto (very volatile)
            elif "JPY" in self.symbol:
                max_distance = 2000.0  # 2000 pips for JPY pairs
            else:
                max_distance = 3000.0  # 3000 pips for major currency pairs
            
            price_difference = abs(price - current_price) * pip_value
            
            is_valid = price_difference <= max_distance
            
            if not is_valid:
                logger.warning(f"Price {price} outside valid range (current: {current_price}, diff: {price_difference:.1f} pips, max: {max_distance})")
                
                # For debugging: log the symbol and pip value being used
                logger.debug(f"Symbol: {self.symbol}, Pip value: {pip_value}, Price diff calculation: {abs(price - current_price)} * {pip_value} = {price_difference}")
            else:
                logger.debug(f"Price {price} within valid range (current: {current_price}, diff: {price_difference:.1f} pips)")
            
            return is_valid
            
        except Exception as e:
            logger.error(f"Error validating price range: {e}")
            # Return True to allow trading to continue if validation fails
            return True

    def _validate_order_parameters(self, price: float, lot_size: float, stop_loss: float, 
                                 take_profit: float, direction: str) -> bool:
        """Validate order parameters to prevent MetaTrader errors"""
        try:
            # Validate lot size (must be positive and within reasonable range)
            if lot_size <= 0 or lot_size > 100:
                logger.error(f"Invalid lot size: {lot_size}")
                return False
            
            # Validate direction
            if direction not in ["BUY", "SELL"]:
                logger.error(f"Invalid direction: {direction}")
                return False
            
            # Validate prices (must be positive)
            if price <= 0:
                logger.error(f"Invalid price: {price}")
                return False
            
            if stop_loss < 0 or take_profit < 0:
                logger.error(f"Invalid SL/TP: SL={stop_loss}, TP={take_profit}")
                return False
            
            # Check margin requirements
            if not self._check_margin_requirements():
                logger.error("Insufficient margin for order")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating order parameters: {e}")
            return False

    def _get_current_market_price(self) -> Optional[float]:
        """Get current market price with fallback methods"""
        try:
            # Try symbol_info_tick method first
            if hasattr(self.meta_trader, 'symbol_info_tick'):
                try:
                    tick = self.meta_trader.symbol_info_tick(self.symbol)
                    if tick and hasattr(tick, 'bid') and hasattr(tick, 'ask'):
                        return (tick.bid + tick.ask) / 2
                except Exception as e:
                    logger.warning(f"symbol_info_tick failed: {e}")
            
            # Fallback to individual bid/ask methods
            if hasattr(self.meta_trader, 'get_bid') and hasattr(self.meta_trader, 'get_ask'):
                try:
                    bid = self.meta_trader.get_bid(self.symbol)
                    ask = self.meta_trader.get_ask(self.symbol)
                    
                    if bid and ask and bid > 0 and ask > 0:
                        return (bid + ask) / 2
                except Exception as e:
                    logger.warning(f"get_bid/get_ask failed: {e}")
            
            logger.error("All market price retrieval methods failed")
            return None
            
        except Exception as e:
            logger.error(f"Error getting current market price: {e}")
            return None

    def _diagnose_trading_conditions(self):
        """Diagnose trading conditions when order placement fails"""
        try:
            logger.info("🔍 DIAGNOSING TRADING CONDITIONS...")
            
            # Check MetaTrader connection
            try:
                account_info = self.meta_trader.get_account_info()
                if account_info:
                    logger.info(f"✅ MetaTrader connected - Account: {account_info.get('login', 'Unknown')}")
                    logger.info(f"   Balance: ${account_info.get('balance', 0):.2f}")
                    logger.info(f"   Equity: ${account_info.get('equity', 0):.2f}")
                    logger.info(f"   Free Margin: ${account_info.get('margin_free', 0):.2f}")
                    logger.info(f"   Margin Level: {account_info.get('margin_level', 0):.1f}%")
                else:
                    logger.error("❌ Cannot get account info - MetaTrader connection lost")
                    return
            except Exception as e:
                logger.error(f"❌ MetaTrader connection check failed: {e}")
                return
            
            # Check symbol availability and trading conditions
            try:
                symbol_info = self.meta_trader.get_symbol_info(self.symbol)
                if symbol_info:
                    logger.info(f"✅ Symbol {self.symbol} available")
                    logger.info(f"   Spread: {symbol_info.spread}")
                    logger.info(f"   Trade Mode: {getattr(symbol_info, 'trade_mode', 'Unknown')}")
                    logger.info(f"   Sessions: {getattr(symbol_info, 'trade_execution', 'Unknown')}")
                else:
                    logger.error(f"❌ Symbol {self.symbol} not available")
                    return
            except Exception as e:
                logger.error(f"❌ Symbol info check failed: {e}")
            
            # Check current market prices
            try:
                current_price = self._get_current_market_price()
                if current_price:
                    logger.info(f"✅ Market price available: {current_price}")
                else:
                    logger.error("❌ Cannot get market price")
            except Exception as e:
                logger.error(f"❌ Market price check failed: {e}")
            
            # Check existing orders
            try:
                orders = self.meta_trader.get_all_orders()
                positions = self.meta_trader.get_all_positions()
                logger.info(f"📊 Current orders: {len(orders) if orders else 0}")
                logger.info(f"📊 Current positions: {len(positions) if positions else 0}")
            except Exception as e:
                logger.error(f"❌ Orders/positions check failed: {e}")
                
        except Exception as e:
            logger.error(f"❌ Trading conditions diagnosis failed: {e}")

    def _handle_order_send_none_result(self):
        """Handle when MetaTrader order_send returns None with recovery attempts"""
        try:
            logger.warning("🔧 ATTEMPTING ORDER PLACEMENT RECOVERY...")
            
            # Wait a moment for potential temporary issues
            import time
            time.sleep(1)
            
            # Check if it's a temporary connection issue
            try:
                account_info = self.meta_trader.get_account_info()
                if not account_info:
                    logger.error("💀 MetaTrader connection lost - cannot recover")
                    return False
            except:
                logger.error("💀 MetaTrader connection lost - cannot recover")
                return False
            
            # Check if market is closed or restricted
            try:
                current_price = self._get_current_market_price()
                if not current_price:
                    logger.error("💀 Market data unavailable - market may be closed")
                    return False
            except:
                logger.error("💀 Market data unavailable - market may be closed")
                return False
            
            # Log common causes of None results
            logger.error("🚨 POSSIBLE CAUSES FOR ORDER FAILURE:")
            logger.error("   1. Market is closed for this symbol")
            logger.error("   2. Insufficient margin or balance")
            logger.error("   3. Symbol trading is disabled")
            logger.error("   4. MetaTrader terminal lost connection")
            logger.error("   5. Invalid order parameters")
            logger.error("   6. Broker restrictions or maintenance")
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Order recovery attempt failed: {e}")
            return False