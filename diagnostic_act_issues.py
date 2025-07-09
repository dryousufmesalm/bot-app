#!/usr/bin/env python3
"""
Diagnostic script for ACT (Advanced Cycles Trader) issues
This script helps diagnose and fix common ACT problems:
1. "No active ACT cycles found" 
2. "Validation failure backoff active"
"""

import sys
import os

# Add the bot app directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from Views.globals.app_logger import logger

def diagnose_act_cycles(cycles_manager):
    """Diagnose ACT cycles issues"""
    print("\n🔍 DIAGNOSING ACT CYCLES ISSUE")
    print("=" * 50)
    
    try:
        # Check account ID
        account_id = getattr(cycles_manager.account, 'id', None)
        print(f"Account ID: {account_id}")
        
        # Check remote API connection
        api_available = cycles_manager.remote_api is not None
        print(f"Remote API Available: {api_available}")
        
        if not api_available:
            print("❌ Remote API is None - this is the problem!")
            return
        
        # Try to get cycles directly
        print("\n📊 Attempting to fetch ACT cycles...")
        cycles = cycles_manager.remote_api.get_all_ACT_active_cycles_by_account(account_id)
        
        if cycles is None:
            print("❌ API returned None - possible connection or authentication issue")
            return
        
        print(f"✅ Found {len(cycles)} total ACT cycles")
        
        if len(cycles) == 0:
            print("ℹ️  No ACT cycles exist in PocketBase for this account")
            print("   This is normal if no ACT trading has been started yet")
            return
        
        # Analyze cycles
        active_count = 0
        closed_count = 0
        
        for cycle in cycles:
            is_closed = getattr(cycle, 'is_closed', False)
            cycle_id = getattr(cycle, 'id', 'unknown')
            
            if is_closed:
                closed_count += 1
                print(f"   📝 Cycle {cycle_id}: CLOSED")
            else:
                active_count += 1
                print(f"   🟢 Cycle {cycle_id}: ACTIVE")
        
        print(f"\n📈 Summary: {active_count} active, {closed_count} closed")
        
        if active_count == 0:
            print("ℹ️  All cycles are closed - this explains the 'No active ACT cycles found' message")
        
    except Exception as e:
        print(f"❌ Error during diagnosis: {e}")

def diagnose_validation_backoff(act_strategy):
    """Diagnose validation backoff issues"""
    print("\n🔍 DIAGNOSING VALIDATION BACKOFF ISSUE")
    print("=" * 50)
    
    try:
        # Check validation failures
        failures = getattr(act_strategy, '_validation_failures', None)
        backoff_start = getattr(act_strategy, '_validation_backoff_start', None)
        resume_time = getattr(act_strategy, '_trading_resume_time', None)
        
        print(f"Validation Failures: {len(failures) if failures else 0}")
        print(f"Backoff Start Time: {backoff_start}")
        print(f"Trading Resume Time: {resume_time}")
        print(f"Strategy Active: {act_strategy.strategy_active}")
        print(f"Trading Active: {act_strategy.trading_active}")
        
        if failures and len(failures) >= 10:
            print("❌ Too many validation failures (≥10) - backoff is active")
            print("   Backoff will reset automatically after 10 minutes")
            print("   Or you can reset it manually")
        elif failures and len(failures) >= 5:
            print("⚠️  Multiple validation failures (≥5) - trading may be paused")
        else:
            print("✅ Validation failures are within normal range")
            
    except Exception as e:
        print(f"❌ Error during validation backoff diagnosis: {e}")

def reset_validation_backoff(act_strategy):
    """Reset validation backoff manually"""
    print("\n🔧 RESETTING VALIDATION BACKOFF")
    print("=" * 40)
    
    try:
        # Clear validation failures
        if hasattr(act_strategy, '_validation_failures'):
            old_count = len(act_strategy._validation_failures)
            delattr(act_strategy, '_validation_failures')
            print(f"✅ Cleared {old_count} validation failures")
        
        # Clear backoff start time
        if hasattr(act_strategy, '_validation_backoff_start'):
            delattr(act_strategy, '_validation_backoff_start')
            print("✅ Reset validation backoff start time")
        
        # Clear trading resume time
        if hasattr(act_strategy, '_trading_resume_time'):
            delattr(act_strategy, '_trading_resume_time')
            print("✅ Cleared trading resume time")
        
        # Re-enable trading if needed
        if not act_strategy.trading_active and act_strategy.strategy_active:
            act_strategy.trading_active = True
            print("✅ Re-enabled trading")
        
        print("🎉 Validation backoff reset complete!")
        return True
        
    except Exception as e:
        print(f"❌ Error resetting validation backoff: {e}")
        return False

def main():
    """Main diagnostic function"""
    print("🩺 ACT DIAGNOSTIC TOOL")
    print("=" * 60)
    
    # This script needs to be run within the context of your bot application
    # where cycles_manager and act_strategy instances are available
    
    print("""
This diagnostic script helps identify and fix ACT issues:

1. 'No active ACT cycles found' - Usually means:
   - No ACT cycles exist in PocketBase for this account
   - All existing cycles are marked as closed
   - API connection issues

2. 'Validation failure backoff active' - Usually means:
   - Too many order validation failures occurred
   - System is in backoff mode to prevent spam
   - Will auto-reset after 10 minutes

To use this script, import it into your bot and call:
- diagnose_act_cycles(cycles_manager_instance)
- diagnose_validation_backoff(act_strategy_instance)  
- reset_validation_backoff(act_strategy_instance)
""")

if __name__ == "__main__":
    main() 