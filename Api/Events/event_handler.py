from abc import ABC, abstractmethod
from .trade_event import TradeEvent, TradeEventMessages
import json
import time
import logging
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)

class EventHandler(ABC):
    '''Base class for event handlers'''
    def __init__(self, event: TradeEvent):
        self.event = event

    @abstractmethod
    def handle_content(self):
        '''Handle the content of the event'''
        pass

class CloseCycleEventHandler(EventHandler):
    '''Specialized handler for close cycle events with Flutter app communication'''
    
    def __init__(self, event: TradeEvent, api_client, strategy_manager):
        super().__init__(event)
        self.api_client = api_client
        self.strategy_manager = strategy_manager
        
    async def handle_content(self):
        '''Handle close cycle event and send response to Flutter app'''
        try:
            # Extract event details
            cycle_id = self.event.contents.get('cycle_id')
            action = self.event.contents.get('action', 'close_cycle')
            username = self.event.contents.get('user_name', 'flutter_app')
            
            # Create response event structure
            response_event = {
                "uuid": f"response_{self.event.uuid}_{int(time.time() * 1000)}",
                "original_event_uuid": self.event.uuid,
                "type": "close_cycle_response",
                "bot_id": self.event.botId,
                "account_id": self.event.accountId,
                "user_name": username,
                "timestamp": datetime.now().isoformat(),
                "status": "processing",
                "action": action,
                "cycle_id": cycle_id,
                "details": {
                    "received_at": datetime.now().isoformat(),
                    "processing_started": True
                }
            }
            
            # Send initial "processing" response to Flutter app
            await self._send_response_to_flutter(response_event)
            
            logger.info(f"🔄 Processing close cycle event from Flutter app: {cycle_id}")
            
            # Execute the close cycle operation
            if action == "close_cycle":
                result = await self._execute_close_cycle(cycle_id, username, response_event)
            elif action == "close_all_cycles":
                result = await self._execute_close_all_cycles(username, response_event)
            else:
                result = False
                response_event["status"] = "failed"
                response_event["details"]["error"] = f"Unknown action: {action}"
            
            # Send final response to Flutter app
            response_event["status"] = "completed" if result else "failed"
            response_event["details"]["processing_completed"] = True
            response_event["details"]["completed_at"] = datetime.now().isoformat()
            
            await self._send_response_to_flutter(response_event)
            
            logger.info(f"✅ Close cycle event processed and response sent to Flutter app")
            return result
            
        except Exception as e:
            logger.error(f"Error handling close cycle event: {e}")
            # Send error response to Flutter app
            error_response = {
                "uuid": f"error_{self.event.uuid}_{int(time.time() * 1000)}",
                "original_event_uuid": self.event.uuid,
                "type": "close_cycle_response",
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
            await self._send_response_to_flutter(error_response)
            return False
    
    async def _execute_close_cycle(self, cycle_id, username, response_event):
        '''Execute close cycle operation'''
        try:
            # Find the strategy instance for this bot
            strategy = self.strategy_manager.get_strategy_by_bot_id(self.event.botId)
            if not strategy:
                logger.error(f"Strategy not found for bot {self.event.botId}")
                response_event["details"]["error"] = "Strategy not found"
                return False
            
            # Execute close cycle on the strategy
            content = {
                'id': cycle_id,
                'user_name': username,
                'sent_from': 'flutter_app'
            }
            
            result = await strategy._handle_close_cycle_event(content)
            
            # Update response with results
            response_event["details"].update({
                "cycle_closed": result,
                "cycle_id": cycle_id,
                "method": "single_cycle_close"
            })
            
            logger.info(f"✅ Close cycle executed for {cycle_id}: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error executing close cycle: {e}")
            response_event["details"]["error"] = str(e)
            return False
    
    async def _execute_close_all_cycles(self, username, response_event):
        '''Execute close all cycles operation'''
        try:
            # Find the strategy instance for this bot
            strategy = self.strategy_manager.get_strategy_by_bot_id(self.event.botId)
            if not strategy:
                logger.error(f"Strategy not found for bot {self.event.botId}")
                response_event["details"]["error"] = "Strategy not found"
                return False
            
            # Execute close all cycles on the strategy
            content = {
                'id': 'all',
                'user_name': username,
                'sent_from': 'flutter_app'
            }
            
            result = await strategy._handle_close_cycle_event(content)
            
            # Update response with results
            response_event["details"].update({
                "all_cycles_closed": result,
                "method": "close_all_cycles",
                "cycles_closed_count": len(strategy.closed_cycles) if hasattr(strategy, 'closed_cycles') else 0
            })
            
            logger.info(f"✅ Close all cycles executed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error executing close all cycles: {e}")
            response_event["details"]["error"] = str(e)
            return False
    
    async def _send_response_to_flutter(self, response_data):
        '''Send response event back to Flutter app via PocketBase'''
        try:
            # Create event record in PocketBase Events collection for Flutter app to receive
            event_record = {
                "event_type": response_data["type"],
                "bot_id": response_data.get("bot_id", ""),
                "account_id": response_data.get("account_id", ""),
                "user_name": response_data.get("user_name", "bot_app"),
                "timestamp": response_data["timestamp"],
                "status": response_data["status"],
                "data": json.dumps(response_data),
                "uuid": response_data["uuid"],
                "response_to": response_data.get("original_event_uuid", ""),
                "source": "bot_app",
                "target": "flutter_app"
            }
            
            # Send to PocketBase
            result = self.api_client.client.collection("Events").create(event_record)
            if result:
                logger.info(f"✅ Response sent to Flutter app: {response_data['uuid']}")
                return True
            else:
                logger.error(f"❌ Failed to send response to Flutter app")
                return False
                
        except Exception as e:
            logger.error(f"Error sending response to Flutter app: {e}")
            return False

class EventRouter:
    '''Routes events to appropriate handlers'''
    
    def __init__(self, api_client, strategy_manager):
        self.api_client = api_client
        self.strategy_manager = strategy_manager
        
    async def route_event(self, event: TradeEvent):
        '''Route event to appropriate handler'''
        try:
            # Determine event type and route to appropriate handler
            action = event.contents.get('action', '')
            
            if action in ['close_cycle', 'close_all_cycles']:
                handler = CloseCycleEventHandler(event, self.api_client, self.strategy_manager)
                return await handler.handle_content()
            elif action == 'open_order':
                # Handle open order events
                return await self._handle_open_order_event(event)
            elif action == 'close_order':
                # Handle close order events
                return await self._handle_close_order_event(event)
            else:
                logger.warning(f"Unknown event action: {action}")
                return False
                
        except Exception as e:
            logger.error(f"Error routing event: {e}")
            return False
    
    async def _handle_open_order_event(self, event):
        '''Handle open order events from Flutter app'''
        try:
            strategy = self.strategy_manager.get_strategy_by_bot_id(event.botId)
            if strategy:
                return await strategy._handle_open_order_event(event.contents)
            return False
        except Exception as e:
            logger.error(f"Error handling open order event: {e}")
            return False
    
    async def _handle_close_order_event(self, event):
        '''Handle close order events from Flutter app'''
        try:
            strategy = self.strategy_manager.get_strategy_by_bot_id(event.botId)
            if strategy:
                return await strategy._handle_close_order_event(event.contents)
            return False
        except Exception as e:
            logger.error(f"Error handling close order event: {e}")
            return False

class FlutterEventListener:
    '''Listens for events from Flutter app and processes them'''
    
    def __init__(self, api_client, strategy_manager):
        self.api_client = api_client
        self.strategy_manager = strategy_manager
        self.event_router = EventRouter(api_client, strategy_manager)
        self.processed_events = set()
        
    async def listen_for_flutter_events(self):
        '''Listen for events from Flutter app via PocketBase subscription'''
        try:
            logger.info("🔄 Starting Flutter event listener...")
            
            # Subscribe to Events collection for real-time updates
            def handle_event_update(event_data):
                # Process event in background
                asyncio.create_task(self._process_flutter_event(event_data))
            
            # Set up PocketBase real-time subscription
            self.api_client.subscribe_events(handle_event_update)
            
            logger.info("✅ Flutter event listener started")
            
        except Exception as e:
            logger.error(f"Error starting Flutter event listener: {e}")
    
    async def _process_flutter_event(self, event_data):
        '''Process individual event from Flutter app'''
        try:
            # Check if event is from Flutter app and not already processed
            source = event_data.get('source', '')
            event_uuid = event_data.get('uuid', '')
            
            if source != 'flutter_app' or event_uuid in self.processed_events:
                return
            
            # Mark as processed
            self.processed_events.add(event_uuid)
            
            # Parse event data
            event_contents = json.loads(event_data.get('data', '{}'))
            
            # Create TradeEvent object
            trade_event = TradeEvent(
                uuid=event_uuid,
                accountId=event_data.get('account_id', ''),
                contents=event_contents,
                botId=event_data.get('bot_id', ''),
                strategyId=event_contents.get('strategy_id', '')
            )
            
            # Route to appropriate handler
            result = await self.event_router.route_event(trade_event)
            
            logger.info(f"✅ Processed Flutter event {event_uuid}: {result}")
            
        except Exception as e:
            logger.error(f"Error processing Flutter event: {e}")
    