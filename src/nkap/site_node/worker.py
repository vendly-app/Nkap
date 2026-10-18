"""Fil d'exécution qui synchronise le site en arrière-plan.

Toutes les ``interval`` secondes (60 par défaut), ou immédiatement sur demande, il lance un
passage de synchronisation. Une erreur inattendue est journalisée sans arrêter le fil :
le site continue de travailler et réessaiera.
"""

from __future__ import annotations

import logging
import threading

from nkap.site_node.sync_sender import SyncSender

logger = logging.getLogger(__name__)


class SyncWorker:
    def __init__(self, sender: SyncSender, interval_seconds: float = 60.0) -> None:
        self._sender = sender
        self._interval = interval_seconds
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="nkap-sync", daemon=True)
        self._thread.start()

    def trigger(self) -> None:
        """Demande un passage sans attendre la fin de l'intervalle."""
        self._wake.set()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._sender.sync_once()
            except Exception:  # le fil ne doit jamais mourir
                logger.exception("Erreur inattendue pendant la synchronisation.")
            self._wake.wait(self._interval)
            self._wake.clear()
