"""
core/ipc.py — Comunicação entre threads e entre processos.

  ThreadQueue  : fila thread-safe (queue.Queue) para o Modo Threads.
  SocketServer : servidor TCP para receber mensagens de outro processo.
  SocketClient : cliente TCP para enviar mensagens a outro processo.
  Message      : estrutura de dados trocada em ambos os modos.
"""
import queue
import json
import socket
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable


# ── Tipos de mensagem ────────────────────────────────────────────────────────
MSG_TEXT    = "text"
MSG_FILE    = "file"
MSG_IMAGE   = "image"
MSG_CONTROL = "control"   # uso interno (handshake, ping…)


# ── Estrutura de mensagem ────────────────────────────────────────────────────
@dataclass
class Message:
    type: str               # MSG_TEXT / MSG_FILE / MSG_IMAGE / MSG_CONTROL
    content: str            # texto ou dados em base64
    filename: str  = ""     # nome do arquivo (tipo file/image)
    sender: str    = ""     # identificação do remetente
    timestamp: float = field(default_factory=time.time)
    msg_id: str    = field(default_factory=lambda: str(id(object())))  # ID único

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False) + "\n"

    @classmethod
    def from_json(cls, raw: str) -> "Message":
        return cls(**json.loads(raw.strip()))


# ── Fila para threads ────────────────────────────────────────────────────────
class ThreadQueue:
    """Fila thread-safe com estatísticas simples."""

    def __init__(self, maxsize: int = 200):
        self._q = queue.Queue(maxsize=maxsize)
        self._lock = threading.Lock()
        self._sent = 0
        self._received = 0

    def put(self, msg: Message, block: bool = True, timeout: float = None):
        self._q.put(msg, block=block, timeout=timeout)
        with self._lock:
            self._sent += 1

    def get(self, timeout: float = 0.05) -> Optional[Message]:
        try:
            msg = self._q.get(timeout=timeout)
            with self._lock:
                self._received += 1
            return msg
        except queue.Empty:
            return None

    def empty(self) -> bool:
        return self._q.empty()

    def qsize(self) -> int:
        return self._q.qsize()

    @property
    def stats(self):
        with self._lock:
            return {"sent": self._sent, "received": self._received}


# ── Servidor de socket (receptor no Modo Processos) ─────────────────────────
class SocketServer:
    """Servidor TCP que escuta mensagens de outro processo."""

    def __init__(self):
        self._srv: Optional[socket.socket] = None
        self._cli: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.on_message: Optional[Callable[[Message], None]] = None
        self.on_connect: Optional[Callable[[], None]] = None
        self.on_disconnect: Optional[Callable[[], None]] = None
        self.port: Optional[int] = None

    def start(self, port: int) -> bool:
        try:
            self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._srv.bind(("localhost", port))
            self._srv.listen(1)
            self._srv.settimeout(1.0)
            self.port = port
            self._running = True
            self._thread = threading.Thread(
                target=self._accept_loop, daemon=True, name="SocketServer"
            )
            self._thread.start()
            return True
        except Exception as exc:
            print(f"[SocketServer] Erro ao iniciar: {exc}")
            return False

    def _accept_loop(self):
        while self._running:
            try:
                cli, _ = self._srv.accept()
                self._cli = cli
                if self.on_connect:
                    self.on_connect()
                self._recv_loop(cli)
                if self.on_disconnect:
                    self.on_disconnect()
            except socket.timeout:
                continue
            except OSError:
                break

    def _recv_loop(self, sock: socket.socket):
        buf = ""
        while self._running:
            try:
                data = sock.recv(65536).decode("utf-8", errors="replace")
                if not data:
                    break
                buf += data
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    if line.strip():
                        try:
                            msg = Message.from_json(line)
                            if self.on_message:
                                self.on_message(msg)
                        except Exception as e:
                            print(f"[SocketServer] parse: {e}")
            except Exception as exc:
                if self._running:
                    print(f"[SocketServer] recv: {exc}")
                break

    def stop(self):
        self._running = False
        for s in (self._cli, self._srv):
            if s:
                try:
                    s.close()
                except Exception:
                    pass


# ── Cliente de socket (remetente no Modo Processos) ─────────────────────────
class SocketClient:
    """Cliente TCP que envia mensagens para o servidor receptor."""

    def __init__(self):
        self._sock: Optional[socket.socket] = None
        self._connected = False

    def connect(self, host: str, port: int, retries: int = 15) -> bool:
        for _ in range(retries):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2.0)
                s.connect((host, port))
                self._sock = s
                self._connected = True
                return True
            except Exception:
                time.sleep(0.4)
        return False

    def send(self, msg: Message) -> bool:
        if not self._connected or self._sock is None:
            return False
        try:
            self._sock.sendall(msg.to_json().encode("utf-8"))
            return True
        except Exception as exc:
            print(f"[SocketClient] send: {exc}")
            self._connected = False
            return False

    def close(self):
        self._connected = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass

    @property
    def connected(self) -> bool:
        return self._connected
