"""
gui/thread_window.py — Modo Threads.

Conceitos demonstrados:
  • Múltiplos receptores, cada um rodando em sua própria thread
  • Fila (ThreadQueue) por receptor — mensagens acumulam visualmente
  • Delay configurável por receptor — simula processamento real
  • ACK de confirmação por mensagem (threading.Event)
  • Modo SÍNCRONO  (paralelismo OFF) — remetente bloqueia até receber ACK
  • Modo PARALELO  (paralelismo ON)  — uma thread por mensagem; remetente
    livre imediatamente; ACKs chegam conforme receptores terminam
  • Monitor ao vivo: threads ativas, stats, estado das filas
"""
import tkinter as tk
from tkinter import filedialog, ttk
import threading
import time
import uuid
import os

from core.ipc import ThreadQueue, Message, MSG_TEXT, MSG_FILE, MSG_IMAGE
from core.thread_manager import ThreadManager
from utils.file_utils import read_as_b64, is_image, file_info, b64_to_bytes
from gui.styles import (
    BG, PANEL, BORDER, TEXT, MUTED, TEXT_DARK,
    ACCENT_BLUE, ACCENT_GREEN, ACCENT_ORANGE, ACCENT_PURPLE,
    ACCENT_RED, ACCENT_YELLOW, BTN_MUTEX_ON, BTN_MUTEX_OFF,
    FONT_MONO, FONT_MONO_S, FONT_BODY, FONT_BODY_B, FONT_H2,
    FONT_TITLE, FONT_SMALL, scrolled_text,
)

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ─────────────────────────────────────────────────────────────────────────────
# Painel de cada receptor independente
# ─────────────────────────────────────────────────────────────────────────────
class ReceiverPanel:
    """
    Um receptor = uma thread de trabalho + fila própria + painel visual.
    Cada mensagem recebida é "processada" com um delay configurável,
    então o ACK é disparado via threading.Event.
    """

    def __init__(self, parent, index: int, ack_registry: dict, log_fn, window_ref):
        self.index        = index
        self.queue        = ThreadQueue(maxsize=500)
        self.ack_registry = ack_registry   # msg_id → threading.Event (compartilhado)
        self._log         = log_fn
        self._win         = window_ref
        self._running     = True
        self._received    = 0
        self._processing  = False
        self._current_msg_id: str = ""
        self._image_refs  = []

        # variáveis tkinter — criadas antes da thread
        self._delay_var   = tk.DoubleVar(value=1.5)
        self._queue_count = tk.IntVar(value=0)
        self._status_var  = tk.StringVar(value="○  Aguardando…")

        self._build(parent)

        self._thread = threading.Thread(
            target=self._worker,
            daemon=True,
            name=f"Receiver-{index}",
        )
        self._thread.start()
        self._lbl_tid.config(text=f"TID: {self._thread.ident}")

    # ── construção do widget ─────────────────────────────────────────────────
    def _build(self, parent):
        self.frame = tk.LabelFrame(
            parent,
            text=f"  📥  Receptor {self.index}  ",
            fg=ACCENT_GREEN,
            bg=PANEL,
            font=FONT_BODY_B,
            bd=1,
            relief="solid",
        )

        inner = tk.Frame(self.frame, bg=PANEL, padx=8, pady=6)
        inner.pack(fill="both", expand=True)

        # ── linha de info ────────────────────────────────────────────────────
        info = tk.Frame(inner, bg=PANEL)
        info.pack(fill="x")

        self._lbl_tid = tk.Label(
            info, text="TID: …", bg=PANEL, fg=MUTED, font=FONT_SMALL
        )
        self._lbl_tid.pack(side="left")

        self._lbl_recv_count = tk.Label(
            info, text="Recebidas: 0", bg=PANEL, fg=MUTED, font=FONT_SMALL
        )
        self._lbl_recv_count.pack(side="right")

        # ── delay ────────────────────────────────────────────────────────────
        delay_row = tk.Frame(inner, bg=PANEL)
        delay_row.pack(fill="x", pady=(4, 0))
        tk.Label(delay_row, text="Delay de processamento:", bg=PANEL,
                 fg=TEXT, font=FONT_SMALL).pack(side="left")
        self._lbl_delay_val = tk.Label(
            delay_row, text="1.5s", bg=PANEL, fg=ACCENT_ORANGE, font=FONT_SMALL
        )
        self._lbl_delay_val.pack(side="right")

        slider = tk.Scale(
            inner,
            variable=self._delay_var,
            from_=0.2, to=5.0, resolution=0.1,
            orient="horizontal",
            bg=PANEL, fg=TEXT, highlightthickness=0,
            troughcolor=BORDER, activebackground=ACCENT_ORANGE,
            showvalue=False,
            command=lambda v: self._lbl_delay_val.config(text=f"{float(v):.1f}s"),
        )
        slider.pack(fill="x")

        # ── fila visual ──────────────────────────────────────────────────────
        q_row = tk.Frame(inner, bg=PANEL)
        q_row.pack(fill="x", pady=(4, 2))
        tk.Label(q_row, text="Fila:", bg=PANEL, fg=TEXT, font=FONT_SMALL).pack(side="left")
        self._lbl_qsize = tk.Label(
            q_row, text="0 msg", bg=PANEL, fg=ACCENT_BLUE, font=FONT_SMALL
        )
        self._lbl_qsize.pack(side="left", padx=4)

        self._q_canvas = tk.Canvas(inner, height=10, bg=BG, highlightthickness=0)
        self._q_canvas.pack(fill="x")

        # ── status / processando ─────────────────────────────────────────────
        self._lbl_status = tk.Label(
            inner,
            textvariable=self._status_var,
            bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w",
        )
        self._lbl_status.pack(fill="x", pady=(2, 0))

        # ── log de mensagens ─────────────────────────────────────────────────
        self._box = scrolled_text(inner, height=7)
        self._box.pack(fill="both", expand=True, pady=(4, 0))
        self._box.tag_config("header", foreground=ACCENT_GREEN, font=FONT_BODY_B)
        self._box.tag_config("meta",   foreground=MUTED,        font=FONT_SMALL)
        self._box.tag_config("body",   foreground=TEXT,         font=FONT_MONO)
        self._box.tag_config("ack",    foreground=ACCENT_ORANGE,font=FONT_SMALL)

        # ── imagem ───────────────────────────────────────────────────────────
        self._img_lbl = tk.Label(inner, bg=PANEL)
        self._img_lbl.pack()

    # ── worker thread ────────────────────────────────────────────────────────
    def _worker(self):
        while self._running:
            msg = self.queue.get(timeout=0.1)
            if msg is None:
                continue

            self._processing = True
            self._current_msg_id = msg.msg_id

            delay = self._delay_var.get()
            self._win.after(
                0,
                lambda m=msg, d=delay: self._status_var.set(
                    f"⏳  Processando '{m.content[:30]}…'  ({d:.1f}s)"
                    if m.type == MSG_TEXT
                    else f"⏳  Processando arquivo '{m.filename}'  ({d:.1f}s)"
                ),
            )

            # simula processamento
            time.sleep(delay)

            # dispara ACK
            ev = self.ack_registry.get(msg.msg_id)
            if ev:
                ev.set()

            self._received += 1
            self._processing = False
            self._win.after(0, lambda m=msg: self._on_done(m))

        # thread encerrada
        self._win.after(
            0, lambda: self._status_var.set("■  Thread encerrada")
        )

    def _on_done(self, msg: Message):
        self._lbl_recv_count.config(text=f"Recebidas: {self._received}")
        self._status_var.set(f"✓  Pronto  (recebidas: {self._received})")
        self._display_message(msg)
        self._update_queue_bar()
        self._log(
            f"[Receptor {self.index}] ACK enviado para msg {msg.msg_id[:8]}…"
            f"  TID={self._thread.ident}"
        )

    def _display_message(self, msg: Message):
        box = self._box
        box.config(state="normal")
        ts = time.strftime("%H:%M:%S", time.localtime(msg.timestamp))
        box.insert("end", f"\n[{ts}] {msg.sender}\n", "header")
        box.insert("end", f"id: {msg.msg_id[:8]}…\n", "meta")

        if msg.type == MSG_TEXT:
            box.insert("end", msg.content + "\n", "body")
        elif msg.type == MSG_IMAGE:
            box.insert("end", f"Imagem: {msg.filename}\n", "body")
            if HAS_PIL:
                try:
                    import io
                    data = b64_to_bytes(msg.content)
                    img = Image.open(io.BytesIO(data))
                    img.thumbnail((180, 130))
                    photo = ImageTk.PhotoImage(img)
                    self._image_refs.append(photo)
                    self._img_lbl.config(image=photo)
                except Exception:
                    pass
        elif msg.type == MSG_FILE:
            box.insert("end", f"Arquivo: {msg.filename}\n", "body")

        box.insert("end", f"✓ ACK  delay={self._delay_var.get():.1f}s\n", "ack")
        box.insert("end", "─" * 32 + "\n", "meta")
        box.config(state="disabled")
        box.see("end")

    # ── atualiza barra de fila ───────────────────────────────────────────────
    def _update_queue_bar(self):
        n = self.queue.qsize()
        self._lbl_qsize.config(text=f"{n} msg")
        c = self._q_canvas
        w = c.winfo_width() or 180
        max_vis = 20
        filled = min(n / max_vis, 1.0)
        color = ACCENT_GREEN if n == 0 else (ACCENT_ORANGE if n < 5 else ACCENT_RED)
        c.delete("all")
        c.create_rectangle(0, 0, int(w * filled), 10, fill=color, outline="")
        c.create_rectangle(int(w * filled), 0, w, 10, fill=BORDER, outline="")

    def poll_queue_bar(self):
        """Chamado pelo window loop para manter a barra de fila atualizada."""
        self._update_queue_bar()

    def stop(self):
        self._running = False

    @property
    def tid(self):
        return self._thread.ident

    @property
    def alive(self):
        return self._thread.is_alive()


# ─────────────────────────────────────────────────────────────────────────────
# Janela principal do Modo Threads
# ─────────────────────────────────────────────────────────────────────────────
class ThreadWindow:
    POLL_MS = 200   # intervalo de refresh do monitor

    def __init__(self, parent: tk.Tk):
        self.parent = parent
        self.win = tk.Toplevel(parent)
        self.win.title("Modo Threads — Demo de Paralelismo")
        self.win.configure(bg=BG)
        self.win.geometry("1280x780")
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

        self.tm          = ThreadManager()
        self._ack_reg: dict = {}          # msg_id → threading.Event
        self._receivers: list[ReceiverPanel] = []
        self._recv_idx   = 0
        self._running    = True
        self._parallel   = True           # paralelismo ON por padrão
        self._waiting_ack = False         # em modo síncrono, bloqueia envio
        self._stats      = {"sent": 0, "acked": 0, "in_flight": 0}
        self._selected_file: str = ""

        self._build()
        self._add_receiver()   # começa com 1 receptor
        self._poll_monitor()

    # ═════════════════════════════════════════════════════════════════════════
    # Interface
    # ═════════════════════════════════════════════════════════════════════════
    def _build(self):
        w = self.win

        # ── barra de título ──────────────────────────────────────────────────
        bar = tk.Frame(w, bg=PANEL, pady=8)
        bar.pack(fill="x")
        tk.Label(bar, text="🧵  Modo Threads", bg=PANEL,
                 fg=ACCENT_BLUE, font=FONT_TITLE).pack(side="left", padx=16)
        self._lbl_pid = tk.Label(
            bar, text=f"PID: {os.getpid()}", bg=PANEL, fg=MUTED, font=FONT_SMALL
        )
        self._lbl_pid.pack(side="left", padx=8)
        tk.Frame(w, bg=BORDER, height=1).pack(fill="x")

        # ── corpo ────────────────────────────────────────────────────────────
        body = tk.Frame(w, bg=BG)
        body.pack(fill="both", expand=True, padx=6, pady=4)
        body.columnconfigure(0, weight=0, minsize=280)
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, weight=0, minsize=240)
        body.rowconfigure(0, weight=1)

        self._build_sender(body)
        self._build_receivers_area(body)
        self._build_monitor(body)

        # ── log ──────────────────────────────────────────────────────────────
        lf = tk.LabelFrame(w, text="  Log de Eventos  ", fg=ACCENT_PURPLE,
                           bg=BG, font=FONT_BODY_B, bd=1, relief="solid")
        lf.pack(fill="x", padx=6, pady=(0, 4))
        self._log_box = scrolled_text(lf, height=4)
        self._log_box.pack(fill="x", padx=4, pady=3)

    # ── painel remetente ─────────────────────────────────────────────────────
    def _build_sender(self, parent):
        frame = tk.LabelFrame(
            parent, text="  📤  Remetente  ",
            fg=ACCENT_BLUE, bg=PANEL, font=FONT_BODY_B, bd=1, relief="solid"
        )
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        inner = tk.Frame(frame, bg=PANEL, padx=10, pady=8)
        inner.pack(fill="both", expand=True)

        # TID do remetente
        self._lbl_sender_tid = tk.Label(
            inner, text="Thread: (main)", bg=PANEL, fg=MUTED, font=FONT_SMALL
        )
        self._lbl_sender_tid.pack(anchor="w")

        # texto
        tk.Label(inner, text="Mensagem:", bg=PANEL, fg=TEXT,
                 font=FONT_BODY).pack(anchor="w", pady=(6, 2))
        self._txt_input = tk.Text(
            inner, height=4, bg=BG, fg=TEXT, insertbackground=TEXT,
            font=FONT_MONO, relief="flat", bd=4, wrap="word"
        )
        self._txt_input.pack(fill="x")
        self._txt_input.insert("1.0", "Olá, Receptor!")

        # destino
        tk.Label(inner, text="Destino:", bg=PANEL, fg=TEXT,
                 font=FONT_BODY).pack(anchor="w", pady=(8, 2))
        self._dest_var = tk.StringVar(value="Broadcast")
        self._dest_menu = tk.OptionMenu(inner, self._dest_var, "Broadcast")
        self._dest_menu.config(
            bg=PANEL, fg=TEXT, font=FONT_SMALL, relief="flat",
            highlightthickness=0, activebackground=BORDER,
        )
        self._dest_menu["menu"].config(bg=PANEL, fg=TEXT, font=FONT_SMALL)
        self._dest_menu.pack(fill="x")

        # ── paralelismo ──────────────────────────────────────────────────────
        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=8)
        tk.Label(inner, text="Modo de envio:", bg=PANEL,
                 fg=TEXT, font=FONT_BODY_B).pack(anchor="w")

        self._lbl_parallel = tk.Label(
            inner, text="⚡  PARALELO  (uma thread por msg)",
            bg=PANEL, fg=ACCENT_GREEN, font=FONT_BODY_B
        )
        self._lbl_parallel.pack(anchor="w", pady=(4, 2))

        tk.Label(
            inner,
            text=(
                "PARALELO: cada mensagem ganha\n"
                "sua própria thread → remetente\n"
                "livre; ACKs chegam conforme\n"
                "os receptores processam.\n\n"
                "SÍNCRONO: remetente aguarda\n"
                "ACK antes de liberar próximo\n"
                "envio (botão trava)."
            ),
            bg=PANEL, fg=MUTED, font=FONT_SMALL, justify="left",
        ).pack(anchor="w", pady=(0, 6))

        self._btn_parallel = tk.Button(
            inner, text="Mudar para SÍNCRONO",
            command=self._toggle_parallel,
            bg=BTN_MUTEX_OFF, fg=TEXT_DARK, font=FONT_BODY_B,
            relief="flat", padx=8, pady=4, cursor="hand2",
        )
        self._btn_parallel.pack(fill="x")

        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=8)

        # arquivo
        tk.Label(inner, text="Arquivo / Imagem:", bg=PANEL,
                 fg=TEXT, font=FONT_BODY).pack(anchor="w")
        self._lbl_file = tk.Label(
            inner, text="(nenhum)", bg=PANEL, fg=MUTED, font=FONT_SMALL
        )
        self._lbl_file.pack(anchor="w", pady=(2, 4))
        tk.Button(
            inner, text="Selecionar  📁", command=self._pick_file,
            bg=PANEL, fg=ACCENT_BLUE, font=FONT_SMALL,
            relief="flat", cursor="hand2", bd=1, highlightbackground=BORDER,
        ).pack(fill="x")

        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=8)

        # ── botão enviar ─────────────────────────────────────────────────────
        self._btn_send_txt = tk.Button(
            inner, text="Enviar Texto  →",
            command=self._send_text,
            bg=ACCENT_BLUE, fg=TEXT_DARK, font=FONT_BODY_B,
            relief="flat", padx=8, pady=6, cursor="hand2",
        )
        self._btn_send_txt.pack(fill="x", pady=2)

        self._btn_send_file = tk.Button(
            inner, text="Enviar Arquivo  →",
            command=self._send_file,
            bg=ACCENT_ORANGE, fg=TEXT_DARK, font=FONT_BODY_B,
            relief="flat", padx=8, pady=6, cursor="hand2", state="disabled",
        )
        self._btn_send_file.pack(fill="x")

        # status do envio
        self._lbl_send_status = tk.Label(
            inner, text="● Pronto", bg=PANEL, fg=ACCENT_GREEN, font=FONT_SMALL
        )
        self._lbl_send_status.pack(anchor="w", pady=(6, 0))

    # ── área de receptores (scrollável) ─────────────────────────────────────
    def _build_receivers_area(self, parent):
        outer = tk.Frame(parent, bg=BG)
        outer.grid(row=0, column=1, sticky="nsew", padx=4)
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(0, weight=1)

        # toolbar
        toolbar = tk.Frame(outer, bg=BG, pady=4)
        toolbar.grid(row=0, column=0, sticky="ew")

        tk.Label(toolbar, text="Receptores:", bg=BG,
                 fg=TEXT, font=FONT_BODY_B).pack(side="left")
        self._lbl_recv_count = tk.Label(
            toolbar, text="1 receptor ativo", bg=BG, fg=MUTED, font=FONT_SMALL
        )
        self._lbl_recv_count.pack(side="left", padx=8)

        tk.Button(
            toolbar, text="+ Adicionar Receptor",
            command=self._add_receiver,
            bg=ACCENT_GREEN, fg=TEXT_DARK, font=FONT_BODY_B,
            relief="flat", padx=8, pady=3, cursor="hand2",
        ).pack(side="right")

        tk.Button(
            toolbar, text="− Remover último",
            command=self._remove_receiver,
            bg=PANEL, fg=MUTED, font=FONT_SMALL,
            relief="flat", padx=6, pady=3, cursor="hand2",
        ).pack(side="right", padx=4)

        # canvas scrollável
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        outer.columnconfigure(0, weight=1)

        self._recv_container = tk.Frame(canvas, bg=BG)
        self._recv_window_id = canvas.create_window(
            (0, 0), window=self._recv_container, anchor="nw"
        )

        def _on_configure(evt):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(self._recv_window_id, width=canvas.winfo_width())

        self._recv_container.bind("<Configure>", _on_configure)
        canvas.bind("<Configure>", _on_configure)
        def _on_mousewheel(e):
            try:
                canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
            except tk.TclError:
                pass   # janela já destruída

        canvas.bind("<Enter>",  lambda _: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>",  lambda _: canvas.unbind_all("<MouseWheel>"))
        self._recv_canvas = canvas

    # ── painel monitor ───────────────────────────────────────────────────────
    def _build_monitor(self, parent):
        frame = tk.LabelFrame(
            parent, text="  📊  Monitor  ",
            fg=ACCENT_PURPLE, bg=PANEL, font=FONT_BODY_B, bd=1, relief="solid"
        )
        frame.grid(row=0, column=2, sticky="nsew", padx=(4, 0))

        inner = tk.Frame(frame, bg=PANEL, padx=10, pady=8)
        inner.pack(fill="both", expand=True)

        # stats
        tk.Label(inner, text="Estatísticas:", bg=PANEL,
                 fg=TEXT, font=FONT_BODY_B).pack(anchor="w")
        self._lbl_stats = tk.Label(
            inner, text="", bg=PANEL, fg=ACCENT_BLUE,
            font=FONT_MONO_S, justify="left"
        )
        self._lbl_stats.pack(anchor="w", pady=(2, 8))

        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=4)

        # threads ativas
        tk.Label(inner, text="Threads do processo:", bg=PANEL,
                 fg=TEXT, font=FONT_BODY_B).pack(anchor="w")
        self._lbl_threads = tk.Label(
            inner, text="", bg=PANEL, fg=ACCENT_BLUE,
            font=FONT_MONO_S, justify="left", wraplength=230
        )
        self._lbl_threads.pack(anchor="w", pady=(2, 8))

        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=4)

        # modo atual
        tk.Label(inner, text="Modo atual:", bg=PANEL,
                 fg=TEXT, font=FONT_BODY_B).pack(anchor="w")
        self._lbl_mode_detail = tk.Label(
            inner, text="", bg=PANEL, fg=TEXT,
            font=FONT_SMALL, justify="left", wraplength=230
        )
        self._lbl_mode_detail.pack(anchor="w", pady=(2, 8))

        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=4)

        # filas
        tk.Label(inner, text="Estado das filas:", bg=PANEL,
                 fg=TEXT, font=FONT_BODY_B).pack(anchor="w")
        self._lbl_queues = tk.Label(
            inner, text="", bg=PANEL, fg=ACCENT_GREEN,
            font=FONT_MONO_S, justify="left"
        )
        self._lbl_queues.pack(anchor="w", pady=(2, 0))

    # ═════════════════════════════════════════════════════════════════════════
    # Gerenciar receptores
    # ═════════════════════════════════════════════════════════════════════════
    def _add_receiver(self):
        self._recv_idx += 1
        idx = self._recv_idx

        rp = ReceiverPanel(
            parent=self._recv_container,
            index=idx,
            ack_registry=self._ack_reg,
            log_fn=self._log_event,
            window_ref=self.win,
        )

        # empacota em grid 2 colunas
        col = (idx - 1) % 2
        row = (idx - 1) // 2
        rp.frame.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)
        self._recv_container.columnconfigure(0, weight=1)
        self._recv_container.columnconfigure(1, weight=1)

        self._receivers.append(rp)
        self._update_dest_menu()
        self._lbl_recv_count.config(
            text=f"{len(self._receivers)} receptor(es) ativo(s)"
        )
        self._log_event(
            f"[Window] Receptor {idx} criado  TID={rp.tid}  "
            f"(total: {len(self._receivers)})"
        )

    def _remove_receiver(self):
        if len(self._receivers) <= 1:
            return
        rp = self._receivers.pop()
        rp.stop()
        rp.frame.destroy()
        self._update_dest_menu()
        self._lbl_recv_count.config(
            text=f"{len(self._receivers)} receptor(es) ativo(s)"
        )
        self._log_event(f"[Window] Receptor {rp.index} removido")

    def _update_dest_menu(self):
        menu = self._dest_menu["menu"]
        menu.delete(0, "end")
        menu.add_command(label="Broadcast", command=lambda: self._dest_var.set("Broadcast"))
        for rp in self._receivers:
            label = f"Receptor {rp.index}"
            menu.add_command(label=label, command=lambda l=label: self._dest_var.set(l))
        if self._dest_var.get() not in (
            ["Broadcast"] + [f"Receptor {rp.index}" for rp in self._receivers]
        ):
            self._dest_var.set("Broadcast")

    def _resolve_targets(self) -> list:
        """Retorna lista de ReceiverPanel de acordo com o destino selecionado."""
        dest = self._dest_var.get()
        if dest == "Broadcast":
            return list(self._receivers)
        for rp in self._receivers:
            if f"Receptor {rp.index}" == dest:
                return [rp]
        return list(self._receivers)

    # ═════════════════════════════════════════════════════════════════════════
    # Envio de mensagens
    # ═════════════════════════════════════════════════════════════════════════
    def _send_text(self):
        if self._waiting_ack:
            return
        text = self._txt_input.get("1.0", "end").strip()
        if not text:
            return
        msg = Message(
            type=MSG_TEXT,
            content=text,
            sender=f"Thread-{threading.current_thread().ident}",
            msg_id=str(uuid.uuid4()),
        )
        self._dispatch(msg)

    def _send_file(self):
        if self._waiting_ack or not self._selected_file:
            return
        path = self._selected_file
        finfo = file_info(path)
        msg_type = MSG_IMAGE if is_image(path) else MSG_FILE

        def _prepare():
            b64 = read_as_b64(path)
            msg = Message(
                type=msg_type,
                content=b64,
                filename=finfo["name"],
                sender=f"Thread-{threading.current_thread().ident}",
                msg_id=str(uuid.uuid4()),
            )
            self.win.after(0, lambda: self._dispatch(msg))

        threading.Thread(target=_prepare, daemon=True).start()

    def _dispatch(self, msg: Message):
        """
        Distribui a mensagem para os receptores-alvo.
        Com paralelismo ON  → uma thread por mensagem (non-blocking).
        Com paralelismo OFF → aguarda todos os ACKs antes de liberar o botão.
        """
        targets = self._resolve_targets()
        if not targets:
            return

        # cria um Event de ACK por (msg × receptor)
        # cada receptor recebe uma cópia da mensagem com ID único
        sub_msgs = []
        for rp in targets:
            sub_id  = str(uuid.uuid4())
            ev      = threading.Event()
            sub_msg = Message(
                type=msg.type, content=msg.content,
                filename=msg.filename, sender=msg.sender,
                timestamp=msg.timestamp, msg_id=sub_id,
            )
            self._ack_reg[sub_id] = ev
            rp.queue.put(sub_msg)
            sub_msgs.append((sub_id, ev, rp.index))

        self._stats["sent"] += len(sub_msgs)
        self._stats["in_flight"] += len(sub_msgs)

        dest_str = self._dest_var.get()
        self._log_event(
            f"[Remetente] Enviado para {dest_str}  "
            f"tipo={msg.type}  "
            f"{'paralelo' if self._parallel else 'síncrono'}"
        )

        if self._parallel:
            # ── modo paralelo: uma thread de espera por sub-mensagem ─────────
            for sub_id, ev, ridx in sub_msgs:
                def _wait(sid=sub_id, event=ev, ri=ridx):
                    event.wait(timeout=60)
                    self._ack_reg.pop(sid, None)
                    self._stats["acked"] += 1
                    self._stats["in_flight"] = max(0, self._stats["in_flight"] - 1)
                    self.win.after(
                        0,
                        lambda si=sid, r=ri: self._log_event(
                            f"[ACK] Receptor {r} confirmou msg {si[:8]}…  "
                            f"TID={threading.current_thread().ident}"
                        ),
                    )

                t = threading.Thread(target=_wait, daemon=True,
                                     name=f"ACK-waiter-{sub_id[:6]}")
                t.start()

            self._lbl_send_status.config(
                text=f"⚡  {len(sub_msgs)} thread(s) aguardando ACK",
                fg=ACCENT_GREEN,
            )

        else:
            # ── modo síncrono: bloqueia o botão ──────────────────────────────
            self._waiting_ack = True
            self._btn_send_txt.config(state="disabled")
            self._btn_send_file.config(state="disabled")
            self._lbl_send_status.config(
                text=f"⏳  Aguardando {len(sub_msgs)} ACK(s)…", fg=ACCENT_YELLOW
            )

            def _wait_all():
                for sub_id, ev, ridx in sub_msgs:
                    ev.wait(timeout=60)
                    self._ack_reg.pop(sub_id, None)
                    self._stats["acked"] += 1
                    self._stats["in_flight"] = max(0, self._stats["in_flight"] - 1)
                    self.win.after(
                        0,
                        lambda si=sub_id, r=ridx: self._log_event(
                            f"[ACK] Receptor {r} confirmou {si[:8]}…"
                        ),
                    )
                # todos ACKs recebidos → libera o remetente
                self.win.after(0, self._release_sender)

            threading.Thread(target=_wait_all, daemon=True,
                             name="SyncWaiter").start()

    def _release_sender(self):
        self._waiting_ack = False
        self._btn_send_txt.config(state="normal")
        if self._selected_file:
            self._btn_send_file.config(state="normal")
        self._lbl_send_status.config(text="● Pronto", fg=ACCENT_GREEN)
        self._log_event("[Remetente] Todos os ACKs recebidos — pronto para próximo envio")

    # ═════════════════════════════════════════════════════════════════════════
    # Paralelismo ON/OFF
    # ═════════════════════════════════════════════════════════════════════════
    def _toggle_parallel(self):
        self._parallel = not self._parallel
        if self._parallel:
            self._lbl_parallel.config(
                text="⚡  PARALELO  (uma thread por msg)", fg=ACCENT_GREEN
            )
            self._btn_parallel.config(text="Mudar para SÍNCRONO", bg=BTN_MUTEX_OFF)
            self._log_event("[Modo] Paralelismo ATIVADO")
        else:
            self._lbl_parallel.config(
                text="🔒  SÍNCRONO  (aguarda ACK)", fg=ACCENT_YELLOW
            )
            self._btn_parallel.config(text="Mudar para PARALELO", bg=BTN_MUTEX_ON)
            self._log_event("[Modo] Paralelismo DESATIVADO — modo síncrono")

    # ═════════════════════════════════════════════════════════════════════════
    # Arquivo
    # ═════════════════════════════════════════════════════════════════════════
    def _pick_file(self):
        path = filedialog.askopenfilename(
            filetypes=[
                ("Todos", "*.*"),
                ("Imagens", "*.png *.jpg *.jpeg *.gif"),
                ("Documentos", "*.pdf *.txt *.docx"),
            ]
        )
        if path:
            self._selected_file = path
            info = file_info(path)
            self._lbl_file.config(
                text=f"{info['name']}  ({info['size_str']})", fg=TEXT
            )
            if not self._waiting_ack:
                self._btn_send_file.config(state="normal")

    # ═════════════════════════════════════════════════════════════════════════
    # Monitor (atualiza a cada POLL_MS)
    # ═════════════════════════════════════════════════════════════════════════
    def _poll_monitor(self):
        if not self._running:
            return

        # stats gerais
        s = self._stats
        self._lbl_stats.config(
            text=(
                f"Enviadas  : {s['sent']}\n"
                f"ACKs rec. : {s['acked']}\n"
                f"Em voo    : {s['in_flight']}\n"
                f"Pendentes : {sum(rp.queue.qsize() for rp in self._receivers)}"
            )
        )

        # threads
        all_t = self.tm.all_threads_info()
        lines = [f"Total: {len(all_t)}\n"]
        for t in all_t[:14]:
            dot = "●" if t["alive"] else "○"
            lines.append(f"{dot} {t['name']}  [{t['ident']}]")
        self._lbl_threads.config(text="\n".join(lines))

        # modo
        if self._parallel:
            mode_txt = (
                "⚡ PARALELO\n"
                "Cada msg → thread própria.\n"
                "Remetente não bloqueia.\n"
                "ACKs chegam de forma\n"
                "assíncrona."
            )
        else:
            mode_txt = (
                "🔒 SÍNCRONO\n"
                "Remetente aguarda ACK\n"
                "de todos os receptores\n"
                "antes do próximo envio."
            )
        self._lbl_mode_detail.config(text=mode_txt)

        # filas
        q_lines = []
        for rp in self._receivers:
            n = rp.queue.qsize()
            bar = "█" * min(n, 10) + "░" * (10 - min(n, 10))
            q_lines.append(f"R{rp.index}: {bar} {n}")
            rp.poll_queue_bar()
        self._lbl_queues.config(text="\n".join(q_lines) if q_lines else "—")

        # TID do remetente
        self._lbl_sender_tid.config(
            text=f"Thread: {threading.current_thread().ident} (main)"
        )

        self.win.after(self.POLL_MS, self._poll_monitor)

    # ═════════════════════════════════════════════════════════════════════════
    def _log_event(self, text: str):
        ts = time.strftime("%H:%M:%S")
        box = self._log_box
        box.config(state="normal")
        box.insert("end", f"[{ts}] {text}\n")
        box.config(state="disabled")
        box.see("end")

    def _on_close(self):
        self._running = False
        try:
            self.win.unbind_all("<MouseWheel>")
        except tk.TclError:
            pass
        for rp in self._receivers:
            rp.stop()
        self.win.destroy()

    def show(self):
        self.win.focus_force()
