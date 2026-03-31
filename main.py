#!/usr/bin/env python3
"""
Demo de Paralelismo — Ponto de entrada principal.

Uso normal:
    python main.py

Modo receptor (lançado automaticamente pelo modo Processos):
    python main.py --receiver <porta>
"""
import sys
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--receiver":
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 55555
        from gui.receiver_window import ReceiverWindow
        win = ReceiverWindow(port=port)
        win.run()
    else:
        from gui.launcher import LauncherWindow
        win = LauncherWindow()
        win.run()


if __name__ == "__main__":
    main()
