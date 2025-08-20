import flet
from helpers.store import store
from helpers.actions_creators import GetUser, GetAccount, isMt5Authorized
from Views.globals.app_router import AppRoutes
from Views.globals.app_logger import app_logger
from fletx import Xview
from Strategy.AdvancedCyclesTrader_Organized import AdvancedCyclesTrader
from Strategy.MoveGuard import MoveGuard
from Api.Events.flutter_event_system import get_strategy_manager


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

        # Get the global strategy manager
        strategy_manager = get_strategy_manager()

        bots_buttons = []
        for bot in bots:
            # Initialize strategy for each bot
            try:
                meta_trader = store.get_state()['mt5'].get(user_id, {}).get(account_id)
                if meta_trader:
                    strategy = None
                    
                    # Initialize strategy based on bot type
                    if hasattr(bot, 'strategy') and bot.strategy == 'AdvancedCyclesTrader':
                        strategy = AdvancedCyclesTrader(
                            meta_trader=meta_trader,
                            config=bot.config,
                            client=auth,
                            symbol=bot.symbol_name,
                            bot=bot
                        )
                    elif hasattr(bot, 'strategy') and bot.strategy == 'MoveGuard':
                        strategy = MoveGuard(
                            meta_trader=meta_trader,
                            config=bot.config,
                            client=auth,
                            symbol=bot.symbol_name,
                            bot=bot
                        )
                    
                    if strategy:
                        if not strategy.initialize():
                            app_logger.error(f"Failed to initialize strategy for bot {bot.id}")
                        else:
                            app_logger.info(f"Successfully initialized strategy for bot {bot.id}")
                            bot.strategy_instance = strategy
                            
                            # Register strategy with the strategy manager for event routing
                            strategy_manager.register_strategy(bot.id, strategy)
                            app_logger.info(f"✅ Strategy registered with event manager for bot {bot.id}")
                            
            except Exception as e:
                app_logger.error(f"Error initializing strategy for bot {bot.id}: {e}")

            bots_buttons.append(
                flet.ElevatedButton(
                    text=bot.name,
                    expand=False,
                    width=300,
                )
            )

        # Get current version for display
        state = store.get_state()
        bot_instance_state = state.get('bot_instance', {})
        bot_instance = bot_instance_state.get('bot_instance')
        current_version = bot_instance.current_version if bot_instance else "Unknown"

        # Manual update check button
        def check_updates(e):
            """Handle manual update check"""
            try:
                if hasattr(self.page, 'check_for_updates'):
                    self.page.check_for_updates()
                else:
                    # Fallback: show message
                    self.page.show_snack_bar(
                        flet.SnackBar(
                            content=flet.Text("Auto-updater not available"),
                            bgcolor=flet.Colors.ORANGE
                        )
                    )
            except Exception as ex:
                app_logger.error(f"Error checking for updates: {ex}")
                self.page.show_snack_bar(
                    flet.SnackBar(
                        content=flet.Text(f"Update check failed: {str(ex)}"),
                        bgcolor=flet.Colors.RED
                    )
                )

        update_button = flet.ElevatedButton(
            text=f"🔄 Check for Updates (v{current_version})",
            on_click=check_updates,
            expand=False,
            width=300,
            color=flet.Colors.BLUE,
            icon=flet.Icons.UPDATE
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

        # Version info text
        version_info = flet.Text(
            value=f"Patrick Display Bot v{current_version}",
            style=flet.TextStyle(
                size=14,
                color=flet.Colors.ON_SURFACE_VARIANT,
            ),
            text_align=flet.TextAlign.CENTER,
        )
        
        return flet.View(
            horizontal_alignment=flet.CrossAxisAlignment.CENTER,
            vertical_alignment=flet.MainAxisAlignment.CENTER,
            controls=[
                headline,
                version_info,
                launch_metatrader,
                Bots_headline,
                *bots_buttons,
                flet.Divider(),
                update_button,
                back_button,
            ]
        )
