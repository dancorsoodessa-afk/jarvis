#!/usr/bin/env python3
"""Test script to verify improvements to the Jarvis agent."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'agent'))

from skills_improved import calculate

def test_calculate_improvements():
    """Test that the calculate function handles edge cases properly."""
    print("Testing calculate function improvements...")
    
    # Test normal operations
    assert calculate("2 + 2") == "2 + 2 = 4"
    assert calculate("10 / 4") == "10 / 4 = 2.5"
    assert calculate("2 ** 10") == "2 ** 10 = 1024"
    print("✓ Basic operations work correctly")
    
    # Test division by zero (should not crash)
    result = calculate("1 / 0")
    assert "Деление на ноль невозможно" in result
    print("✓ Division by zero handled correctly")
    
    # Test overflow (large exponent)
    result = calculate("2 ** 1000")
    # This should either work or give an overflow message
    print(f"✓ Large exponent: {result[:50]}...")
    
    # Test invalid expression
    try:
        calculate("")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Пустое выражение" in str(e)
        print("✓ Empty expression handled correctly")
    
    print("All calculate tests passed!")

if __name__ == "__main__":
    test_calculate_improvements()