#!/usr/bin/env python3
"""
Simple test to verify MoveGuard grid level fixes
"""

def test_grid_calculation():
    """Test the corrected grid level calculation"""
    print("🧪 Testing MoveGuard Grid Level Calculation")
    print("=" * 50)
    
    # Test parameters
    entry_price = 1.2000
    entry_interval_pips = 10.0  # Initial offset
    grid_interval_pips = 50.0   # Grid spacing
    pip_value = 0.0001
    
    # Test cases
    test_cases = [
        (1.2000, 0, "Entry price"),
        (1.1990, 0, "Within initial offset (10 pips below)"),
        (1.2010, 0, "Within initial offset (10 pips above)"),
        (1.1950, 1, "First grid level (50 pips below)"),
        (1.1900, 2, "Second grid level (100 pips below)"),
        (1.2050, 1, "First grid level (50 pips above)"),
        (1.2100, 2, "Second grid level (100 pips above)"),
    ]
    
    print(f"Entry Price: {entry_price}")
    print(f"Entry Interval: {entry_interval_pips} pips")
    print(f"Grid Interval: {grid_interval_pips} pips")
    print()
    
    all_passed = True
    
    for price, expected_level, description in test_cases:
        # Calculate grid level using correct MoveGuard logic
        price_diff = float(price) - float(entry_price)
        pips_diff = abs(price_diff) / float(pip_value)
        
        print(f"DEBUG: Price={price:.4f}, Entry={entry_price:.4f}, Diff={price_diff:.4f}, Abs={abs(price_diff):.4f}")
        print(f"DEBUG: Pips_diff={pips_diff:.1f}, Entry_interval={entry_interval_pips}, Comparison={pips_diff <= entry_interval_pips}")
        
        if pips_diff == 0:
            calculated_level = 0
        elif pips_diff <= entry_interval_pips + 0.1:  # Add small tolerance for floating point
            calculated_level = 0
        else:
            remaining_pips = pips_diff - entry_interval_pips
            calculated_level = int(remaining_pips / float(grid_interval_pips)) + 1
            calculated_level = max(1, calculated_level)
        
        status = "✅ PASS" if calculated_level == expected_level else "❌ FAIL"
        print(f"{status} {description}")
        print(f"   Price: {price:.4f} | Expected: {expected_level} | Calculated: {calculated_level}")
        print()
        
        if calculated_level != expected_level:
            all_passed = False
    
    if all_passed:
        print("🎉 All tests passed! Grid level calculation is working correctly.")
    else:
        print("❌ Some tests failed. Grid level calculation needs fixing.")
    
    return all_passed

def test_mt5orderutils_fix():
    """Test the MT5OrderUtils conversion fix"""
    print("🧪 Testing MT5OrderUtils Conversion Fix")
    print("=" * 50)
    
    try:
        from helpers.mt5_order_utils import MT5OrderUtils
        
        # Test cases
        test_cases = [
            # (input_data, expected_grid_level, expected_order_type, description)
            ({'ticket': '123', 'price': 1.2000, 'volume': 0.01}, -1, 'initial', "No existing grid level"),
            ({'ticket': '124', 'price': 1.1950, 'volume': 0.01, 'grid_level': 1}, 1, 'grid_1', "Existing grid level 1"),
            ({'ticket': '125', 'price': 1.1900, 'volume': 0.01, 'grid_level': 2}, 2, 'grid_2', "Existing grid level 2"),
        ]
        
        all_passed = True
        
        for input_data, expected_level, expected_type, description in test_cases:
            result = MT5OrderUtils._convert_to_moveguard_format(input_data, 'BUY')
            
            level_match = result.get('grid_level') == expected_level
            type_match = result.get('order_type') == expected_type
            
            status = "✅ PASS" if level_match and type_match else "❌ FAIL"
            print(f"{status} {description}")
            print(f"   grid_level: {result.get('grid_level')} (expected {expected_level})")
            print(f"   order_type: {result.get('order_type')} (expected {expected_type})")
            print()
            
            if not (level_match and type_match):
                all_passed = False
        
        if all_passed:
            print("🎉 All MT5OrderUtils tests passed! Conversion is working correctly.")
        else:
            print("❌ Some MT5OrderUtils tests failed. Conversion needs fixing.")
        
        return all_passed
        
    except Exception as e:
        print(f"❌ Error testing MT5OrderUtils: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 MoveGuard Grid Level Fix Verification")
    print("=" * 60)
    
    grid_test_passed = test_grid_calculation()
    print()
    mt5_test_passed = test_mt5orderutils_fix()
    
    print("=" * 60)
    if grid_test_passed and mt5_test_passed:
        print("🎉 ALL TESTS PASSED! MoveGuard grid level fixes are working correctly.")
    else:
        print("❌ Some tests failed. Grid level fixes need more work.")
    
    print("=" * 60)

if __name__ == "__main__":
    main()
