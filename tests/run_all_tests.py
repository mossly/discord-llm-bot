"""
Test runner for all tool calling system tests
"""
import sys
import os
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import test modules
from test_base_tool import run_base_tool_tests
from test_tool_registry import run_registry_tests
from test_web_search_tool import run_web_search_tests
from test_content_tool import run_content_tool_tests
from test_integration import run_integration_tests


def run_all_tests():
    """Run all test suites"""
    print("=" * 60)
    print("DISCORD LLM BOT - TOOL CALLING SYSTEM TEST SUITE")
    print("=" * 60)
    
    start_time = time.time()
    
    # Run all test suites
    test_suites = [
        ("BaseTool", run_base_tool_tests),
        ("ToolRegistry", run_registry_tests),
        ("WebSearchTool", run_web_search_tests),
        ("ContentRetrievalTool", run_content_tool_tests),
        ("Integration", run_integration_tests)
    ]
    
    results = []
    
    for suite_name, test_function in test_suites:
        print(f"\n{'=' * 20} {suite_name} Tests {'=' * 20}")
        
        suite_start = time.time()
        
        try:
            test_function()
            suite_time = time.time() - suite_start
            results.append((suite_name, "PASSED", suite_time))
            print(f"✅ {suite_name} tests completed in {suite_time:.2f}s")
        except Exception as e:
            suite_time = time.time() - suite_start
            results.append((suite_name, f"FAILED: {e}", suite_time))
            print(f"❌ {suite_name} tests failed in {suite_time:.2f}s: {e}")
    
    # Print summary
    total_time = time.time() - start_time
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for suite_name, status, duration in results:
        if status == "PASSED":
            print(f"✅ {suite_name:<20} PASSED ({duration:.2f}s)")
            passed += 1
        else:
            print(f"❌ {suite_name:<20} FAILED ({duration:.2f}s)")
            failed += 1
    
    print("-" * 60)
    print(f"Total: {len(results)} suites, {passed} passed, {failed} failed")
    print(f"Total time: {total_time:.2f}s")
    
    if failed == 0:
        print("\n🎉 All tests passed! Tool calling system is ready for deployment.")
        return True
    else:
        print(f"\n⚠️  {failed} test suite(s) failed. Please review and fix issues.")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)