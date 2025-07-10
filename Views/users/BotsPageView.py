import flet
from helpers.store import store
from helpers.actions_creators import GetUser, GetAccount, isMt5Authorized
from Views.globals.app_router import AppRoutes
from Views.globals.app_logger import app_logger
from fletx import Xview
from Strategy.AdvancedCyclesTrader_Organized import AdvancedCyclesTrader


class BotsPageView(Xview):
    def build(self):
        account_id = self.get_param('account')
        user_id = self.get_param('user')
        user_data = GetUser(user_id)
        if not user_data:
            self.back()
        auth = user_data.get('auth_api')
        bots = auth.get_account_bots(account_id)
        account_data = GetAccount(user_id, account_id)
        headline = flet.Text(
            value=account_data.name + " account",
            style=flet.TextStyle(
                size=28,
                weight=flet.FontWeight.BOLD,
                color=flet.Colors.PRIMARY,
            ),
            text_align=flet.TextAlign.CENTER,
        )

        bots_buttons = []
        for bot in bots:
            # Initialize strategy for each bot
            try:
                if hasattr(bot, 'strategy') and bot.strategy == 'AdvancedCyclesTrader':
                    meta_trader = store.get_state()['mt5'].get(user_id, {}).get(account_id)
                    if meta_trader:
                        strategy = AdvancedCyclesTrader(
                            meta_trader=meta_trader,
                            config=bot.config,
                            client=auth,
                            symbol=bot.symbol_name,
                            bot=bot
                        )
                        if not strategy.initialize():
                            app_logger.error(f"Failed to initialize strategy for bot {bot.id}")
                        else:
                            app_logger.info(f"Successfully initialized strategy for bot {bot.id}")
                            bot.strategy_instance = strategy
            except Exception as e:
                app_logger.error(f"Error initializing strategy for bot {bot.id}: {e}")

            bots_buttons.append(
                flet.ElevatedButton(
                    text=bot.name,
                    expand=False,
                    width=300,
                )
            )

        back_button = flet.Button(
            text="< back",
            on_click=lambda e: self.back(),
            expand=False,
            width=200,
            color=flet.Colors.TERTIARY,
        )
        
        launch_metatrader = flet.ElevatedButton(
            text="Metatrader is running" if isMt5Authorized(user_id,account_id) else "Launch MT5",
            on_click=lambda e: self.go(f'/MT5/{user_id}/{account_id}'),
            expand=False,
            width=200,
        )
        
        Bots_headline = flet.Text(
            value="Bots",
            style=flet.TextStyle(
                size=28,
                weight=flet.FontWeight.BOLD,
                color=flet.Colors.PRIMARY,
            ),
            text_align=flet.TextAlign.CENTER,
        )
        
        return flet.View(
            horizontal_alignment=flet.CrossAxisAlignment.CENTER,
            vertical_alignment=flet.MainAxisAlignment.CENTER,
            controls=[
                headline,
                launch_metatrader,
                Bots_headline,
                *bots_buttons,
                back_button,
            ]
        )
