"""
Servicio de Notificaciones para Radio Automator.
Proporciona notificaciones desktop (GLib/Gio) y notificaciones inline (toast).
Se integra con EventBus para reaccionar automaticamente a eventos del sistema.

Tipos de notificacion:
- INFO: Informativas (azul)
- SUCCESS: Exitosas (verde)
- WARNING: Advertencias (naranja)
- ERROR: Errores criticos (rojo)

La notificacion desktop requiere que la aplicacion tenga un window presente.
Las notificaciones toast se muestran como overlay en la ventana principal.
"""

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from gi.repository import GLib

from radio_automator.core.logger import get_logger


logger = get_logger("notification_service")


class NotificationType(Enum):
    """Tipos de notificacion."""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class Notification:
    """Una notificacion individual."""
    message: str
    title: str = ""
    type: NotificationType = NotificationType.INFO
    timeout_ms: int = 4000
    persistent: bool = False  # Si True, no se auto-descarta

    # Timestamps (se asignan al crear)
    created_at: float = 0.0
    id: str = ""

    def __post_init__(self):
        if not self.created_at:
            import time
            self.created_at = time.time()
        if not self.id:
            import uuid
            self.id = str(uuid.uuid4())[:8]

    def __repr__(self) -> str:
        return f"Notification({self.type.value}: '{self.message[:40]}')"


# ── Colores CSS por tipo ──
NOTIFICATION_COLORS = {
    NotificationType.INFO: {
        "border": "var(--ra-info)",
        "icon": "dialog-information-symbolic",
        "label": "Info",
    },
    NotificationType.SUCCESS: {
        "border": "var(--ra-success)",
        "icon": "emblem-ok-symbolic",
        "label": "OK",
    },
    NotificationType.WARNING: {
        "border": "var(--ra-warning)",
        "icon": "dialog-warning-symbolic",
        "label": "Aviso",
    },
    NotificationType.ERROR: {
        "border": "var(--ra-error)",
        "icon": "dialog-error-symbolic",
        "label": "Error",
    },
}


class NotificationService:
    """
    Servicio central de notificaciones.

    Gestiona dos canales de notificacion:
    1. Desktop: notificaciones nativas del sistema via Gio.Notification
    2. Toast: overlay visual dentro de la ventana de la aplicacion

    Se integra con EventBus para emitir notificaciones automaticas cuando
    ocurren eventos importantes del sistema (errores, tracks, streams, etc.).
    """

    def __init__(self):
        self._on_toast_callback: Callable[[Notification], None] | None = None
        self._lock = threading.Lock()
        self._history: list[Notification] = []
        self._max_history = 100
        self._desktop_enabled = True
        self._toast_enabled = True
        self._muted_event_types: set[str] = set()
        self._event_bus_subscriptions: list[tuple[str, Callable]] = []

    @property
    def history(self) -> list[Notification]:
        """Historial de notificaciones emitidas."""
        with self._lock:
            return list(self._history)

    @property
    def desktop_enabled(self) -> bool:
        return self._desktop_enabled

    @property
    def toast_enabled(self) -> bool:
        return self._toast_enabled

    def set_desktop_enabled(self, enabled: bool) -> None:
        """Activar/desactivar notificaciones desktop."""
        self._desktop_enabled = enabled

    def set_toast_enabled(self, enabled: bool) -> None:
        """Activar/desactivar notificaciones toast."""
        self._toast_enabled = enabled

    def set_on_toast_callback(self, callback: Callable[[Notification], None]) -> None:
        """
        Establecer callback para notificaciones toast.
        Se llama desde el hilo principal de GTK.
        """
        self._on_toast_callback = callback

    def notify(
        self,
        message: str,
        title: str = "",
        type: NotificationType = NotificationType.INFO,
        timeout_ms: int = 4000,
        persistent: bool = False,
    ) -> Notification:
        """
        Emitir una notificacion por todos los canales activos.

        Args:
            message: Texto principal de la notificacion.
            title: Titulo opcional (por defecto: "Radio Automator").
            type: Tipo de notificacion (INFO, SUCCESS, WARNING, ERROR).
            timeout_ms: Tiempo de auto-descarte en milisegundos.
            persistent: Si True, no se descarta automaticamente.

        Returns:
            La notificacion creada.
        """
        if not title:
            title = "Radio Automator"

        notification = Notification(
            message=message,
            title=title,
            type=type,
            timeout_ms=timeout_ms,
            persistent=persistent,
        )

        # Guardar en historial
        with self._lock:
            self._history.append(notification)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

        # Emitir por canales activos
        if self._desktop_enabled:
            self._send_desktop(notification)

        if self._toast_enabled and self._on_toast_callback:
            self._dispatch_toast(notification)

        # Log de la notificacion
        log_fn = {
            NotificationType.INFO: logger.info,
            NotificationType.SUCCESS: logger.info,
            NotificationType.WARNING: logger.warning,
            NotificationType.ERROR: logger.error,
        }
        log_fn.get(type, logger.info)("[Notificacion] %s: %s", title, message)

        return notification

    def info(self, message: str, title: str = "", timeout_ms: int = 3000) -> Notification:
        """Notificacion informativa."""
        return self.notify(message, title=title, type=NotificationType.INFO, timeout_ms=timeout_ms)

    def success(self, message: str, title: str = "", timeout_ms: int = 3000) -> Notification:
        """Notificacion de exito."""
        return self.notify(message, title=title, type=NotificationType.SUCCESS, timeout_ms=timeout_ms)

    def warning(self, message: str, title: str = "", timeout_ms: int = 5000) -> Notification:
        """Notificacion de advertencia."""
        return self.notify(message, title=title, type=NotificationType.WARNING, timeout_ms=timeout_ms)

    def error(self, message: str, title: str = "", timeout_ms: int = 8000) -> Notification:
        """Notificacion de error."""
        return self.notify(message, title=title, type=NotificationType.ERROR, timeout_ms=timeout_ms, persistent=True)

    def _send_desktop(self, notification: Notification) -> None:
        """
        Enviar notificacion desktop nativa via Gio.
        Se ejecuta en hilo separado para no bloquear.
        """
        try:
            def _send():
                try:
                    notification_id = f"radio-automator-{notification.id}"
                    n = GLib.Notification.new(notification.title)
                    n.set_body(notification.message)

                    # Icono por tipo
                    colors = NOTIFICATION_COLORS.get(notification.type, NOTIFICATION_COLORS[NotificationType.INFO])
                    n.set_icon(GLib.ThemedIcon.new(colors["icon"]))

                    # Prioridad (HIGH para errores y warnings)
                    if notification.type in (NotificationType.ERROR, NotificationType.WARNING):
                        n.set_priority(GLib.NotificationPriority.HIGH)

                    # TODO: Se necesita acceso a la instancia de Gtk.Application
                    # para llamar a app.send_notification(id, notification).
                    # Esto se conectara desde main.py con set_application().

                    logger.debug("Notificacion desktop preparada: %s", notification.message[:50])
                except Exception as e:
                    logger.debug("No se pudo enviar notificacion desktop: %s", e)

            # Ejecutar en thread para no bloquear
            threading.Thread(target=_send, daemon=True).start()

        except Exception as e:
            logger.debug("Error preparando notificacion desktop: %s", e)

    def _dispatch_toast(self, notification: Notification) -> None:
        """Despachar notificacion toast via GLib.idle_add para thread-safety."""
        try:
            callback = self._on_toast_callback
            if callback:
                GLib.idle_add(callback, notification)
        except Exception:
            pass

    def dismiss(self, notification_id: str) -> None:
        """
        Descartar una notificacion toast por ID.
        Se envia como evento para que el widget ToastOverlay lo elimine.
        """
        from radio_automator.core.event_bus import get_event_bus
        get_event_bus().publish("notification.dismiss", {"id": notification_id})

    def dismiss_all(self) -> None:
        """Descartar todas las notificaciones toast visibles."""
        from radio_automator.core.event_bus import get_event_bus
        get_event_bus().publish("notification.dismiss_all", {})

    def clear_history(self) -> None:
        """Limpiar el historial de notificaciones."""
        with self._lock:
            self._history.clear()

    def subscribe_to_events(self) -> None:
        """
        Suscribirse a eventos del EventBus para emitir notificaciones
        automaticas cuando ocurren eventos importantes del sistema.
        """
        from radio_automator.core.event_bus import get_event_bus, Event

        bus = get_event_bus()

        def on_event(event: Event):
            """Handler global de eventos para notificaciones automaticas."""
            event_type = event.type
            data = event.data

            # No notificar eventos silenciados
            if event_type in self._muted_event_types:
                return

            # ── Errores de audio ──
            if event_type == "audio.error":
                self.error(
                    message=data.get("message", "Error de audio desconocido"),
                    title="Error de Audio",
                )

            # ── Inicio/Final de pista ──
            elif event_type == "audio.track_started" and data.get("title"):
                # Solo notificar si viene de streaming o parrilla
                source = data.get("source", "")
                if source in ("streaming", "parrilla"):
                    self.info(
                        message=f"Reproduciendo: {data['title']}",
                        title="Pista iniciada",
                        timeout_ms=2000,
                    )

            # ── Stream conectado/desconectado ──
            elif event_type == "parrilla.event_started":
                name = data.get("name", "Evento")
                etype = data.get("type", "normal")
                if etype == "streaming":
                    self.info(
                        message=f"Stream conectado: {name}",
                        title="Stream Activo",
                        timeout_ms=3000,
                    )

            elif event_type == "parrilla.event_stopped":
                name = data.get("name", "Evento")
                self.info(
                    message=f"Evento finalizado: {name}",
                    title="Programacion",
                    timeout_ms=2000,
                )

            # ── Podcast descargado ──
            elif event_type == "podcast.downloaded":
                title = data.get("title", "Episodio")
                feed = data.get("feed", "Feed")
                self.success(
                    message=f"{title} ({feed})",
                    title="Podcast descargado",
                    timeout_ms=3000,
                )

            # ── Errores de podcast ──
            elif event_type == "podcast.error":
                self.warning(
                    message=data.get("message", "Error descargando podcast"),
                    title="Error de Podcast",
                )

            # ── Feed RSS comprobado ──
            elif event_type == "feed.checked":
                new_count = data.get("new_episodes", 0)
                if new_count > 0:
                    self.info(
                        message=f"{new_count} episodio(s) nuevo(s)",
                        title=data.get("feed_name", "Feed RSS"),
                        timeout_ms=3000,
                    )

        # Suscribir a eventos especificos
        specific_events = [
            "audio.error",
            "audio.track_started",
            "parrilla.event_started",
            "parrilla.event_stopped",
            "podcast.downloaded",
            "podcast.error",
            "feed.checked",
        ]

        for event_type in specific_events:
            bus.subscribe(event_type, on_event)
            self._event_bus_subscriptions.append((event_type, on_event))

        logger.info("Suscripcion a %d eventos del EventBus para notificaciones", len(specific_events))

    def unsubscribe_from_events(self) -> None:
        """Cancelar suscripciones a eventos del EventBus."""
        from radio_automator.core.event_bus import get_event_bus
        bus = get_event_bus()
        for event_type, handler in self._event_bus_subscriptions:
            try:
                bus.unsubscribe(event_type, handler)
            except Exception:
                pass
        self._event_bus_subscriptions.clear()

    def mute_event(self, event_type: str) -> None:
        """Silenciar un tipo de evento para que no genere notificaciones."""
        self._muted_event_types.add(event_type)

    def unmute_event(self, event_type: str) -> None:
        """Reactivar notificaciones para un tipo de evento."""
        self._muted_event_types.discard(event_type)


# ── Instancia global ──
_notification_service: NotificationService | None = None


def get_notification_service() -> NotificationService:
    """Obtener la instancia singleton del NotificationService."""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service


def reset_notification_service():
    """Reiniciar el servicio de notificaciones (util para pruebas)."""
    global _notification_service
    if _notification_service:
        _notification_service.unsubscribe_from_events()
    _notification_service = None
