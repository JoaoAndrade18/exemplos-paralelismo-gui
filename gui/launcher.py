"""
gui/launcher.py — Janela inicial com escolha de modo.
"""
import tkinter as tk
import os
import sys

from gui.styles import (
    BG, PANEL, TEXT, MUTED, ACCENT_BLUE, ACCENT_ORANGE, ACCENT_GREEN,
    FONT_TITLE, FONT_BODY, FONT_BODY_B, FONT_SMALL, BORDER,
)


class LauncherWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Demo de Paralelismo")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self._center(520, 440)
        self._build()

    def _center(self, w, h):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _build(self):
        root = self.root

        # ── cabeçalho ────────────────────────────────────────────────────────
        header = tk.Frame(root, bg=PANEL, pady=20)
        header.pack(fill="x")

        tk.Label(
            header, text="Demo de Paralelismo",
            bg=PANEL, fg=ACCENT_BLUE, font=FONT_TITLE
        ).pack()
        tk.Label(
            header,
            text="Escolha o modo de demonstração para os alunos",
            bg=PANEL, fg=MUTED, font=FONT_SMALL,
        ).pack(pady=(2, 0))

        # ── separador ────────────────────────────────────────────────────────
        tk.Frame(root, bg=BORDER, height=1).pack(fill="x")

        # ── cartões de modo ──────────────────────────────────────────────────
        cards = tk.Frame(root, bg=BG, padx=30, pady=20)
        cards.pack(fill="both", expand=True)

        self._card(
            cards,
            icon="🧵",
            title="Modo Threads",
            desc=(
                "Duas interfaces no mesmo processo,\n"
                "comunicando-se via Queue de threads.\n"
                "Demonstra mutex, race condition e\n"
                "compartilhamento de memória."
            ),
            color=ACCENT_BLUE,
            command=self._open_threads,
            col=0,
        )

        self._card(
            cards,
            icon="⚙️",
            title="Modo Processos",
            desc=(
                "Dois processos separados (PIDs distintos)\n"
                "comunicando-se via socket TCP.\n"
                "Demonstra IPC, memória independente\n"
                "e uso de núcleos diferentes."
            ),
            color=ACCENT_ORANGE,
            command=self._open_processes,
            col=1,
        )

        cards.columnconfigure(0, weight=1, pad=10)
        cards.columnconfigure(1, weight=1, pad=10)

        # ── rodapé ───────────────────────────────────────────────────────────
        footer = tk.Frame(root, bg=BG)
        footer.pack(fill="x", padx=30, pady=(0, 15))
        tk.Label(
            footer,
            text=f"PID atual: {os.getpid()}  |  Python {sys.version.split()[0]}",
            bg=BG, fg=MUTED, font=FONT_SMALL,
        ).pack(side="left")

    def _card(self, parent, icon, title, desc, color, command, col):
        frame = tk.Frame(parent, bg=PANEL, bd=1, relief="flat",
                         highlightthickness=1, highlightbackground=BORDER)
        frame.grid(row=0, column=col, sticky="nsew", padx=8, pady=8)

        inner = tk.Frame(frame, bg=PANEL, padx=18, pady=18)
        inner.pack(fill="both", expand=True)

        tk.Label(inner, text=icon, bg=PANEL, fg=color, font=("Segoe UI", 28)).pack()
        tk.Label(inner, text=title, bg=PANEL, fg=color, font=FONT_BODY_B).pack(pady=(4, 2))
        tk.Label(inner, text=desc, bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 9), justify="center").pack(pady=(0, 12))

        btn = tk.Button(
            inner, text=f"Abrir {title}", command=command,
            bg=color, fg="#1e1e2e", font=FONT_BODY_B,
            relief="flat", padx=12, pady=6, cursor="hand2",
            activebackground=color,
        )
        btn.pack(fill="x")

    # ── abrir modos ─────────────────────────────────────────────────────────
    def _open_threads(self):
        from gui.thread_window import ThreadWindow
        win = ThreadWindow(self.root)
        win.show()

    def _open_processes(self):
        from gui.process_window import ProcessWindow
        win = ProcessWindow(self.root)
        win.show()

    def run(self):
        self.root.mainloop()
