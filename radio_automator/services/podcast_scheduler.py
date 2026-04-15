"""
Scheduler de comprobacion periodica de feeds de podcast.
Se ejecuta en un hilo separado con intervalo configurable.
"""

import threading
import time
from datetime import datetime, timezone

from radio_automator.core.config import get_config
from radio_automator.core.event_bus import get_event_bus
from radio_automator.services.podcast_service import get_podcast_service


class PodcastScheduler:
    """
    Planificador que comprueba periodicamente los feeds de podcast.
    El intervalo se lee de la configuracion (podcast_check_interval_hours).
    """

    def __init__(self):
        self._thread: threading.Thread | None = None
        self._running = False
        self._stop_event = threading.Event()

    def start(self):
        """Iniciar el scheduler en un hilo daemon."""
        if self._running:
            return

        config = get_config()
        interval_hours = config.get_int("podcast_check_interval_hours", 24)

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="podcast-scheduler",
        )
        self._thread.start()

        get_event_bus().publish("podcast.scheduler_started", {
            "interval_hours": interval_hours,
        })
        print(f"[PodcastScheduler] Iniciado (intervalo: {interval_hours}h)")

    def stop(self):
        """Detener el scheduler."""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

        get_event_bus().publish("podcast.scheduler_stopped", {})
        print("[PodcastScheduler] Detenido")

    def restart(self):
        """Reiniciar el scheduler (por ejemplo tras cambiar la configuracion)."""
        self.stop()
        self.start()

    def check_now(self):
        """Forzar una comprobacion inmediata (en un hilo separado)."""
        def _worker():
            try:
                service = get_podcast_service()
                result = service.check_all_feeds()
                get_event_bus().publish("podcast.manual_check_complete", result)
            except Exception as e:
                get_event_bus().publish("podcast.manual_check_error", {"error": str(e)})

        thread = threading.Thread(target=_worker, daemon=True, name="podcast-manual-check")
        thread.start()
        return thread

    def _run(self):
        """Bucle principal del scheduler."""
        while self._running:
            # Esperar el intervalo o hasta que se pida parar
            config = get_config()
            interval_hours = config.get_int("podcast_check_interval_hours", 24)
            interval_seconds = interval_hours * 3600

            # Esperar con checks periodicos para poder parar
            waited = 0
            check_increment = 60  # Comprobar cada 60 segundos si debemos parar
            while waited < interval_seconds and self._running:
                self._stop_event.wait(timeout=check_increment)
                waited += check_increment

            if not self._running:
                break

            # Ejecutar comprobacion
            try:
                service = get_podcast_service()
                result = service.check_all_feeds()
                now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
                print(
                    f"[PodcastScheduler] Revision periodica ({now}): "
                    f"{result['downloaded']} descargados, "
                    f"{result['errors']} errores"
                )
            except Exception as e:
                print(f"[PodcastScheduler] Error en revision periodica: {e}")


# ── Instancia global ──
_scheduler: PodcastScheduler | None = None


def get_podcast_scheduler() -> PodcastScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = PodcastScheduler()
    return _scheduler
