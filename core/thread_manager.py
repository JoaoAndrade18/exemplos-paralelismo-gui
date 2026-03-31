"""
core/thread_manager.py — Gerencia threads de trabalho.

ThreadManager mantém um registro de threads criadas, seu estado e
permite inspecionar PID / TID para fins didáticos.
"""
import threading
import os
import time
from typing import Callable, List, Dict, Any, Optional


class ManagedThread:
    def __init__(self, thread: threading.Thread, label: str):
        self.thread = thread
        self.label = label
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self._tid: Optional[int] = None

    def start(self):
        self.started_at = time.time()
        self.thread.start()

    @property
    def alive(self) -> bool:
        return self.thread.is_alive()

    @property
    def ident(self) -> Optional[int]:
        return self.thread.ident

    def info(self) -> Dict[str, Any]:
        elapsed = None
        if self.started_at:
            end = self.finished_at or time.time()
            elapsed = round(end - self.started_at, 3)
        return {
            "label":   self.label,
            "name":    self.thread.name,
            "ident":   self.thread.ident,
            "alive":   self.alive,
            "daemon":  self.thread.daemon,
            "elapsed": elapsed,
        }


class ThreadManager:
    def __init__(self):
        self._threads: List[ManagedThread] = []
        self._lock = threading.Lock()

    @property
    def pid(self) -> int:
        return os.getpid()

    def create(
        self,
        target: Callable,
        name: str = "",
        label: str = "",
        daemon: bool = True,
        args: tuple = (),
        kwargs: dict = None,
    ) -> ManagedThread:
        t = threading.Thread(
            target=target,
            name=name or f"Thread-{len(self._threads)+1}",
            daemon=daemon,
            args=args,
            kwargs=kwargs or {},
        )
        mt = ManagedThread(t, label or t.name)
        with self._lock:
            self._threads.append(mt)
        return mt

    def start(self, mt: ManagedThread):
        mt.start()

    def stop_all(self):
        # Threads daemon morrem quando o processo principal termina.
        # Aqui apenas limpamos as que já terminaram.
        with self._lock:
            self._threads = [t for t in self._threads if t.alive]

    def status(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [t.info() for t in self._threads]

    def active_count(self) -> int:
        return sum(1 for t in self._threads if t.alive)

    def all_threads_info(self) -> List[Dict[str, Any]]:
        """Retorna info de TODAS as threads do processo (inclui as do sistema)."""
        return [
            {"name": t.name, "ident": t.ident, "daemon": t.daemon, "alive": t.is_alive()}
            for t in threading.enumerate()
        ]
