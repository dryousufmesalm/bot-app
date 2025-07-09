import MetaTrader5 as mt5
import logging

logger = logging.getLogger(__name__)

class SymbolManager:
    """ Symbol manager class to manage the symbols """
    def __init__(self):
        self.symbols = {}
        self.selected_symbol = None
        
    def get_symbols(self):
        """ Get all available symbols """
        try:
            symbols = mt5.symbols_get()
            if not symbols:
                logger.error("Failed to get symbols from MetaTrader5")
                return {}
                
            self.symbols = {symbol.name: symbol for symbol in symbols}
            return self.symbols
            
        except Exception as e:
            logger.error(f"Error getting symbols: {e}")
            return {}
    
    def get_selected_symbol(self):
        """ Get the selected symbol """
        return self.selected_symbol
    
    def set_selected_symbol(self, symbol):
        """ Set the selected symbol """
        try:
            if isinstance(symbol, str):
                # If string provided, try to get symbol info
                symbol_info = mt5.symbol_info(symbol)
                if not symbol_info:
                    logger.error(f"Symbol info not found for {symbol}")
                    return None
                self.selected_symbol = symbol_info
            else:
                self.selected_symbol = symbol
            return self.selected_symbol
            
        except Exception as e:
            logger.error(f"Error setting selected symbol: {e}")
            return None
    
    def select_symbol(self, symbol_name):
        """ Select a symbol """
        try:
            # First try to get from cached symbols
            if symbol_name in self.symbols:
                self.selected_symbol = self.symbols[symbol_name]
                return self.selected_symbol
            
            # If not in cache, try to get from MT5 directly
            symbol_info = mt5.symbol_info(symbol_name)
            if not symbol_info:
                logger.error(f"Symbol info not found for {symbol_name}")
                return None
                
            # Cache the symbol info
            self.symbols[symbol_name] = symbol_info
            self.selected_symbol = symbol_info
            return self.selected_symbol
            
        except Exception as e:
            logger.error(f"Error selecting symbol {symbol_name}: {e}")
            return None
            
    def get_symbol_info(self, symbol_name):
        """Get symbol info with error handling"""
        try:
            # First try to get from cached symbols
            if symbol_name in self.symbols:
                return self.symbols[symbol_name]
            
            # If not in cache, try to get from MT5 directly
            symbol_info = mt5.symbol_info(symbol_name)
            if not symbol_info:
                logger.error(f"Symbol info not found for {symbol_name}")
                return None
                
            # Cache the symbol info
            self.symbols[symbol_name] = symbol_info
            return symbol_info
            
        except Exception as e:
            logger.error(f"Error getting symbol info for {symbol_name}: {e}")
            return None
