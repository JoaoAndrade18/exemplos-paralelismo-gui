"""
gui/demos_window.py — Janela de Demos de Paralelismo.

5 abas, cada uma demonstra um conceito diferente:
  1. Race Condition  — threads ou processos, mutex on/off
  2. Deadlock        — dois threads aguardando o lock um do outro
  3. Semáforo        — limitar acesso concorrente a N slots
  4. Barreira        — sincronizar N threads num ponto comum
  5. Thread Pool     — reutilizar pool fixo de workers
"""
import tkinter as tk
from tkinter import ttk
import threading
import time
import os
import random
import multiprocessing
from concurrent.futures import ThreadPoolExecutor

from core.mutex_manager import _mp_worker_unsafe, _mp_worker_safe
from gui.styles import (
    BG, PANEL, BORDER, TEXT, MUTED, TEXT_DARK,
    ACCENT_BLUE, ACCENT_GREEN, ACCENT_ORANGE, ACCENT_PURPLE,
    ACCENT_RED, ACCENT_YELLOW, BTN_MUTEX_ON, BTN_MUTEX_OFF,
    FONT_MONO, FONT_MONO_S, FONT_BODY, FONT_BODY_B, FONT_SMALL,
    FONT_TITLE, FONT_H2, scrolled_text, btn,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers compartilhados
# ─────────────────────────────────────────────────────────────────────────────

def _spin(parent, label, from_, to, init, step=1, width=5):
    row = tk.Frame(parent, bg=PANEL)
    row.pack(fill="x", pady=2)
    tk.Label(row, text=label, bg=PANEL, fg=TEXT, font=FONT_SMALL, width=18, anchor="w").pack(side="left")
    sp = tk.Spinbox(row, from_=from_, to=to, increment=step, width=width,
                    bg=BG, fg=TEXT, buttonbackground=PANEL, font=FONT_SMALL, relief="flat")
    sp.pack(side="left")
    sp.delete(0, "end"); sp.insert(0, str(init))
    return sp


def _label_log(parent, h=8):
    lf = tk.Frame(parent, bg=BG)
    lf.pack(fill="both", expand=True, pady=4)
    st = scrolled_text(lf, height=h)
    st.pack(fill="both", expand=True)
    st.tag_config("ok",   foreground=ACCENT_GREEN)
    st.tag_config("err",  foreground=ACCENT_RED)
    st.tag_config("warn", foreground=ACCENT_YELLOW)
    st.tag_config("info", foreground=ACCENT_BLUE)
    st.tag_config("muted",foreground=MUTED, font=FONT_SMALL)
    return st


def _log(box, text, tag="info"):
    ts = time.strftime("%H:%M:%S")
    box.config(state="normal")
    box.insert("end", f"[{ts}] {text}\n", tag)
    box.config(state="disabled")
    box.see("end")


def _bar_canvas(parent):
    c = tk.Canvas(parent, height=16, bg=BG, highlightthickness=0)
    c.pack(fill="x", pady=2)
    return c


def _draw_bar(canvas, pct, color=ACCENT_GREEN):
    canvas.delete("all")
    w = canvas.winfo_width() or 400
    filled = int(w * min(pct, 1.0))
    canvas.create_rectangle(0, 0, filled, 16, fill=color, outline="")
    canvas.create_rectangle(filled, 0, w, 16, fill=BORDER, outline="")


# ═════════════════════════════════════════════════════════════════════════════
# ABA 1 — Race Condition
# ═════════════════════════════════════════════════════════════════════════════
class RaceConditionTab:
    """
    N workers incrementam um contador compartilhado M vezes.
    Com mutex: resultado = N*M (sempre correto).
    Sem mutex: resultado < N*M  (race condition).
    Suporta modo Thread ou Processo.
    """

    def __init__(self, notebook):
        self.frame = tk.Frame(notebook, bg=BG)
        self._mutex_on = True
        self._running  = False
        self._build()

    def _build(self):
        f = self.frame
        # ── título + descrição ───────────────────────────────────────────────
        tk.Label(f, text="Race Condition", bg=BG, fg=ACCENT_RED,
                 font=FONT_H2).pack(anchor="w", padx=12, pady=(10, 0))
        tk.Label(
            f,
            text=(
                "N workers incrementam um contador compartilhado M vezes.\n"
                "Sem mutex: sleep(0) entre leitura e escrita libera o GIL → race!\n"
                "Com mutex: Lock garante acesso exclusivo.\n"
                "⚠  Use 10+ workers e 500+ incr para ver o efeito.\n"
                "   Processos: race real entre núcleos (sem GIL)."
            ),
            bg=BG, fg=MUTED, font=FONT_SMALL, justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        body = tk.Frame(f, bg=BG)
        body.pack(fill="both", expand=True, padx=12)
        body.columnconfigure(0, weight=0, minsize=260)
        body.columnconfigure(1, weight=1)

        # ── controles ────────────────────────────────────────────────────────
        ctrl = tk.LabelFrame(body, text="  Configuração  ", fg=ACCENT_BLUE,
                             bg=PANEL, font=FONT_BODY_B, bd=1, relief="solid")
        ctrl.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=4)
        inner = tk.Frame(ctrl, bg=PANEL, padx=10, pady=8)
        inner.pack(fill="both", expand=True)

        # tipo
        tk.Label(inner, text="Tipo de worker:", bg=PANEL, fg=TEXT,
                 font=FONT_BODY_B).pack(anchor="w", pady=(0, 4))
        self._tipo = tk.StringVar(value="thread")
        for val, lbl in [("thread", "🧵  Threads"), ("process", "⚙️  Processos")]:
            tk.Radiobutton(
                inner, text=lbl, variable=self._tipo, value=val,
                bg=PANEL, fg=TEXT, selectcolor=BG, font=FONT_BODY,
                activebackground=PANEL,
            ).pack(anchor="w")

        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=6)

        self._sp_workers = _spin(inner, "Workers (N):", 2, 20, 5)
        self._sp_incr    = _spin(inner, "Incrementos (M):", 50, 5000, 300, step=50)

        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=6)

        # mutex
        tk.Label(inner, text="Mutex:", bg=PANEL, fg=TEXT,
                 font=FONT_BODY_B).pack(anchor="w")
        self._lbl_mutex = tk.Label(inner, text="● ON", bg=PANEL,
                                   fg=BTN_MUTEX_ON, font=FONT_BODY_B)
        self._lbl_mutex.pack(anchor="w", pady=(2, 4))
        self._btn_mutex = tk.Button(
            inner, text="Desativar Mutex",
            command=self._toggle_mutex,
            bg=BTN_MUTEX_OFF, fg=TEXT_DARK, font=FONT_BODY_B,
            relief="flat", padx=8, pady=4, cursor="hand2",
        )
        self._btn_mutex.pack(fill="x")

        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=6)

        self._btn_start = tk.Button(
            inner, text="▶  Iniciar Demo",
            command=self._run,
            bg=ACCENT_RED, fg=TEXT_DARK, font=FONT_BODY_B,
            relief="flat", padx=8, pady=6, cursor="hand2",
        )
        self._btn_start.pack(fill="x")

        # ── resultado ────────────────────────────────────────────────────────
        res = tk.LabelFrame(body, text="  Resultado  ", fg=ACCENT_RED,
                            bg=PANEL, font=FONT_BODY_B, bd=1, relief="solid")
        res.grid(row=0, column=1, sticky="nsew", pady=4)
        rinner = tk.Frame(res, bg=PANEL, padx=10, pady=8)
        rinner.pack(fill="both", expand=True)

        self._lbl_result = tk.Label(
            rinner, text="Aguardando…", bg=PANEL, fg=TEXT,
            font=("Consolas", 11), justify="left"
        )
        self._lbl_result.pack(anchor="w")
        self._bar = _bar_canvas(rinner)
        self._log_box = _label_log(rinner, h=10)

    # ── lógica ───────────────────────────────────────────────────────────────
    def _toggle_mutex(self):
        self._mutex_on = not self._mutex_on
        if self._mutex_on:
            self._lbl_mutex.config(text="● ON", fg=BTN_MUTEX_ON)
            self._btn_mutex.config(text="Desativar Mutex", bg=BTN_MUTEX_OFF)
        else:
            self._lbl_mutex.config(text="○ OFF", fg=BTN_MUTEX_OFF)
            self._btn_mutex.config(text="Ativar Mutex", bg=BTN_MUTEX_ON)

    def _run(self):
        if self._running:
            return
        try:
            n = int(self._sp_workers.get())
            m = int(self._sp_incr.get())
        except ValueError:
            return
        tipo = self._tipo.get()
        self._running = True
        self._btn_start.config(state="disabled", text="Executando…")
        modo = "COM mutex" if self._mutex_on else "SEM mutex (race!)"
        _log(self._log_box, f"Iniciando: {n} {tipo}s × {m} incr = {n*m} esperado  |  {modo}", "info")

        def run_threads():
            import threading as thr
            counter = [0]
            lock = thr.Lock()
            start = time.perf_counter()

            def worker():
                for _ in range(m):
                    if self._mutex_on:
                        with lock:
                            v = counter[0]; counter[0] = v + 1
                    else:
                        v = counter[0]
                        time.sleep(0)        # libera GIL: outra thread pode ler o mesmo valor!
                        counter[0] = v + 1   # escrita com valor desatualizado = race condition

            workers = [thr.Thread(target=worker, daemon=True, name=f"W-{i+1}") for i in range(n)]
            for w in workers: w.start()

            # progresso
            while any(w.is_alive() for w in workers):
                pct = counter[0] / (n * m)
                self.frame.after(0, lambda p=pct: _draw_bar(self._bar, p,
                    ACCENT_GREEN if self._mutex_on else ACCENT_ORANGE))
                time.sleep(0.05)
            for w in workers: w.join()
            return counter[0], time.perf_counter() - start

        def run_processes():
            import multiprocessing as mp
            counter = mp.Value('i', 0)
            lock    = mp.Lock()
            start   = time.perf_counter()
            if self._mutex_on:
                procs = [mp.Process(target=_mp_worker_safe,   args=(counter, lock, m)) for _ in range(n)]
            else:
                procs = [mp.Process(target=_mp_worker_unsafe, args=(counter, m))       for _ in range(n)]
            for p in procs: p.start()
            while any(p.is_alive() for p in procs):
                pct = counter.value / (n * m)
                self.frame.after(0, lambda p=pct: _draw_bar(self._bar, p,
                    ACCENT_GREEN if self._mutex_on else ACCENT_RED))
                time.sleep(0.05)
            for p in procs: p.join()
            return counter.value, time.perf_counter() - start

        def _background():
            try:
                final, elapsed = run_threads() if tipo == "thread" else run_processes()
                expected = n * m
                ok = final == expected
                color = ACCENT_GREEN if ok else ACCENT_RED
                result_txt = (
                    f"Esperado : {expected}\n"
                    f"Obtido   : {final}\n"
                    f"Diferença: {expected - final}\n"
                    f"Status   : {'✓ CORRETO' if ok else '✗ RACE CONDITION!'}\n"
                    f"Tempo    : {elapsed:.3f}s"
                )
                tag = "ok" if ok else "err"
                self.frame.after(0, lambda: (
                    self._lbl_result.config(text=result_txt, fg=color),
                    _log(self._log_box, f"Final={final}/{expected}  {'OK' if ok else 'RACE CONDITION'}  {elapsed:.3f}s", tag),
                    _draw_bar(self._bar, 1.0, color),
                    self._btn_start.config(state="normal", text="▶  Iniciar Demo"),
                    setattr(self, "_running", False),
                ))
            except Exception as exc:
                self.frame.after(0, lambda: (
                    _log(self._log_box, f"Erro: {exc}", "err"),
                    self._btn_start.config(state="normal", text="▶  Iniciar Demo"),
                    setattr(self, "_running", False),
                ))

        threading.Thread(target=_background, daemon=True).start()


# ═════════════════════════════════════════════════════════════════════════════
# ABA 2 — Deadlock
# ═════════════════════════════════════════════════════════════════════════════
class DeadlockTab:
    """
    Dois threads tentam adquirir dois locks em ordem inversa → deadlock.
    Versão com timeout detecta e reporta o problema.
    """

    def __init__(self, notebook):
        self.frame = tk.Frame(notebook, bg=BG)
        self._threads = []
        self._build()

    def _build(self):
        f = self.frame
        tk.Label(f, text="Deadlock", bg=BG, fg=ACCENT_RED,
                 font=FONT_H2).pack(anchor="w", padx=12, pady=(10, 0))
        tk.Label(
            f,
            text=(
                "Thread A: adquire Lock-1, depois tenta Lock-2.\n"
                "Thread B: adquire Lock-2, depois tenta Lock-1.\n"
                "Ambos ficam bloqueados esperando o outro → deadlock.\n"
                "Com timeout: cada thread desiste após N segundos e reporta."
            ),
            bg=BG, fg=MUTED, font=FONT_SMALL, justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        body = tk.Frame(f, bg=BG)
        body.pack(fill="both", expand=True, padx=12)
        body.columnconfigure(0, weight=0, minsize=260)
        body.columnconfigure(1, weight=1)

        # ── controles ────────────────────────────────────────────────────────
        ctrl = tk.LabelFrame(body, text="  Controle  ", fg=ACCENT_RED,
                             bg=PANEL, font=FONT_BODY_B, bd=1, relief="solid")
        ctrl.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=4)
        inner = tk.Frame(ctrl, bg=PANEL, padx=10, pady=8)
        inner.pack(fill="both", expand=True)

        self._sp_timeout = _spin(inner, "Timeout (s):", 1, 10, 3)

        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=8)

        tk.Button(
            inner, text="💀  Criar Deadlock\n(sem timeout)",
            command=self._deadlock_no_timeout,
            bg=ACCENT_RED, fg=TEXT_DARK, font=FONT_BODY_B,
            relief="flat", padx=8, pady=6, cursor="hand2",
        ).pack(fill="x", pady=2)

        tk.Button(
            inner, text="⏱  Criar com Timeout\n(detecta e resolve)",
            command=self._deadlock_with_timeout,
            bg=ACCENT_ORANGE, fg=TEXT_DARK, font=FONT_BODY_B,
            relief="flat", padx=8, pady=6, cursor="hand2",
        ).pack(fill="x", pady=2)

        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=8)

        # estado visual dos locks
        tk.Label(inner, text="Estado dos Locks:", bg=PANEL, fg=TEXT,
                 font=FONT_BODY_B).pack(anchor="w")
        self._lbl_a = tk.Label(inner, text="Thread A: —", bg=PANEL,
                               fg=MUTED, font=FONT_MONO_S, justify="left")
        self._lbl_a.pack(anchor="w")
        self._lbl_b = tk.Label(inner, text="Thread B: —", bg=PANEL,
                               fg=MUTED, font=FONT_MONO_S, justify="left")
        self._lbl_b.pack(anchor="w")

        # ── log ──────────────────────────────────────────────────────────────
        res = tk.LabelFrame(body, text="  Log  ", fg=ACCENT_RED,
                            bg=PANEL, font=FONT_BODY_B, bd=1, relief="solid")
        res.grid(row=0, column=1, sticky="nsew", pady=4)
        self._log_box = _label_log(tk.Frame(res, bg=PANEL), h=18)
        self._log_box.master.pack(fill="both", expand=True, padx=8, pady=8)

        tk.Label(
            f,
            text="⚠  Sem timeout: os threads ficam bloqueados PARA SEMPRE até fechar a janela.",
            bg=BG, fg=ACCENT_YELLOW, font=FONT_SMALL,
        ).pack(padx=12, pady=4)

    def _deadlock_no_timeout(self):
        lock1 = threading.Lock()
        lock2 = threading.Lock()

        def thread_a():
            self.frame.after(0, lambda: self._lbl_a.config(
                text="Thread A: tentando Lock-1…", fg=ACCENT_BLUE))
            lock1.acquire()
            self.frame.after(0, lambda: (
                self._lbl_a.config(text="Thread A: 🔒 tem Lock-1, quer Lock-2…", fg=ACCENT_ORANGE),
                _log(self._log_box, "Thread A: adquiriu Lock-1, aguardando Lock-2…", "warn"),
            ))
            time.sleep(0.1)
            lock2.acquire()   # ← bloqueia aqui para sempre
            lock2.release(); lock1.release()

        def thread_b():
            self.frame.after(0, lambda: self._lbl_b.config(
                text="Thread B: tentando Lock-2…", fg=ACCENT_BLUE))
            lock2.acquire()
            self.frame.after(0, lambda: (
                self._lbl_b.config(text="Thread B: 🔒 tem Lock-2, quer Lock-1…", fg=ACCENT_ORANGE),
                _log(self._log_box, "Thread B: adquiriu Lock-2, aguardando Lock-1…", "warn"),
            ))
            time.sleep(0.1)
            lock1.acquire()   # ← bloqueia aqui para sempre
            lock1.release(); lock2.release()

        _log(self._log_box, "=== DEADLOCK SEM TIMEOUT ===", "err")
        _log(self._log_box, "Threads criadas — vão travar indefinidamente!", "err")
        ta = threading.Thread(target=thread_a, daemon=True, name="ThreadA-DL")
        tb = threading.Thread(target=thread_b, daemon=True, name="ThreadB-DL")
        ta.start(); tb.start()
        self.frame.after(500, lambda: _log(
            self._log_box, "💀 DEADLOCK! Nenhum thread avança. Feche a janela para encerrar.", "err"
        ))
        self.frame.after(500, lambda: (
            self._lbl_a.config(text="Thread A: 💀 BLOQUEADA esperando Lock-2", fg=ACCENT_RED),
            self._lbl_b.config(text="Thread B: 💀 BLOQUEADA esperando Lock-1", fg=ACCENT_RED),
        ))

    def _deadlock_with_timeout(self):
        try:
            timeout = float(self._sp_timeout.get())
        except ValueError:
            timeout = 3.0
        lock1 = threading.Lock()
        lock2 = threading.Lock()

        def thread_a():
            self.frame.after(0, lambda: _log(
                self._log_box, f"Thread A [{threading.current_thread().ident}]: tentando Lock-1…", "info"
            ))
            lock1.acquire()
            self.frame.after(0, lambda: (
                self._lbl_a.config(text="Thread A: 🔒 Lock-1  ⏳ Lock-2", fg=ACCENT_ORANGE),
                _log(self._log_box, "Thread A: adquiriu Lock-1, tentando Lock-2 (com timeout)…", "warn"),
            ))
            time.sleep(0.05)
            got = lock2.acquire(timeout=timeout)
            if got:
                self.frame.after(0, lambda: (
                    self._lbl_a.config(text="Thread A: ✓ concluiu sem deadlock", fg=ACCENT_GREEN),
                    _log(self._log_box, "Thread A: concluiu normalmente.", "ok"),
                ))
                lock2.release()
            else:
                self.frame.after(0, lambda: (
                    self._lbl_a.config(text="Thread A: ⏱ TIMEOUT — deadlock detectado!", fg=ACCENT_RED),
                    _log(self._log_box, f"Thread A: TIMEOUT após {timeout}s — deadlock detectado, desistiu.", "err"),
                ))
            lock1.release()

        def thread_b():
            self.frame.after(0, lambda: _log(
                self._log_box, f"Thread B [{threading.current_thread().ident}]: tentando Lock-2…", "info"
            ))
            lock2.acquire()
            self.frame.after(0, lambda: (
                self._lbl_b.config(text="Thread B: 🔒 Lock-2  ⏳ Lock-1", fg=ACCENT_ORANGE),
                _log(self._log_box, "Thread B: adquiriu Lock-2, tentando Lock-1 (com timeout)…", "warn"),
            ))
            time.sleep(0.05)
            got = lock1.acquire(timeout=timeout)
            if got:
                self.frame.after(0, lambda: (
                    self._lbl_b.config(text="Thread B: ✓ concluiu sem deadlock", fg=ACCENT_GREEN),
                    _log(self._log_box, "Thread B: concluiu normalmente.", "ok"),
                ))
                lock1.release()
            else:
                self.frame.after(0, lambda: (
                    self._lbl_b.config(text="Thread B: ⏱ TIMEOUT — deadlock detectado!", fg=ACCENT_RED),
                    _log(self._log_box, f"Thread B: TIMEOUT após {timeout}s — deadlock detectado, desistiu.", "err"),
                ))
            lock2.release()

        _log(self._log_box, f"=== DEADLOCK COM TIMEOUT ({timeout}s) ===", "info")
        self._lbl_a.config(text="Thread A: iniciando…", fg=MUTED)
        self._lbl_b.config(text="Thread B: iniciando…", fg=MUTED)
        threading.Thread(target=thread_a, daemon=True, name="ThreadA").start()
        threading.Thread(target=thread_b, daemon=True, name="ThreadB").start()


# ═════════════════════════════════════════════════════════════════════════════
# ABA 3 — Semáforo
# ═════════════════════════════════════════════════════════════════════════════
class SemaphoreTab:
    """
    Semaphore(N) — somente N workers entram na seção crítica ao mesmo tempo.
    Os demais ficam na fila esperando.
    """

    def __init__(self, notebook):
        self.frame = tk.Frame(notebook, bg=BG)
        self._running = False
        self._build()

    def _build(self):
        f = self.frame
        tk.Label(f, text="Semáforo", bg=BG, fg=ACCENT_ORANGE,
                 font=FONT_H2).pack(anchor="w", padx=12, pady=(10, 0))
        tk.Label(
            f,
            text=(
                "threading.Semaphore(N) permite que no máximo N threads\n"
                "entrem na seção crítica simultaneamente. As demais aguardam.\n"
                "Quadrados: 🟢 executando | 🟡 aguardando | ⬜ concluído"
            ),
            bg=BG, fg=MUTED, font=FONT_SMALL, justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        body = tk.Frame(f, bg=BG)
        body.pack(fill="both", expand=True, padx=12)
        body.columnconfigure(0, weight=0, minsize=240)
        body.columnconfigure(1, weight=1)

        ctrl = tk.LabelFrame(body, text="  Configuração  ", fg=ACCENT_ORANGE,
                             bg=PANEL, font=FONT_BODY_B, bd=1, relief="solid")
        ctrl.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=4)
        inner = tk.Frame(ctrl, bg=PANEL, padx=10, pady=8)
        inner.pack(fill="both", expand=True)

        self._sp_slots   = _spin(inner, "Slots (N):", 1, 10, 3)
        self._sp_workers = _spin(inner, "Workers (M):", 2, 20, 10)
        self._sp_delay   = _spin(inner, "Delay (s):", 1, 8, 2)
        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=6)
        self._btn = tk.Button(
            inner, text="▶  Iniciar", command=self._run,
            bg=ACCENT_ORANGE, fg=TEXT_DARK, font=FONT_BODY_B,
            relief="flat", padx=8, pady=6, cursor="hand2",
        )
        self._btn.pack(fill="x")

        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=6)
        tk.Label(inner, text="Ativos (dentro do sem.):", bg=PANEL,
                 fg=TEXT, font=FONT_SMALL).pack(anchor="w")
        self._lbl_active = tk.Label(inner, text="0", bg=PANEL,
                                    fg=ACCENT_ORANGE, font=("Consolas", 22, "bold"))
        self._lbl_active.pack(anchor="w")

        res = tk.LabelFrame(body, text="  Workers  ", fg=ACCENT_ORANGE,
                            bg=PANEL, font=FONT_BODY_B, bd=1, relief="solid")
        res.grid(row=0, column=1, sticky="nsew", pady=4)
        self._grid_frame = tk.Frame(res, bg=PANEL)
        self._grid_frame.pack(fill="both", expand=True, padx=8, pady=8)
        self._log_box = _label_log(res, h=5)

    def _run(self):
        if self._running:
            return
        try:
            slots   = int(self._sp_slots.get())
            workers = int(self._sp_workers.get())
            delay   = float(self._sp_delay.get())
        except ValueError:
            return

        self._running = True
        self._btn.config(state="disabled")
        _log(self._log_box, f"Semáforo({slots})  {workers} workers  delay={delay}s", "info")

        # limpa grid
        for w in self._grid_frame.winfo_children():
            w.destroy()

        sem = threading.Semaphore(slots)
        active_count = [0]
        active_lock  = threading.Lock()
        labels = {}
        cols = min(workers, 10)

        for i in range(workers):
            lbl = tk.Label(
                self._grid_frame, text=f"W{i+1}\n🟡",
                bg=PANEL, fg=TEXT, font=FONT_SMALL, width=5, relief="solid", bd=1
            )
            lbl.grid(row=i // cols, column=i % cols, padx=2, pady=2)
            labels[i] = lbl

        def worker(idx):
            self.frame.after(0, lambda i=idx: labels[i].config(text=f"W{i+1}\n🟡 esp"))
            sem.acquire()
            with active_lock:
                active_count[0] += 1
            self.frame.after(0, lambda i=idx, ac=active_count[0]: (
                labels[i].config(text=f"W{i+1}\n🟢 run", bg="#1a3a1a"),
                self._lbl_active.config(text=str(active_count[0])),
                _log(self._log_box, f"W{i+1} entrou — {active_count[0]}/{slots} ativos", "ok"),
            ))
            time.sleep(delay + random.uniform(-0.3, 0.5))
            with active_lock:
                active_count[0] -= 1
            sem.release()
            self.frame.after(0, lambda i=idx, ac=active_count[0]: (
                labels[i].config(text=f"W{i+1}\n⬜ ok", bg=PANEL),
                self._lbl_active.config(text=str(active_count[0])),
                _log(self._log_box, f"W{i+1} saiu — {ac}/{slots} ativos", "muted"),
            ))

        def _monitor():
            threads = [threading.Thread(target=worker, args=(i,), daemon=True,
                                        name=f"Sem-W{i+1}") for i in range(workers)]
            for t in threads: t.start()
            for t in threads: t.join()
            self.frame.after(0, lambda: (
                self._btn.config(state="normal"),
                _log(self._log_box, "Todos os workers concluíram.", "ok"),
                setattr(self, "_running", False),
            ))

        threading.Thread(target=_monitor, daemon=True).start()


# ═════════════════════════════════════════════════════════════════════════════
# ABA 4 — Barreira (Barrier)
# ═════════════════════════════════════════════════════════════════════════════
class BarrierTab:
    """
    threading.Barrier(N): todas as threads chegam a um ponto de
    sincronização e só avançam quando a última chegar.
    """

    def __init__(self, notebook):
        self.frame = tk.Frame(notebook, bg=BG)
        self._running = False
        self._build()

    def _build(self):
        f = self.frame
        tk.Label(f, text="Barreira (Barrier)", bg=BG, fg=ACCENT_PURPLE,
                 font=FONT_H2).pack(anchor="w", padx=12, pady=(10, 0))
        tk.Label(
            f,
            text=(
                "threading.Barrier(N): cada thread faz sua 'fase 1', depois aguarda\n"
                "na barreira. Quando a última thread chegar, TODAS avançam juntas\n"
                "para a 'fase 2'. Útil para sincronizar etapas em algoritmos paralelos."
            ),
            bg=BG, fg=MUTED, font=FONT_SMALL, justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        body = tk.Frame(f, bg=BG)
        body.pack(fill="both", expand=True, padx=12)
        body.columnconfigure(0, weight=0, minsize=240)
        body.columnconfigure(1, weight=1)

        ctrl = tk.LabelFrame(body, text="  Configuração  ", fg=ACCENT_PURPLE,
                             bg=PANEL, font=FONT_BODY_B, bd=1, relief="solid")
        ctrl.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=4)
        inner = tk.Frame(ctrl, bg=PANEL, padx=10, pady=8)
        inner.pack(fill="both", expand=True)

        self._sp_threads = _spin(inner, "Threads (N):", 2, 12, 5)
        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=6)

        tk.Label(inner, text="Threads na barreira:", bg=PANEL,
                 fg=TEXT, font=FONT_SMALL).pack(anchor="w")
        self._lbl_waiting = tk.Label(inner, text="0 / 0", bg=PANEL,
                                     fg=ACCENT_PURPLE, font=("Consolas", 18, "bold"))
        self._lbl_waiting.pack(anchor="w")

        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=6)
        self._btn = tk.Button(
            inner, text="▶  Iniciar", command=self._run,
            bg=ACCENT_PURPLE, fg=TEXT_DARK, font=FONT_BODY_B,
            relief="flat", padx=8, pady=6, cursor="hand2",
        )
        self._btn.pack(fill="x")

        res = tk.LabelFrame(body, text="  Estado das Threads  ", fg=ACCENT_PURPLE,
                            bg=PANEL, font=FONT_BODY_B, bd=1, relief="solid")
        res.grid(row=0, column=1, sticky="nsew", pady=4)
        self._grid_frame = tk.Frame(res, bg=PANEL)
        self._grid_frame.pack(fill="x", padx=8, pady=8)
        self._bar = _bar_canvas(res)
        self._log_box = _label_log(res, h=8)

    def _run(self):
        if self._running:
            return
        try:
            n = int(self._sp_threads.get())
        except ValueError:
            return

        self._running = True
        self._btn.config(state="disabled")
        _log(self._log_box, f"Barrier({n}) criado — iniciando {n} threads", "info")

        for w in self._grid_frame.winfo_children():
            w.destroy()

        barrier = threading.Barrier(n)
        waiting_count = [0]
        wlock = threading.Lock()
        labels = {}
        cols = min(n, 8)

        for i in range(n):
            lbl = tk.Label(
                self._grid_frame, text=f"T{i+1}\n🔵 f1",
                bg=PANEL, fg=TEXT, font=FONT_SMALL, width=5, relief="solid", bd=1
            )
            lbl.grid(row=i // cols, column=i % cols, padx=2, pady=2)
            labels[i] = lbl

        self._lbl_waiting.config(text=f"0 / {n}")

        def worker(idx):
            tid = threading.current_thread().ident
            # Fase 1
            delay1 = random.uniform(0.5, 3.0)
            self.frame.after(0, lambda i=idx: labels[i].config(
                text=f"T{i+1}\n🔵 f1", bg="#0a1a2e"
            ))
            self.frame.after(0, lambda i=idx, d=delay1: _log(
                self._log_box, f"T{i+1} [TID {tid}]: fase 1 ({d:.1f}s)…", "info"
            ))
            time.sleep(delay1)

            # chega à barreira
            with wlock:
                waiting_count[0] += 1
                wc = waiting_count[0]
            self.frame.after(0, lambda i=idx, wc=wc: (
                labels[i].config(text=f"T{i+1}\n⏸ esp", bg="#2a1a0a"),
                self._lbl_waiting.config(text=f"{wc} / {n}"),
                _draw_bar(self._bar, wc / n, ACCENT_PURPLE),
                _log(self._log_box, f"T{i+1}: NA BARREIRA  ({wc}/{n})", "warn"),
            ))

            barrier.wait()   # ← todas as threads chegam aqui antes de avançar

            with wlock:
                waiting_count[0] -= 1
            # Fase 2
            delay2 = random.uniform(0.3, 1.5)
            self.frame.after(0, lambda i=idx: (
                labels[i].config(text=f"T{i+1}\n🟢 f2", bg="#0a2a0a"),
                _log(self._log_box, f"T{i+1}: PASSOU A BARREIRA → fase 2", "ok"),
            ))
            time.sleep(delay2)
            self.frame.after(0, lambda i=idx: labels[i].config(
                text=f"T{i+1}\n✓ ok", bg=PANEL
            ))

        def _monitor():
            threads = [threading.Thread(target=worker, args=(i,), daemon=True,
                                        name=f"Barrier-T{i+1}") for i in range(n)]
            for t in threads: t.start()
            for t in threads: t.join()
            self.frame.after(0, lambda: (
                _log(self._log_box, "Todas as threads concluíram fase 2.", "ok"),
                self._btn.config(state="normal"),
                setattr(self, "_running", False),
            ))

        threading.Thread(target=_monitor, daemon=True).start()


# ═════════════════════════════════════════════════════════════════════════════
# ABA 5 — Thread Pool
# ═════════════════════════════════════════════════════════════════════════════
class ThreadPoolTab:
    """
    ThreadPoolExecutor(N): N workers fixos processam M tarefas.
    Demonstra reutilização de threads vs criar nova thread por tarefa.
    """

    def __init__(self, notebook):
        self.frame = tk.Frame(notebook, bg=BG)
        self._running = False
        self._build()

    def _build(self):
        f = self.frame
        tk.Label(f, text="Thread Pool (Pool Fixo)", bg=BG, fg=ACCENT_GREEN,
                 font=FONT_H2).pack(anchor="w", padx=12, pady=(10, 0))
        tk.Label(
            f,
            text=(
                "ThreadPoolExecutor(N): cria N threads de uma vez e as reutiliza.\n"
                "Mais eficiente que criar uma thread nova por tarefa (overhead de criação).\n"
                "Compara: Pool fixo vs criar N threads novas para cada lote de tarefas."
            ),
            bg=BG, fg=MUTED, font=FONT_SMALL, justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        body = tk.Frame(f, bg=BG)
        body.pack(fill="both", expand=True, padx=12)
        body.columnconfigure(0, weight=0, minsize=240)
        body.columnconfigure(1, weight=1)

        ctrl = tk.LabelFrame(body, text="  Configuração  ", fg=ACCENT_GREEN,
                             bg=PANEL, font=FONT_BODY_B, bd=1, relief="solid")
        ctrl.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=4)
        inner = tk.Frame(ctrl, bg=PANEL, padx=10, pady=8)
        inner.pack(fill="both", expand=True)

        self._sp_pool  = _spin(inner, "Tamanho do pool:", 1, 16, 4)
        self._sp_tasks = _spin(inner, "Nº de tarefas:", 4, 50, 12)
        self._sp_delay = _spin(inner, "Delay por tarefa (s):", 1, 5, 1)
        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=6)

        tk.Button(
            inner, text="▶  Rodar com Pool",
            command=lambda: self._run(use_pool=True),
            bg=ACCENT_GREEN, fg=TEXT_DARK, font=FONT_BODY_B,
            relief="flat", padx=8, pady=5, cursor="hand2",
        ).pack(fill="x", pady=2)

        tk.Button(
            inner, text="▶  Rodar sem Pool\n(nova thread por tarefa)",
            command=lambda: self._run(use_pool=False),
            bg=ACCENT_ORANGE, fg=TEXT_DARK, font=FONT_BODY_B,
            relief="flat", padx=8, pady=5, cursor="hand2",
        ).pack(fill="x", pady=2)

        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=6)
        self._lbl_stats = tk.Label(
            inner, text="", bg=PANEL, fg=TEXT,
            font=FONT_MONO_S, justify="left"
        )
        self._lbl_stats.pack(anchor="w")

        res = tk.LabelFrame(body, text="  Progresso  ", fg=ACCENT_GREEN,
                            bg=PANEL, font=FONT_BODY_B, bd=1, relief="solid")
        res.grid(row=0, column=1, sticky="nsew", pady=4)
        rinner = tk.Frame(res, bg=PANEL, padx=8, pady=8)
        rinner.pack(fill="both", expand=True)

        tk.Label(rinner, text="Tarefas concluídas:", bg=PANEL,
                 fg=TEXT, font=FONT_SMALL).pack(anchor="w")
        self._bar = _bar_canvas(rinner)
        self._lbl_done = tk.Label(rinner, text="0 / 0", bg=PANEL,
                                  fg=ACCENT_GREEN, font=("Consolas", 18, "bold"))
        self._lbl_done.pack(anchor="w")
        self._log_box = _label_log(rinner, h=12)

    def _run(self, use_pool: bool):
        if self._running:
            return
        try:
            pool_size = int(self._sp_pool.get())
            n_tasks   = int(self._sp_tasks.get())
            delay     = float(self._sp_delay.get())
        except ValueError:
            return

        self._running = True
        mode = f"Pool({pool_size})" if use_pool else f"Nova thread por tarefa"
        _log(self._log_box, f"=== {mode}  {n_tasks} tarefas  delay={delay}s ===", "info")

        done_count = [0]
        done_lock  = threading.Lock()
        start_time = [0.0]

        def task(task_id):
            _log(self._log_box,
                 f"Tarefa {task_id:02d} iniciada  TID={threading.current_thread().ident}", "info")
            time.sleep(delay + random.uniform(-0.2, 0.4))
            with done_lock:
                done_count[0] += 1
                dc = done_count[0]
            pct = dc / n_tasks
            self.frame.after(0, lambda: (
                _draw_bar(self._bar, pct, ACCENT_GREEN if use_pool else ACCENT_ORANGE),
                self._lbl_done.config(text=f"{dc} / {n_tasks}"),
                _log(self._log_box, f"Tarefa {task_id:02d} concluída  ({dc}/{n_tasks})", "ok"),
            ))

        def _background():
            start_time[0] = time.perf_counter()
            if use_pool:
                with ThreadPoolExecutor(max_workers=pool_size) as ex:
                    futures = [ex.submit(task, i + 1) for i in range(n_tasks)]
                    for fut in futures:
                        fut.result()
            else:
                threads = [threading.Thread(target=task, args=(i + 1,), daemon=True)
                           for i in range(n_tasks)]
                for t in threads: t.start()
                for t in threads: t.join()

            elapsed = time.perf_counter() - start_time[0]
            self.frame.after(0, lambda: (
                _log(self._log_box,
                     f"Concluído em {elapsed:.2f}s  ({mode})", "ok"),
                self._lbl_stats.config(
                    text=f"{mode}\nTempo: {elapsed:.2f}s\nTarefas: {n_tasks}"
                ),
                setattr(self, "_running", False),
            ))

        threading.Thread(target=_background, daemon=True).start()


# ═════════════════════════════════════════════════════════════════════════════
# Janela principal de Demos
# ═════════════════════════════════════════════════════════════════════════════
class DemosWindow:
    def __init__(self, parent):
        self.win = tk.Toplevel(parent)
        self.win.title("Demos de Paralelismo")
        self.win.configure(bg=BG)
        self.win.geometry("1000x680")
        self._build()

    def _build(self):
        w = self.win

        bar = tk.Frame(w, bg=PANEL, pady=8)
        bar.pack(fill="x")
        tk.Label(bar, text="🔬  Demos de Paralelismo", bg=PANEL,
                 fg=ACCENT_PURPLE, font=FONT_TITLE).pack(side="left", padx=16)
        tk.Label(bar, text=f"PID: {os.getpid()}", bg=PANEL,
                 fg=MUTED, font=FONT_SMALL).pack(side="left", padx=8)
        tk.Frame(w, bg=BORDER, height=1).pack(fill="x")

        # estilo do Notebook
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Demo.TNotebook",           background=BG, borderwidth=0)
        style.configure("Demo.TNotebook.Tab",
                        background=PANEL, foreground=TEXT,
                        padding=[12, 6], font=FONT_BODY_B)
        style.map("Demo.TNotebook.Tab",
                  background=[("selected", ACCENT_PURPLE)],
                  foreground=[("selected", TEXT_DARK)])

        nb = ttk.Notebook(w, style="Demo.TNotebook")
        nb.pack(fill="both", expand=True, padx=6, pady=6)

        tabs = [
            (RaceConditionTab, "⚡  Race Condition"),
            (DeadlockTab,      "💀  Deadlock"),
            (SemaphoreTab,     "🚦  Semáforo"),
            (BarrierTab,       "🚧  Barreira"),
            (ThreadPoolTab,    "🏊  Thread Pool"),
        ]
        for TabClass, title in tabs:
            tab = TabClass(nb)
            nb.add(tab.frame, text=title)

    def show(self):
        self.win.focus_force()
