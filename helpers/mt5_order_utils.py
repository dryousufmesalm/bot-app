"""
MT5 Order Placement Utilities

This module provides unified MT5 order placement functionality that can be reused
across all trading strategies. It standardizes the order placement process and
ensures consistent behavior across different strategies.
"""

from Views.globals.app_logger import app_logger as logger
from typing import Dict, List, Optional, Any, Tuple
import traceback
import datetime


class MT5OrderUtils:
    """Utility class for MT5 order placement operations"""
    
    @staticmethod
    def place_buy_order(meta_trader, symbol: str, lot_size: float, magic_number: int, 
                       stop_loss_pips: float = 0.0, take_profit_pips: float = 0.0, 
                       slippage: int = 20, comment: str = "") -> Tuple[bool, Optional[Dict]]:
        """
        Place a buy order using MT5
        
        Args:
            meta_trader: MetaTrader instance
            symbol: Trading symbol
            lot_size: Order volume
            magic_number: Magic number for the order
            stop_loss_pips: Stop loss in pips (0.0 for no stop loss)
            take_profit_pips: Take profit in pips (0.0 for no take profit)
            slippage: Maximum slippage in points
            comment: Order comment
            
        Returns:
            Tuple[bool, Optional[Dict]]: (success, order_data)
        """
        try:
            logger.info(f"📈 Placing BUY order: {symbol} {lot_size} lots at market")
            
            # Create order in meta trader with all required parameters
            order_data = meta_trader.buy(
                symbol=symbol,
                volume=lot_size,
                magic=magic_number,
                sl=stop_loss_pips,
                tp=take_profit_pips,
                sltp_type="PIPS",
                slippage=slippage,
                comment=comment
            )
            
            # Check if order was successful
            if not order_data or len(order_data) == 0:
                logger.error("Buy order failed - no order data returned")
                return False, None
                
            # Extract order information - order_data is a tuple of _MqlTradePosition objects
            if isinstance(order_data, tuple) and len(order_data) > 0:
                order_info = order_data[0]  # Get the first position from the tuple
            elif isinstance(order_data, list) and len(order_data) > 0:
                order_info = order_data[0]  # Get the first position from the list
            else:
                order_info = order_data  # Fallback for other cases
            
            # Create standardized order data structure
            processed_order_data = {
                'price': meta_trader.get_ask(symbol),
                'ticket': str(order_info.ticket) if hasattr(order_info, 'ticket') else '',
                'volume': lot_size,
                'symbol': symbol,
                'type': 0,  # BUY = 0
                'magic_number': magic_number,
                'comment': comment,
                'sl': stop_loss_pips,
                'tp': take_profit_pips,
                'status': 'active'
            }
            
            logger.info(f"✅ BUY order placed successfully: Ticket {processed_order_data['ticket']}")
            return True, processed_order_data
            
        except Exception as e:
            logger.error(f"❌ Error placing BUY order: {str(e)}")
            logger.error(traceback.format_exc())
            return False, None
    
    @staticmethod
    def place_sell_order(meta_trader, symbol: str, lot_size: float, magic_number: int,
                        stop_loss_pips: float = 0.0, take_profit_pips: float = 0.0,
                        slippage: int = 20, comment: str = "") -> Tuple[bool, Optional[Dict]]:
        """
        Place a sell order using MT5
        
        Args:
            meta_trader: MetaTrader instance
            symbol: Trading symbol
            lot_size: Order volume
            magic_number: Magic number for the order
            stop_loss_pips: Stop loss in pips (0.0 for no stop loss)
            take_profit_pips: Take profit in pips (0.0 for no take profit)
            slippage: Maximum slippage in points
            comment: Order comment
            
        Returns:
            Tuple[bool, Optional[Dict]]: (success, order_data)
        """
        try:
            logger.info(f"📉 Placing SELL order: {symbol} {lot_size} lots at market")
            
            # Create order in meta trader with all required parameters
            order_data = meta_trader.sell(
                symbol=symbol,
                volume=lot_size,
                magic=magic_number,
                sl=stop_loss_pips,
                tp=take_profit_pips,
                sltp_type="PIPS",
                slippage=slippage,
                comment=comment
            )
            
            # Check if order was successful
            if not order_data or len(order_data) == 0:
                logger.error("Sell order failed - no order data returned")
                return False, None
                
            # Extract order information - order_data is a tuple of _MqlTradePosition objects
            if isinstance(order_data, tuple) and len(order_data) > 0:
                order_info = order_data[0]  # Get the first position from the tuple
            elif isinstance(order_data, list) and len(order_data) > 0:
                order_info = order_data[0]  # Get the first position from the list
            else:
                order_info = order_data  # Fallback for other cases
            
            # Create standardized order data structure
            processed_order_data = {
                'price': meta_trader.get_bid(symbol),
                'ticket': str(order_info.ticket) if hasattr(order_info, 'ticket') else '',
                'volume': lot_size,
                'symbol': symbol,
                'type': 1,  # SELL = 1
                'magic_number': magic_number,
                'comment': comment,
                'sl': stop_loss_pips,
                'tp': take_profit_pips,
                'status': 'active'
            }
            
            logger.info(f"✅ SELL order placed successfully: Ticket {processed_order_data['ticket']}")
            return True, processed_order_data
            
        except Exception as e:
            logger.error(f"❌ Error placing SELL order: {str(e)}")
            logger.error(traceback.format_exc())
            return False, None
    
    @staticmethod
    def place_dual_orders(meta_trader, symbol: str, lot_size: float, magic_number: int,
                         stop_loss_pips: float = 0.0, take_profit_pips: float = 0.0,
                         slippage: int = 20, comment: str = "") -> Tuple[bool, Optional[Dict], Optional[Dict]]:
        """
        Place both BUY and SELL orders simultaneously
        
        Args:
            meta_trader: MetaTrader instance
            symbol: Trading symbol
            lot_size: Order volume
            magic_number: Magic number for the orders
            stop_loss_pips: Stop loss in pips (0.0 for no stop loss)
            take_profit_pips: Take profit in pips (0.0 for no take profit)
            slippage: Maximum slippage in points
            comment: Order comment
            
        Returns:
            Tuple[bool, Optional[Dict], Optional[Dict]]: (success, buy_order_data, sell_order_data)
        """
        try:
            logger.info(f"🔄 Placing DUAL orders: {symbol} {lot_size} lots each")
            
            # Place buy order
            buy_success, buy_order_data = MT5OrderUtils.place_buy_order(
                meta_trader, symbol, lot_size, magic_number, 
                stop_loss_pips, take_profit_pips, slippage, f"{comment}_BUY"
            )
            
            # Place sell order
            sell_success, sell_order_data = MT5OrderUtils.place_sell_order(
                meta_trader, symbol, lot_size, magic_number,
                stop_loss_pips, take_profit_pips, slippage, f"{comment}_SELL"
            )
            
            success = buy_success and sell_success
            
            if success:
                logger.info("✅ DUAL orders placed successfully")
            else:
                logger.error("❌ Failed to place one or both DUAL orders")
                
            return success, buy_order_data, sell_order_data
            
        except Exception as e:
            logger.error(f"❌ Error placing DUAL orders: {str(e)}")
            logger.error(traceback.format_exc())
            return False, None, None
    
    @staticmethod
    def close_order(meta_trader, order_ticket: str, deviation: int = 10) -> bool:
        """
        Close an order by ticket
        
        Args:
            meta_trader: MetaTrader instance
            order_ticket: Order ticket to close
            deviation: Maximum deviation in points
            
        Returns:
            bool: True if order was closed successfully
        """
        try:
            logger.info(f"🔄 Closing order: {order_ticket}")
            
            # Get the order/position
            order_data = meta_trader.get_position_by_ticket(order_ticket)
            if not order_data:
                logger.warning(f"Order {order_ticket} not found")
                return False
            
            # Close the order
            result = meta_trader.close_position(order_data, deviation)
            
            if result:
                logger.info(f"✅ Order {order_ticket} closed successfully")
                return True
            else:
                logger.error(f"❌ Failed to close order {order_ticket}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error closing order {order_ticket}: {str(e)}")
            logger.error(traceback.format_exc())
            return False
    
    @staticmethod
    def get_current_prices(meta_trader, symbol: str) -> Optional[Dict[str, float]]:
        """
        Get current bid and ask prices for a symbol
        
        Args:
            meta_trader: MetaTrader instance
            symbol: Trading symbol
            
        Returns:
            Optional[Dict[str, float]]: Dictionary with 'bid' and 'ask' prices
        """
        try:
            bid = meta_trader.get_bid(symbol)
            ask = meta_trader.get_ask(symbol)
            
            if bid is None or ask is None:
                logger.error(f"Failed to get prices for {symbol}")
                return None
                
            return {
                'bid': bid,
                'ask': ask,
                'spread': ask - bid
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting current prices for {symbol}: {str(e)}")
            return None

    @staticmethod
    def _convert_to_moveguard_format(order_data: dict, direction: str) -> dict:
        """
        Convert MT5OrderUtils format to MoveGuard format
        
        Args:
            order_data: Order data in MT5OrderUtils format
            direction: Order direction ('BUY' or 'SELL')
            
        Returns:
            dict: Order data in MoveGuard format
        """
        try:
            # Preserve existing grid level if present, otherwise set to -1 for initial orders
            existing_grid_level = order_data.get('grid_level')
            if existing_grid_level is not None:
                grid_level = existing_grid_level
                is_initial = False
                order_type = f'grid_{grid_level}' if grid_level > 0 else 'initial'
            else:
                grid_level = -1  # -1 indicates initial order (not a grid order)
                is_initial = True
                order_type = 'initial'
            
            # Convert MT5OrderUtils format to MoveGuard format
            moveguard_order = {
                'order_id': order_data.get('ticket', ''),
                'ticket': order_data.get('ticket', ''),
                'direction': direction,
                'price': order_data.get('price', 0.0),
                'lot_size': order_data.get('volume', 0.0),
                'is_initial': is_initial,
                'order_type': order_type,
                'status': 'active',
                'placed_at': datetime.datetime.now().isoformat(),
                'profit': 0.0,
                'profit_pips': 0.0,
                'last_profit_update': datetime.datetime.now().isoformat(),
                'grid_level': grid_level
            }
            
            return moveguard_order
            
        except Exception as e:
            logger.error(f"❌ Error converting order data to MoveGuard format: {str(e)}")
            return order_data  # Return original if conversion fails
