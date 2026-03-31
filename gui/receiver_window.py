"""
gui/receiver_window.py — Janela do Receptor (Modo Processos).

Lançado como subprocesso por process_window.py via:
    python main.py --receiver <porta>

Inicia um SocketServer, exibe mensagens recebidas e mostra
o próprio PID para demonstrar que é um processo separado.
"""
import tkinter as tk
import os
import time
import threading

from core.ipc import SocketServer, Message, MSG_TEXT, MSG_FILE, MSG_IMAGE
from utils.file_utils import b64_to_bytes, save_from_b64, is_image
from gui.styles import (
    BG, PANEL, BORDER, TEXT, MUTED, TEXT_DARK,
    ACCENT_GREEN, ACCENT_ORANGE, ACCENT_BLUE, ACCENT_PURPLE, ACCENT_RED,
    ACCENT_YELLOW, BTN_MUTEX_OFF,
    FONT_MONO, FONT_MONO_S, FONT_BODY, FONT_BODY_B, FONT_SMALL,
    FONT_TITLE, scrolled_text,
)

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

SAVE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "received_files")


class ReceiverWindow:
    def __init__(self, port: int = 55555):
        self.port = port
        self.server = SocketServer()
        self._image_refs = []

        self.root = tk.Tk()
        self.root.title(f"Modo Processos — Receptor  |  PID {os.getpid()}")
        self.root.configure(bg=BG)
        self.root.geometry("700x620")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._center()
        self._build()
        self._start_server()

    def _center(self):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = 700, 620
        self.root.geometry(f"{w}x{h}+{(sw-w)//2+100}+{(sh-h)//2+40}")

    # ═════════════════════════════════════════════════════════════════════════
    # Construção da interface
    # ═════════════════════════════════════════════════════════════════════════
    def _build(self):
        r = self.root

        # ── barra de título ──────────────────────────────────────────────────
        bar = tk.Frame(r, bg=PANEL, pady=8)
        bar.pack(fill="x")
        tk.Label(
            bar, text="📥  Receptor — Processo Separado",
            bg=PANEL, fg=ACCENT_GREEN, font=FONT_TITLE
        ).pack(side="left", padx=16)
        tk.Label(
            bar, text=f"PID: {os.getpid()}", bg=PANEL, fg=ACCENT_ORANGE, font=FONT_BODY_B
        ).pack(side="left", padx=8)
        tk.Frame(r, bg=BORDER, height=1).pack(fill="x")

        # ── info de processo ─────────────────────────────────────────────────
        info_bar = tk.Frame(r, bg=BG, padx=12, pady=6)
        info_bar.pack(fill="x")

        self._lbl_status = tk.Label(
            info_bar,
            text=f"○  Aguardando conexão na porta {self.port}…",
            bg=BG, fg=MUTED, font=FONT_SMALL,
        )
        self._lbl_status.pack(side="left")

        self._lbl_msg_count = tk.Label(
            info_bar, text="Mensagens: 0",
            bg=BG, fg=MUTED, font=FONT_SMALL
        )
        self._lbl_msg_count.pack(side="right")

        # ── mensagens recebidas ──────────────────────────────────────────────
        msg_frame = tk.LabelFrame(
            r, text="  Mensagens Recebidas  ", fg=ACCENT_GREEN,
            bg=BG, font=FONT_BODY_B, bd=1, relief="solid"
        )
        msg_frame.pack(fill="both", expand=True, padx=8, pady=4)

        self._msg_box = scrolled_text(msg_frame, height=18)
        self._msg_box.pack(fill="both", expand=True, padx=4, pady=4)
        self._msg_box.tag_config("header", foreground=ACCENT_GREEN,  font=FONT_BODY_B)
        self._msg_box.tag_config("meta",   foreground=MUTED,         font=FONT_SMALL)
        self._msg_box.tag_config("body",   foreground=TEXT,          font=FONT_MONO)
        self._msg_box.tag_config("warn",   foreground=ACCENT_YELLOW, font=FONT_MONO_S)
        self._msg_box.tag_config("file",   foreground=ACCENT_BLUE,   font=FONT_MONO_S)

        # ── imagem ───────────────────────────────────────────────────────────
        self._img_frame = tk.LabelFrame(
            r, text="  Última Imagem Recebida  ", fg=ACCENT_BLUE,
            bg=BG, font=FONT_BODY_B, bd=1, relief="solid"
        )
        self._img_frame.pack(fill="x", padx=8, pady=(0, 4))
        self._img_label = tk.Label(self._img_frame, bg=BG,
                                   text="(nenhuma imagem ainda)", fg=MUTED, font=FONT_SMALL)
        self._img_label.pack(pady=6)

        # ── log ──────────────────────────────────────────────────────────────
        lf = tk.LabelFrame(
            r, text="  Log  ", fg=ACCENT_PURPLE,
            bg=BG, font=FONT_BODY_B, bd=1, relief="solid"
        )
        lf.pack(fill="x", padx=8, pady=(0, 6))
        self._log = scrolled_text(lf, height=4)
        self._log.pack(fill="x", padx=4, pady=4)

        # botão limpar
        tk.Button(
            r, text="Limpar tudo", command=self._clear,
            bg=PANEL, fg=MUTED, font=FONT_SMALL, relief="flat", cursor="hand2"
        ).pack(anchor="e", padx=12, pady=(0, 4))

    # ═════════════════════════════════════════════════════════════════════════
    # Servidor de socket
    # ═════════════════════════════════════════════════════════════════════════
    def _start_server(self):
        self.server.on_message    = self._on_message_received
        self.server.on_connect    = self._on_client_connected
        self.server.on_disconnect = self._on_client_disconnected

        ok = self.server.start(self.port)
        if ok:
            self._log_event(f"[Servidor] Escutando na porta {self.port}")
        else:
            self._log_event(f"[Servidor] ERRO ao iniciar na porta {self.port}")
            self._lbl_status.config(text="ERRO ao iniciar servidor", fg=ACCENT_RED)

    def _on_client_connected(self):
        self.root.after(
            0,
            lambda: (
                self._lbl_status.config(
                    text=f"● Remetente conectado  |  porta {self.port}",
                    fg=ACCENT_GREEN,
                ),
                self._log_event("[Servidor] Remetente conectado"),
            ),
        )

    def _on_client_disconnected(self):
        self.root.after(
            0,
            lambda: (
                self._lbl_status.config(
                    text=f"○ Remetente desconectado  |  porta {self.port}",
                    fg=MUTED,
                ),
                self._log_event("[Servidor] Remetente desconectado"),
            ),
        )

    def _on_message_received(self, msg: Message):
        """Chamado pela thread do servidor — agenda atualização de GUI."""
        self.root.after(0, lambda m=msg: self._display_message(m))

    # ═════════════════════════════════════════════════════════════════════════
    # Exibir mensagem
    # ═════════════════════════════════════════════════════════════════════════
    _msg_count = 0

    def _display_message(self, msg: Message):
        self._msg_count += 1
        self._lbl_msg_count.config(text=f"Mensagens: {self._msg_count}")

        box = self._msg_box
        box.config(state="normal")

        ts = time.strftime("%H:%M:%S", time.localtime(msg.timestamp))
        box.insert("end", f"\n[{ts}] De: {msg.sender}\n", "header")
        box.insert("end", f"Tipo: {msg.type}  |  PID receptor: {os.getpid()}\n", "meta")

        if msg.type == MSG_TEXT:
            box.insert("end", msg.content + "\n", "body")

        elif msg.type == MSG_IMAGE:
            box.insert("end", f"Imagem: {msg.filename}\n", "file")
            self._show_image(msg)
            # salvar
            path = save_from_b64(msg.content, msg.filename, SAVE_DIR)
            box.insert("end", f"Salva em: {path}\n", "meta")

        elif msg.type == MSG_FILE:
            size_kb = len(msg.content) * 3 // 4 // 1024
            box.insert("end", f"Arquivo: {msg.filename}  (~{size_kb} KB)\n", "file")
            path = save_from_b64(msg.content, msg.filename, SAVE_DIR)
            box.insert("end", f"Salvo em: {path}\n", "meta")

        box.insert("end", "─" * 42 + "\n", "meta")
        box.config(state="disabled")
        box.see("end")

        self._log_event(f"[Recebido] tipo={msg.type}  de={msg.sender}")

    def _show_image(self, msg: Message):
        if not HAS_PIL:
            return
        try:
            import io
            data = b64_to_bytes(msg.content)
            img = Image.open(io.BytesIO(data))
            img.thumbnail((300, 200))
            photo = ImageTk.PhotoImage(img)
            self._image_refs.append(photo)
            self._img_label.config(image=photo, text="")
        except Exception as exc:
            self._log_event(f"[Imagem] Erro ao exibir: {exc}")

    # ═════════════════════════════════════════════════════════════════════════
    def _clear(self):
        self._msg_box.config(state="normal")
        self._msg_box.delete("1.0", "end")
        self._msg_box.config(state="disabled")
        self._img_label.config(image="", text="(nenhuma imagem ainda)")
        self._msg_count = 0
        self._lbl_msg_count.config(text="Mensagens: 0")

    def _log_event(self, text: str):
        ts = time.strftime("%H:%M:%S")
        self._log.config(state="normal")
        self._log.insert("end", f"[{ts}] {text}\n")
        self._log.config(state="disabled")
        self._log.see("end")

    def _on_close(self):
        self.server.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
