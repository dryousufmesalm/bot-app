#!/usr/bin/env python3
"""
Test script to verify store fix
"""

import sys
from pathlib import Path

# Add the bot app directory to Python path
bot_app_dir = Path(__file__).parent
sys.path.insert(0, str(bot_app_dir))

try:
    # Test imports
    print("Testing imports...")
    from helpers.store import store
    from helpers.actions_creators import set_bot_instance
    print("✅ Imports successful")
    
    # Test store dispatch
    print("Testing store dispatch...")
    
    class MockBotInstance:
        def __init__(self):
            self.current_version = "1.0.71"
    
    mock_bot = MockBotInstance()
    
    # Test dispatch
    store.dispatch(set_bot_instance(mock_bot))
    print("✅ Store dispatch successful")
    
    # Test state retrieval
    state = store.get_state()
    bot_instance_state = state.get('bot_instance', {})
    bot_instance = bot_instance_state.get('bot_instance')
    
    if bot_instance and hasattr(bot_instance, 'current_version'):
        print(f"✅ State retrieval successful - Version: {bot_instance.current_version}")
    else:
        print("❌ State retrieval failed")
    
    print("🎉 All tests passed!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc() 