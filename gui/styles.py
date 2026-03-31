"""
gui/styles.py — Paleta de cores e helpers de estilo para toda a aplicação.
"""

# ── Paleta ────────────────────────────────────────────────────────────────────
BG          = "#1e1e2e"   # fundo geral
PANEL       = "#2a2a3e"   # fundo de painéis internos
BORDER      = "#44475a"   # borda de frames

TEXT        = "#cdd6f4"   # texto principal
MUTED       = "#6c7086"   # texto secundário
TEXT_DARK   = "#1e1e2e"   # texto em botões claros

ACCENT_BLUE    = "#89b4fa"   # azul — Modo Threads / Remetente
ACCENT_GREEN   = "#a6e3a1"   # verde — Receptor
ACCENT_ORANGE  = "#fab387"   # laranja — Modo Processos
ACCENT_PURPLE  = "#cba6f7"   # roxo — detalhes de mutex
ACCENT_RED     = "#f38ba8"   # vermelho — mutex OFF / erro
ACCENT_YELLOW  = "#f9e2af"   # amarelo — avisos / race condition

BTN_MUTEX_ON   = "#a6e3a1"
BTN_MUTEX_OFF  = "#f38ba8"

TAG_THREAD  = ACCENT_BLUE
TAG_PROCESS = ACCENT_ORANGE
TAG_MUTEX   = ACCENT_PURPLE
TAG_WARN    = ACCENT_YELLOW

# ── Fontes ────────────────────────────────────────────────────────────────────
FONT_MONO   = ("Consolas", 10)
FONT_MONO_S = ("Consolas", 9)
FONT_BODY   = ("Segoe UI", 10)
FONT_BODY_B = ("Segoe UI", 10, "bold")
FONT_TITLE  = ("Segoe UI", 14, "bold")
FONT_H2     = ("Segoe UI", 11, "bold")
FONT_SMALL  = ("Segoe UI", 8)


# ── Helpers ───────────────────────────────────────────────────────────────────
def badge(parent, text: str, color: str, **kw):
    """Label pequena com fundo colorido (estilo badge)."""
    import tkinter as tk
    lbl = tk.Label(
        parent,
        text=text,
        bg=color,
        fg=TEXT_DARK,
        font=FONT_SMALL,
        padx=4,
        pady=1,
        relief="flat",
    )
    if kw:
        lbl.grid(**kw) if "row" in kw else lbl.pack(**kw)
    return lbl


def section(parent, title: str, color: str = ACCENT_BLUE) -> "tk.LabelFrame":
    import tkinter as tk
    frame = tk.LabelFrame(
        parent,
        text=f"  {title}  ",
        fg=color,
        bg=PANEL,
        font=FONT_BODY_B,
        bd=1,
        relief="solid",
        highlightbackground=BORDER,
    )
    return frame


def scrolled_text(parent, height: int = 10, **kw):
    """Text widget com scrollbar vertical."""
    import tkinter as tk
    from tkinter import scrolledtext
    st = scrolledtext.ScrolledText(
        parent,
        height=height,
        bg=BG,
        fg=TEXT,
        insertbackground=TEXT,
        font=FONT_MONO,
        relief="flat",
        bd=0,
        wrap="word",
        state="disabled",
        **kw,
    )
    return st


def btn(parent, text: str, command, color: str = ACCENT_BLUE, **kw):
    import tkinter as tk
    b = tk.Button(
        parent,
        text=text,
        command=command,
        bg=color,
        fg=TEXT_DARK,
        font=FONT_BODY_B,
        relief="flat",
        bd=0,
        padx=10,
        pady=5,
        cursor="hand2",
        activebackground=color,
        activeforeground=TEXT_DARK,
    )
    return b
