"""
Motor de Automatizacion (AutomationEngine).
Cerebro del automatizador de radio: coordina Parrilla, AudioEngine y Continuidad.

Logica principal:
- Cada N segundos comprueba la parrilla
- Si hay un evento programado ahora y no se esta reproduciendo, lo inicia
- Si un evento programado termino, lo detiene
- Si no hay evento programado, reproduce Continuidad como fallback
- Si el usuario reproduce algo manualmente, no interfiere hasta que termine
- Persiste el estado de Continuidad (indice, posicion) para reanudar
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Callable

from radio_automator.core.database import (
    get_session, Session,
    Playlist, PlaylistItem, RadioEvent, ContinuityState
)
from radio_automator.core.event_bus import get_event_bus, Event
from radio_automator.services.audio_engine import (
    get_audio_engine, PlaybackState, TrackInfo
)
from radio_automator.services.play_queue import get_play_queue, QueueItem
from radio_automator.services.parrilla_service import (
    get_parrilla_service, ParrillaService
)


# ═══════════════════════════════════════
# Enums y DTOs
# ═══════════════════════════════════════

class PlaybackSource(Enum):
    """Origen de la reproduccion actual."""
    NONE = "none"
    PARRILLA = "parrilla"
    CONTINUIDAD = "continuidad"
    MANUAL = "manual"


@dataclass
class AutomationStatus:
    """Estado actual del motor de automatizacion."""
    is_active: bool = False
    source: PlaybackSource = PlaybackSource.NONE
    event_name: str | None = None
    event_id: int | None = None
    next_event_name: str | None = None
    next_event_time: str | None = None
    continuidad_active: bool = False
    uptime_seconds: float = 0.0
    events_started: int = 0
    continuidad_resumes: int = 0


@dataclass
class ContinuidadState:
    """Estado interno de Continuidad (no persistente)."""
    playlist_id: int | None = None
    item_index: int = 0
    is_playing: bool = False


# ═══════════════════════════════════════
# Excepciones
# ═══════════════════════════════════════

class AutomationError(Exception):
    pass


# ═══════════════════════════════════════
# AutomationEngine
# ═══════════════════════════════════════

class AutomationEngine:
    """
    Motor de automatizacion de la emisora.

    Orquesta la reproduccion automatica basandose en:
    1. Parrilla semanal (eventos programados con hora inicio/fin)
    2. Playlist Continuidad (fallback cuando no hay eventos)
    3. Reproduccion manual del usuario (no interfiere)

    Flujo de decisiones cada tick:
        Hay evento ahora?
        ├── Si: Ya lo estamos reproduciendo?
        │   ├── Si: Comprobar si debe terminar -> detener
        │   └── No: Detener lo actual, iniciar evento
        └── No: Estamos en Continuidad?
            ├── Si: Continuar
            └── No: Iniciar Continuidad

    El usuario puede activar "modo manual" para reproducir lo que quiera.
    Cuando el modo manual termine (stop o fin de cola), la automatizacion
    retomara el control.
    """

    # Intervalo por defecto entre ticks
    DEFAULT_CHECK_INTERVAL_S = 5
    # Intervalo minimo entre ticks
    MIN_CHECK_INTERVAL_S = 2
    # Intervalo maximo entre ticks
    MAX_CHECK_INTERVAL_S = 60

    def __init__(self):
        # Estado
        self._source: PlaybackSource = PlaybackSource.NONE
        self._active: bool = False
        self._current_event_id: int | None = None
        self._started_at: datetime | None = None

        # Contadores
        self._events_started: int = 0
        self._continuidad_resumes: int = 0

        # Threading
        self._check_interval_s: float = self.DEFAULT_CHECK_INTERVAL_S
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        # Estado de Continuidad
        self._continuidad = ContinuidadState()

        # Cache del ID de playlist Continuidad
        self._continuidad_playlist_id: int | None = None

        # Callbacks
        self._on_status_changed: Callable[[AutomationStatus], None] | None = None
        self._on_source_changed: Callable[[PlaybackSource], None] | None = None

    # ── Propiedades ──

    @property
    def is_active(self) -> bool:
        """True si la automatizacion esta activa."""
        return self._active

    @property
    def source(self) -> PlaybackSource:
        """Origen de reproduccion actual."""
        return self._source

    @property
    def current_event_id(self) -> int | None:
        """ID del evento de parrilla reproduciendose, si aplica."""
        return self._current_event_id

    @property
    def check_interval_s(self) -> float:
        return self._check_interval_s

    @property
    def uptime_seconds(self) -> float:
        if not self._started_at:
            return 0.0
        return (datetime.now() - self._started_at).total_seconds()

    # ── Configuracion ──

    def set_callbacks(self,
                     on_status_changed: Callable[[AutomationStatus], None] | None = None,
                     on_source_changed: Callable[[PlaybackSource], None] | None = None):
        """Establecer callbacks de notificacion."""
        self._on_status_changed = on_status_changed
        self._on_source_changed = on_source_changed

    def set_check_interval(self, seconds: float):
        """Establecer intervalo de comprobacion (2-60 segundos)."""
        self._check_interval_s = max(
            self.MIN_CHECK_INTERVAL_S,
            min(self.MAX_CHECK_INTERVAL_S, seconds)
        )

    # ── Ciclo de vida ──

    def start(self):
        """Activar el motor de automatizacion."""
        if self._active:
            return

        self._active = True
        self._started_at = datetime.now()
        self._stop_event.clear()

        print(f"[AutomationEngine] Motor activado (check cada {self._check_interval_s}s)")

        # Obtener ID de playlist Continuidad
        self._load_continuidad_playlist_id()

        # Iniciar hilo de check
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="automation")
        self._thread.start()

        # Publicar evento
        get_event_bus().publish("automation.started", {"interval": self._check_interval_s})

        # Hacer un primer tick inmediato
        self.tick()

        self._notify_status()

    def stop(self):
        """Desactivar el motor de automatizacion."""
        if not self._active:
            return

        self._active = False
        self._stop_event.set()

        # Esperar a que el hilo termine
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

        self._thread = None
        self._source = PlaybackSource.NONE
        self._current_event_id = None

        print("[AutomationEngine] Motor desactivado")

        get_event_bus().publish("automation.stopped", {})

        self._notify_status()

    def restart(self):
        """Reiniciar el motor."""
        self.stop()
        self._events_started = 0
        self._continuidad_resumes = 0
        self.start()

    # ── Tick principal ──

    def tick(self):
        """
        Ciclo principal de automatizacion.
        Se ejecuta periodicamente desde el hilo de automation.
        """
        if not self._active:
            return

        try:
            self._do_tick()
        except Exception as e:
            print(f"[AutomationEngine] Error en tick: {e}")

    def _do_tick(self):
        """Logica del tick."""
        now = datetime.now()
        parrilla = get_parrilla_service()
        engine = get_audio_engine()
        queue = get_play_queue()

        # ── 1. Si el usuario esta reproduciendo algo manualmente, no interferir ──
        if self._source == PlaybackSource.MANUAL:
            # El usuario tomo control. Esperar a que termine o pare.
            if engine.state in (PlaybackState.PLAYING, PlaybackState.PAUSED):
                return
            else:
                # El usuario paro la reproduccion, retomar control
                print("[AutomationEngine] Reproduccion manual finalizada, retomando control")
                self._set_source(PlaybackSource.NONE)

        # ── 2. Comprobar si hay un evento programado ahora ──
        current_event = parrilla.get_event_at_time(now)

        if current_event:
            # 2a. Ya estamos reproduciendo ESTE evento?
            if (self._source == PlaybackSource.PARRILLA
                    and self._current_event_id == current_event.id):
                # Verificar si el evento deberia terminar
                if current_event.end_time and engine.state == PlaybackState.PLAYING:
                    end_time = self._parse_time(current_event.end_time)
                    if now.time() >= end_time:
                        print(f"[AutomationEngine] Evento '{current_event.name}' termino (hora fin: {current_event.end_time})")
                        self._stop_playback()
                        self._current_event_id = None
                        # Publicar evento de fin
                        get_event_bus().publish("automation.event_ended", {
                            "event_id": current_event.id,
                            "event_name": current_event.name,
                        })
                        # El proximo tick iniciara Continuidad o el siguiente evento
                        return
                return  # Seguir reproduciendo el evento actual

            # 2b. Nuevo evento que iniciar
            print(f"[AutomationEngine] Iniciando evento: {current_event.name}")
            self._save_continuidad_state()
            self._stop_playback()
            self._start_event(current_event)
            return

        # ── 3. No hay evento programado ahora ──

        # 3a. Estabamos reproduciendo un evento que ya termino?
        if self._source == PlaybackSource.PARRILLA and self._current_event_id is not None:
            print(f"[AutomationEngine] Evento de parrilla finalizado, parando")
            self._stop_playback()
            self._current_event_id = None
            # Caer al caso 3b para iniciar Continuidad

        # 3b. Iniciar/mantener Continuidad si no estamos ya en ella
        if self._source != PlaybackSource.CONTINUIDAD:
            # Solo iniciar si no hay reproduccion en curso
            if engine.state not in (PlaybackState.PLAYING, PlaybackState.PAUSED):
                print("[AutomationEngine] Sin eventos, iniciando Continuidad")
                self._start_continuidad()

    # ── Gestion de eventos de parrilla ──

    def _start_event(self, event: RadioEvent):
        """Iniciar la reproduccion de un evento de parrilla."""
        engine = get_audio_engine()
        queue = get_play_queue()

        self._set_source(PlaybackSource.PARRILLA)
        self._current_event_id = event.id
        self._events_started += 1

        # Streaming
        if event.is_streaming and event.streaming_url:
            success = engine.play_stream(event.streaming_url)
            if success:
                self._publish_event_started(event, "streaming")
                return

        # Playlist
        if event.playlist_id:
            count = queue.load_playlist(event.playlist_id)
            if count > 0:
                item = queue.play_next()
                if item:
                    if item.is_streaming:
                        engine.play_stream(item.filepath)
                    else:
                        engine.play_file(item.filepath)
                    self._publish_event_started(event, "playlist")
                    return

        # Archivo local
        if event.local_file_path:
            engine.play_file(event.local_file_path)
            self._publish_event_started(event, "file")
            return

        # Carpeta local
        if event.local_folder_path:
            from radio_automator.services.folder_scanner import FolderScanner
            scanner = FolderScanner()
            next_file = scanner.get_next_random(event.local_folder_path)
            if next_file:
                engine.play_file(next_file)
                self._publish_event_started(event, "folder")
                return

        print(f"[AutomationEngine] Evento '{event.name}' sin contenido reproducible")

    def _publish_event_started(self, event: RadioEvent, content_type: str):
        """Publicar evento de inicio en EventBus."""
        get_event_bus().publish("automation.event_started", {
            "event_id": event.id,
            "event_name": event.name,
            "content_type": content_type,
        })
        self._notify_status()

    # ── Gestion de Continuidad ──

    def _start_continuidad(self):
        """Iniciar la reproduccion de Continuidad como fallback."""
        # Verificar que existe la playlist
        playlist_id = self._continuidad_playlist_id
        if playlist_id is None:
            print("[AutomationEngine] No se encontro playlist Continuidad")
            return

        # Verificar que tiene pistas
        session = get_session()
        try:
            items = (
                session.query(PlaylistItem)
                .filter_by(playlist_id=playlist_id)
                .order_by(PlaylistItem.position)
                .all()
            )
            if not items:
                print("[AutomationEngine] Playlist Continuidad vacia")
                return
        finally:
            session.close()

        # Restaurar estado guardado
        self._restore_continuidad_state()

        # Cargar playlist en la cola
        queue = get_play_queue()
        count = queue.load_playlist(playlist_id)
        if count == 0:
            print("[AutomationEngine] No se pudieron resolver pistas de Continuidad")
            return

        # Restaurar al indice guardado
        if self._continuidad.item_index > 0:
            queue.jump_to(self._continuidad.item_index)

        # Iniciar reproduccion
        item = queue.play_next()
        if item:
            engine = get_audio_engine()
            if item.is_streaming:
                engine.play_stream(item.filepath)
            else:
                engine.play_file(item.filepath)

            self._set_source(PlaybackSource.CONTINUIDAD)
            self._continuidad.is_playing = True
            self._continuidad.playlist_id = playlist_id
            self._continuidad_resumes += 1

            print(f"[AutomationEngine] Continuidad iniciada ({count} pistas, indice {self._continuidad.item_index})")

            get_event_bus().publish("automation.continuidad_started", {
                "playlist_id": playlist_id,
                "tracks": count,
            })

            self._notify_status()

    def _stop_continuidad(self):
        """Detener Continuidad y guardar estado."""
        self._save_continuidad_state()
        self._continuidad.is_playing = False

        if self._source == PlaybackSource.CONTINUIDAD:
            get_event_bus().publish("automation.continuidad_stopped", {})

    def _save_continuidad_state(self):
        """Guardar el estado actual de Continuidad en la base de datos."""
        if self._source != PlaybackSource.CONTINUIDAD:
            return

        queue = get_play_queue()
        engine = get_audio_engine()

        # Guardar en memoria
        self._continuidad.item_index = queue.current_index

        # Guardar en base de datos
        playlist_id = self._continuidad_playlist_id
        if playlist_id is None:
            return

        session = get_session()
        try:
            state = (
                session.query(ContinuityState)
                .filter_by(playlist_id=playlist_id)
                .first()
            )
            if state:
                state.current_item_index = queue.current_index
                state.current_file_position_ms = engine.track_info.position_ms
                state.is_playing = False  # Se guarda porque se va a pausar/parar
                state.updated_at = datetime.now()
                session.commit()
        except Exception as e:
            print(f"[AutomationEngine] Error guardando estado Continuidad: {e}")
            session.rollback()
        finally:
            session.close()

    def _restore_continuidad_state(self):
        """Restaurar el estado de Continuidad desde la base de datos."""
        playlist_id = self._continuidad_playlist_id
        if playlist_id is None:
            return

        session = get_session()
        try:
            state = (
                session.query(ContinuityState)
                .filter_by(playlist_id=playlist_id)
                .first()
            )
            if state:
                self._continuidad.item_index = state.current_item_index
                print(f"[AutomationEngine] Estado Continuidad restaurado: indice {state.current_item_index}")
        finally:
            session.close()

    def _load_continuidad_playlist_id(self):
        """Cargar el ID de la playlist Continuidad desde la base de datos."""
        session = get_session()
        try:
            pl = (
                session.query(Playlist)
                .filter_by(is_system=True, name="Continuidad")
                .first()
            )
            if pl:
                self._continuidad_playlist_id = pl.id
        finally:
            session.close()

    # ── Control de reproduccion ──

    def _stop_playback(self):
        """Detener toda la reproduccion actual."""
        engine = get_audio_engine()
        queue = get_play_queue()

        if self._source == PlaybackSource.CONTINUIDAD:
            self._stop_continuidad()

        engine.stop()
        queue.clear()

    def set_manual_mode(self):
        """
        Activar modo manual. La automatizacion no interferira
        hasta que el usuario pare la reproduccion.
        """
        if self._source == PlaybackSource.PARRILLA:
            # Detener el evento de parrilla pero no la automatizacion
            self._save_continuidad_state()
            self._stop_playback()
        elif self._source == PlaybackSource.CONTINUIDAD:
            self._stop_continuidad()

        self._current_event_id = None
        self._set_source(PlaybackSource.MANUAL)

        print("[AutomationEngine] Modo manual activado")
        get_event_bus().publish("automation.manual_mode", {})

        self._notify_status()

    def exit_manual_mode(self):
        """Salir del modo manual y retomar la automatizacion."""
        if self._source != PlaybackSource.MANUAL:
            return

        self._set_source(PlaybackSource.NONE)
        print("[AutomationEngine] Modo manual desactivado")
        self.tick()  # Ejecutar tick inmediato

    # ── Callback de fin de pista ──

    def on_track_finished(self, track_info: TrackInfo | None = None):
        """
        Callback invocado cuando termina una pista.
        Gestiona el avance en Continuidad y guarda estado.
        """
        if not self._active:
            return

        if self._source == PlaybackSource.CONTINUIDAD:
            # Guardar estado antes de avanzar
            self._save_continuidad_state()
            # Avanzar a la siguiente pista en la cola
            queue = get_play_queue()
            next_item = queue.play_next()
            if next_item:
                engine = get_audio_engine()
                if next_item.is_streaming:
                    engine.play_stream(next_item.filepath)
                else:
                    engine.play_file(next_item.filepath)
            else:
                # La cola termino, reiniciar (Continuidad es loop)
                print("[AutomationEngine] Continuidad alcanzo el final, reiniciando")
                self._continuidad.item_index = 0
                self._start_continuidad()

    # ── Estado y notificaciones ──

    def _set_source(self, source: PlaybackSource):
        """Cambiar el origen de reproduccion y notificar."""
        old = self._source
        self._source = source

        if old != source:
            print(f"[AutomationEngine] Fuente: {old.value} -> {source.value}")
            if self._on_source_changed:
                try:
                    self._on_source_changed(source)
                except Exception as e:
                    print(f"[AutomationEngine] Error en callback: {e}")

            get_event_bus().publish("automation.source_changed", {
                "old_source": old.value,
                "new_source": source.value,
            })

    def _notify_status(self):
        """Notificar cambio de estado a callbacks."""
        if self._on_status_changed:
            try:
                self._on_status_changed(self.get_status())
            except Exception:
                pass

    def get_status(self) -> AutomationStatus:
        """Obtener el estado actual del motor de automatizacion."""
        # Proximo evento
        parrilla = get_parrilla_service()
        next_event = parrilla.get_next_event()
        next_name = next_event.name if next_event else None
        next_time = next_event.start_time if next_event else None

        # Nombre del evento actual
        event_name = None
        if self._current_event_id:
            session = get_session()
            try:
                ev = session.get(RadioEvent, self._current_event_id)
                if ev:
                    event_name = ev.name
            finally:
                session.close()

        return AutomationStatus(
            is_active=self._active,
            source=self._source,
            event_name=event_name,
            event_id=self._current_event_id,
            next_event_name=next_name,
            next_event_time=next_time,
            continuidad_active=(self._source == PlaybackSource.CONTINUIDAD),
            uptime_seconds=self.uptime_seconds,
            events_started=self._events_started,
            continuidad_resumes=self._continuidad_resumes,
        )

    # ── Hilo de automatizacion ──

    def _run_loop(self):
        """Bucle principal del hilo de automatizacion."""
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception as e:
                print(f"[AutomationEngine] Error en bucle: {e}")

            # Esperar al proximo tick o hasta que se pida parar
            self._stop_event.wait(self._check_interval_s)

    # ── Utilidades ──

    @staticmethod
    def _parse_time(time_str: str) -> time:
        """Convertir 'HH:MM' a objeto time."""
        parts = time_str.split(":")
        return time(int(parts[0]), int(parts[1]))


# ── Instancia global ──
_automation: AutomationEngine | None = None


def get_automation_engine() -> AutomationEngine:
    """Obtener la instancia singleton del AutomationEngine."""
    global _automation
    if _automation is None:
        _automation = AutomationEngine()
    return _automation


def reset_automation_engine():
    """Reiniciar el motor (para tests)."""
    global _automation
    if _automation:
        _automation.stop()
    _automation = None
