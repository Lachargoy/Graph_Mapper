from __future__ import annotations
#bootstrap/timing.py
import time
from typing import Callable, TypeVar

T = TypeVar("T")


def ts() -> str:
    return time.strftime("%H:%M:%S")


def timed(label: str, fn: Callable[[], T]) -> T:
    start = time.perf_counter()
    print(f"[{ts()}] [graph_mapper.timing] START {label}", flush=True)
    try:
        result = fn()
        elapsed = time.perf_counter() - start
        print(
            f"[{ts()}] [graph_mapper.timing] END {label} elapsed={elapsed:.3f}s",
            flush=True,
        )
        return result
    except Exception as exc:
        elapsed = time.perf_counter() - start
        print(
            f"[{ts()}] [graph_mapper.timing] FAIL {label} elapsed={elapsed:.3f}s exc={exc!r}",
            flush=True,
        )
        raise