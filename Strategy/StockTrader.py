from Strategy.strategy import Strategy


class StockTrader(Strategy):
    def __init__(self, meta_trader, config, client):
        self.meta_trader = meta_trader
        self.config = config
        self.client = client
        self.positions = {}
        self.orders = {}
        self.symbols = []

    def init_settings(self):
        """ Initialize the settings for the StockTrader strategy """
        pass

    def initialize(self, config, settings):
        """ Initialize the StockTrader strategy """
        pass

    def update_configs(self, config, settings):
        """
        This function updates the settings for the adaptive hedging strategy.

        Parameters:
        config (dict): The new configuration settings for the strategy.

        Returns:
        None
        """
        self.config = config
        self.init_settings()
        
        # Update magic number in PocketBase if it has changed
        self._update_magic_number_if_needed(config)

    def _update_magic_number_if_needed(self, cfg):
        """Update magic number in PocketBase if it has changed"""
        try:
            if 'magic_number' in cfg and hasattr(self, 'bot') and cfg['magic_number'] != self.bot.magic:
                # Update magic number in PocketBase
                if hasattr(self.client, 'update_bot_magic_number'):
                    result = self.client.update_bot_magic_number(self.bot.id, cfg['magic_number'])
                    if result:
                        self.bot.magic = cfg['magic_number']
                        print(f"✅ Magic number updated to {cfg['magic_number']} in PocketBase")
                    else:
                        print(f"❌ Failed to update magic number in PocketBase")
                else:
                    print(f"⚠️ Client does not support update_bot_magic_number method")
        except Exception as e:
            print(f"❌ Error updating magic number: {str(e)}")
