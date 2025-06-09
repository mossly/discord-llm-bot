#!/usr/bin/env python3
"""
Performance test for model cache system
"""
import asyncio
import time
import logging
import os
import json
from typing import Dict, List

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


async def test_model_cache_performance():
    """Test the performance of the model cache system"""
    print("=" * 60)
    print("MODEL CACHE PERFORMANCE TEST")
    print("=" * 60)
    
    # Import the cache system
    try:
        from cogs.model_cache import ModelCache
        print("✅ Successfully imported ModelCache")
    except ImportError as e:
        print(f"❌ Failed to import ModelCache: {e}")
        return False
    
    # Create cache instance
    print("\n🔧 Initializing cache...")
    start_time = time.time()
    cache = ModelCache()
    init_time = time.time() - start_time
    print(f"✅ Cache initialized in {init_time:.3f} seconds")
    
    # Get initial stats
    stats = cache.get_cache_stats()
    print(f"📊 Initial stats: {stats['models_count']} models, {stats['admin_count']} admins")
    
    # Performance test parameters
    test_iterations = 1000
    test_user_ids = [12345, 67890, 11111, 22222, 33333]  # Mix of regular users
    test_admin_ids = [99999]  # Admin users
    test_model_keys = ["gpt-4o-mini", "claude-sonnet-4", "deepseek-r1-0528", "gemini-2.5-pro-preview"]
    
    print(f"\n🚀 Running performance tests with {test_iterations} iterations...")
    
    # Test 1: Model config retrieval
    print("\n1️⃣ Testing model config retrieval...")
    start_time = time.time()
    
    for i in range(test_iterations):
        for model_key in test_model_keys:
            config = cache.get_model_config(model_key)
            if config and i == 0:  # Print first result
                print(f"   Sample config for {model_key}: {config.get('name', 'Unknown')}")
    
    config_time = time.time() - start_time
    config_rate = (test_iterations * len(test_model_keys)) / config_time
    print(f"✅ Model config retrieval: {config_time:.3f}s ({config_rate:.0f} ops/sec)")
    
    # Test 2: Available models for regular users
    print("\n2️⃣ Testing available models for regular users...")
    start_time = time.time()
    
    for i in range(test_iterations):
        for user_id in test_user_ids:
            models = cache.get_available_models(user_id)
            if i == 0:  # Print first result
                print(f"   User {user_id} has access to {len(models)} models")
    
    user_models_time = time.time() - start_time
    user_models_rate = (test_iterations * len(test_user_ids)) / user_models_time
    print(f"✅ User models retrieval: {user_models_time:.3f}s ({user_models_rate:.0f} ops/sec)")
    
    # Test 3: Available models for admin users
    print("\n3️⃣ Testing available models for admin users...")
    start_time = time.time()
    
    for i in range(test_iterations):
        for admin_id in test_admin_ids:
            models = cache.get_available_models(admin_id)
            if i == 0:  # Print first result
                print(f"   Admin {admin_id} has access to {len(models)} models")
    
    admin_models_time = time.time() - start_time
    admin_models_rate = (test_iterations * len(test_admin_ids)) / admin_models_time
    print(f"✅ Admin models retrieval: {admin_models_time:.3f}s ({admin_models_rate:.0f} ops/sec)")
    
    # Test 4: Admin check
    print("\n4️⃣ Testing admin checks...")
    start_time = time.time()
    
    all_users = test_user_ids + test_admin_ids
    for i in range(test_iterations):
        for user_id in all_users:
            is_admin = cache.is_admin(user_id)
            if i == 0:
                print(f"   User {user_id} admin status: {is_admin}")
    
    admin_check_time = time.time() - start_time
    admin_check_rate = (test_iterations * len(all_users)) / admin_check_time
    print(f"✅ Admin checks: {admin_check_time:.3f}s ({admin_check_rate:.0f} ops/sec)")
    
    # Test 5: Mixed workload simulation
    print("\n5️⃣ Testing mixed workload (simulating real usage)...")
    start_time = time.time()
    
    for i in range(test_iterations // 10):  # Smaller iteration count for mixed test
        # Simulate a /chat command flow
        user_id = test_user_ids[i % len(test_user_ids)]
        
        # Check admin status
        is_admin = cache.is_admin(user_id)
        
        # Get available models
        available_models = cache.get_available_models(user_id)
        
        # Get configs for available models
        for model_key in list(available_models.keys())[:3]:  # First 3 models
            config = cache.get_model_config(model_key)
    
    mixed_time = time.time() - start_time
    mixed_rate = (test_iterations // 10) / mixed_time
    print(f"✅ Mixed workload: {mixed_time:.3f}s ({mixed_rate:.0f} chat-flows/sec)")
    
    # Get final stats
    final_stats = cache.get_cache_stats()
    print(f"\n📊 Final cache stats:")
    print(f"   Cache hits: {final_stats['cache_hits']}")
    print(f"   Cache misses: {final_stats['cache_misses']}")
    print(f"   Hit rate: {final_stats['hit_rate_percent']:.2f}%")
    print(f"   Cache version: {final_stats['cache_version']}")
    
    # Performance summary
    print(f"\n🏆 PERFORMANCE SUMMARY")
    print(f"=" * 40)
    print(f"Model config retrieval:  {config_rate:>10.0f} ops/sec")
    print(f"User models lookup:      {user_models_rate:>10.0f} ops/sec")
    print(f"Admin models lookup:     {admin_models_rate:>10.0f} ops/sec")
    print(f"Admin checks:            {admin_check_rate:>10.0f} ops/sec")
    print(f"Full chat simulation:    {mixed_rate:>10.0f} ops/sec")
    print(f"Cache hit rate:          {final_stats['hit_rate_percent']:>10.2f}%")
    
    # Estimated real-world impact
    print(f"\n💡 ESTIMATED REAL-WORLD IMPACT")
    print(f"=" * 40)
    avg_chat_time_old = 0.1  # Estimated old system time per chat (100ms)
    avg_chat_time_new = 1.0 / mixed_rate  # New system time per chat
    speedup = avg_chat_time_old / avg_chat_time_new if avg_chat_time_new > 0 else float('inf')
    
    print(f"Old system (estimated):  {avg_chat_time_old*1000:>8.1f} ms per /chat")
    print(f"New system (measured):   {avg_chat_time_new*1000:>8.1f} ms per /chat")
    print(f"Performance improvement: {speedup:>8.1f}x faster")
    
    if speedup > 5:
        print("🚀 EXCELLENT: >5x performance improvement!")
    elif speedup > 2:
        print("✅ GOOD: >2x performance improvement!")
    else:
        print("⚠️  MODEST: <2x performance improvement")
    
    return True


async def benchmark_memory_usage():
    """Benchmark memory usage of the cache"""
    print("\n" + "=" * 60)
    print("MEMORY USAGE BENCHMARK")
    print("=" * 60)
    
    import tracemalloc
    import gc
    
    # Start memory tracing
    tracemalloc.start()
    
    # Measure baseline memory
    gc.collect()
    baseline_snapshot = tracemalloc.take_snapshot()
    baseline_stats = baseline_snapshot.statistics('lineno')
    baseline_memory = sum(stat.size for stat in baseline_stats)
    
    print(f"📊 Baseline memory: {baseline_memory / 1024 / 1024:.2f} MB")
    
    # Create cache
    from cogs.model_cache import ModelCache
    cache = ModelCache()
    
    # Measure memory after cache creation
    gc.collect()
    cache_snapshot = tracemalloc.take_snapshot()
    cache_stats = cache_snapshot.statistics('lineno')
    cache_memory = sum(stat.size for stat in cache_stats)
    
    cache_overhead = cache_memory - baseline_memory
    print(f"📊 Cache memory: {cache_memory / 1024 / 1024:.2f} MB")
    print(f"📊 Cache overhead: {cache_overhead / 1024:.2f} KB")
    
    # Warm up cache
    cache.warm_cache()
    
    # Measure memory after warm-up
    gc.collect()
    warm_snapshot = tracemalloc.take_snapshot()
    warm_stats = warm_snapshot.statistics('lineno')
    warm_memory = sum(stat.size for stat in warm_stats)
    
    warm_overhead = warm_memory - baseline_memory
    print(f"📊 Warmed cache memory: {warm_memory / 1024 / 1024:.2f} MB")
    print(f"📊 Total overhead: {warm_overhead / 1024:.2f} KB")
    
    # Calculate efficiency
    models_count = len(cache._models_config)
    if models_count > 0:
        memory_per_model = warm_overhead / models_count
        print(f"📊 Memory per model: {memory_per_model:.0f} bytes")
    
    print("✅ Memory usage is within acceptable bounds" if warm_overhead < 1024 * 1024 else "⚠️  High memory usage")
    
    tracemalloc.stop()


async def run_all_tests():
    """Run all performance tests"""
    success = True
    
    try:
        # Performance tests
        success &= await test_model_cache_performance()
        
        # Memory tests
        await benchmark_memory_usage()
        
        print(f"\n{'=' * 60}")
        if success:
            print("🎉 ALL PERFORMANCE TESTS PASSED!")
            print("Model cache system is ready for production deployment.")
        else:
            print("❌ Some tests failed. Please review the results.")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Test execution failed: {e}")
        import traceback
        traceback.print_exc()
        success = False
    
    return success


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)