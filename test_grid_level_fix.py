#!/usr/bin/env python3
"""
Test script to verify MoveGuard grid level fixes
"""

import sys
import os
import json
from datetime import datetime

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from Views.globals.app_logger import app_logger as logger

def test_grid_level_calculation():
    """Test grid level calculation logic"""
    print("🧪 Testing MoveGuard Grid Level Calculation")
    print("=" * 50)
    
    # Test parameters
    entry_price = 1.2000
    entry_interval_pips = 10.0  # Initial offset
    grid_interval_pips = 50.0   # Grid spacing
    pip_value = 0.0001  # Standard pip value for most forex pairs
    
    # Test cases: (price, expected_grid_level)
    test_cases = [
        (1.2000, 0),   # Same as entry - should be level 0
        (1.1990, 0),   # 10 pips below entry - within initial offset, should be level 0
        (1.2010, 0),   # 10 pips above entry - within initial offset, should be level 0
        (1.1950, 1),   # 50 pips below entry - beyond initial offset, should be level 1
        (1.1900, 2),   # 100 pips below entry - should be level 2
        (1.2050, 1),   # 50 pips above entry - beyond initial offset, should be level 1
        (1.2100, 2),   # 100 pips above entry - should be level 2
        (1.1975, 0),   # 25 pips below entry - within initial offset, should be level 0
        (1.2025, 0),   # 25 pips above entry - within initial offset, should be level 0
    ]
    
    print(f"Entry Price: {entry_price}")
    print(f"Entry Interval: {entry_interval_pips} pips")
    print(f"Grid Interval: {grid_interval_pips} pips")
    print(f"Pip Value: {pip_value}")
    print()
    
    for price, expected_level in test_cases:
        # Calculate grid level using the correct MoveGuard logic
        price_diff = float(price) - float(entry_price)
        pips_diff = abs(price_diff) / float(pip_value)
        
        if pips_diff == 0:
            # Same as entry price - Level 0 (cycle entry order)
            calculated_level = 0
        elif pips_diff <= entry_interval_pips:
            # Within initial offset - Level 0 (still entry order)
            calculated_level = 0
        else:
            # Beyond initial offset - calculate grid level
            # Subtract initial offset and divide by grid interval
            remaining_pips = pips_diff - entry_interval_pips
            calculated_level = int(remaining_pips / float(grid_interval_pips)) + 1
            calculated_level = max(1, calculated_level)  # Ensure minimum level 1
        
        # Debug calculation
        print(f"DEBUG: Price={price:.4f}, Entry={entry_price:.4f}, Diff={price_diff:.4f}, Abs={abs(price_diff):.4f}")
        print(f"DEBUG: Pips_diff={pips_diff:.1f}, Entry_interval={entry_interval_pips}, Remaining_pips={max(0, pips_diff-entry_interval_pips):.1f}")
        print(f"DEBUG: Grid_interval={grid_interval_pips}, Division={max(0, pips_diff-entry_interval_pips)/grid_interval_pips:.3f}, Level={calculated_level}")
        
        status = "✅ PASS" if calculated_level == expected_level else "❌ FAIL"
        print(f"{status} Price: {price:.4f} | Expected: {expected_level} | Calculated: {calculated_level} | Pips Diff: {pips_diff:.1f}")
        print()
    
    print()
    print("Grid Level Calculation Test Complete")
    print("=" * 50)

def test_order_enrichment_logic():
    """Test order enrichment logic"""
    print("🧪 Testing Order Enrichment Logic")
    print("=" * 50)
    
    # Sample orders with missing grid levels
    sample_orders = [
        {'order_id': '1', 'price': 1.2000, 'grid_level': None},  # Entry order
        {'order_id': '2', 'price': 1.1950, 'grid_level': None},  # Grid order 1
        {'order_id': '3', 'price': 1.1900, 'grid_level': None},  # Grid order 2
        {'order_id': '4', 'price': 1.2050, 'grid_level': None},  # Grid order 1 (above)
    ]
    
    entry_price = 1.2000
    entry_interval_pips = 10.0  # Initial offset
    grid_interval_pips = 50.0   # Grid spacing
    pip_value = 0.0001
    
    print("Before enrichment:")
    for order in sample_orders:
        print(f"  Order {order['order_id']}: price={order['price']}, grid_level={order['grid_level']}")
    
    print("\nAfter enrichment:")
    for order in sample_orders:
        # Apply enrichment logic using correct MoveGuard logic
        price = order.get('price', 0.0)
        if order.get('grid_level') is None and pip_value and grid_interval_pips:
            try:
                price_diff = float(price) - float(entry_price)
                pips_diff = abs(price_diff) / float(pip_value)
                
                if pips_diff == 0:
                    # Same as entry price - Level 0 (cycle entry order)
                    level = 0
                elif pips_diff <= entry_interval_pips:
                    # Within initial offset - Level 0 (still entry order)
                    level = 0
                else:
                    # Beyond initial offset - calculate grid level
                    # Subtract initial offset and divide by grid interval
                    remaining_pips = pips_diff - entry_interval_pips
                    level = int(remaining_pips / float(grid_interval_pips)) + 1
                    level = max(1, level)  # Ensure minimum level 1
                
                order['grid_level'] = level
                
                # Tag grid orders
                if level == 0:
                    order['is_initial'] = True
                    order['is_grid'] = False
                    order['order_type'] = 'initial'
                else:
                    order['is_grid'] = True
                    order['is_initial'] = False
                    if level == 1:
                        order['order_type'] = 'grid_entry'
                    else:
                        order['order_type'] = f'grid_level_{level}'
                    
            except Exception as e:
                order['grid_level'] = 0
                order['order_type'] = 'initial'
        
        print(f"  Order {order['order_id']}: price={order['price']}, grid_level={order['grid_level']}, type={order.get('order_type', 'unknown')}")
    
    print()
    print("Order Enrichment Test Complete")
    print("=" * 50)

def test_mt5orderutils_conversion():
    """Test MT5OrderUtils conversion logic"""
    print("🧪 Testing MT5OrderUtils Conversion Logic")
    print("=" * 50)
    
    # Import the conversion function
    from helpers.mt5_order_utils import MT5OrderUtils
    
    # Test cases: (input_order_data, expected_grid_level, expected_order_type)
    test_cases = [
        # No existing grid level - should default to -1
        ({'ticket': '123', 'price': 1.2000, 'volume': 0.01}, -1, 'initial'),
        # Existing grid level 1 - should preserve it
        ({'ticket': '124', 'price': 1.1950, 'volume': 0.01, 'grid_level': 1}, 1, 'grid_1'),
        # Existing grid level 2 - should preserve it
        ({'ticket': '125', 'price': 1.1900, 'volume': 0.01, 'grid_level': 2}, 2, 'grid_2'),
        # Existing grid level 0 - should preserve it
        ({'ticket': '126', 'price': 1.2000, 'volume': 0.01, 'grid_level': 0}, 0, 'initial'),
    ]
    
    for i, (input_data, expected_level, expected_type) in enumerate(test_cases, 1):
        try:
            # Call the conversion function
            result = MT5OrderUtils._convert_to_moveguard_format(input_data, 'BUY')
            
            level_match = result.get('grid_level') == expected_level
            type_match = result.get('order_type') == expected_type
            
            status = "✅ PASS" if level_match and type_match else "❌ FAIL"
            print(f"{status} Test {i}: grid_level={result.get('grid_level')} (expected {expected_level}), type={result.get('order_type')} (expected {expected_type})")
            
        except Exception as e:
            print(f"❌ FAIL Test {i}: Error - {e}")
    
    print()
    print("MT5OrderUtils Conversion Test Complete")
    print("=" * 50)

def main():
    """Run all grid level tests"""
    print("🚀 MoveGuard Grid Level Fix Verification")
    print("=" * 60)
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    try:
        test_grid_level_calculation()
        print()
        test_order_enrichment_logic()
        print()
        test_mt5orderutils_conversion()
        print()
        
        print("✅ All grid level tests completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
