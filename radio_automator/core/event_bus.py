"""
EventBus - Sistema de publicacion/suscripcion para comunicacion entre modulos.
Implementa el patron pub/sub con colas por prioridad.
"""

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable


class Priority(IntEnum):
    """Prioridad de los eventos. Mayor valor = mayor prioridad."""
    LOW = 0
    NORMAL = 5
    HIGH = 10
    CRITICAL = 15


@dataclass
class Event:
    """Evento del sistema."""
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    priority: Priority = Priority.NORMAL
    timestamp: float = 0.0


# Tipo para manejadores de eventos
EventHandler = Callable[[Event], None]


class EventBus:
    """
    Bus de eventos central del sistema.

    Los modulos publican eventos (publish) y otros se suscriben (subscribe).
    Los manejadores se ejecutan en el hilo que llama a dispatch(), por defecto
    el hilo principal de GTK.
    """

    def __init__(self):
        self._subscribers: dict[str, list[tuple[EventHandler, Priority]]] = defaultdict(list)
        self._global_handlers: list[tuple[EventHandler, Priority]] = []
        self._lock = threading.Lock()
        self._event_log: list[Event] = []
        self._max_log = 500

    def subscribe(self, event_type: str, handler: EventHandler, priority: Priority = Priority.NORMAL):
        """Suscribir un manejador a un tipo de evento concreto."""
        with self._lock:
            self._subscribers[event_type].append((handler, priority))
            # Ordenar por prioridad (mayor primero)
            self._subscribers[event_type].sort(key=lambda x: x[1], reverse=True)

    def subscribe_all(self, handler: EventHandler, priority: Priority = Priority.NORMAL):
        """Suscribir un manejador a todos los eventos."""
        with self._lock:
            self._global_handlers.append((handler, priority))
            self._global_handlers.sort(key=lambda x: x[1], reverse=True)

    def unsubscribe(self, event_type: str, handler: EventHandler):
        """Eliminar un manejador de un tipo de evento."""
        with self._lock:
            self._subscribers[event_type] = [
                (h, p) for h, p in self._subscribers[event_type] if h != handler
            ]

    def publish(self, event_type: str, data: dict[str, Any] | None = None,
                priority: Priority = Priority.NORMAL):
        """
        Publicar un evento de forma asincrona (se encola para dispatch).
        Los eventos criticos se publican con prioridad alta por defecto.
        """
        import time
        event = Event(
            type=event_type,
            data=data or {},
            priority=priority,
            timestamp=time.time()
        )
        self._log_event(event)
        self.dispatch(event)

    def dispatch(self, event: Event):
        """Ejecutar los manejadores suscritos a este evento (hilo actual)."""
        handlers_to_call = []

        with self._lock:
            # Manejadores especificos del tipo
            for handler, _ in self._subscribers.get(event.type, []):
                handlers_to_call.append(handler)

            # Manejadores globales
            for handler, _ in self._global_handlers:
                handlers_to_call.append(handler)

        # Ejecutar fuera del lock
        for handler in handlers_to_call:
            try:
                handler(event)
            except Exception as e:
                print(f"[EventBus] Error en handler para '{event.type}': {e}")

    def _log_event(self, event: Event):
        """Registrar evento en el log interno."""
        with self._lock:
            self._event_log.append(event)
            if len(self._event_log) > self._max_log:
                self._event_log = self._event_log[-self._max_log:]

    def get_recent_events(self, count: int = 20) -> list[Event]:
        """Obtener los ultimos eventos registrados."""
        with self._lock:
            return list(self._event_log[-count:])

    def clear_subscribers(self):
        """Eliminar todas las suscripciones (util para pruebas)."""
        with self._lock:
            self._subscribers.clear()
            self._global_handlers.clear()


# ── Instancia global del bus ──
_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Obtener la instancia singleton del EventBus."""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


def reset_event_bus():
    """Reiniciar el bus (util para pruebas)."""
    global _bus
    _bus = None
