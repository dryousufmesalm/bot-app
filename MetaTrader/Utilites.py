from SymbolManager import SymbolManager
class Utillites :
    """ A class that contains all the utility functions for the MetaTrader API """
    def __init__(self,symbol):
        self.symbol = symbol
        self.points=None
        self.spread=None
        self.pips=None
        self.symbol_manager = SymbolManager()
        
    def get_symbols(self):
        """ Get all available symbols """
        return self.symbol_manager.get_symbols()
    def set_symbols(self,symbol):
        """ Set the selected symbol """
        return self.symbol=symbol
    def get_symbol_info(self):
        """ Get the information of a symbol """
        return self.symbol_manager.select_symbol(self.symbol)
    
    def get_symbol_points(self) :
        """ Get the points of a symbol """
        return self.symbol_manager.select_symbol(self.symbol).point
    
    def get_symbol_spread(self):
        """ Get the spread of a symbol """
        return self.symbol_manager.select_symbol(self.symbol).spread
    
    def get_symbol_pips(self):
        """ Get the pips of a symbol """
        return self.symbol_manager.select_symbol(self.symbol).point*10
    def Ask(self):
        """ Get the ask price of a symbol """
        return mt5.symbol_info_tick(self.symbol).ask
    def Bid(self, symbol):
        """ Get the bid price of a symbol """
        return mt5.symbol_info_tick(self.symbol).bid
    