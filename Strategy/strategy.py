from abc import ABC, abstractmethod

class Strategy(ABC):
    """The base class for all the trading strategies"""
    def __init__(self,  meta_trader, config, client):
        """Initialize the strategy"""
        self.meta_trader = meta_trader
        self.config = config
        self.client = client
        self.positions = []
        self.orders = []
        self.symbols = []
        self.stop=False
   
    @abstractmethod
    async def handle_event(self, event):
        """Handle the incoming event"""
        pass
    @abstractmethod
    def initialize(self):
        """ Initialize the CycleTrader strategy """
        pass
    def init_settings(self):
        """ Initialize the settings for the CycleTrader strategy """
        pass
    
    def update_configs(self, config):
        """
        This function updates the settings for the adaptive hedging strategy.

        Parameters:
        config (dict): The new configuration settings for the strategy.

        Returns:
        None
        """
        pass
        