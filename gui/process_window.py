"""
gui/process_window.py — Janela do Remetente no Modo Processos.

Este processo (remetente) lança um subprocesso separado (receptor)
e se comunica com ele via socket TCP.  Dois PIDs distintos = dois
processos = potencialmente dois núcleos de CPU diferentes.
"""
import tkinter as tk
from tkinter import filedialog
import threading
import os
import time

from core.ipc import SocketClient, Message, MSG_TEXT, MSG_FILE, MSG_IMAGE
from core.process_manager import ProcessManager
from core.mutex_manager import MutexManager
from utils.file_utils import read_as_b64, is_image, file_info
from gui.styles import (
    BG, PANEL, BORDER, TEXT, MUTED, TEXT_DARK,
    ACCENT_BLUE, ACCENT_GREEN, ACCENT_ORANGE, ACCENT_PURPLE,
    ACCENT_RED, ACCENT_YELLOW, BTN_MUTEX_ON, BTN_MUTEX_OFF,
    FONT_MONO, FONT_MONO_S, FONT_BODY, FONT_BODY_B, FONT_SMALL,
    FONT_TITLE, scrolled_text,
)

DEFAULT_PORT = 55555


class ProcessWindow:
    POLL_MS = 1000

    def __init__(self, parent: tk.Tk):
        self.parent = parent
        self.win = tk.Toplevel(parent)
        self.win.title("Modo Processos — Remetente")
        self.win.configure(bg=BG)
        self.win.geometry("900x680")
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

        self.pm     = ProcessManager()
        self.client = SocketClient()
        self.mutex  = MutexManager()
        self._running = True
        self._selected_file: str = ""

        self._build()
        self._poll_status()

    # ═════════════════════════════════════════════════════════════════════════
    # Construção da interface
    # ═════════════════════════════════════════════════════════════════════════
    def _build(self):
        w = self.win

        # ── barra de título ──────────────────────────────────────────────────
        bar = tk.Frame(w, bg=PANEL, pady=8)
        bar.pack(fill="x")
        tk.Label(bar, text="⚙️  Modo Processos — Remetente",
                 bg=PANEL, fg=ACCENT_ORANGE, font=FONT_TITLE).pack(side="left", padx=16)
        self._lbl_my_pid = tk.Label(
            bar, text=f"PID: {os.getpid()}", bg=PANEL, fg=MUTED, font=FONT_SMALL
        )
        self._lbl_my_pid.pack(side="left", padx=8)
        tk.Frame(w, bg=BORDER, height=1).pack(fill="x")

        # ── corpo ────────────────────────────────────────────────────────────
        body = tk.Frame(w, bg=BG)
        body.pack(fill="both", expand=True, padx=8, pady=6)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        self._build_sender(body)
        self._build_control(body)

        # ── log ──────────────────────────────────────────────────────────────
        lf = tk.LabelFrame(w, text="  Log de Eventos  ", fg=ACCENT_PURPLE,
                           bg=BG, font=FONT_BODY_B, bd=1, relief="solid")
        lf.pack(fill="x", padx=8, pady=(0, 6))
        self._log = scrolled_text(lf, height=5)
        self._log.pack(fill="x", padx=4, pady=4)

    # ── painel Remetente ─────────────────────────────────────────────────────
    def _build_sender(self, parent):
        frame = tk.LabelFrame(
            parent, text="  📤  Remetente (este processo)  ",
            fg=ACCENT_ORANGE, bg=PANEL, font=FONT_BODY_B, bd=1, relief="solid"
        )
        frame.grid(row=0, column=0, sticky="nsew", padx=4)

        inner = tk.Frame(frame, bg=PANEL, padx=10, pady=10)
        inner.pack(fill="both", expand=True)

        # texto
        tk.Label(inner, text="Mensagem de texto:", bg=PANEL,
                 fg=TEXT, font=FONT_BODY).pack(anchor="w", pady=(0, 2))
        self._txt_input = tk.Text(inner, height=5, bg=BG, fg=TEXT,
                                  insertbackground=TEXT, font=FONT_MONO,
                                  relief="flat", bd=4, wrap="word")
        self._txt_input.pack(fill="x")
        self._txt_input.insert("1.0", "Olá, processo receptor!")

        self._btn_send_txt = tk.Button(
            inner, text="Enviar Texto  →", command=self._send_text,
            bg=ACCENT_ORANGE, fg=TEXT_DARK, font=FONT_BODY_B,
            relief="flat", padx=8, pady=5, cursor="hand2", state="disabled",
        )
        self._btn_send_txt.pack(fill="x", pady=(4, 0))

        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=10)

        # arquivo
        tk.Label(inner, text="Arquivo / Imagem:", bg=PANEL,
                 fg=TEXT, font=FONT_BODY).pack(anchor="w")
        self._lbl_file = tk.Label(
            inner, text="(nenhum selecionado)", bg=PANEL, fg=MUTED, font=FONT_SMALL
        )
        self._lbl_file.pack(anchor="w", pady=(2, 4))

        tk.Button(
            inner, text="Selecionar Arquivo  📁", command=self._pick_file,
            bg=PANEL, fg=ACCENT_ORANGE, font=FONT_BODY,
            relief="flat", cursor="hand2", bd=1, highlightbackground=BORDER,
        ).pack(fill="x", pady=2)

        self._btn_send_file = tk.Button(
            inner, text="Enviar Arquivo  →", command=self._send_file,
            bg=ACCENT_ORANGE, fg=TEXT_DARK, font=FONT_BODY_B,
            relief="flat", padx=8, pady=5, cursor="hand2", state="disabled",
        )
        self._btn_send_file.pack(fill="x")

        # info de transferência
        self._lbl_transfer = tk.Label(
            inner, text="", bg=PANEL, fg=ACCENT_GREEN, font=FONT_SMALL
        )
        self._lbl_transfer.pack(anchor="w", pady=(6, 0))

    # ── painel de controle ───────────────────────────────────────────────────
    def _build_control(self, parent):
        frame = tk.LabelFrame(
            parent, text="  🔧  Controle  ",
            fg=ACCENT_PURPLE, bg=PANEL, font=FONT_BODY_B, bd=1, relief="solid"
        )
        frame.grid(row=0, column=1, sticky="nsew", padx=4)

        inner = tk.Frame(frame, bg=PANEL, padx=12, pady=10)
        inner.pack(fill="both", expand=True)

        # ── processo receptor ────────────────────────────────────────────────
        tk.Label(inner, text="Processo Receptor:", bg=PANEL,
                 fg=TEXT, font=FONT_BODY_B).pack(anchor="w")

        port_row = tk.Frame(inner, bg=PANEL)
        port_row.pack(fill="x", pady=(4, 8))
        tk.Label(port_row, text="Porta:", bg=PANEL, fg=MUTED, font=FONT_SMALL).pack(side="left")
        self._entry_port = tk.Entry(port_row, width=7, bg=BG, fg=TEXT,
                                    insertbackground=TEXT, font=FONT_MONO, relief="flat", bd=4)
        self._entry_port.pack(side="left", padx=6)
        self._entry_port.insert(0, str(DEFAULT_PORT))

        self._btn_start = tk.Button(
            inner, text="▶  Iniciar Receptor", command=self._start_receiver,
            bg=ACCENT_GREEN, fg=TEXT_DARK, font=FONT_BODY_B,
            relief="flat", padx=8, pady=5, cursor="hand2",
        )
        self._btn_start.pack(fill="x")

        self._btn_stop = tk.Button(
            inner, text="■  Parar Receptor", command=self._stop_receiver,
            bg=ACCENT_RED, fg=TEXT_DARK, font=FONT_BODY_B,
            relief="flat", padx=8, pady=5, cursor="hand2", state="disabled",
        )
        self._btn_stop.pack(fill="x", pady=(4, 0))

        # status
        self._lbl_recv_status = tk.Label(
            inner, text="○  Receptor não iniciado",
            bg=PANEL, fg=MUTED, font=FONT_SMALL
        )
        self._lbl_recv_status.pack(anchor="w", pady=(6, 2))

        self._lbl_recv_pid = tk.Label(
            inner, text="PID Receptor: —",
            bg=PANEL, fg=MUTED, font=FONT_SMALL
        )
        self._lbl_recv_pid.pack(anchor="w")

        self._lbl_recv_uptime = tk.Label(
            inner, text="",
            bg=PANEL, fg=MUTED, font=FONT_SMALL
        )
        self._lbl_recv_uptime.pack(anchor="w")

        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=10)

        # ── mutex ────────────────────────────────────────────────────────────
        tk.Label(inner, text="Mutex (Lock):", bg=PANEL,
                 fg=TEXT, font=FONT_BODY_B).pack(anchor="w")

        self._lbl_mutex = tk.Label(
            inner, text="● MUTEX ON", bg=PANEL, fg=BTN_MUTEX_ON, font=FONT_BODY_B
        )
        self._lbl_mutex.pack(anchor="w", pady=(2, 4))

        self._btn_mutex = tk.Button(
            inner, text="Desativar Mutex", command=self._toggle_mutex,
            bg=BTN_MUTEX_OFF, fg=TEXT_DARK, font=FONT_BODY_B,
            relief="flat", padx=8, pady=4, cursor="hand2",
        )
        self._btn_mutex.pack(fill="x")

        tk.Label(
            inner,
            text=(
                "Com mutex ativo, apenas uma\n"
                "thread envia por vez (lock).\n"
                "Desativado: envios concorrentes\n"
                "sem proteção."
            ),
            bg=PANEL, fg=MUTED, font=FONT_SMALL, justify="left",
        ).pack(anchor="w", pady=(4, 0))

        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=10)

        # ── info de PIDs ─────────────────────────────────────────────────────
        tk.Label(inner, text="Informações de Processo:", bg=PANEL,
                 fg=TEXT, font=FONT_BODY_B).pack(anchor="w")
        info_txt = (
            f"PID Remetente : {os.getpid()}\n"
            f"Processos distintos têm\n"
            f"memória separada e podem\n"
            f"rodar em núcleos diferentes."
        )
        tk.Label(inner, text=info_txt, bg=PANEL, fg=MUTED,
                 font=FONT_SMALL, justify="left").pack(anchor="w", pady=(4, 0))

    # ═════════════════════════════════════════════════════════════════════════
    # Controle do receptor
    # ═════════════════════════════════════════════════════════════════════════
    def _start_receiver(self):
        try:
            port = int(self._entry_port.get())
        except ValueError:
            self._log_event("[Erro] Porta inválida")
            return

        self._log_event(f"[Processo] Lançando receptor na porta {port}…")
        ok = self.pm.spawn_receiver(port)
        if not ok:
            self._log_event("[Erro] Não foi possível lançar o receptor")
            return

        self._btn_start.config(state="disabled")
        self._btn_stop.config(state="normal")
        self._log_event(f"[Processo] Receptor iniciado — PID={self.pm.receiver_pid}")

        # Conecta o cliente em thread separada (aguarda o servidor subir)
        def _connect():
            self._log_event("[Socket] Conectando ao receptor…")
            ok = self.client.connect("localhost", port, retries=20)
            if ok:
                self.win.after(0, self._on_connected)
            else:
                self.win.after(0, lambda: self._log_event("[Socket] Falha ao conectar"))

        threading.Thread(target=_connect, daemon=True).start()

    def _on_connected(self):
        self._log_event("[Socket] Conectado ao receptor!")
        self._btn_send_txt.config(state="normal")
        self._btn_send_file.config(
            state="normal" if self._selected_file else "disabled"
        )

    def _stop_receiver(self):
        self.client.close()
        self.pm.terminate()
        self._btn_start.config(state="normal")
        self._btn_stop.config(state="disabled")
        self._btn_send_txt.config(state="disabled")
        self._btn_send_file.config(state="disabled")
        self._lbl_recv_status.config(text="○  Receptor encerrado", fg=MUTED)
        self._lbl_recv_pid.config(text="PID Receptor: —")
        self._log_event("[Processo] Receptor encerrado")

    # ═════════════════════════════════════════════════════════════════════════
    # Envio de mensagens
    # ═════════════════════════════════════════════════════════════════════════
    def _send_text(self):
        text = self._txt_input.get("1.0", "end").strip()
        if not text:
            return

        def _do():
            self.mutex.acquire()
            try:
                msg = Message(
                    type=MSG_TEXT,
                    content=text,
                    sender=f"Processo-{os.getpid()}",
                )
                ok = self.client.send(msg)
                status = "enviado" if ok else "FALHOU"
                self.win.after(
                    0,
                    lambda: (
                        self._lbl_transfer.config(
                            text=f"Texto {status}", fg=ACCENT_GREEN if ok else ACCENT_RED
                        ),
                        self._log_event(f"[Remetente] Texto {status} — PID={os.getpid()}"),
                    ),
                )
            finally:
                self.mutex.release()

        threading.Thread(target=_do, daemon=True).start()

    def _pick_file(self):
        path = filedialog.askopenfilename(
            title="Selecionar arquivo",
            filetypes=[
                ("Todos os arquivos", "*.*"),
                ("Imagens", "*.png *.jpg *.jpeg *.gif *.bmp"),
                ("Documentos", "*.pdf *.txt *.docx"),
            ],
        )
        if path:
            self._selected_file = path
            info = file_info(path)
            self._lbl_file.config(
                text=f"{info['name']}  ({info['size_str']})", fg=TEXT
            )
            if self.client.connected:
                self._btn_send_file.config(state="normal")

    def _send_file(self):
        if not self._selected_file:
            return
        path = self._selected_file
        finfo = file_info(path)
        msg_type = MSG_IMAGE if is_image(path) else MSG_FILE

        def _do():
            self.mutex.acquire()
            try:
                b64 = read_as_b64(path)
                msg = Message(
                    type=msg_type,
                    content=b64,
                    filename=finfo["name"],
                    sender=f"Processo-{os.getpid()}",
                )
                ok = self.client.send(msg)
                kind = "Imagem" if msg_type == MSG_IMAGE else "Arquivo"
                status = "enviado" if ok else "FALHOU"
                self.win.after(
                    0,
                    lambda: (
                        self._lbl_transfer.config(
                            text=f"{kind} '{finfo['name']}' {status}",
                            fg=ACCENT_GREEN if ok else ACCENT_RED,
                        ),
                        self._log_event(
                            f"[Remetente] {kind} {status}: {finfo['name']} "
                            f"({finfo['size_str']}) — PID={os.getpid()}"
                        ),
                    ),
                )
            finally:
                self.mutex.release()

        threading.Thread(target=_do, daemon=True, name="FileSender").start()

    # ═════════════════════════════════════════════════════════════════════════
    # Mutex
    # ═════════════════════════════════════════════════════════════════════════
    def _toggle_mutex(self):
        self.mutex.toggle()
        if self.mutex.enabled:
            self._lbl_mutex.config(text="● MUTEX ON", fg=BTN_MUTEX_ON)
            self._btn_mutex.config(text="Desativar Mutex", bg=BTN_MUTEX_OFF)
            self._log_event("[Mutex] Ativado")
        else:
            self._lbl_mutex.config(text="○ MUTEX OFF", fg=BTN_MUTEX_OFF)
            self._btn_mutex.config(text="Ativar Mutex", bg=BTN_MUTEX_ON)
            self._log_event("[Mutex] Desativado — envios sem proteção!")

    # ═════════════════════════════════════════════════════════════════════════
    # Polling de status do receptor
    # ═════════════════════════════════════════════════════════════════════════
    def _poll_status(self):
        if not self._running:
            return
        st = self.pm.status()
        if st["alive"]:
            self._lbl_recv_status.config(
                text=f"● Receptor rodando", fg=ACCENT_GREEN
            )
            self._lbl_recv_pid.config(text=f"PID Receptor: {st['pid']}", fg=TEXT)
            if st["uptime"] is not None:
                self._lbl_recv_uptime.config(
                    text=f"Uptime: {st['uptime']}s", fg=MUTED
                )
        elif st["pid"] is not None:
            self._lbl_recv_status.config(text="○ Receptor encerrado", fg=ACCENT_RED)
            self._btn_start.config(state="normal")
            self._btn_stop.config(state="disabled")
        self.win.after(self.POLL_MS, self._poll_status)

    # ═════════════════════════════════════════════════════════════════════════
    def _log_event(self, text: str):
        ts = time.strftime("%H:%M:%S")
        self._log.config(state="normal")
        self._log.insert("end", f"[{ts}] {text}\n")
        self._log.config(state="disabled")
        self._log.see("end")

    def _on_close(self):
        self._running = False
        self.client.close()
        self.pm.terminate()
        self.win.destroy()

    def show(self):
        self.win.focus_force()
