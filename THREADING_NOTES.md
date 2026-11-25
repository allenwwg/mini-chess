"""
Multi-Threading Implementation Note:

Due to Python's Global Interpreter Lock (GIL), pure threading won't achieve 
4x speedup on 4 cores for CPU-bound tasks. However, multi-threading still provides benefits:

1. Shared transposition table allows threads to learn from each other
2. Parallel search of different depths helps find good moves faster
3. Expect 30-50% performance improvement (not 4x)

For true multi-core parallelism (4x speedup), would need to use multiprocessing
instead of threading, but that's more complex and will be a future enhancement.

Current implementation: Lazy SMP with helper threads searching at varied depths.
"""
