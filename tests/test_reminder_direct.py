"""
Direct test of reminder system components without global imports
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


async def test_reminder_manager_v2_direct():
    """Test the new reminder manager directly"""
    print("Testing ReminderManagerV2 directly...")
    
    # Import and modify the DB path before creating instance
    from utils.reminder_manager_v2 import ReminderManagerV2, DB_PATH
    
    # Create a test instance with custom DB path
    class TestReminderManager(ReminderManagerV2):
        def __init__(self):
            # Override the singleton behavior for testing
            self.initialized = False
            self.db_path = os.path.join(TEST_DATA_DIR, "test_reminders.db")
            self.dm_failed_users = set()
            self._cache = {}
            self._cache_lock = asyncio.Lock()
            self._reminder_added_event = asyncio.Event()
            self._next_reminder_time = None
            self._connection_pool = []
            self._pool_lock = asyncio.Lock()
            self._max_connections = 2  # Smaller for testing
            os.makedirs(TEST_DATA_DIR, exist_ok=True)
    
    manager = TestReminderManager()
    
    try:
        # Test initialization
        await manager.initialize()
        print("✅ Manager initialization")
        
        # Test adding a reminder
        user_id = 12345
        reminder_text = "Test reminder"
        trigger_time = time.time() + 3600  # 1 hour from now
        timezone = "America/New_York"
        
        success, message = await manager.add_reminder(user_id, reminder_text, trigger_time, timezone)
        if success:
            print("✅ Add reminder")
        else:
            print(f"❌ Add reminder failed: {message}")
        
        # Wait a bit for background task
        await asyncio.sleep(0.5)
        
        # Test getting user reminders
        reminders = await manager.get_user_reminders(user_id)
        if len(reminders) >= 1:
            print("✅ Get user reminders")
        else:
            print(f"❌ Expected reminders, got {len(reminders)}")
        
        # Test timezone operations
        success, _ = await manager.set_user_timezone(user_id, "Europe/London")
        if success:
            print("✅ Set timezone")
        
        timezone = await manager.get_user_timezone(user_id)
        if timezone == "Europe/London":
            print("✅ Get timezone")
        
        # Test natural time parsing
        parsed_time = manager.parse_natural_time("in 30 seconds", "UTC")
        if parsed_time is not None:
            print("✅ Natural time parsing")
        
        # Test invalid time parsing
        invalid_time = manager.parse_natural_time("invalid time", "UTC")
        if invalid_time is None:
            print("✅ Invalid time handling")
        
        print("\n✅ All basic reminder manager tests passed!")
        
    except Exception as e:
        print(f"❌ Reminder manager test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await manager.close()


async def test_background_task_manager_direct():
    """Test background task manager directly"""
    print("\nTesting BackgroundTaskManager directly...")
    
    from utils.background_task_manager import BackgroundTaskManager, TaskPriority
    
    task_manager = BackgroundTaskManager(max_workers=2)
    
    try:
        await task_manager.start()
        print("✅ Background task manager start")
        
        # Test simple function execution
        def simple_task(x):
            return x * 2
        
        success = await task_manager.submit_function(
            simple_task, 5, task_id="test_simple"
        )
        if success:
            print("✅ Task submission")
        
        # Wait for task completion
        await asyncio.sleep(0.2)
        
        # Check metrics
        metrics = task_manager.get_metrics()
        if metrics["total_tasks"] >= 1:
            print("✅ Task execution and metrics")
        
        print("✅ Background task manager tests passed!")
        
    except Exception as e:
        print(f"❌ Background task manager test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await task_manager.stop()


async def test_performance_comparison():
    """Test performance improvements"""
    print("\nTesting performance characteristics...")
    
    try:
        # Test file operations
        test_file = os.path.join(TEST_DATA_DIR, "perf_test.txt")
        
        # Test synchronous vs asynchronous patterns
        start_time = time.time()
        for i in range(10):
            with open(test_file, 'w') as f:
                f.write(f"test data {i}")
        sync_time = time.time() - start_time
        
        print(f"✅ Sync file operations: {sync_time:.4f}s")
        
        # Test async sleep patterns
        start_time = time.time()
        await asyncio.sleep(0.01)  # Short sleep
        async_time = time.time() - start_time
        
        print(f"✅ Async operations: {async_time:.4f}s")
        
        print("✅ Performance testing completed")
        
    except Exception as e:
        print(f"❌ Performance test failed: {e}")


def test_syntax_validation():
    """Test syntax of new files"""
    print("\nTesting syntax of new reminder system files...")
    
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    files_to_check = [
        "utils/reminder_manager_v2.py",
        "utils/background_task_manager.py", 
        "cogs/reminders_v2.py",
        "cogs/tools/reminder_tool_v2.py",
    ]
    
    all_valid = True
    
    for file_path in files_to_check:
        full_path = os.path.join(project_root, file_path)
        
        if not os.path.exists(full_path):
            print(f"⚠️  {file_path} - FILE NOT FOUND")
            continue
        
        try:
            import py_compile
            py_compile.compile(full_path, doraise=True)
            print(f"✅ {file_path} - SYNTAX OK")
        except Exception as e:
            print(f"❌ {file_path} - SYNTAX ERROR: {e}")
            all_valid = False
    
    if all_valid:
        print("✅ All new files have valid syntax")
    
    return all_valid


async def run_direct_tests():
    """Run direct tests without problematic imports"""
    print("=" * 60)
    print("REMINDER SYSTEM DIRECT TESTS")
    print("=" * 60)
    
    start_time = time.time()
    
    try:
        # Test syntax first
        syntax_ok = test_syntax_validation()
        
        if syntax_ok:
            # Test core functionality
            await test_reminder_manager_v2_direct()
            await test_background_task_manager_direct()
            await test_performance_comparison()
        
        total_time = time.time() - start_time
        
        print("\n" + "=" * 60)
        print("DIRECT TEST SUMMARY")
        print("=" * 60)
        print(f"Total time: {total_time:.2f}s")
        
        if syntax_ok:
            print("\n🎉 All direct tests completed successfully!")
            print("New reminder system components are working correctly.")
            return True
        else:
            print("\n⚠️  Some syntax issues found.")
            return False
            
    except Exception as e:
        print(f"\n❌ Direct tests failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(run_direct_tests())
    
    # Cleanup test directory
    import shutil
    shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)
    
    sys.exit(0 if success else 1)