"""
Enhanced Order Manager for Advanced Cycles Trader
Implements hybrid order placement strategy with immediate retry + background queue
"""

import threading
import time
import datetime
import asyncio
from typing import Dict, List, Optional, Tuple, Any
from queue import Queue, Empty
from Views.globals.app_logger import app_logger as logger
import MetaTrader5 as Mt5


class OrderDiagnostics:
    """Comprehensive failure analysis and logging for order placement"""
    
    def __init__(self):
        self.failure_history: List[Dict] = []
        self.success_history: List[Dict] = []
        self.failure_patterns: Dict[str, int] = {}
        self.max_history = 1000
        
    def record_failure(self, order_request: Dict, result: Any, error_type: str):
        """Record order placement failure for analysis"""
        try:
            failure_record = {
                "timestamp": time.time(),
                "datetime": datetime.datetime.utcnow().isoformat(),
                "order_request": order_request.copy(),
                "result": str(result),
                "error_type": error_type,
                "market_conditions": self._capture_market_conditions()
            }
            
            self.failure_history.append(failure_record)
            
            # Track failure patterns
            if error_type not in self.failure_patterns:
                self.failure_patterns[error_type] = 0
            self.failure_patterns[error_type] += 1
            
            # Maintain history size
            if len(self.failure_history) > self.max_history:
                self.failure_history = self.failure_history[-self.max_history:]
            
            logger.warning(f"Order failure recorded: {error_type} - {result}")
            
        except Exception as e:
            logger.error(f"Error recording order failure: {e}")
    
    def record_success(self, order_request: Dict, ticket: str, retry_count: int):
        """Record successful order placement"""
        try:
            success_record = {
                "timestamp": time.time(),
                "datetime": datetime.datetime.utcnow().isoformat(),
                "order_request": order_request.copy(),
                "ticket": ticket,
                "retry_count": retry_count,
                "market_conditions": self._capture_market_conditions()
            }
            
            self.success_history.append(success_record)
            
            # Maintain history size
            if len(self.success_history) > self.max_history:
                self.success_history = self.success_history[-self.max_history:]
            
            logger.info(f"Order success recorded: {ticket} (retries: {retry_count})")
            
        except Exception as e:
            logger.error(f"Error recording order success: {e}")
    
    def _capture_market_conditions(self) -> Dict:
        """Capture current market conditions for analysis"""
        return {
            "timestamp": time.time(),
            "market_hours": self._is_market_hours(),
            "connection_status": "unknown"  # Can be enhanced with actual status
        }
    
    def _is_market_hours(self) -> bool:
        """Check if market is currently open"""
        try:
            # Simplified market hours check (can be enhanced)
            current_time = datetime.datetime.utcnow()
            weekday = current_time.weekday()
            
            # Basic forex market hours (Sunday 22:00 UTC to Friday 22:00 UTC)
            if weekday == 6:  # Sunday
                return current_time.hour >= 22
            elif weekday == 5:  # Friday
                return current_time.hour < 22
            else:  # Monday-Thursday
                return True
        except Exception as e:
            logger.error(f"Error checking market hours: {e}")
            return True  # Default to True
    
    def get_failure_analysis(self) -> Dict:
        """Get comprehensive failure analysis"""
        try:
            total_failures = len(self.failure_history)
            total_successes = len(self.success_history)
            total_attempts = total_failures + total_successes
            
            if total_attempts == 0:
                return {"no_data": True}
            
            success_rate = (total_successes / total_attempts) * 100
            
            # Recent failure rate (last 100 attempts)
            recent_history = (self.failure_history[-50:] + self.success_history[-50:])
            recent_history.sort(key=lambda x: x["timestamp"])
            recent_failures = len([h for h in recent_history[-100:] if "error_type" in h])
            recent_success_rate = ((100 - recent_failures) / 100) * 100 if len(recent_history) >= 100 else success_rate
            
            return {
                "total_attempts": total_attempts,
                "total_failures": total_failures,
                "total_successes": total_successes,
                "success_rate": success_rate,
                "recent_success_rate": recent_success_rate,
                "failure_patterns": self.failure_patterns.copy(),
                "most_common_failure": max(self.failure_patterns.items(), key=lambda x: x[1])[0] if self.failure_patterns else None
            }
            
        except Exception as e:
            logger.error(f"Error getting failure analysis: {e}")
            return {"error": str(e)}


class EnhancedOrderManager:
    """
    Hybrid order placement strategy with immediate retry + background queue.
    Provides best balance of real-time performance and reliability for multi-cycle operations.
    """
    
    def __init__(self, meta_trader, symbol: str, magic_number: int):
        """
        Initialize enhanced order manager
        
        Args:
            meta_trader: MetaTrader 5 connection
            symbol: Trading symbol
            magic_number: Magic number for orders
        """
        self.meta_trader = meta_trader
        self.symbol = symbol
        self.magic_number = magic_number
        
        # Hybrid strategy settings
        self.immediate_retries = 2  # Quick retries before queuing
        self.retry_delays = [1, 2, 5]  # Exponential backoff seconds
        self.max_background_retries = 5  # Maximum background retry attempts
        self.background_queue: Queue = Queue()  # Failed orders for background processing
        
        # Order management
        self.order_sequence: List[Dict] = []
        self.active_orders: Dict[str, Dict] = {}  # ticket -> order_info
        self.failed_orders: Dict[str, Dict] = {}  # request_id -> order_request
        
        # Diagnostics and monitoring
        self.diagnostics = OrderDiagnostics()
        self.performance_metrics = {
            "immediate_success": 0,
            "retry_success": 0,
            "background_success": 0,
            "total_failures": 0,
            "queue_size": 0
        }
        
        # Background processing
        self.background_thread = None
        self.background_active = False
        self._start_background_processor()
        
        # Thread safety
        self.order_lock = threading.Lock()
        
        logger.info(f"EnhancedOrderManager initialized for {symbol} - Magic: {magic_number}")
        logger.info(f"Strategy: {self.immediate_retries} immediate retries + background queue")
    
    def place_order_with_resilience(self, order_request: Dict, cycle_id: str = None) -> Optional[str]:
        """
        Hybrid order placement with immediate + background retry
        
        Args:
            order_request: Order request parameters
            cycle_id: Associated cycle ID (optional)
            
        Returns:
            str: Order ticket if successful, None otherwise
        """
        try:
            request_id = f"{cycle_id}_{int(time.time() * 1000)}" if cycle_id else f"order_{int(time.time() * 1000)}"
            order_request["request_id"] = request_id
            order_request["cycle_id"] = cycle_id
            order_request["creation_time"] = time.time()
            
            # Phase 1: Immediate attempt
            ticket = self._attempt_immediate_placement(order_request)
            if ticket:
                self.performance_metrics["immediate_success"] += 1
                self.diagnostics.record_success(order_request, ticket, 0)
                return ticket
            
            # Phase 2: Immediate retries with exponential backoff
            for retry_count in range(self.immediate_retries):
                delay = self.retry_delays[min(retry_count, len(self.retry_delays) - 1)]
                time.sleep(delay)
                
                ticket = self._attempt_immediate_placement(order_request)
                if ticket:
                    self.performance_metrics["retry_success"] += 1
                    self.diagnostics.record_success(order_request, ticket, retry_count + 1)
                    return ticket
                
                logger.debug(f"Immediate retry {retry_count + 1} failed for {request_id}")
            
            # Phase 3: Queue for background processing
            logger.info(f"Queueing order {request_id} for background processing")
            self._queue_for_background_processing(order_request)
            
            return None  # Will be processed in background
            
        except Exception as e:
            logger.error(f"Error in resilient order placement: {e}")
            self.performance_metrics["total_failures"] += 1
            return None
    
    def place_market_order(self, direction: str, lot_size: float, price: float = None,
                          stop_loss: float = 0, take_profit: float = 0,
                          cycle_id: str = None) -> Optional[str]:
        """
        Place market order with resilience
        
        Args:
            direction: BUY or SELL
            lot_size: Order lot size
            price: Entry price (optional, uses market price if None)
            stop_loss: Stop loss price (0 for no SL)
            take_profit: Take profit price (0 for no TP)
            cycle_id: Associated cycle ID
            
        Returns:
            str: Order ticket if successful
        """
        try:
            # Get market price if not provided
            if price is None:
                if direction == "BUY":
                    price = self.meta_trader.get_ask(self.symbol)
                else:
                    price = self.meta_trader.get_bid(self.symbol)
                
                if price is None:
                    logger.error(f"Failed to get market price for {self.symbol}")
                    return None
            
            # Prepare order request
            order_request = {
                "symbol": self.symbol,
                "direction": direction,
                "lot_size": lot_size,
                "price": price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "magic_number": self.magic_number,
                "order_type": "MARKET",
                "comment": f"ACT_{cycle_id}" if cycle_id else "ACT_order"
            }
            
            return self.place_order_with_resilience(order_request, cycle_id)
            
        except Exception as e:
            logger.error(f"Error placing market order: {e}")
            return None
    
    def place_order(self, current_price: float, direction: str, 
                   lot_size: float, cycle_id: str = None) -> Optional[str]:
        """
        Place a simple market order
        
        Args:
            current_price: Current market price
            direction: Trading direction
            lot_size: Order lot size
            cycle_id: Associated cycle ID
            
        Returns:
            str: Order ticket if successful
        """
        try:
            # Place order at current market price
            order_price = current_price
            
            return self.place_market_order(
                direction=direction,
                lot_size=lot_size,
                price=order_price,
                cycle_id=cycle_id
            )
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None
    
    def process_background_queue(self) -> Dict:
        """
        Background thread processing failed orders
        
        Returns:
            Dict: Processing results
        """
        try:
            processed = 0
            successful = 0
            failed = 0
            
            # Process all queued orders
            while not self.background_queue.empty():
                try:
                    order_request = self.background_queue.get_nowait()
                    processed += 1
                    
                    # Attempt background placement with retries
                    ticket = self._attempt_background_placement(order_request)
                    
                    if ticket:
                        successful += 1
                        self.performance_metrics["background_success"] += 1
                        self.diagnostics.record_success(order_request, ticket, 
                                                      order_request.get("background_retries", 0))
                    else:
                        failed += 1
                        self.performance_metrics["total_failures"] += 1
                        
                        # Store failed order for analysis
                        request_id = order_request.get("request_id", "unknown")
                        self.failed_orders[request_id] = order_request
                    
                except Empty:
                    break
                except Exception as e:
                    logger.error(f"Error processing background queue item: {e}")
                    failed += 1
            
            return {
                "processed": processed,
                "successful": successful,
                "failed": failed,
                "queue_remaining": self.background_queue.qsize()
            }
            
        except Exception as e:
            logger.error(f"Error processing background queue: {e}")
            return {"error": str(e)}
    
    def _attempt_immediate_placement(self, order_request: Dict) -> Optional[str]:
        """Attempt immediate order placement"""
        try:
            # Validate order parameters
            if not self._validate_order_request(order_request):
                return None
            
            # Execute order through MetaTrader
            result = self._execute_order_request(order_request)
            
            if result is None:
                self.diagnostics.record_failure(order_request, result, "none_result")
                return None
            
            # Check if result contains ticket
            ticket = self._extract_ticket_from_result(result)
            
            if ticket:
                # Record successful order
                with self.order_lock:
                    self.active_orders[ticket] = {
                        "request": order_request.copy(),
                        "ticket": ticket,
                        "placement_time": time.time(),
                        "status": "active"
                    }
                
                return ticket
            else:
                self.diagnostics.record_failure(order_request, result, "no_ticket")
                return None
            
        except Exception as e:
            logger.error(f"Error in immediate placement: {e}")
            self.diagnostics.record_failure(order_request, str(e), "exception")
            return None
    
    def _attempt_background_placement(self, order_request: Dict) -> Optional[str]:
        """Attempt background order placement with extended retries"""
        try:
            retry_count = order_request.get("background_retries", 0)
            
            if retry_count >= self.max_background_retries:
                logger.warning(f"Background placement exceeded max retries: {order_request.get('request_id')}")
                return None
            
            # Update retry count
            order_request["background_retries"] = retry_count + 1
            
            # Extended delay for background retries
            delay = min(retry_count * 5, 30)  # Max 30 seconds delay
            time.sleep(delay)
            
            # Attempt placement
            ticket = self._attempt_immediate_placement(order_request)
            
            if not ticket and retry_count < self.max_background_retries - 1:
                # Re-queue for another attempt
                self.background_queue.put(order_request)
            
            return ticket
            
        except Exception as e:
            logger.error(f"Error in background placement: {e}")
            return None
    
    def _queue_for_background_processing(self, order_request: Dict):
        """Queue order for background processing"""
        try:
            order_request["queued_time"] = time.time()
            order_request["background_retries"] = 0
            
            self.background_queue.put(order_request)
            self.performance_metrics["queue_size"] = self.background_queue.qsize()
            
            logger.debug(f"Order queued for background processing: {order_request.get('request_id')}")
            
        except Exception as e:
            logger.error(f"Error queueing order for background processing: {e}")
    
    def _execute_order_request(self, order_request: Dict) -> Any:
        """Execute order request through MetaTrader"""
        try:
            direction = order_request["direction"]
            symbol = order_request["symbol"]
            lot_size = order_request["lot_size"]
            price = order_request["price"]
            stop_loss = order_request.get("stop_loss", 0)
            take_profit = order_request.get("take_profit", 0)
            magic_number = order_request.get("magic_number", self.magic_number)
            comment = order_request.get("comment", "ACT_order")
            
            # Execute through MetaTrader
            if direction == "BUY":
                # Create a proper request dictionary for MetaTrader.order_send
                mt_request = {
                    "action": Mt5.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": float(lot_size),
                    "type": Mt5.ORDER_TYPE_BUY,
                    "price": price,
                    "magic": magic_number,
                    "comment": comment,
                    "type_time": Mt5.ORDER_TIME_GTC,
                    "type_filling": Mt5.ORDER_FILLING_FOK,
                }
                
                # Add SL/TP if provided
                if stop_loss > 0:
                    mt_request["sl"] = stop_loss
                if take_profit > 0:
                    mt_request["tp"] = take_profit
                    
                result = self.meta_trader.order_send(mt_request)
            else:  # SELL
                # Create a proper request dictionary for MetaTrader.order_send
                mt_request = {
                    "action": Mt5.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": float(lot_size),
                    "type": Mt5.ORDER_TYPE_SELL,
                    "price": price,
                    "magic": magic_number,
                    "comment": comment,
                    "type_time": Mt5.ORDER_TIME_GTC,
                    "type_filling": Mt5.ORDER_FILLING_FOK,
                }
                
                # Add SL/TP if provided
                if stop_loss > 0:
                    mt_request["sl"] = stop_loss
                if take_profit > 0:
                    mt_request["tp"] = take_profit
                    
                result = self.meta_trader.order_send(mt_request)
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing order request: {e}")
            return None
    
    def _extract_ticket_from_result(self, result: Any) -> Optional[str]:
        """Extract ticket from MetaTrader result"""
        try:
            if result is None:
                return None
            
            # Handle different result formats
            if hasattr(result, 'order'):
                return str(result.order)
            elif hasattr(result, 'ticket'):
                return str(result.ticket)
            elif isinstance(result, dict) and 'order' in result:
                return str(result['order'])
            elif isinstance(result, dict) and 'ticket' in result:
                return str(result['ticket'])
            elif isinstance(result, (int, str)) and str(result).isdigit():
                return str(result)
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting ticket from result: {e}")
            return None
    
    def _validate_order_request(self, order_request: Dict) -> bool:
        """Validate order request parameters"""
        try:
            required_fields = ["symbol", "direction", "lot_size", "price"]
            
            for field in required_fields:
                if field not in order_request:
                    logger.error(f"Missing required field: {field}")
                    return False
            
            # Validate direction
            if order_request["direction"] not in ["BUY", "SELL"]:
                logger.error(f"Invalid direction: {order_request['direction']}")
                return False
            
            # Validate lot size
            if order_request["lot_size"] <= 0:
                logger.error(f"Invalid lot size: {order_request['lot_size']}")
                return False
            
            # Validate price
            if order_request["price"] <= 0:
                logger.error(f"Invalid price: {order_request['price']}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating order request: {e}")
            return False
    
    def _get_last_order_price(self, cycle_id: str, direction: str) -> Optional[float]:
        """Get last order price for cycle and direction"""
        try:
            last_price = None
            last_time = 0
            
            for ticket, order_info in self.active_orders.items():
                request = order_info["request"]
                if (request.get("cycle_id") == cycle_id and 
                    request.get("direction") == direction and
                    order_info["placement_time"] > last_time):
                    last_price = request["price"]
                    last_time = order_info["placement_time"]
            
            return last_price
            
        except Exception as e:
            logger.error(f"Error getting last order price: {e}")
            return None
    
    def _start_background_processor(self):
        """Start background processing thread"""
        try:
            self.background_active = True
            self.background_thread = threading.Thread(target=self._background_processor_loop, daemon=True)
            self.background_thread.start()
            logger.info("Background order processor started")
            
        except Exception as e:
            logger.error(f"Error starting background processor: {e}")
    
    def _background_processor_loop(self):
        """Background processor main loop"""
        try:
            while self.background_active:
                try:
                    # Process queue every 5 seconds
                    time.sleep(5)
                    
                    if not self.background_queue.empty():
                        results = self.process_background_queue()
                        if results.get("processed", 0) > 0:
                            logger.info(f"Background processing: {results}")
                    
                except Exception as e:
                    logger.error(f"Error in background processor loop: {e}")
                    time.sleep(10)  # Longer delay on error
            
        except Exception as e:
            logger.error(f"Fatal error in background processor: {e}")
    
    def _get_pip_value(self) -> float:
        """Get pip value for the current symbol"""
        try:
            if 'JPY' in self.symbol:
                return 100.0  # JPY pairs have 2 decimal places
            else:
                return 10000.0  # Most pairs have 4 decimal places
        except Exception as e:
            logger.error(f"Error getting pip value: {e}")
            return 10000.0  # Default
    
    def stop_background_processor(self):
        """Stop background processing"""
        try:
            self.background_active = False
            if self.background_thread and self.background_thread.is_alive():
                self.background_thread.join(timeout=10)
            logger.info("Background order processor stopped")
            
        except Exception as e:
            logger.error(f"Error stopping background processor: {e}")
    
    def get_manager_statistics(self) -> Dict:
        """Get comprehensive manager statistics"""
        try:
            stats = {
                "symbol": self.symbol,
                "magic_number": self.magic_number,
                "performance_metrics": self.performance_metrics.copy(),
                "active_orders": len(self.active_orders),
                "failed_orders": len(self.failed_orders),
                "background_queue_size": self.background_queue.qsize(),
                "background_active": self.background_active,
                "diagnostics": self.diagnostics.get_failure_analysis()
            }
            
            # Update queue size metric
            self.performance_metrics["queue_size"] = self.background_queue.qsize()
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting manager statistics: {e}")
            return {"error": str(e)} 