#!/usr/bin/env python3
"""
Apply Recovery Mode Migration
Adds recovery mode fields to the advanced_cycles_trader collection
"""

import subprocess
import sys
import os
from pathlib import Path

def apply_migration():
    """Apply the recovery mode migration"""
    try:
        print("🚀 Applying Recovery Mode Migration...")
        
        # Get the project root directory
        project_root = Path(__file__).parent
        migration_file = project_root / "pb_migrations" / "1750743300_add_recovery_mode_fields.js"
        
        # Check if migration file exists
        if not migration_file.exists():
            print(f"❌ Migration file not found: {migration_file}")
            return False
        
        print(f"📁 Migration file: {migration_file}")
        
        # Instructions for manual application
        print("\n📋 MANUAL MIGRATION STEPS:")
        print("1. Start your PocketBase server if not already running")
        print("2. Copy the migration file to your PocketBase migrations directory:")
        print(f"   cp '{migration_file}' /path/to/your/pocketbase/pb_migrations/")
        print("3. The migration will be applied automatically on the next PocketBase restart")
        print("   OR you can trigger it manually through the PocketBase admin panel")
        
        print("\n✅ Migration file is ready for application!")
        print("\n🔧 The following fields will be added to advanced_cycles_trader collection:")
        print("   - in_recovery_mode (boolean): Tracks if cycle is in recovery mode")
        print("   - recovery_zone_base_price (number): Price where recovery zone was activated")
        print("   - initial_stop_loss_price (number): Price where initial order was stopped out")
        
        return True
        
    except Exception as e:
        print(f"❌ Error applying migration: {e}")
        return False

def main():
    """Main function"""
    print("=" * 60)
    print("RECOVERY MODE MIGRATION TOOL")
    print("=" * 60)
    
    success = apply_migration()
    
    if success:
        print("\n🎉 Migration preparation completed successfully!")
        print("\nNext steps:")
        print("1. Apply the migration to your PocketBase database")
        print("2. Test the new recovery zone functionality")
        print("3. Monitor initial stop loss → recovery zone → reversal flow")
    else:
        print("\n❌ Migration preparation failed!")
        sys.exit(1)

if __name__ == "__main__":
    main() 