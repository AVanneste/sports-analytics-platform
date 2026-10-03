"""Helpers for process-parallel backtests."""
import os


def limit_worker_threads() -> None:
    """One BLAS/OpenMP thread per worker process. Idle BLAS and OpenMP threads spin, so a pool of
    workers that each keep full-size thread pools runs many times slower than single-threaded."""
    from threadpoolctl import threadpool_limits
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[var] = "1"  # read by libraries loaded later in the worker
    threadpool_limits(1)  # libraries already loaded (numpy/scipy OpenBLAS)
