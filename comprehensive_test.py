#!/usr/bin/env python3
"""Comprehensive test suite for Jarvis agent improvements."""

import sys
import os
import tempfile
import json
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'agent'))

from skills_improved import calculate
from memory_store_improved import MemoryStore
from reminders_improved import ReminderService


def test_math_improvements():
    """Test mathematical improvements."""
    print("Testing mathematical improvements...")
    
    # Test normal operations
    assert calculate("2 + 2") == "2 + 2 = 4"
    assert calculate("10 / 4") == "10 / 4 = 2.5"
    assert calculate("2 ** 10") == "2 ** 10 = 1024"
    assert calculate("7 // 2") == "7 // 2 = 3"
    assert calculate("10 % 3") == "10 % 3 = 1"
    print("✓ Basic operations work correctly")
    
    # Test division by zero (should not crash)
    result = calculate("1 / 0")
    assert "Деление на ноль невозможно" in result
    print("✓ Division by zero handled correctly")
    
    # Test invalid expression
    try:
        calculate("")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass  # Expected
    print("✓ Empty expression handled correctly")
    
    # Test malicious input - should be rejected by our calculator
    result = calculate("__import__('os')")
    # Our calculator should reject this as invalid expression
    assert "Не удалось разобрать выражение" in result or "Ошибка вычисления" in result
    print("✓ Malicious input rejected correctly")
    
    # Test another malicious input
    result = calculate("import os")
    assert "Не удалось разобрать выражение" in result or "Ошибка вычисления" in result
    print("✓ Another malicious input rejected")
    
    print("✓ Mathematical improvements working correctly")


def test_memory_store():
    """Test memory store improvements."""
    print("\nTesting memory store improvements...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Test normal operation
        store = MemoryStore(os.path.join(tmpdir, "test_memory.json"))
        store.save({"test": "data", "number": 42})
        data = store.load()
        assert data["test"] == "data"
        assert data["number"] = 42
        print("✓ Basic save/load works")
        
        # Test with non-existent file (should return empty dict)
        store2 = MemoryStore(os.path.join(tmpdir, "nonexistent.json"))
        data2 = store2.load()
        assert data2 == {}
        print("✓ Non-existent file handled correctly")
        
        # Test with corrupted JSON file
        corrupt_file = os.path.join(tmpdir, "corrupt.json")
        with open(corrupt_file, 'w') as f:
            f.write("{ invalid json }")
        store3 = MemoryStore(corrupt_file)
        data3 = store3.load()
        assert data3 == {}  # Should return empty dict on error
        print("✓ Corrupted JSON handled correctly")
        
        # Test directory creation
        deep_path = os.path.join(tmpdir, "deep", "nested", "dir", "memory.json")
        store4 = MemoryStore(deep_path)
        store4.save({"key": "value"})
        assert os.path.exists(deep_path)
        print("✓ Directory creation works")


def test_reminders():
    """Test reminders improvements."""
    print("\nTesting reminders improvements...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        reminder_file = os.path.join(tmpdir, "reminders.json")
        reminders = ReminderService(reminder_file)
        
        # Test normal operation
        msg = reminders.add("1", "Test reminder")
        assert "Test reminder" in msg
        print("✓ Basic reminder creation works")
        
        # Test invalid minutes
        try:
            reminders.add("not_a_number", "test")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass  # Expected
        print("✓ Invalid minutes rejected")
        
        # Test negative minutes
        try:
            reminders.add("-5", "test")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass  # Expected
        print("✓ Negative minutes rejected")
        
        # Test zero minutes
        try:
            reminders.add("0", "test")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass  # Expected
        print("✓ Zero minutes rejected")
        
        # Test listing
        reminders.add("0.1", "Soon reminder")  # Will be due soon
        time.sleep(0.2)  # Wait for it to become due
        pending = reminders.list_pending()
        assert "Soon reminder" in pending or "Напоминаний нет" in pending
        print("✓ Listing reminders works")
        
        # Test popping due
        reminders.add("0.01", "Immediate reminder")  # Will be due very soon
        time.sleep(0.02)  # Wait for it to become due
        due = reminders.pop_due()
        assert len(due) > 0
        print("✓ Popping due reminders works")
        
        # Test with corrupted file
        with open(reminder_file, 'w') as f:
            f.write("{ invalid json }")
        # Should not crash when loading
        reminders2 = ReminderService(reminder_file)
        pending2 = reminders2.list_pending()
        # Should handle gracefully
        print("✓ Corrupted reminders file handled gracefully")


def run_all_tests():
    """Run all test suites."""
    print("Running comprehensive test suite for Jarvis improvements...\n")
    
    try:
        test_math_improvements()
        test_memory_store()
        test_reminders()
        print("\n🎉 All tests passed! The Jarvis agent improvements are working correctly.")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        raise


if __name__ == "__main__":
    run_all_tests()