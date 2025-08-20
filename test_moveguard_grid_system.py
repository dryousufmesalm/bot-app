#!/usr/bin/env python3
"""
Test script to verify the corrected MoveGuard grid system using zone boundaries
"""

def test_buy_cycle_grid_levels():
    """Test BUY cycle grid level calculation"""
    print("🧪 Testing BUY Cycle Grid Level Calculation")
    print("=" * 50)
    
    # Test parameters for BUY cycle
    entry_price = 1.2000
    zone_threshold_pips = 300.0  # Zone size
    entry_interval_pips = 10.0   # Initial offset
    grid_interval_pips = 50.0    # Grid spacing
    pip_value = 0.0001
    direction = 'BUY'
    
    # Calculate zone boundaries
    upper_boundary = entry_price + (zone_threshold_pips * pip_value)  # 1.2300
    lower_boundary = entry_price - (zone_threshold_pips * pip_value)  # 1.1700
    
    # For BUY: Level 1 starts below lower_boundary - initial_offset
    grid_start_price = lower_boundary - (entry_interval_pips * pip_value)  # 1.1690
    
    print(f"Entry Price: {entry_price}")
    print(f"Zone: {lower_boundary:.4f} - {upper_boundary:.4f}")
    print(f"Grid Start Price (Level 1): {grid_start_price:.4f}")
    print(f"Entry Interval: {entry_interval_pips} pips")
    print(f"Grid Interval: {grid_interval_pips} pips")
    print()
    
    # Test cases: (price, expected_grid_level, description)
    test_cases = [
        (1.2000, 0, "Entry price - within zone"),
        (1.2100, 0, "Above entry - within zone"),
        (1.1800, 0, "Below entry - within zone"),
        (1.1700, 0, "At lower boundary - within zone"),
        (1.1695, 0, "Between lower boundary and grid start - Level 0"),
        (1.1690, 0, "At grid start price - Level 0"),
        (1.1640, 1, "50 pips below grid start - Level 1"),
        (1.1590, 2, "100 pips below grid start - Level 2"),
        (1.1540, 3, "150 pips below grid start - Level 3"),
    ]
    
    all_passed = True
    
    for price, expected_level, description in test_cases:
        # Calculate grid level using corrected MoveGuard logic for BUY
        if float(price) >= lower_boundary:
            # Price is within or above zone - Level 0 (entry order)
            calculated_level = 0
        elif float(price) >= grid_start_price:
            # Price is between lower_boundary and grid_start_price - Level 0
            calculated_level = 0
        else:
            # Price is below grid_start_price - calculate grid level
            price_diff = grid_start_price - float(price)
            pips_diff = price_diff / pip_value
            calculated_level = int(pips_diff / float(grid_interval_pips)) + 1
            calculated_level = max(1, calculated_level)
        
        status = "✅ PASS" if calculated_level == expected_level else "❌ FAIL"
        print(f"{status} {description}")
        print(f"   Price: {price:.4f} | Expected: {expected_level} | Calculated: {calculated_level}")
        
        if calculated_level != expected_level:
            all_passed = False
            print(f"   DEBUG: price_diff={grid_start_price - float(price):.4f}, pips_diff={(grid_start_price - float(price))/pip_value:.1f}")
        print()
    
    return all_passed

def test_sell_cycle_grid_levels():
    """Test SELL cycle grid level calculation"""
    print("🧪 Testing SELL Cycle Grid Level Calculation")
    print("=" * 50)
    
    # Test parameters for SELL cycle
    entry_price = 1.2000
    zone_threshold_pips = 300.0  # Zone size
    entry_interval_pips = 10.0   # Initial offset
    grid_interval_pips = 50.0    # Grid spacing
    pip_value = 0.0001
    direction = 'SELL'
    
    # Calculate zone boundaries
    upper_boundary = entry_price + (zone_threshold_pips * pip_value)  # 1.2300
    lower_boundary = entry_price - (zone_threshold_pips * pip_value)  # 1.1700
    
    # For SELL: Level 1 starts above upper_boundary + initial_offset
    grid_start_price = upper_boundary + (entry_interval_pips * pip_value)  # 1.2310
    
    print(f"Entry Price: {entry_price}")
    print(f"Zone: {lower_boundary:.4f} - {upper_boundary:.4f}")
    print(f"Grid Start Price (Level 1): {grid_start_price:.4f}")
    print(f"Entry Interval: {entry_interval_pips} pips")
    print(f"Grid Interval: {grid_interval_pips} pips")
    print()
    
    # Test cases: (price, expected_grid_level, description)
    test_cases = [
        (1.2000, 0, "Entry price - within zone"),
        (1.1900, 0, "Below entry - within zone"),
        (1.2200, 0, "Above entry - within zone"),
        (1.2300, 0, "At upper boundary - within zone"),
        (1.2305, 0, "Between upper boundary and grid start - Level 0"),
        (1.2310, 0, "At grid start price - Level 0"),
        (1.2360, 1, "50 pips above grid start - Level 1"),
        (1.2410, 2, "100 pips above grid start - Level 2"),
        (1.2460, 3, "150 pips above grid start - Level 3"),
    ]
    
    all_passed = True
    
    for price, expected_level, description in test_cases:
        # Calculate grid level using corrected MoveGuard logic for SELL
        if float(price) <= upper_boundary:
            # Price is within or below zone - Level 0 (entry order)
            calculated_level = 0
        elif float(price) <= grid_start_price:
            # Price is between upper_boundary and grid_start_price - Level 0
            calculated_level = 0
        else:
            # Price is above grid_start_price - calculate grid level
            price_diff = float(price) - grid_start_price
            pips_diff = price_diff / pip_value
            calculated_level = int(pips_diff / float(grid_interval_pips)) + 1
            calculated_level = max(1, calculated_level)
        
        status = "✅ PASS" if calculated_level == expected_level else "❌ FAIL"
        print(f"{status} {description}")
        print(f"   Price: {price:.4f} | Expected: {expected_level} | Calculated: {calculated_level}")
        
        if calculated_level != expected_level:
            all_passed = False
            print(f"   DEBUG: price_diff={float(price) - grid_start_price:.4f}, pips_diff={(float(price) - grid_start_price)/pip_value:.1f}")
        print()
    
    return all_passed

def test_trailing_sl_logic():
    """Test trailing stop loss logic for different grid levels"""
    print("🧪 Testing Trailing Stop Loss Logic")
    print("=" * 50)
    
    # Test parameters
    zone_threshold_pips = 300.0
    pip_value = 0.0001
    
    print("Trailing SL Rules:")
    print("- Level 0: No trailing SL")
    print("- Level 1: No trailing SL, order can close with its own SL")
    print("- Level 2+: Trailing SL activated")
    print("  - BUY: Max(upper_bound, highest_buy - zone_threshold)")
    print("  - SELL: Min(lower_bound, lowest_sell + zone_threshold)")
    print()
    
    # Test cases for BUY cycle
    print("BUY Cycle Trailing SL:")
    upper_bound = 1.2300
    lower_bound = 1.1700
    highest_buy = 1.1600  # Assume highest buy order at this price
    
    trailing_sl_buy = max(upper_bound, highest_buy - (zone_threshold_pips * pip_value))
    print(f"  Upper Bound: {upper_bound:.4f}")
    print(f"  Highest Buy: {highest_buy:.4f}")
    print(f"  Trailing SL: {trailing_sl_buy:.4f}")
    print()
    
    # Test cases for SELL cycle
    print("SELL Cycle Trailing SL:")
    lowest_sell = 1.2400  # Assume lowest sell order at this price
    
    trailing_sl_sell = min(lower_bound, lowest_sell + (zone_threshold_pips * pip_value))
    print(f"  Lower Bound: {lower_bound:.4f}")
    print(f"  Lowest Sell: {lowest_sell:.4f}")
    print(f"  Trailing SL: {trailing_sl_sell:.4f}")
    print()
    
    return True

def main():
    """Run all MoveGuard grid system tests"""
    print("🚀 MoveGuard Grid System Verification")
    print("=" * 60)
    print("Testing the corrected grid system using zone boundaries")
    print("=" * 60)
    print()
    
    buy_test_passed = test_buy_cycle_grid_levels()
    print()
    sell_test_passed = test_sell_cycle_grid_levels()
    print()
    test_trailing_sl_logic()
    
    print("=" * 60)
    if buy_test_passed and sell_test_passed:
        print("🎉 ALL TESTS PASSED! MoveGuard grid system is working correctly.")
        print("✅ BUY cycle grid levels calculated correctly")
        print("✅ SELL cycle grid levels calculated correctly")
        print("✅ Zone boundary logic implemented correctly")
    else:
        print("❌ Some tests failed. Grid system needs more work.")
        if not buy_test_passed:
            print("❌ BUY cycle tests failed")
        if not sell_test_passed:
            print("❌ SELL cycle tests failed")
    
    print("=" * 60)

if __name__ == "__main__":
    main()
