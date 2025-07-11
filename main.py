#!/usr/bin/env python3
"""
Patrick Display Bot - Main Entry Point
Enhanced with Auto-Update System
"""

import os
import sys
import flet
import asyncio
import signal
from pathlib import Path
from Views.globals.app_logger import app_logger as logger
from Views.globals.auto_updater import AutoUpdater

# Add the bot app directory to Python path
bot_app_dir = Path(__file__).parent
sys.path.insert(0, str(bot_app_dir))

# Import main application components
from Views.globals.app_router import AppRoutes
from helpers.store import store

class PatrickDisplayBot:
    """Main bot application with auto-update capability"""
    
    def __init__(self):
        self.auto_updater = None
        self.app_running = False
        self.current_version = self._get_current_version()
        
    def _get_current_version(self) -> str:
        """Get current bot version from version.txt"""
        try:
            version_file = bot_app_dir / "version.txt"
            if version_file.exists():
                return version_file.read_text().strip()
            return "1.0.71"  # Default version
        except Exception as e:
            logger.error(f"Error reading version file: {e}")
            return "1.0.71"
    
    def _setup_auto_updater(self):
        """Set up the auto-updater system"""
        try:
            # Get API client from store (will be available after app starts)
            state = store.get_state()
            api_clients = state.get('api_clients', {})
            
            if api_clients:
                # Use the first available API client
                api_client = next(iter(api_clients.values()))
                
                # Initialize auto-updater
                self.auto_updater = AutoUpdater(
                    api_client=api_client,
                    current_version=self.current_version,
                    check_interval=300  # Check every 5 minutes
                )
                
                # Start update checker
                self.auto_updater.start_update_checker()
                logger.info(f"🔄 Auto-updater started - Version: {self.current_version}")
                
            else:
                logger.warning("No API clients available, auto-updater disabled")
                
        except Exception as e:
            logger.error(f"Error setting up auto-updater: {e}")
    
    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            logger.info("Received shutdown signal, stopping bot...")
            self.shutdown()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def shutdown(self):
        """Graceful shutdown of the bot"""
        try:
            self.app_running = False
            
            # Stop auto-updater
            if self.auto_updater:
                self.auto_updater.stop_update_checker()
                logger.info("Auto-updater stopped")
            
            # Additional cleanup can be added here
            logger.info("Bot shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    def start_auto_updater_delayed(self):
        """Start auto-updater after a delay to allow app initialization"""
        import threading
        import time
        
        def delayed_start():
            time.sleep(10)  # Wait 10 seconds for app to initialize
            self._setup_auto_updater()
        
        thread = threading.Thread(target=delayed_start, daemon=True)
        thread.start()

def main(page: flet.Page):
    """Main Flet application entry point"""
    try:
        # Initialize bot instance
        bot_instance = PatrickDisplayBot()
        
        # Store bot instance globally for access by other components
        store.update_state({'bot_instance': bot_instance})
        
        # Set up signal handlers
        bot_instance._setup_signal_handlers()
        
        # Start auto-updater after app initialization
        bot_instance.start_auto_updater_delayed()
        
        # Set app as running
        bot_instance.app_running = True
        
        # Configure page
        page.title = f"Patrick Display Bot v{bot_instance.current_version}"
        page.window.width = 1200
        page.window.height = 800
        page.window.resizable = True
        page.theme_mode = flet.ThemeMode.DARK
        
        # Initialize app router
        app_router = AppRoutes(page)
        app_router.route_change(page.route)
        
        # Add update notification function to page
        def check_for_updates():
            """Manual update check function"""
            if bot_instance.auto_updater:
                result = bot_instance.auto_updater.force_check_update()
                if result:
                    if result.get('success'):
                        page.show_snack_bar(
                            flet.SnackBar(
                                content=flet.Text(f"✅ Updated to version {result.get('version')}"),
                                bgcolor=flet.Colors.GREEN
                            )
                        )
                    else:
                        page.show_snack_bar(
                            flet.SnackBar(
                                content=flet.Text("🔍 No updates available"),
                                bgcolor=flet.Colors.BLUE
                            )
                        )
                else:
                    page.show_snack_bar(
                        flet.SnackBar(
                            content=flet.Text("🔍 No updates available"),
                            bgcolor=flet.Colors.BLUE
                        )
                    )
        
        # Add update check function to page for access by UI components
        page.check_for_updates = check_for_updates
        
        logger.info(f"🚀 Patrick Display Bot v{bot_instance.current_version} started successfully")
        
    except Exception as e:
        logger.error(f"Error in main application: {e}")
        raise

if __name__ == "__main__":
    try:
        # Log startup
        logger.info("=" * 60)
        logger.info("🚀 PATRICK DISPLAY BOT STARTING")
        logger.info("=" * 60)
        
        # Start Flet app
        flet.app(
            target=main,
            name="Patrick Display Bot",
            assets_dir="assets"
        )
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
