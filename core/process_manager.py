"""
core/process_manager.py — Gerencia o subprocesso receptor.

ProcessManager lança o receiver_window como subprocesso separado
(processo filho com PID diferente = núcleo/memória independente)
e expõe utilitários para verificar seu estado.
"""
import subprocess
import sys
import os
import time
from typing import Optional


class ProcessManager:
    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None
        self._port: Optional[int] = None
        self._started_at: Optional[float] = None

    def spawn_receiver(self, port: int) -> bool:
        """
        Lança  `python main.py --receiver <port>`  como processo filho.
        Retorna True se o processo foi criado com sucesso.
        """
        if self._proc and self._proc.poll() is None:
            return False   # já está rodando

        main_script = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "main.py",
        )
        try:
            self._proc = subprocess.Popen(
                [sys.executable, main_script, "--receiver", str(port)],
                creationflags=subprocess.CREATE_NEW_CONSOLE
                if sys.platform == "win32"
                else 0,
            )
            self._port = port
            self._started_at = time.time()
            return True
        except Exception as exc:
            print(f"[ProcessManager] Erro ao lançar receptor: {exc}")
            return False

    def terminate(self):
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None

    @property
    def receiver_pid(self) -> Optional[int]:
        if self._proc:
            return self._proc.pid
        return None

    @property
    def receiver_alive(self) -> bool:
        if self._proc is None:
            return False
        return self._proc.poll() is None

    def status(self) -> dict:
        return {
            "pid":       self.receiver_pid,
            "alive":     self.receiver_alive,
            "port":      self._port,
            "uptime":    round(time.time() - self._started_at, 1)
            if self._started_at and self.receiver_alive
            else None,
        }

    @staticmethod
    def current_pid() -> int:
        return os.getpid()
