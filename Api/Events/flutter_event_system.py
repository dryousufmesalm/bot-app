"""
Flutter Event Communication System
Handles bidirectional communication between Flutter app and bot app
"""

import json
import time
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class FlutterEventCommunicator:
    """Handles communication with Flutter app via PocketBase Events collection"""
    
    def __init__(self, api_client, strategy_manager):
        self.api_client = api_client
        self.strategy_manager = strategy_manager
        self.processed_events = set()
        
    async def send_event_to_flutter(self, event_data: Dict[str, Any]) -> bool:
        """Send event to Flutter app via PocketBase"""
        try:
            # Create event record for Flutter app
            event_record = {
                "uuid": event_data.get("uuid", f"bot_{int(time.time() * 1000)}"),
                "account": event_data.get("account_id", ""),
                "bot": event_data.get("bot_id", ""),
                "strategy": event_data.get("strategy_id", ""),
                "content": {
                    "event_type": event_data.get("type", "unknown"),
                    "bot_id": event_data.get("bot_id", ""),
                    "account_id": event_data.get("account_id", ""),
                    "user_name": event_data.get("user_name", "bot_app"),
                    "timestamp": event_data.get("timestamp", datetime.now().isoformat()),
                    "status": event_data.get("status", "sent"),
                    "message": event_data.get("message", ""),
                    "source": "bot_app",
                    "target": "flutter_app",
                    "response_to": event_data.get("response_to", ""),
                    "details": event_data.get("details", {})
                }
            }
            
            # Create in PocketBase Events collection
            result = self.api_client.client.collection("Events").create(event_record)
            if result:
                logger.info(f"✅ Event sent to Flutter app: {event_data.get('uuid')}")
                return True
            else:
                logger.error(f"❌ Failed to send event to Flutter app")
                return False
                
        except Exception as e:
            logger.error(f"Error sending event to Flutter app: {e}")
            return False
    
    async def  listen_for_flutter_events(self):
        """Listen for events from Flutter app"""
        try:
            logger.info("🔄 Starting Flutter event listener...")
            
            # Set up real-time subscription to Events collection
            def handle_event_update(event_data):
                try:
                    # Get the current event loop
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        # No event loop running, create a new one
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    # Create task in the current loop and store reference
                    task = loop.create_task(self._process_flutter_event(event_data))
                    # Add error handling for the task
                    task.add_done_callback(lambda t: self._handle_task_result(t))
                    
                    # Store the task to prevent it from being garbage collected
                    if not hasattr(self, '_active_tasks'):
                        self._active_tasks = set()
                    self._active_tasks.add(task)
                    
                    # Remove completed tasks from the set
                    task.add_done_callback(lambda t: self._active_tasks.discard(t))
                    
                except Exception as e:
                    logger.error(f"Error in event callback: {e}")
            
            # Subscribe to PocketBase Events collection
            self.api_client.subscribe_events(handle_event_update)
            logger.info("✅ Flutter event listener started")
            
        except Exception as e:
            logger.error(f"Error starting Flutter event listener: {e}")
    
    def _handle_task_result(self, task):
        """Handle task completion and any exceptions"""
        try:
            if task.exception():
                logger.error(f"Task failed with exception: {task.exception()}")
        except Exception as e:
            logger.error(f"Error handling task result: {e}")
    
    async def cleanup(self):
        """Cleanup method to properly close the communicator"""
        try:
            # Cancel all active tasks
            if hasattr(self, '_active_tasks'):
                for task in self._active_tasks:
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                self._active_tasks.clear()
            logger.info("✅ FlutterEventCommunicator cleaned up")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    async def _process_flutter_event(self, event_data):
        """Process incoming event from Flutter app"""
        try:
            # Check if event is from Flutter app
            content = event_data.get('content', {})
            source = content.get('source', '')
            target = content.get('target', '')
            event_uuid = event_data.get('uuid', '')
            
            if source != 'flutter_app' or target != 'bot_app':
                return
                
            if event_uuid in self.processed_events:
                return
                
            # Mark as processed
            self.processed_events.add(event_uuid)
            
            # Parse event data from content
            event_type = content.get('event_type', '')
            message = content.get('message', '')
            
            logger.info(f"📨 Received event from Flutter app: {event_type} - {event_uuid}")
            
            # Route to appropriate handler
            if event_type in ['close_cycle', 'close_all_cycles']:
                await self._handle_close_cycle_event(event_data, content)
            elif event_type == 'open_order':
                await self._handle_open_order_event(event_data, content)
            elif event_type == 'close_order':
                await self._handle_close_order_event(event_data, content)
            else:
                logger.warning(f"Unknown event type from Flutter: {event_type}")
                
        except Exception as e:
            logger.error(f"Error processing Flutter event: {e}")
    
    async def _handle_close_cycle_event(self, event_data, content):
        """Handle close cycle event from Flutter app"""
        try:
            bot_id = content.get('bot_id')
            cycle_id = content.get('cycle_id')
            action = content.get('action', 'close_cycle')
            username = content.get('user_name', 'flutter_app')
            
            # Create response structure
            response_event = {
                "uuid": f"response_{event_data['uuid']}_{int(time.time() * 1000)}",
                "type": "close_cycle_response",
                "bot_id": bot_id,
                "account_id": content.get('account_id', ''),
                "user_name": username,
                "timestamp": datetime.now().isoformat(),
                "status": "processing",
                "action": action,
                "cycle_id": cycle_id,
                "message": "close_cycle_processing",
                "response_to": event_data['uuid'],
                "details": {
                    "received_at": datetime.now().isoformat(),
                    "processing_started": True
                }
            }
            
            # Send initial processing response
            await self.send_event_to_flutter(response_event)
            
            # Find and execute on strategy
            strategy = self.strategy_manager.get_strategy_by_bot_id(bot_id)
            if not strategy:
                response_event["status"] = "failed"
                response_event["message"] = "strategy_not_found"
                response_event["details"]["error"] = f"Strategy not found for bot {bot_id}"
                await self.send_event_to_flutter(response_event)
                return
            
            # Format event for strategy handle_event method
            strategy_event = {
                'message': 'close_cycle',
                'content': {
                    'id': cycle_id if action == 'close_cycle' else 'all',
                    'user_name': username,
                    'sent_from': 'flutter_app'
                }
            }
            
            # Execute the operation using strategy's handle_event method
            result = await strategy.handle_event(strategy_event)
            
            # Send final response
            response_event["status"] = "completed" if result else "failed"
            response_event["message"] = "close_cycle_completed" if result else "close_cycle_failed"
            response_event["details"].update({
                "processing_completed": True,
                "completed_at": datetime.now().isoformat(),
                "success": result,
                "cycles_affected": len(strategy.closed_cycles) if hasattr(strategy, 'closed_cycles') else 0
            })
            
            if not result:
                response_event["details"]["error"] = "Failed to execute close cycle operation"
            
            await self.send_event_to_flutter(response_event)
            logger.info(f"✅ Close cycle event processed: {result}")
            
        except Exception as e:
            logger.error(f"Error handling close cycle event: {e}")
            # Send error response
            error_response = {
                "uuid": f"error_{event_data['uuid']}_{int(time.time() * 1000)}",
                "type": "close_cycle_response",
                "status": "failed",
                "message": "close_cycle_error",
                "error": str(e),
                "response_to": event_data['uuid'],
                "timestamp": datetime.now().isoformat()
            }
            await self.send_event_to_flutter(error_response)

    async def _handle_open_order_event(self, event_data, content):
        """Handle open order event from Flutter app"""
        try:
            bot_id = content.get('bot_id')
            strategy = self.strategy_manager.get_strategy_by_bot_id(bot_id)
            if not strategy:
                logger.error(f"Strategy not found for bot {bot_id}")
                return False
            
            # Format event for strategy handle_event method
            strategy_event = {
                'message': 'open_order',
                'content': content
            }
            
            result = await strategy.handle_event(strategy_event)
            logger.info(f"✅ Open order event processed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error handling open order event: {e}")
            return False

    async def _handle_close_order_event(self, event_data, content):
        """Handle close order event from Flutter app"""
        try:
            bot_id = content.get('bot_id')
            strategy = self.strategy_manager.get_strategy_by_bot_id(bot_id)
            if not strategy:
                logger.error(f"Strategy not found for bot {bot_id}")
                return False
            
            # Format event for strategy handle_event method
            strategy_event = {
                'message': 'close_order',
                'content': content
            }
            
            result = await strategy.handle_event(strategy_event)
            logger.info(f"✅ Close order event processed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error handling close order event: {e}")
            return False

class StrategyManager:
    """Manages strategy instances for event routing"""
    
    def __init__(self):
        self.strategies = {}  # bot_id -> strategy instance
    
    def register_strategy(self, bot_id: str, strategy):
        """Register a strategy instance for a bot"""
        self.strategies[bot_id] = strategy
        logger.info(f"Strategy registered for bot {bot_id}")
    
    def unregister_strategy(self, bot_id: str):
        """Unregister a strategy instance"""
        if bot_id in self.strategies:
            del self.strategies[bot_id]
            logger.info(f"Strategy unregistered for bot {bot_id}")
    
    def get_strategy_by_bot_id(self, bot_id: str):
        """Get strategy instance by bot ID"""
        return self.strategies.get(bot_id)
    
    def get_all_strategies(self):
        """Get all registered strategies"""
        return self.strategies.copy()

# Global instances
strategy_manager = StrategyManager()

def get_strategy_manager():
    """Get the global strategy manager instance"""
    return strategy_manager

def create_flutter_communicator(api_client):
    """Create a Flutter event communicator instance"""
    return FlutterEventCommunicator(api_client, strategy_manager)
