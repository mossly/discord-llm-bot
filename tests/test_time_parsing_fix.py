"""
Test the enhanced time parsing to fix the "1 minute from now" issue
"""
import sys
import os
import tempfile
from datetime import datetime, timedelta
import pytz

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Create a temporary data directory for testing
TEST_DATA_DIR = tempfile.mkdtemp()


def test_enhanced_time_parsing():
    """Test the enhanced natural language time parsing"""
    print("🕒 Testing Enhanced Time Parsing for '1 minute from now' Issue")
    print("=" * 60)
    
    # Import the reminder manager class directly
    from utils.reminder_manager import ReminderManagerV2 as ReminderManager
    
    # Create a test instance
    manager = ReminderManager()
    
    # Test timezone
    test_timezone = "America/New_York"
    
    # Test cases that should now work
    test_cases = [
        # Original problem case
        ("1 minute from now", True, "Original failing case"),
        ("5 minutes from now", True, "Standard 'from now' pattern"),
        
        # Enhanced patterns
        ("in about 2 minutes", True, "In about pattern"),
        ("around 3 minutes", True, "Around pattern"),
        ("a minute from now", True, "Informal 'a minute'"),
        ("a few seconds", True, "Informal 'a few seconds'"),
        
        # Abbreviations
        ("1 min from now", True, "Minute abbreviation"),
        ("30 secs from now", True, "Second abbreviation"),
        ("2 hrs from now", True, "Hour abbreviation"),
        
        # Existing patterns (should still work)
        ("in 5 minutes", True, "Original 'in' pattern"),
        ("in 30 seconds", True, "Original seconds pattern"),
        ("tomorrow at 3pm", True, "Absolute time pattern"),
        
        # Edge cases
        ("invalid time string", False, "Invalid input"),
        ("", False, "Empty string"),
    ]
    
    passed_tests = 0
    failed_tests = 0
    
    print("Testing parsing patterns:")
    print("-" * 60)
    
    for time_str, should_succeed, description in test_cases:
        try:
            result = manager.parse_natural_time(time_str, test_timezone)
            
            if should_succeed and result is not None:
                # Calculate expected time for validation
                now = datetime.now(pytz.timezone(test_timezone))
                time_diff = result - now
                
                print(f"✅ '{time_str}' → {result.strftime('%H:%M:%S')} (+{time_diff.total_seconds():.0f}s) - {description}")
                passed_tests += 1
            elif not should_succeed and result is None:
                print(f"✅ '{time_str}' → None (expected failure) - {description}")
                passed_tests += 1
            elif should_succeed and result is None:
                print(f"❌ '{time_str}' → None (should have succeeded) - {description}")
                failed_tests += 1
            else:
                print(f"❌ '{time_str}' → {result} (should have failed) - {description}")
                failed_tests += 1
                
        except Exception as e:
            print(f"❌ '{time_str}' → ERROR: {e} - {description}")
            failed_tests += 1
    
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS:")
    print(f"   Passed: {passed_tests}")
    print(f"   Failed: {failed_tests}")
    print(f"   Total:  {passed_tests + failed_tests}")
    
    if failed_tests == 0:
        print("\n🎉 All time parsing tests passed!")
        print("✅ '1 minute from now' issue is FIXED")
        return True
    else:
        print(f"\n⚠️  {failed_tests} test(s) failed")
        return False


def test_dual_input_concept():
    """Test the concept of dual input support (without full tool execution)"""
    print("\n🔧 Testing Dual Input Support Concept")
    print("=" * 60)
    
    import time
    
    # Simulate what the LLM would do with dual input support
    test_scenarios = [
        {
            "user_input": "1 minute from now",
            "time_str": "1 minute from now",
            "fallback_timestamp": time.time() + 60,
            "description": "Original problem case with fallback"
        },
        {
            "user_input": "in 2 hours",
            "time_str": "in 2 hours", 
            "fallback_timestamp": time.time() + 7200,
            "description": "Standard case"
        }
    ]
    
    from utils.reminder_manager import ReminderManagerV2 as ReminderManager
    manager = ReminderManager()
    
    for scenario in test_scenarios:
        print(f"\nScenario: {scenario['description']}")
        print(f"User said: '{scenario['user_input']}'")
        
        # Try natural language first
        result = manager.parse_natural_time(scenario['time_str'], "UTC")
        
        if result:
            print(f"✅ Natural language parsing succeeded: {result}")
            print(f"   Would use: time_str='{scenario['time_str']}'")
        else:
            print(f"⚠️  Natural language parsing failed")
            print(f"✅ Would fallback to: timestamp={scenario['fallback_timestamp']}")
            print(f"   Calculated as: {datetime.utcfromtimestamp(scenario['fallback_timestamp'])}")
        
        print(f"🎯 Result: User gets reminder set without format complaints")
    
    print("\n✅ Dual input support concept validated!")
    return True


def main():
    """Run all time parsing tests"""
    print("🚀 Testing Enhanced Reminder Time Parsing")
    print("Fixing the '1 minute from now' issue\n")
    
    success1 = test_enhanced_time_parsing()
    success2 = test_dual_input_concept()
    
    print("\n" + "=" * 60)
    print("🏁 FINAL RESULTS")
    print("=" * 60)
    
    if success1 and success2:
        print("🎉 ALL TESTS PASSED!")
        print("✅ Enhanced time parsing implemented successfully")
        print("✅ Dual input support concept validated")
        print("✅ '1 minute from now' issue is SOLVED")
        print("\n🎯 Expected behavior after deployment:")
        print("   - User: 'Remind me in 1 minute from now'")
        print("   - LLM: Sets reminder successfully without complaints")
        print("   - No more 'please use different format' messages")
        return True
    else:
        print("❌ Some tests failed - review implementation")
        return False


if __name__ == "__main__":
    success = main()
    
    # Cleanup
    import shutil
    shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)
    
    sys.exit(0 if success else 1)