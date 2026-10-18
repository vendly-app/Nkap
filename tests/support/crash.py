"""Lancer et tuer brutalement un processus qui travaille sur une base (T17).

Fonctionne sous Linux comme sous Windows (``Popen.kill`` = arrêt immédiat du processus,
comme une coupure de courant pour le programme, sans lui laisser le temps de finir).
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from sqlalchemy import URL

TESTS_DIR = Path(__file__).resolve().parent.parent
KILLED_EXIT_CODE = 137
"""Code de sortie des scénarios qui meurent volontairement (comme un processus tué)."""


def _command(scenario: str, *args: str | URL) -> list[str]:
    rendered = [a.render_as_string(hide_password=False) if isinstance(a, URL) else a for a in args]
    return [sys.executable, "-m", "support.crash_child", scenario, *rendered]


def _env() -> dict[str, str]:
    existing = os.environ.get("PYTHONPATH", "")
    return {**os.environ, "PYTHONPATH": os.pathsep.join(p for p in (str(TESTS_DIR), existing) if p)}


def start(scenario: str, *args: str | URL) -> subprocess.Popen[str]:
    return subprocess.Popen(
        _command(scenario, *args),
        env=_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def wait_ready(process: subprocess.Popen[str], timeout: float = 60.0) -> None:
    """Attend que le processus annonce « ready » (il a commencé à écrire)."""
    line: list[str] = []
    reader = threading.Thread(target=lambda: line.append(process.stdout.readline()))  # type: ignore[union-attr]
    reader.start()
    reader.join(timeout)
    if not line or line[0].strip() != "ready":
        process.kill()
        _, err = process.communicate(timeout=10)
        raise AssertionError(f"Le processus n'a pas démarré correctement :\n{err}")


def run_until_exit(scenario: str, *args: str | URL, timeout: float = 60.0) -> int:
    """Lance un scénario qui se termine seul (mort volontaire) et renvoie son code de sortie."""
    process = start(scenario, *args)
    _, err = process.communicate(timeout=timeout)
    if process.returncode != KILLED_EXIT_CODE:
        raise AssertionError(f"Code de sortie inattendu {process.returncode} :\n{err}")
    return process.returncode


def kill(process: subprocess.Popen[str]) -> None:
    process.kill()
    process.communicate(timeout=30)
