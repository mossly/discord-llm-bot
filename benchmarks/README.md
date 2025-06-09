# Performance Benchmarks

This folder contains performance benchmarking tools for the Discord LLM Bot.

## Files

- `test_model_performance.py` - Comprehensive performance benchmarking for the model cache system
- `test_real_world_performance.py` - Real-world performance comparison between old and new systems

## Usage

These benchmarks are used to measure and validate performance improvements, particularly for the model caching system. They are separate from the main test suite in `/tests/` as they focus on performance measurement rather than functional testing.

## Running Benchmarks

```bash
python benchmarks/test_model_performance.py
python benchmarks/test_real_world_performance.py
```