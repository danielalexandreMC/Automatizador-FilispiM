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

import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Callable

import gi
gi.require_version('GLib', '2.0')
from gi.repository import GLib

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
from radio_automator.services.time_announce_service import (
    get_time_announce_service, TimeAnnounceService
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
    TIME_ANNOUNCE = "time_announce"


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
        self._current_event_type: str | None = None  # "streaming", "playlist", "file", "folder"
        self._event_content_finished: bool = False  # True cando o contido do evento rematou e Continuidad enche
        self._current_folder_path: str | None = None  # Ruta da carpeta para eventos tipo folder

        # Contadores
        self._events_started: int = 0
        self._continuidad_resumes: int = 0

        # Threading
        self._check_interval_s: float = self.DEFAULT_CHECK_INTERVAL_S
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._play_lock = threading.Lock()  # Evitar double-play (race condition)

        # Estado de Continuidad
        self._continuidad = ContinuidadState()

        # Cache del ID de playlist Continuidad
        self._continuidad_playlist_id: int | None = None

        # Fonte anterior ao Time Announce (para restaurar despois)
        self._prev_source_for_announce: PlaybackSource | None = None
        self._prev_event_type_for_announce: str | None = None

        # Flag para evitar que on_track_finished intente avanzar a cola
        # mentres unha insercion horaria esta pendente de iniciar no fio principal.
        # O timer thread marca True, e _trigger_time_announce marcar False.
        self._announce_pending: bool = False

        # Contador de ticks para diagnósticos periódicos
        self._tick_count: int = 0

        # Contador de reintentos por evento parado inesperadamente
        # (debounce anti-bucle por ficheiro roto). Despois de 3
        # reintentos, pasa a Continuidad en vez de seguir intentando.
        self._event_reload_attempts: int = 0

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

        # Cargar configuracion de insercions horarias
        try:
            get_time_announce_service().load_config()
        except Exception as e:
            print(f"[AutomationEngine] Error cargando config insercions horarias: {e}")

        # Iniciar hilo de check
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="automation")
        self._thread.start()

        # Publicar evento
        get_event_bus().publish("automation.started", {"interval": self._check_interval_s})

        # NOTA: Non chamamos self.tick() aqui.
        # O fío de automatizacion (_run_loop) xa chama tick()
        # como primeira operacion. Chamar tick() aqui e no fío
        # simultaneamente causaba unha race condition que facía
        # que Continuidad se iniciase DUAS VEZES (dous play_file).

        self._notify_status()

    def stop(self):
        """Desactivar el motor de automatizacion."""
        if not self._active:
            return

        self._active = False
        self._stop_event.set()
        self._announce_pending = False

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
        """Logica del tick.

        Protexido por _play_lock para evitar que se execute
        simultaneamente con on_track_finished() ou outro tick.
        Isto previne a double-play race condition.
        """
        now = datetime.now()
        parrilla = get_parrilla_service()
        engine = get_audio_engine()
        queue = get_play_queue()

        # ── 0. Comprobar insercions horarias (solo via timer) ──
        # As insercions horarias por timer SO SE disparan durante Continuidad
        # ou cando non hai fonte activa. Durante un evento de Parrilla/Playlist,
        # as insercións horarias están integradas na playlist como
        # __time_announce__ e soan cando a playlist chega a esa posición.
        ta_service = get_time_announce_service()

        # Diagnóstico periódico (cada ~60s = 12 ticks con interval=5s)
        self._tick_count += 1
        if self._tick_count % 12 == 0:
            ta_interval = getattr(ta_service, '_interval', '?')
            ta_folder = getattr(ta_service, '_folder', '?')
            ta_last_slot = getattr(ta_service, '_last_announced_slot', '?')
            ta_enabled = ta_service.is_enabled
            ta_announcing = ta_service.is_announcing
            print(f"[AutomationEngine] TA diag: enabled={ta_enabled}, announcing={ta_announcing}, "
                  f"interval={ta_interval}min, last_slot={ta_last_slot}, "
                  f"folder={ta_folder[:40] if ta_folder else 'None'}, "
                  f"now={now.strftime('%H:%M:%S')}")

        # Safety: se _is_announcing levou bloqueado mais de 5 minutos,
        # resetear automaticamente (pode quedar bloqueado se o app
        # se pechou inesperadamente durante unha insercion).
        if ta_service.is_announcing:
            ta_service._announce_start_time = getattr(ta_service, '_announce_start_time', None)
            if ta_service._announce_start_time:
                elapsed = (now - ta_service._announce_start_time).total_seconds()
                if elapsed > 60:  # 1 minuto (antes 5min, demasiado longo)
                    print(f"[AutomationEngine] WARNING: _is_announcing bloqueado durante {elapsed:.0f}s, reseteando")
                    ta_service.finish_announcement()

        # Solo disparar por timer se estamos en Continuidad, NONE, ou MANUAL
        # (non durante eventos de Parrilla, onde a playlist ten os seus
        # propios __time_announce__ na posición correcta)
        _timer_allowed = self._source in (
            PlaybackSource.CONTINUIDAD,
            PlaybackSource.NONE,
            PlaybackSource.MANUAL,
        )

        if ta_service.is_enabled and not ta_service.is_announcing and _timer_allowed:
            announce_files = ta_service.check_and_announce(now)
            if announce_files is not None and len(announce_files) > 0:
                # Marcar como pendente para que on_track_finished non avance
                # a cola mentres a insercion se prepara no fio principal.
                self._announce_pending = True
                # NON modificar estado aqui (no fio do timer)!
                # Toda a logica (cambiar fonte, parar engine, reproducir)
                # delegase a _trigger_time_announce via idle_add para
                # executarse de forma atomica no fio principal.
                # check_and_announce() xa gardou _pending_files e marcou
                # _is_announcing = True.
                GLib.idle_add(self._trigger_time_announce, announce_files)
                print(f"[AutomationEngine] Insercion horaria programada: {[os.path.basename(f) for f in announce_files]}")
                return

        # ── 0b. Se estamos a reproducir unha insercion, non facer nada ──
        if self._source == PlaybackSource.TIME_ANNOUNCE:
            # A insercion esta activa; on_track_finished encargase de avanzar
            # ou de rematar cando non quedan ficheiros.
            return

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
            # 2a. Ya estamos en ESTE evento (por ID)?
            if self._current_event_id == current_event.id:
                # 2a-0. O engine parou sen motivo (p.e. debounce anti-bucle
                # por ficheiro roto). Tentar reiniciar o evento unhas veces.
                if engine.state == PlaybackState.STOPPED and not self._event_content_finished:
                    self._event_reload_attempts += 1
                    if self._event_reload_attempts <= 3:
                        print(f"[AutomationEngine] Evento '{current_event.name}' parou "
                              f"inesperadamente, reintento {self._event_reload_attempts}/3")
                        self._reload_current_event_playlist()
                    else:
                        print(f"[AutomationEngine] Evento '{current_event.name}' segue "
                              f"fallando tras 3 reintentos, pasando a Continuidad")
                        self._event_content_finished = True
                        self._stop_playback()
                        self._start_continuidad()
                    return

                # 2a-i. O contido do evento rematou e Continuidad esta enchendo
                if self._event_content_finished:
                    # Solo comprobar se a hora de fin do evento chegou
                    if current_event.end_time and engine.state == PlaybackState.PLAYING:
                        end_time = self._parse_time(current_event.end_time)
                        if now.time() >= end_time:
                            print(f"[AutomationEngine] Evento '{current_event.name}' rematou (gap-fill)")
                            self._stop_playback()
                            self._current_event_id = None
                            self._event_content_finished = False
                            self._current_folder_path = None
                            self._set_source(PlaybackSource.NONE)
                            get_event_bus().publish("automation.event_ended", {
                                "event_id": current_event.id,
                                "event_name": current_event.name,
                            })
                            if not parrilla.get_event_at_time(now):
                                self._start_continuidad()
                    return  # Continuidad segue enchendo ou limpiamos

                # 2a-ii. Evento reproduciendose normalmente (contido non rematado)
                if current_event.end_time and engine.state == PlaybackState.PLAYING:
                    end_time = self._parse_time(current_event.end_time)
                    if now.time() >= end_time:
                        print(f"[AutomationEngine] Evento '{current_event.name}' terminou (hora fin: {current_event.end_time})")
                        self._stop_playback()
                        self._current_event_id = None
                        self._event_content_finished = False
                        self._current_folder_path = None
                        self._set_source(PlaybackSource.NONE)
                        get_event_bus().publish("automation.event_ended", {
                            "event_id": current_event.id,
                            "event_name": current_event.name,
                        })
                        if not parrilla.get_event_at_time(now):
                            self._start_continuidad()
                return  # Seguir reproduciendo el evento actual

            # 2b. Novo evento que iniciar (ou mesmo evento tras reinicio)
            print(f"[AutomationEngine] Iniciando evento: {current_event.name}")
            self._save_continuidad_state()
            self._stop_playback()
            self._event_content_finished = False
            self._current_folder_path = None
            self._start_event(current_event)
            return

        # ── 3. No hay evento programado ahora ──

        # 3a. Estabamos reproduciendo un evento que ya termino?
        if self._source == PlaybackSource.PARRILLA and self._current_event_id is not None:
            print("[AutomationEngine] Evento de parrilla finalizado, parando")
            self._stop_playback()
            self._current_event_id = None
            self._event_content_finished = False
            self._current_folder_path = None
            # Limpar a fonte residual para que _start_continuidad
            # estableza o valor correcto (non PARRILLA)
            self._set_source(PlaybackSource.NONE)
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
        self._event_reload_attempts = 0  # Resetear reintentos para novo evento

        # Streaming - enche todo o evento
        if event.is_streaming and event.streaming_url:
            self._current_event_type = "streaming"
            success = engine.play_stream(event.streaming_url)
            if success:
                self._update_display_title(event.name, event.streaming_url)
                self._publish_event_started(event, "streaming")
                return

        # Playlist (loop ou single)
        if event.playlist_id:
            self._current_event_type = "playlist"
            count = queue.load_playlist(event.playlist_id)
            if count > 0:
                item = queue.play_next()
                if item:
                    self._play_queue_item(item, queue)
                    self._update_display_title(event.name, item.filepath)
                    self._publish_event_started(event, "playlist")
                    return

        # Arquivo local - non fai bucle
        if event.local_file_path:
            self._current_event_type = "file"
            engine.play_file(event.local_file_path)
            self._update_display_title(event.name, event.local_file_path)
            self._publish_event_started(event, "file")
            return

        # Carpeta local - enche todo o evento con audios aleatorios
        if event.local_folder_path:
            self._current_event_type = "folder"
            self._current_folder_path = event.local_folder_path
            from radio_automator.services.folder_scanner import FolderScanner
            scanner = FolderScanner()
            next_file = scanner.get_next_random(event.local_folder_path)
            if next_file:
                engine.play_file(next_file)
                self._update_display_title(event.name, next_file)
                self._publish_event_started(event, "folder")
                return

        print(f"[AutomationEngine] Evento '{event.name}' sin contenido reproducible")

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

        # Establecer fonte a CONTINUIDAD ANTES de reproducir o primeiro item.
        # Isto e critico: se o primeiro item e __time_announce__, o metodo
        # _play_time_announce_from_queue gardara _prev_source = CONTINUIDAD
        # (o valor correcto) en vez do valor residual (PARRILLA/NONE).
        self._set_source(PlaybackSource.CONTINUIDAD)

        # Restaurar al indice guardado
        if self._continuidad.item_index > 0:
            queue.jump_to(self._continuidad.item_index)

        # Iniciar reproduccion
        item = queue.play_next()
        if item:
            self._play_queue_item(item, queue)

            # NOTA: Non restaurar a fonte aqui. Se o item era __time_announce__,
            # _play_time_announce_from_queue xa cambio a fonte a TIME_ANNOUNCE.
            # A fonte volvera a CONTINUIDAD cando a insercion remate e
            # _restore_after_announce sexa chamado. Mentres tanto, o tick
            # detecta TIME_ANNOUNCE en step 0b e non interfire.

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
        self._current_event_type = None
        self._current_folder_path = None

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
        Gestiona el avance en Continuidad, parrilla e garda estado.

        Comportamento por tipo de evento:
        - Streaming: conexion cortouse -> Continuidad (gap-fill)
        - Playlist (loop): avanzar na playlist (enche evento)
        - Playlist (single): avanzar; se remata -> Continuidad (gap-fill)
        - File: audio rematou -> Continuidad (gap-fill, non fai bucle)
        - Folder: obter seguinte audio aleatorio da carpeta (enche evento)

        Protexido por _play_lock para evitar race conditions.
        """
        if not self._active:
            return

        # Se hai unha insercion horaria pendente de iniciar (o timer thread
        # programouna via idle_add pero aind non se executou), non facer
        # nada. _trigger_time_announce encargase de todo cando se execute.
        if self._announce_pending:
            print("[AutomationEngine] on_track_finished: insercion pendente, saltando")
            return

        # Adquirir lock para evitar double-play co tick thread
        if not self._play_lock.acquire(blocking=False):
            # O fío de automatizacion esta executando un tick,
            # que xa se encargara de avanzar a pista.
            print("[AutomationEngine] on_track_finished: lock ocupado, saltando")
            return

        try:
            self._handle_track_finished(track_info)
        finally:
            self._play_lock.release()

    def _handle_track_finished(self, track_info: TrackInfo | None = None):
        """Logica interna de on_track_finished (xa co lock adquirido)."""
        if self._source == PlaybackSource.CONTINUIDAD:
            # Guardar estado antes de avanzar
            self._save_continuidad_state()
            # Avanzar a la siguiente pista en la cola
            queue = get_play_queue()
            next_item = queue.play_next()
            if next_item:
                self._play_queue_item(next_item, queue)
            else:
                # La cola termino, reiniciar (Continuidad es loop)
                print("[AutomationEngine] Continuidad alcanzo el final, reiniciando")
                self._continuidad.item_index = 0
                self._start_continuidad()

        elif self._source == PlaybackSource.TIME_ANNOUNCE:
            # Insercion horaria: reproducir seguinte ficheiro da cola.
            ta_svc = get_time_announce_service()
            next_file = ta_svc.get_next_pending_file()
            if next_file:
                eng = get_audio_engine()
                # Chamada directa (xa estamos no fio principal,
                # despachado via idle_add desde _on_eos).
                success = eng.play_file(next_file)
                if success:
                    get_event_bus().publish("automation.update_title", {
                        "title": "Insercion Horaria",
                        "artist": os.path.basename(next_file),
                    })
                    print(f"[AutomationEngine] Insercion horaria seguinte: {os.path.basename(next_file)}")
                else:
                    # play_file fallou (ficheiro non atopado, etc.)
                    # Non bloquear: intentar o seguinte ou rematar
                    print(f"[AutomationEngine] ERRO reproducindo {os.path.basename(next_file)}, "
                          f"saltando ao seguinte (pendentes: {ta_svc.pending_count})")
                    # Se quedan máis ficheiros, intentar o seguinte inmediatamente
                    if ta_svc.pending_count > 0:
                        self._handle_track_finished(track_info)
                    else:
                        ta_svc.finish_announcement()
                        self._restore_after_announce()
            else:
                # A insercion rematou, volver a fonte anterior
                ta_svc.finish_announcement()
                self._restore_after_announce()

        elif self._source == PlaybackSource.PARRILLA:
            if self._current_event_type == "playlist":
                # Playlist: avanzar a seguinte pista
                queue = get_play_queue()
                next_item = queue.play_next()
                if next_item:
                    self._play_queue_item(next_item, queue)
                    self._update_display_title_for_current_event(next_item.filepath)
                else:
                    # A playlist rematou (cola exaurida)
                    if queue.mode == "loop":
                        print("[AutomationEngine] Playlist loop exaurida inesperadamente, recargando")
                        self._reload_current_event_playlist()
                    else:
                        # Single: rematou -> Continuidad (gap-fill)
                        print("[AutomationEngine] Playlist single terminou, gap-fill con Continuidad")
                        self._event_content_finished = True
                        queue.clear()
                        self._start_continuidad()

            elif self._current_event_type == "file":
                # Audio unico rematou -> Continuidad (non fai bucle)
                print("[AutomationEngine] Audio de evento rematou, gap-fill con Continuidad")
                self._event_content_finished = True
                queue = get_play_queue()
                queue.clear()
                self._start_continuidad()

            elif self._current_event_type == "folder":
                # Carpeta: obter seguinte audio aleatorio da mesma carpeta
                if self._current_folder_path:
                    from radio_automator.services.folder_scanner import FolderScanner
                    scanner = FolderScanner()
                    next_file = scanner.get_next_random(self._current_folder_path)
                    if next_file:
                        engine = get_audio_engine()
                        engine.play_file(next_file)
                        self._update_display_title_for_current_event(next_file)
                    else:
                        print("[AutomationEngine] Carpeta de evento sen arquivos, gap-fill con Continuidad")
                        self._event_content_finished = True
                        queue = get_play_queue()
                        queue.clear()
                        self._start_continuidad()
                else:
                    self._event_content_finished = True
                    self._start_continuidad()

            elif self._current_event_type == "streaming":
                # Streaming: conexion cortouse -> Continuidad (gap-fill)
                print("[AutomationEngine] Streaming de evento cortouse, gap-fill con Continuidad")
                self._event_content_finished = True
                queue = get_play_queue()
                queue.clear()
                self._start_continuidad()

    # ── Insercions horarias ──

    def _trigger_time_announce(self, announce_files):
        """Iniciar insercion horaria. Executase no fio principal (via idle_add).

        TODA a logica de cambio de estado, parada e reproducion do primeiro
        ficheiro faise aqui de forma atomica, no fio principal GTK,
        evitando race conditions co callback on_track_finished.

        Antes chamabase _play_time_announce_first, pero agora fai todo
        o traballo que antes estaba espallado entre o fio do timer
        e idle_adds separados.
        """
        # Se o motor se desactivou mentres esperabamos idle_add, cancelar
        if not self._active:
            get_time_announce_service().finish_announcement()
            self._announce_pending = False
            return

        engine = get_audio_engine()
        queue = get_play_queue()

        # Limpar flag de pendente
        self._announce_pending = False

        # Gardar a fonte actual para restaurar despois
        self._prev_source_for_announce = self._source
        self._prev_event_type_for_announce = self._current_event_type

        # Gardar estado de Continuidad antes de cambiar fonte
        if self._source == PlaybackSource.CONTINUIDAD:
            self._save_continuidad_state()
            self._continuidad.is_playing = False
            get_event_bus().publish("automation.continuidad_stopped", {})

        # Marcar fonte como TIME_ANNOUNCE (no fio principal, seguro)
        self._set_source(PlaybackSource.TIME_ANNOUNCE)

        # Limpar cola e parar engine de forma sincrona (no fio principal)
        queue.clear()
        self._current_event_type = None
        self._current_folder_path = None
        engine.stop()

        # check_and_announce() xa gardou todos os ficheiros en _pending_files.
        # Pop o primeiro para reproducir agora; os demais quedan para on_track_finished.
        ta_svc = get_time_announce_service()
        first_file = ta_svc._pending_files.pop(0) if ta_svc._pending_files else announce_files[0]

        # Reproducir o primeiro ficheiro
        success = engine.play_file(first_file)
        if success:
            get_event_bus().publish("automation.update_title", {
                "title": "Insercion Horaria",
                "artist": os.path.basename(first_file),
            })
            print(f"[AutomationEngine] Insercion horaria iniciada: {[os.path.basename(f) for f in announce_files]}")
        else:
            # O primeiro ficheiro fallou, tentar o seguinte
            print(f"[AutomationEngine] ERRO: non se puido reproducir {os.path.basename(first_file)}")
            if ta_svc.pending_count > 0:
                # Tentar o seguinte ficheiro inmediatamente
                next_file = ta_svc.get_next_pending_file()
                if next_file:
                    engine.play_file(next_file)
                    get_event_bus().publish("automation.update_title", {
                        "title": "Insercion Horaria",
                        "artist": os.path.basename(next_file),
                    })
                    print(f"[AutomationEngine] Insercion horaria (fallback): {os.path.basename(next_file)}")
                    return
            # Todo fallou, rematar insercion
            ta_svc.finish_announcement()
            self._restore_after_announce()
            print("[AutomationEngine] Insercion horaria fallida, restaurando fonte anterior")

    def _restore_after_announce(self):
        """Restaurar a fonte de reproduccion anterior despois dunha insercion horaria.

        Garantiza que _is_announcing sempre se resetea e que a fonte anterior
        se restaura correctamente. Para eventos de parrilla, avanza ao seguinte
        item da cola (que xa estaba posicionado) en vez de recargar a playlist
        enteira dende o principio, para que o loop sexa continuo.
        """
        prev_source = self._prev_source_for_announce
        prev_event_type = self._prev_event_type_for_announce
        self._prev_source_for_announce = None
        self._prev_event_type_for_announce = None

        # Se non hai fonte anterior, volver a NONE ou Continuidad
        if not prev_source:
            print("[AutomationEngine] Insercion horaria rematada, sen fonte anterior")
            self._set_source(PlaybackSource.NONE)
            engine = get_audio_engine()
            if engine.state != PlaybackState.PLAYING:
                self._start_continuidad()
            return

        # Restaurar Continuidad: avanzar ao seguinte item da cola
        # (non recargar a playlist enteira, que causaria bucle infinito
        # se __time_announce__ esta na posicion restaurada).
        if prev_source == PlaybackSource.CONTINUIDAD:
            print("[AutomationEngine] Insercion horaria rematada, retomando Continuidad")
            self._set_source(PlaybackSource.CONTINUIDAD)
            queue = get_play_queue()
            next_item = queue.play_next()
            if next_item:
                self._play_queue_item(next_item, queue)
                # Se o seguinte item e __time_announce__, _play_time_announce_from_queue
                # xa cambio a fonte a TIME_ANNOUNCE. Non restaurar aqui — a fonte
                # volvera a CONTINUIDAD cando esa insercion remate e
                # _restore_after_announce sexa chamado de novo.
            else:
                # Cola exaurida, reiniciar Continuidad dende o principio
                print("[AutomationEngine] Continuidad: cola exaurida tras insercion, reiniciando")
                self._continuidad.item_index = 0
                self._start_continuidad()
            return

        # Restaurar evento de parrilla: avanzar ao seguinte item da cola
        if prev_source == PlaybackSource.PARRILLA and self._current_event_id:
            print("[AutomationEngine] Insercion horaria rematada, retomando evento")
            queue = get_play_queue()
            next_item = queue.play_next()
            if next_item:
                if next_item.filepath == "__time_announce__":
                    self._play_queue_item(next_item, queue)
                    return
                engine = get_audio_engine()
                engine.play_file(next_item.filepath)
                self._set_source(prev_source)
                if prev_event_type:
                    self._current_event_type = prev_event_type
                self._update_display_title_for_current_event(next_item.filepath)
                return
            else:
                # Cola exaurida, recargar playlist (loop)
                print("[AutomationEngine] Insercion horaria rematada, recargando playlist do evento")
                self._reload_current_event_playlist()
                self._set_source(prev_source)
                if prev_event_type:
                    self._current_event_type = prev_event_type
                return

        # Outros casos
        print(f"[AutomationEngine] Insercion horaria rematada, restaurando {prev_source.value}")
        self._set_source(prev_source)

    def _play_queue_item(self, item, queue):
        """Reproducir un item da cola, manexando placeholders de insercion horaria."""
        engine = get_audio_engine()
        if item.filepath == "__time_announce__":
            self._play_time_announce_from_queue(queue)
        elif item.is_streaming:
            engine.play_stream(item.filepath)
        else:
            engine.play_file(item.filepath)

    def _play_time_announce_from_queue(self, queue):
        """Resolver e reproducir unha insercion horaria desde a cola.

        O placeholder __time_announce__ xa esta no current_index da cola.
        Resolve os audios da hora ACTUAL DO SISTEMA, reprodúceos unha vez,
        e ao rematar avanza automaticamente ao seguinte item da cola.
        """
        ta_svc = get_time_announce_service()

        # Resetear estado de announcing por se quedou bloqueado
        # (pode pasar se un reinicio anterior non se completou)
        if ta_svc.is_announcing:
            print("[AutomationEngine] _play_time_announce_from_queue: "
                  "resetear _is_announcing bloqueado")
            ta_svc.finish_announcement()

        ta_svc.load_config()

        # SEMPRE usar a hora actual do sistema
        now = datetime.now()
        files = ta_svc._build_announcement_files(now.hour, now.minute)

        if not files:
            print(f"[AutomationEngine] Insercion horaria: sen audios para {now.hour:02d}:{now.minute:02d}, saltando")
            # Saltar placeholder e avanzar ao seguinte item
            next_item = queue.play_next()
            if next_item:
                if next_item.filepath == "__time_announce__":
                    next_item = queue.play_next()
                if next_item:
                    self._play_queue_item(next_item, queue)
            return

        # Gardar a fonte actual para restaurar despois
        self._prev_source_for_announce = self._source
        self._prev_event_type_for_announce = self._current_event_type
        self._set_source(PlaybackSource.TIME_ANNOUNCE)

        # Gardar os ficheiros pendentes no servizo (o primeiro xa se reproduce)
        if len(files) > 1:
            ta_svc._pending_files = list(files[1:])
        else:
            ta_svc._pending_files = []
        ta_svc._is_announcing = True

        # Reproducir o primeiro ficheiro
        engine = get_audio_engine()
        success = engine.play_file(files[0])
        if not success:
            print(f"[AutomationEngine] ERRO: non se puido reproducir o primeiro ficheiro de insercion")
            ta_svc.finish_announcement()
            # Saltar placeholder e avanzar ao seguinte item da cola
            next_item = queue.play_next()
            if next_item:
                if next_item.filepath == "__time_announce__":
                    next_item = queue.play_next()
                if next_item:
                    self._play_queue_item(next_item, queue)
            else:
                self._restore_after_announce()
            return

        get_event_bus().publish("automation.update_title", {
            "title": "Insercion Horaria",
            "artist": f"{now.hour:02d}:{now.minute:02d}",
        })
        print(f"[AutomationEngine] Insercion horaria desde playlist: {files}")

    # ── Recarga de playlist ──

    def _reload_current_event_playlist(self):
        """Recargar a playlist do evento actual (para loop inesperadamente exaurido
        ou para restaurar tras unha insercion horaria por timer)."""
        if not self._current_event_id:
            return
        session = get_session()
        try:
            ev = session.get(RadioEvent, self._current_event_id)
            if ev and ev.playlist_id:
                self._current_event_type = "playlist"  # Restaurar tipo
                queue = get_play_queue()
                queue.clear()
                count = queue.load_playlist(ev.playlist_id)
                if count > 0:
                    item = queue.play_next()
                    if item:
                        self._play_queue_item(item, queue)
                        # So restaurar fonte se non foi cambiada a TIME_ANNOUNCE
                        if self._source != PlaybackSource.TIME_ANNOUNCE:
                            self._set_source(PlaybackSource.PARRILLA)
                        self._update_display_title_for_current_event(item.filepath)
        finally:
            session.close()

    # ── Display ──

    def _update_display_title(self, title: str, track_path: str = ""):
        """Publicar evento para actualizar o titulo no reproductor."""
        from pathlib import Path as _Path
        artist = _Path(track_path).stem if track_path else ""
        get_event_bus().publish("automation.update_title", {
            "title": title,
            "artist": artist,
        })

    def _update_display_title_for_current_event(self, track_path: str = ""):
        """Actualizar display co nome do evento actual e pista actual."""
        if not self._current_event_id:
            return
        session = get_session()
        try:
            ev = session.get(RadioEvent, self._current_event_id)
            if ev:
                self._update_display_title(ev.name, track_path)
        finally:
            session.close()

    def _publish_event_started(self, event: RadioEvent, content_type: str):
        """Publicar evento de inicio en EventBus."""
        get_event_bus().publish("automation.event_started", {
            "event_id": event.id,
            "event_name": event.name,
            "content_type": content_type,
        })
        self._notify_status()

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
        """Bucle principal del hilo de automatizacion.

        Cada tick esta protexido por _play_lock para evitar
        race conditions con on_track_finished ou ticks simultaneos.
        """
        while not self._stop_event.is_set():
            try:
                with self._play_lock:
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
