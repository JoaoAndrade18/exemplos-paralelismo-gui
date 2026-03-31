"""
core/mutex_manager.py — Demonstração de Mutex / Race Condition.

MutexManager gerencia um Lock compartilhado e expõe métodos para:
  - ativar / desativar o mutex em tempo real
  - rodar uma demonstração de condição de corrida com N threads

A demonstração usa um contador compartilhado que N threads incrementam
M vezes cada.  Sem mutex o resultado final costuma ser < N*M (race).
Com mutex o resultado é sempre exatamente N*M (correto).
"""
import threading
import time
from typing import Callable, Optional


class MutexManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._enabled = True          # mutex ativo por padrão

        # estado do contador compartilhado
        self.counter: int = 0
        self.expected: int = 0
        self.running: bool = False

    # ── controle do mutex ────────────────────────────────────────────────────
    @property
    def enabled(self) -> bool:
        return self._enabled

    def toggle(self):
        self._enabled = not self._enabled

    def set_enabled(self, value: bool):
        self._enabled = value

    # ── adquirir / liberar manualmente ──────────────────────────────────────
    def acquire(self) -> bool:
        if self._enabled:
            return self._lock.acquire()
        return True   # sem bloqueio

    def release(self):
        if self._enabled:
            try:
                self._lock.release()
            except RuntimeError:
                pass   # já liberado

    # ── demonstração de condição de corrida ─────────────────────────────────
    def run_demo(
        self,
        n_threads: int = 5,
        increments: int = 200,
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_done: Optional[Callable[[int, int, float], None]] = None,
    ):
        """
        Cria n_threads threads que incrementam `self.counter` `increments`
        vezes cada.  Chama on_progress(current, expected) durante a execução
        e on_done(final, expected, elapsed) ao terminar.
        """
        if self.running:
            return

        self.counter = 0
        self.expected = n_threads * increments
        self.running = True
        start = time.perf_counter()

        def worker():
            for _ in range(increments):
                if self._enabled:
                    with self._lock:
                        val = self.counter
                        time.sleep(0)          # yield para aumentar disputa
                        self.counter = val + 1
                else:
                    # leitura + escrita sem proteção → race condition
                    val = self.counter
                    time.sleep(0)
                    self.counter = val + 1

        threads = [
            threading.Thread(target=worker, daemon=True, name=f"Worker-{i+1}")
            for i in range(n_threads)
        ]

        def _monitor():
            for t in threads:
                t.start()
            # progresso
            while any(t.is_alive() for t in threads):
                if on_progress:
                    on_progress(self.counter, self.expected)
                time.sleep(0.05)
            for t in threads:
                t.join()
            elapsed = time.perf_counter() - start
            self.running = False
            if on_done:
                on_done(self.counter, self.expected, elapsed)

        threading.Thread(target=_monitor, daemon=True, name="MutexMonitor").start()
