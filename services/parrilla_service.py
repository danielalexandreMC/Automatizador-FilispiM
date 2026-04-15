"""
Servicio de Parrilla Semanal.
Gestiona la programacion semanal de la emisora:
- Obtener eventos de un dia o semana completa
- Detectar conflictos entre eventos (solapamientos horarios)
- Determinar que evento deberia estar sonando ahora
- Auto-iniciar eventos segun la parrilla
- Calcular posiciones y dimensiones para el grid visual
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, date, timezone
from enum import Enum
from typing import Any

from radio_automator.core.database import (
    get_session, Session, RadioEvent, Playlist
)
from radio_automator.core.event_bus import get_event_bus, Event, Priority
from radio_automator.services.audio_engine import (
    get_audio_engine, PlaybackState
)
from radio_automator.services.play_queue import get_play_queue


# ═══════════════════════════════════════
# Constantes
# ═══════════════════════════════════════

DAY_NAMES = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
DAY_NAMES_SHORT = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]
HOUR_START = 0  # Hora de inicio del grid
HOUR_END = 24   # Hora de fin del grid
SLOT_HEIGHT_MINUTES = 30  # Cada slot representa 30 min


# ═══════════════════════════════════════
# DTOs
# ═══════════════════════════════════════

@dataclass
class GridEvent:
    """Evento posicionado en el grid para la UI."""
    event_id: int
    name: str
    start_time: str      # "HH:MM"
    end_time: str | None  # "HH:MM" o None
    day_index: int       # 0=Lun ... 6=Dom
    is_streaming: bool
    is_active: bool
    playlist_id: int | None
    playlist_name: str | None = None
    streaming_url: str | None = None
    repeat_pattern: str = "weekly"

    # Posicion en el grid (calculadas)
    start_minutes: int = 0   # Minutos desde medianoche (para el grid)
    duration_minutes: int = 60  # Duracion en minutos

    # Estado
    is_now_playing: bool = False
    is_past: bool = False
    is_future: bool = True
    has_conflict: bool = False

    @property
    def start_hour_float(self) -> float:
        """Hora de inicio como float (ej: 14.5 para 14:30)."""
        h, m = divmod(self.start_minutes, 60)
        return h + m / 60.0

    @property
    def end_hour_float(self) -> float:
        """Hora de fin como float."""
        total = self.start_minutes + self.duration_minutes
        h, m = divmod(total, 60)
        return h + m / 60.0

    @property
    def color(self) -> str:
        """Color segun tipo de evento."""
        if self.is_streaming:
            return "#FB8C00"  # Naranja
        if self.is_now_playing:
            return "#E53935"  # Rojo
        return "#1E88E5"  # Azul


@dataclass
class ConflictInfo:
    """Informacion de un conflicto entre eventos."""
    event1_name: str
    event2_name: str
    day_index: int
    overlap_start: str  # "HH:MM"
    overlap_end: str    # "HH:MM"
    severity: str = "warning"  # warning | error


@dataclass
class NowPlayingInfo:
    """Informacion de lo que se esta reproduciendo ahora."""
    is_active: bool = False
    event: RadioEvent | None = None
    time_until_next: timedelta | None = None
    next_event: RadioEvent | None = None


@dataclass
class WeekData:
    """Datos completos de una semana para el grid."""
    week_start: date  # Lunes de la semana
    days: list[list[GridEvent]] = field(default_factory=list)  # 7 listas (Lun-Dom)
    conflicts: list[ConflictInfo] = field(default_factory=list)
    now_playing: NowPlayingInfo | None = None
    total_events: int = 0


# ═══════════════════════════════════════
# Excepciones
# ═══════════════════════════════════════

class ParrillaError(Exception):
    pass


class ParrillaConflictError(ParrillaError):
    """Hay conflictos en la parrilla."""
    pass


# ═══════════════════════════════════════
# ParrillaService
# ═══════════════════════════════════════

class ParrillaService:
    """
    Servicio de gestion de la parrilla semanal.

    Organiza los eventos del sistema en una vista semanal de 7 dias x 24 horas,
    detecta conflictos y gestiona la reproduccion automatica.
    """

    def __init__(self):
        self._auto_scheduler_active = False
        self._current_event_id: int | None = None
        self._check_interval_ms = 30000  # Comprobar cada 30 segundos

    # ── Consultas ──

    def get_events_for_day(self, day_index: int,
                           session: Session | None = None) -> list[RadioEvent]:
        """
        Obtener todos los eventos activos para un dia de la semana.
        day_index: 0=Lunes, 1=Martes, ..., 6=Domingo
        """
        close = False
        if session is None:
            session = get_session()
            close = True

        try:
            events = (
                session.query(RadioEvent)
                .filter(RadioEvent.is_active == True)
                .order_by(RadioEvent.start_time)
                .all()
            )

            result = []
            for ev in events:
                days = ev.week_days_list
                if day_index < len(days) and days[day_index]:
                    result.append(ev)

            return result

        finally:
            if close:
                session.close()

    def get_events_for_week(self,
                           week_start: date | None = None,
                           session: Session | None = None) -> WeekData:
        """
        Obtener todos los eventos organizados por dia para una semana completa.

        week_start: Fecha del lunes de la semana (None = semana actual)
        """
        if week_start is None:
            week_start = self._get_week_start(date.today())

        close = False
        if session is None:
            session = get_session()
            close = True

        try:
            all_events = (
                session.query(RadioEvent)
                .filter(RadioEvent.is_active == True)
                .order_by(RadioEvent.start_time, RadioEvent.end_time)
                .all()
            )

            # Cache de nombres de playlists
            playlist_names = {}
            playlists = session.query(Playlist).all()
            for pl in playlists:
                playlist_names[pl.id] = pl.name

            # Hora actual para marcar estados
            now = datetime.now()
            now_day_index = self._date_to_day_index(now.date())
            now_minutes = now.hour * 60 + now.minute

            # Organizar por dia
            days: list[list[GridEvent]] = [[] for _ in range(7)]

            for ev in all_events:
                days_list = ev.week_days_list
                for day_idx in range(min(7, len(days_list))):
                    if not days_list[day_idx]:
                        continue

                    start_mins = self._time_to_minutes(ev.start_time)
                    end_mins = self._time_to_minutes(ev.end_time) if ev.end_time else start_mins + 60

                    # Duracion minima 30 min
                    duration = max(30, end_mins - start_mins)
                    # Si cruza medianoche, limitar a 24h
                    if start_mins + duration > 24 * 60:
                        duration = 24 * 60 - start_mins

                    grid_ev = GridEvent(
                        event_id=ev.id,
                        name=ev.name,
                        start_time=ev.start_time,
                        end_time=ev.end_time,
                        day_index=day_idx,
                        is_streaming=ev.is_streaming,
                        is_active=ev.is_active,
                        playlist_id=ev.playlist_id,
                        playlist_name=playlist_names.get(ev.playlist_id),
                        streaming_url=ev.streaming_url,
                        repeat_pattern=ev.repeat_pattern or "weekly",
                        start_minutes=start_mins,
                        duration_minutes=duration,
                    )

                    # Marcar estado temporal
                    if day_idx == now_day_index:
                        if now_minutes >= start_mins and now_minutes < start_mins + duration:
                            grid_ev.is_now_playing = True
                        elif now_minutes >= start_mins + duration:
                            grid_ev.is_past = True
                        else:
                            grid_ev.is_future = True

                    days[day_idx].append(grid_ev)

            # Detectar conflictos
            conflicts = self._detect_conflicts(days)

            # Info de "ahora"
            now_playing = self._get_now_playing_info(
                days, now_day_index, now_minutes, session
            )

            # Total eventos unicos
            unique_ids = set()
            for day_events in days:
                for ge in day_events:
                    unique_ids.add(ge.event_id)

            return WeekData(
                week_start=week_start,
                days=days,
                conflicts=conflicts,
                now_playing=now_playing,
                total_events=len(unique_ids),
            )

        finally:
            if close:
                session.close()

    def get_now_playing(self) -> NowPlayingInfo:
        """Obtener info de lo que deberia estar reproduciendose ahora."""
        now = datetime.now()
        week_data = self.get_events_for_week()
        if week_data.now_playing:
            return week_data.now_playing
        return NowPlayingInfo()

    def get_event_at_time(self, target_time: datetime,
                          session: Session | None = None) -> RadioEvent | None:
        """
        Obtener el evento que deberia estar activo en un momento dado.
        """
        day_index = self._date_to_day_index(target_time.date())
        target_minutes = target_time.hour * 60 + target_time.minute

        events = self.get_events_for_day(day_index, session=session)

        for ev in events:
            start = self._time_to_minutes(ev.start_time)
            if ev.end_time:
                end = self._time_to_minutes(ev.end_time)
            else:
                end = start + 60

            # Streaming: hora de fin obligatoria
            if ev.is_streaming and not ev.end_time:
                continue

            if start <= target_minutes < end:
                return ev

        return None

    def get_next_event(self, from_time: datetime | None = None,
                       session: Session | None = None) -> RadioEvent | None:
        """Obtener el proximo evento programado a partir de un momento dado."""
        if from_time is None:
            from_time = datetime.now()

        day_index = self._date_to_day_index(from_time.date())
        from_minutes = from_time.hour * 60 + from_time.minute

        events = self.get_events_for_day(day_index, session=session)

        # Buscar el proximo evento que empiece despues de from_time
        candidates = []
        for ev in events:
            start = self._time_to_minutes(ev.start_time)
            if ev.is_streaming and not ev.end_time:
                continue
            if start > from_minutes:
                candidates.append((start, ev))

        if candidates:
            candidates.sort(key=lambda x: x[0])
            return candidates[0][1]

        # Si no hay mas hoy, buscar manana (con wrap a lunes)
        for offset in range(1, 8):
            next_day_index = (day_index + offset) % 7
            next_events = self.get_events_for_day(next_day_index, session=session)
            if next_events:
                # Devolver el primero del dia siguiente
                for ev in next_events:
                    if ev.is_streaming and not ev.end_time:
                        continue
                    return ev
                return next_events[0]

        return None

    def get_time_until_next(self) -> timedelta | None:
        """Tiempo restante hasta el proximo evento."""
        now = datetime.now()
        next_ev = self.get_next_event(now)
        if not next_ev:
            return None

        parts = next_ev.start_time.split(":")
        if len(parts) != 2:
            return None

        try:
            h, m = int(parts[0]), int(parts[1])
            next_time = now.replace(hour=h, minute=m, second=0, microsecond=0)

            # Si la hora ya paso hoy, es manana
            if next_time <= now:
                next_time += timedelta(days=1)
                # Ajustar si es otro dia de la semana
                day_index = self._date_to_day_index(now.date())
                days_list = next_ev.week_days_list
                for offset in range(1, 8):
                    check_idx = (day_index + offset) % 7
                    if check_idx < len(days_list) and days_list[check_idx]:
                        next_time = now + timedelta(days=offset)
                        next_time = next_time.replace(hour=h, minute=m, second=0, microsecond=0)
                        break

            return next_time - now
        except (ValueError, IndexError):
            return None

    # ── Deteccion de conflictos ──

    def detect_conflicts(self, day_index: int | None = None) -> list[ConflictInfo]:
        """
        Detectar solapamientos entre eventos.
        Si day_index es None, comprueba toda la semana.
        """
        if day_index is not None:
            days_data = {day_index: self.get_events_for_day(day_index)}
        else:
            days_data = {}
            for d in range(7):
                days_data[d] = self.get_events_for_day(d)

        all_conflicts = []
        for d_idx, events in days_data.items():
            # Ordenar por hora de inicio
            sorted_events = sorted(events, key=lambda e: e.start_time)

            for i in range(len(sorted_events)):
                for j in range(i + 1, len(sorted_events)):
                    ev1 = sorted_events[i]
                    ev2 = sorted_events[j]

                    conflict = self._check_overlap(ev1, ev2, d_idx)
                    if conflict:
                        all_conflicts.append(conflict)

        return all_conflicts

    def _check_overlap(self, ev1: RadioEvent, ev2: RadioEvent,
                       day_index: int) -> ConflictInfo | None:
        """Comprobar si dos eventos se solapan."""
        start1 = self._time_to_minutes(ev1.start_time)
        end1 = self._time_to_minutes(ev1.end_time) if ev1.end_time else start1 + 60
        start2 = self._time_to_minutes(ev2.start_time)
        end2 = self._time_to_minutes(ev2.end_time) if ev2.end_time else start2 + 60

        overlap_start = max(start1, start2)
        overlap_end = min(end1, end2)

        if overlap_start < overlap_end:
            return ConflictInfo(
                event1_name=ev1.name,
                event2_name=ev2.name,
                day_index=day_index,
                overlap_start=self._minutes_to_time(overlap_start),
                overlap_end=self._minutes_to_time(overlap_end),
            )

        return None

    def _detect_conflicts(self,
                          days: list[list[GridEvent]]) -> list[ConflictInfo]:
        """Detectar conflictos en datos del grid ya organizados."""
        conflicts = []

        for day_idx, day_events in enumerate(days):
            for i in range(len(day_events)):
                for j in range(i + 1, len(day_events)):
                    ev1 = day_events[i]
                    ev2 = day_events[j]

                    end1 = ev1.start_minutes + ev1.duration_minutes
                    end2 = ev2.start_minutes + ev2.duration_minutes

                    overlap_start = max(ev1.start_minutes, ev2.start_minutes)
                    overlap_end = min(end1, end2)

                    if overlap_start < overlap_end:
                        ev1.has_conflict = True
                        ev2.has_conflict = True

                        conflicts.append(ConflictInfo(
                            event1_name=ev1.name,
                            event2_name=ev2.name,
                            day_index=day_idx,
                            overlap_start=self._minutes_to_time(overlap_start),
                            overlap_end=self._minutes_to_time(overlap_end),
                        ))

        return conflicts

    # ── Auto-scheduler ──

    def check_and_play_event(self, force: bool = False) -> NowPlayingInfo:
        """
        Comprobar si hay un evento que deba reproducirse ahora y arrancarlo.
        Se llama periodicamente (cada 30s) o manualmente (force=True).
        """
        now = datetime.now()
        current_event = self.get_event_at_time(now)

        engine = get_audio_engine()

        # Si hay un evento actual
        if current_event:
            # Si ya estamos reproduciendo este evento, no hacer nada
            if self._current_event_id == current_event.id:
                if engine.state in (PlaybackState.PLAYING, PlaybackState.PAUSED):
                    return self.get_now_playing()

            # Cambio de evento: parar lo anterior y arrancar el nuevo
            self._start_event(current_event)
            return self.get_now_playing()

        # No hay evento ahora
        if not force:
            # Si estabamos reproduciendo un evento que ya termino, parar
            if self._current_event_id is not None:
                # Comprobar si el evento anterior termino
                prev_ev_time = self._get_event_end_time(self._current_event_id)
                if prev_ev_time and now.time() >= prev_ev_time:
                    print(f"[Parrilla] Evento {self._current_event_id} terminado, deteniendo")
                    self._stop_current_event()

        return self.get_now_playing()

    def _start_event(self, event: RadioEvent):
        """Iniciar la reproduccion de un evento."""
        engine = get_audio_engine()
        queue = get_play_queue()

        print(f"[Parrilla] Iniciando evento: {event.name}")

        # Detener reproduccion actual
        engine.stop()
        queue.clear()

        # Streaming
        if event.is_streaming and event.streaming_url:
            success = engine.play_stream(event.streaming_url)
            if success:
                self._current_event_id = event.id
                get_event_bus().publish("parrilla.event_started", {
                    "event_id": event.id,
                    "event_name": event.name,
                    "type": "streaming",
                })
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
                    self._current_event_id = event.id
                    get_event_bus().publish("parrilla.event_started", {
                        "event_id": event.id,
                        "event_name": event.name,
                        "type": "playlist",
                        "tracks": count,
                    })
                    return

        # Archivo local unico
        if event.local_file_path:
            engine.play_file(event.local_file_path)
            self._current_event_id = event.id
            return

        # Carpeta local
        if event.local_folder_path:
            from radio_automator.services.folder_scanner import FolderScanner
            scanner = FolderScanner()
            next_file = scanner.get_next_random(event.local_folder_path)
            if next_file:
                engine.play_file(next_file)
                self._current_event_id = event.id
                return

        print(f"[Parrilla] No se pudo iniciar evento {event.name}: sin contenido")

    def _stop_current_event(self):
        """Detener el evento actual."""
        engine = get_audio_engine()
        engine.stop()
        get_play_queue().clear()

        if self._current_event_id:
            get_event_bus().publish("parrilla.event_stopped", {
                "event_id": self._current_event_id,
            })

        self._current_event_id = None

    def _get_event_end_time(self, event_id: int) -> time | None:
        """Obtener la hora de fin de un evento."""
        session = get_session()
        try:
            ev = session.get(RadioEvent, event_id)
            if ev and ev.end_time:
                parts = ev.end_time.split(":")
                return time(int(parts[0]), int(parts[1]))
        finally:
            session.close()
        return None

    def start_auto_scheduler(self):
        """Iniciar el scheduler automatico (comprueba cada 30s)."""
        if self._auto_scheduler_active:
            return

        self._auto_scheduler_active = True
        self._run_scheduler_check()

    def stop_auto_scheduler(self):
        """Detener el scheduler automatico."""
        self._auto_scheduler_active = False

    def _run_scheduler_check(self):
        """Ejecutar comprobacion periodica."""
        if not self._auto_scheduler_active:
            return

        try:
            import gi
            gi.require_version('GLib', '2.0')
            from gi.repository import GLib
            self.check_and_play_event()
            GLib.timeout_add(self._check_interval_ms, self._run_scheduler_check)
        except ImportError:
            # Sin GLib, usar threading
            import threading
            def _loop():
                while self._auto_scheduler_active:
                    self.check_and_play_event()
                    threading.Event().wait(self._check_interval_ms / 1000)
            t = threading.Thread(target=_loop, daemon=True)
            t.start()

    def _get_now_playing_info(self,
                             days: list[list[GridEvent]],
                             now_day: int,
                             now_minutes: int,
                             session: Session) -> NowPlayingInfo:
        """Calcular info de reproduccion actual."""
        # Buscar evento que suena ahora
        current = None
        for ge in days[now_day]:
            if ge.is_now_playing:
                current = ge
                break

        if not current:
            return NowPlayingInfo()

        # Buscar el proximo evento
        next_ev = None
        all_today = sorted(days[now_day], key=lambda e: e.start_minutes)
        for ge in all_today:
            if ge.start_minutes > now_minutes:
                next_ev = ge
                break

        time_until = None
        if next_ev:
            delta_mins = next_ev.start_minutes - now_minutes
            time_until = timedelta(minutes=delta_mins)

        # Obtener evento real de la DB
        event = session.get(RadioEvent, current.event_id)

        return NowPlayingInfo(
            is_active=True,
            event=event,
            time_until_next=time_until,
            next_event=session.get(RadioEvent, next_ev.event_id) if next_ev else None,
        )

    # ── Utilidades de tiempo ──

    @staticmethod
    def _time_to_minutes(time_str: str) -> int:
        """Convertir 'HH:MM' a minutos desde medianoche."""
        try:
            parts = time_str.split(":")
            if len(parts) != 2:
                return 0
            h, m = int(parts[0]), int(parts[1])
            return max(0, min(24 * 60 - 1, h * 60 + m))
        except (ValueError, IndexError):
            return 0

    @staticmethod
    def _minutes_to_time(minutes: int) -> str:
        """Convertir minutos desde medianoche a 'HH:MM'."""
        minutes = max(0, min(24 * 60 - 1, minutes))
        h, m = divmod(minutes, 60)
        return f"{h:02d}:{m:02d}"

    @staticmethod
    def _date_to_day_index(d: date) -> int:
        """
        Convertir una fecha a indice de dia de la semana.
        0=Lunes, 1=Martes, ..., 6=Domingo.
        """
        # Python: weekday() = 0=Lun, 6=Dom
        return d.weekday()

    @staticmethod
    def _get_week_start(d: date) -> date:
        """Obtener el lunes de la semana que contiene la fecha dada."""
        return d - timedelta(days=d.weekday())

    @staticmethod
    def get_week_start_date(week_offset: int = 0) -> date:
        """Obtener lunes de la semana actual o desplazada."""
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        return monday + timedelta(weeks=week_offset)

    @staticmethod
    def format_time_range(start: str, end: str | None) -> str:
        """Formatear rango horario para mostrar."""
        if end:
            return f"{start} - {end}"
        return f"{start} (sin fin)"


# ── Instancia global ──
_service: ParrillaService | None = None


def get_parrilla_service() -> ParrillaService:
    """Obtener la instancia singleton del ParrillaService."""
    global _service
    if _service is None:
        _service = ParrillaService()
    return _service


def reset_parrilla_service():
    """Reiniciar el servicio (para tests)."""
    global _service
    if _service:
        _service.stop_auto_scheduler()
    _service = None
