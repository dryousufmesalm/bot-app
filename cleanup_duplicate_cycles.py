#!/usr/bin/env python3
"""
Script to identify and clean up duplicate MoveGuard cycles
"""

import sqlite3
import json
from datetime import datetime

def find_duplicate_cycles():
    """Find duplicate cycles in the database"""
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        # Check if moveguard_cycles table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='moveguard_cycles'")
        if not cursor.fetchone():
            print("❌ moveguard_cycles table not found")
            return []
        
        # Find duplicates by entry_price and direction
        cursor.execute("""
            SELECT entry_price, direction, COUNT(*) as count, 
                   GROUP_CONCAT(cycle_id) as cycle_ids,
                   GROUP_CONCAT(created) as created_times
            FROM moveguard_cycles 
            WHERE status = 'active'
            GROUP BY entry_price, direction 
            HAVING COUNT(*) > 1
            ORDER BY entry_price, direction
        """)
        
        duplicates = cursor.fetchall()
        
        print("🔍 DUPLICATE CYCLES ANALYSIS")
        print("=" * 60)
        
        if not duplicates:
            print("✅ No duplicate cycles found!")
            return []
        
        for dup in duplicates:
            entry_price, direction, count, cycle_ids, created_times = dup
            print(f"\n🚨 DUPLICATE FOUND:")
            print(f"   Entry Price: {entry_price}")
            print(f"   Direction: {direction}")
            print(f"   Count: {count}")
            print(f"   Cycle IDs: {cycle_ids}")
            print(f"   Created Times: {created_times}")
        
        conn.close()
        return duplicates
        
    except Exception as e:
        print(f"❌ Error finding duplicates: {e}")
        return []

def cleanup_duplicates(duplicates, keep_oldest=True):
    """Clean up duplicate cycles, keeping the oldest or newest"""
    if not duplicates:
        print("✅ No duplicates to clean up")
        return
    
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        print(f"\n🧹 CLEANING UP DUPLICATES (keeping {'oldest' if keep_oldest else 'newest'})")
        print("=" * 60)
        
        for dup in duplicates:
            entry_price, direction, count, cycle_ids, created_times = dup
            
            # Parse cycle IDs and creation times
            cycle_id_list = cycle_ids.split(',')
            created_list = created_times.split(',')
            
            # Create list of (cycle_id, created_time) tuples
            cycle_data = list(zip(cycle_id_list, created_list))
            
            # Sort by creation time
            cycle_data.sort(key=lambda x: x[1], reverse=not keep_oldest)
            
            # Keep the first one (oldest or newest), remove the rest
            keep_cycle = cycle_data[0][0]
            remove_cycles = [cycle[0] for cycle in cycle_data[1:]]
            
            print(f"\n📍 Price {entry_price} Direction {direction}:")
            print(f"   ✅ Keeping: {keep_cycle}")
            print(f"   🗑️  Removing: {', '.join(remove_cycles)}")
            
            # Update status to 'closed' for duplicates
            for cycle_id in remove_cycles:
                cursor.execute("""
                    UPDATE moveguard_cycles 
                    SET status = 'closed', 
                        closed_reason = 'duplicate_cleanup',
                        closed_at = ?
                    WHERE cycle_id = ?
                """, (datetime.now().isoformat(), cycle_id))
                
                print(f"   ✅ Marked {cycle_id} as closed (duplicate cleanup)")
        
        conn.commit()
        conn.close()
        
        print(f"\n✅ Cleanup completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")

def main():
    print("🔍 MoveGuard Duplicate Cycle Cleanup Tool")
    print("=" * 50)
    
    # Find duplicates
    duplicates = find_duplicate_cycles()
    
    if duplicates:
        print(f"\n📊 Found {len(duplicates)} duplicate groups")
        
        # Ask user for confirmation
        response = input("\n🤔 Do you want to clean up these duplicates? (y/N): ").strip().lower()
        
        if response == 'y':
            keep_oldest = input("🤔 Keep oldest cycles? (Y/n): ").strip().lower() != 'n'
            cleanup_duplicates(duplicates, keep_oldest)
        else:
            print("❌ Cleanup cancelled by user")
    else:
        print("✅ No duplicates found - system is clean!")

if __name__ == "__main__":
    main()
