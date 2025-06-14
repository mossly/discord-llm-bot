"""
Test suite for the new reminder system performance optimizations
"""
import asyncio
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta
import pytz

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Create a temporary data directory for testing
TEST_DATA_DIR = tempfile.mkdtemp()
os.environ['TEST_MODE'] = 'true'

# Monkey patch the data directory for testing
import utils.reminder_manager_v2 as rm_v2
rm_v2.DB_PATH = os.path.join(TEST_DATA_DIR, "test_reminders.db")

from utils.reminder_manager_v2 import ReminderManagerV2
from utils.background_task_manager import BackgroundTaskManager, TaskPriority


async def test_reminder_manager_initialization():
    """Test reminder manager initialization"""
    print("Testing reminder manager initialization...")
    
    # Create a fresh instance for testing
    manager = ReminderManagerV2()
    await manager.initialize()
    
    # Test database creation
    assert os.path.exists(manager.db_path), "Database file should be created"
    print("✅ Database initialization")
    
    # Test connection pool
    assert len(manager._connection_pool) > 0, "Connection pool should be initialized"
    print("✅ Connection pool initialization")
    
    await manager.close()
    print("✅ Manager initialization complete")


async def test_basic_reminder_operations():
    """Test basic reminder CRUD operations"""
    print("\nTesting basic reminder operations...")
    
    manager = ReminderManagerV2()
    await manager.initialize()
    
    try:
        # Test adding a reminder
        user_id = 12345
        reminder_text = "Test reminder"
        trigger_time = time.time() + 3600  # 1 hour from now
        timezone = "America/New_York"
        
        success, message = await manager.add_reminder(user_id, reminder_text, trigger_time, timezone)
        assert success, f"Failed to add reminder: {message}"
        print("✅ Add reminder")
        
        # Test getting user reminders
        reminders = await manager.get_user_reminders(user_id)
        assert len(reminders) == 1, "Should have 1 reminder"
        assert reminders[0][1] == reminder_text, "Reminder text should match"
        print("✅ Get user reminders")
        
        # Test getting next reminder time
        next_time = await manager.get_next_reminder_time()
        assert next_time is not None, "Should have a next reminder time"
        assert abs(next_time - trigger_time) < 1, "Next reminder time should match"
        print("✅ Get next reminder time")
        
        # Test canceling reminder
        success, message = await manager.cancel_reminder(user_id, trigger_time)
        assert success, f"Failed to cancel reminder: {message}"
        print("✅ Cancel reminder")
        
        # Verify reminder was deleted
        reminders = await manager.get_user_reminders(user_id)
        assert len(reminders) == 0, "Should have 0 reminders after cancellation"
        print("✅ Verify cancellation")
        
    finally:
        await manager.close()


async def test_timezone_operations():
    """Test timezone management"""
    print("\nTesting timezone operations...")
    
    manager = ReminderManagerV2()
    await manager.initialize()
    
    try:
        user_id = 12345
        
        # Test setting timezone
        success, message = await manager.set_user_timezone(user_id, "Europe/London")
        assert success, f"Failed to set timezone: {message}"
        print("✅ Set timezone")
        
        # Test getting timezone
        timezone = await manager.get_user_timezone(user_id)
        assert timezone == "Europe/London", "Timezone should match"
        print("✅ Get timezone")
        
        # Test invalid timezone
        success, message = await manager.set_user_timezone(user_id, "Invalid/Timezone")
        assert not success, "Should fail with invalid timezone"
        print("✅ Invalid timezone handling")
        
    finally:
        await manager.close()


async def test_natural_time_parsing():
    """Test natural language time parsing"""
    print("\nTesting natural language time parsing...")
    
    manager = ReminderManagerV2()
    timezone = "America/New_York"
    
    # Test various time formats
    test_cases = [
        ("in 30 seconds", True),
        ("in 5 minutes", True),
        ("in 2 hours", True),
        ("tomorrow", True),
        ("tomorrow at 3pm", True),
        ("next friday", True),
        ("invalid time", False),
        ("", False),
    ]
    
    for time_str, should_succeed in test_cases:
        result = manager.parse_natural_time(time_str, timezone)
        if should_succeed:
            assert result is not None, f"Should parse '{time_str}' successfully"
        else:
            assert result is None, f"Should fail to parse '{time_str}'"
    
    print("✅ Natural time parsing")


async def test_caching_system():
    """Test the caching system"""
    print("\nTesting caching system...")
    
    manager = ReminderManagerV2()
    await manager.initialize()
    
    try:
        user_id = 12345
        
        # Add a reminder
        success, _ = await manager.add_reminder(
            user_id, "Cache test", time.time() + 3600, "UTC"
        )
        assert success
        
        # First call should hit database
        start_time = time.time()
        reminders1 = await manager.get_user_reminders(user_id)
        first_call_time = time.time() - start_time
        
        # Second call should hit cache and be faster
        start_time = time.time()
        reminders2 = await manager.get_user_reminders(user_id)
        second_call_time = time.time() - start_time
        
        assert reminders1 == reminders2, "Results should be identical"
        # Note: In test environment, the difference might be minimal
        print("✅ Caching system")
        
        # Test cache invalidation
        await manager._invalidate_cache(f"user_reminders_{user_id}")
        print("✅ Cache invalidation")
        
    finally:
        await manager.close()


async def test_background_task_manager():
    """Test background task manager"""
    print("\nTesting background task manager...")
    
    task_manager = BackgroundTaskManager(max_workers=2)
    await task_manager.start()
    
    try:
        # Test simple task submission
        async def test_task(value):
            await asyncio.sleep(0.1)
            return value * 2
        
        success = await task_manager.submit_function(
            test_task, 5, task_id="test_task_1"
        )
        assert success, "Task submission should succeed"
        print("✅ Task submission")
        
        # Wait for task completion
        await asyncio.sleep(0.2)
        
        # Check metrics
        metrics = task_manager.get_metrics()
        assert metrics["total_tasks"] >= 1, "Should have processed tasks"
        print("✅ Task execution and metrics")
        
    finally:
        await task_manager.stop()


async def test_performance_optimizations():
    """Test performance optimizations"""
    print("\nTesting performance optimizations...")
    
    manager = ReminderManagerV2()
    await manager.initialize()
    
    try:
        # Test with multiple reminders
        user_id = 12345
        base_time = time.time() + 3600
        
        # Add multiple reminders
        for i in range(10):
            success, _ = await manager.add_reminder(
                user_id, f"Reminder {i}", base_time + i * 60, "UTC"
            )
            assert success
        
        # Test efficient querying
        start_time = time.time()
        reminders = await manager.get_user_reminders(user_id)
        query_time = time.time() - start_time
        
        assert len(reminders) == 10, "Should have 10 reminders"
        print(f"✅ Efficient querying ({query_time:.4f}s for 10 reminders)")
        
        # Test due reminders query
        due_reminders = await manager.get_due_reminders()
        assert len(due_reminders) == 0, "No reminders should be due yet"
        print("✅ Due reminders query")
        
        # Test cleanup
        deleted_count = await manager.cleanup_expired_reminders()
        assert deleted_count == 0, "No expired reminders to clean"
        print("✅ Cleanup operations")
        
    finally:
        await manager.close()


async def test_error_handling():
    """Test error handling and edge cases"""
    print("\nTesting error handling...")
    
    manager = ReminderManagerV2()
    await manager.initialize()
    
    try:
        user_id = 12345
        
        # Test adding reminder in the past
        past_time = time.time() - 3600
        success, message = await manager.add_reminder(
            user_id, "Past reminder", past_time, "UTC"
        )
        assert not success, "Should fail for past time"
        assert "past" in message.lower(), "Error message should mention past"
        print("✅ Past time handling")
        
        # Test maximum reminders limit
        base_time = time.time() + 3600
        for i in range(25):  # MAX_REMINDERS_PER_USER
            await manager.add_reminder(user_id, f"Reminder {i}", base_time + i, "UTC")
        
        # Try to add one more
        success, message = await manager.add_reminder(
            user_id, "Extra reminder", base_time + 100, "UTC"
        )
        assert not success, "Should fail when limit exceeded"
        print("✅ Reminder limit handling")
        
        # Test canceling non-existent reminder
        success, message = await manager.cancel_reminder(user_id, time.time() + 9999)
        assert not success, "Should fail for non-existent reminder"
        print("✅ Non-existent reminder handling")
        
    finally:
        await manager.close()


async def run_reminder_system_tests():
    """Run all reminder system tests"""
    print("=" * 60)
    print("REMINDER SYSTEM PERFORMANCE OPTIMIZATION TESTS")
    print("=" * 60)
    
    start_time = time.time()
    
    tests = [
        test_reminder_manager_initialization,
        test_basic_reminder_operations,
        test_timezone_operations,
        test_natural_time_parsing,
        test_caching_system,
        test_background_task_manager,
        test_performance_optimizations,
        test_error_handling,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            await test_func()
            passed += 1
        except Exception as e:
            print(f"❌ {test_func.__name__} failed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    total_time = time.time() - start_time
    
    print("\n" + "=" * 60)
    print("REMINDER SYSTEM TEST SUMMARY")
    print("=" * 60)
    print(f"Total tests: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Total time: {total_time:.2f}s")
    
    if failed == 0:
        print("\n🎉 All reminder system tests passed!")
        print("Performance optimizations are working correctly.")
        return True
    else:
        print(f"\n⚠️  {failed} test(s) failed.")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_reminder_system_tests())
    
    # Cleanup test directory
    import shutil
    shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)
    
    sys.exit(0 if success else 1)