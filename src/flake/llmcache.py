"""On-disk LLM cache, so re-running the same plan costs nothing.

langchain_community ships a SQLiteCache, but it is not a dependency of this
project and BaseCache is only three methods, so this is cheaper than the import.
Keys are (prompt, llm_string), and llm_string carries the model and its
parameters -- change the prompt or the model and you get a miss, never a stale hit.
"""

import os
import sqlite3
import threading
import warnings

from langchain_core._api import LangChainBetaWarning
from langchain_core.caches import RETURN_VAL_TYPE, BaseCache
from langchain_core.globals import set_llm_cache
from langchain_core.load import dumps, loads

DEFAULT_PATH = ".llm_cache.sqlite"


class SQLiteCache(BaseCache):
    def __init__(self, path: str = DEFAULT_PATH) -> None:
        self._lock = threading.Lock()   # LangGraph may call nodes from a thread pool
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("CREATE TABLE IF NOT EXISTS cache "
                           "(prompt TEXT, llm TEXT, response TEXT, PRIMARY KEY (prompt, llm))")
        self._conn.commit()

    def lookup(self, prompt: str, llm_string: str) -> RETURN_VAL_TYPE | None:
        with self._lock:
            row = self._conn.execute("SELECT response FROM cache WHERE prompt = ? AND llm = ?",
                                     (prompt, llm_string)).fetchone()
        if row is None:
            return None
        try:
            with warnings.catch_warnings():     # loads() is flagged beta; the rows are our own
                warnings.simplefilter("ignore", LangChainBetaWarning)
                return loads(row[0], allowed_objects="core")
        except Exception:
            return None      # a row written by an older langchain; treat it as a miss

    def update(self, prompt: str, llm_string: str, return_val: RETURN_VAL_TYPE) -> None:
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO cache (prompt, llm, response) VALUES (?, ?, ?)",
                               (prompt, llm_string, dumps(list(return_val))))
            self._conn.commit()

    def clear(self, **kwargs) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM cache")
            self._conn.commit()


def install() -> str | None:
    """Turn the cache on unless LLM_CACHE=0. Returns the path in use, else None."""
    if os.environ.get("LLM_CACHE", "1").strip().lower() in ("0", "false", "no", "off"):
        return None
    path = os.environ.get("LLM_CACHE_PATH", DEFAULT_PATH)
    set_llm_cache(SQLiteCache(path))
    return path
