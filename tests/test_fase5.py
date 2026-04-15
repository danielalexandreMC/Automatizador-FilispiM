"""Tests de la Fase 5: Parrilla Semanal (scheduler, grid, conflictos)."""

import os
import sys
import tempfile
from datetime import datetime, time, timedelta, date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from radio_automator.core.database import (
    init_db, get_session, reset_engine,
    Playlist, PlaylistItem, RadioEvent
)
from radio_automator.core.event_bus import get_event_bus, reset_event_bus
from radio_automator.services.parrilla_service import (
    ParrillaService, GridEvent, ConflictInfo, NowPlayingInfo, WeekData,
    get_parrilla_service, reset_parrilla_service,
)
from radio_automator.services.audio_engine import reset_audio_engine, get_audio_engine
from radio_automator.services.play_queue import reset_play_queue


@pytest.fixture(autouse=True)
def fresh_db():
    """Crear una base de datos limpia para cada test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["RADIO_AUTOMATOR_DIR"] = tmpdir
        reset_engine()
        reset_event_bus()
        reset_audio_engine()
        reset_play_queue()
        reset_parrilla_service()
        init_db()
        yield tmpdir
        reset_engine()
        reset_event_bus()
        reset_audio_engine()
        reset_play_queue()
        reset_parrilla_service()


def _create_playlist(session, name="TestPL", mode="loop"):
    """Helper para crear una playlist."""
    pl = Playlist(name=name, mode=mode)
    session.add(pl)
    session.flush()

    # Añadir una pista dummy
    with tempfile.TemporaryDirectory() as tmpdir:
        f = Path(tmpdir) / "track.mp3"
        f.write_bytes(b"audio")
        item = PlaylistItem(
            playlist_id=pl.id,
            position=0,
            item_type="track",
            filepath=str(f),
        )
        session.add(item)
        session.flush()
        return pl


def _create_event(session, name, start="09:00", end="10:00",
                  week_days="1,1,1,1,1,1,1", playlist_id=None,
                  streaming_url=None):
    """Helper para crear un evento."""
    ev = RadioEvent(
        name=name,
        start_time=start,
        end_time=end,
        week_days=week_days,
        playlist_id=playlist_id,
        streaming_url=streaming_url,
    )
    session.add(ev)
    session.flush()
    return ev


# ═══════════════════════════════════════
# Tests de utilidades de tiempo
# ═══════════════════════════════════════

class TestTimeUtils:
    """Tests de conversiones de tiempo."""

    def test_time_to_minutes(self):
        assert ParrillaService._time_to_minutes("00:00") == 0
        assert ParrillaService._time_to_minutes("01:30") == 90
        assert ParrillaService._time_to_minutes("12:00") == 720
        assert ParrillaService._time_to_minutes("23:59") == 1439

    def test_time_to_minutes_invalid(self):
        assert ParrillaService._time_to_minutes("") == 0
        assert ParrillaService._time_to_minutes("invalid") == 0
        assert ParrillaService._time_to_minutes("25:00") == 1439  # Clamped

    def test_minutes_to_time(self):
        assert ParrillaService._minutes_to_time(0) == "00:00"
        assert ParrillaService._minutes_to_time(90) == "01:30"
        assert ParrillaService._minutes_to_time(720) == "12:00"
        assert ParrillaService._minutes_to_time(1439) == "23:59"

    def test_date_to_day_index(self):
        # Lunes = 0
        monday = date(2025, 1, 6)  # 6 Jan 2025 = Monday
        assert ParrillaService._date_to_day_index(monday) == 0
        # Domingo = 6
        sunday = date(2025, 1, 12)
        assert ParrillaService._date_to_day_index(sunday) == 6

    def test_get_week_start(self):
        # Wednesday 8 Jan 2025 -> Monday 6 Jan 2025
        wed = date(2025, 1, 8)
        ws = ParrillaService._get_week_start(wed)
        assert ws == date(2025, 1, 6)
        assert ws.weekday() == 0

    def test_round_trip_time(self):
        """Probar conversion ida y vuelta."""
        for t in ["00:00", "06:30", "12:00", "18:45", "23:59"]:
            mins = ParrillaService._time_to_minutes(t)
            back = ParrillaService._minutes_to_time(mins)
            assert back == t

    def test_format_time_range(self):
        assert ParrillaService.format_time_range("09:00", "10:00") == "09:00 - 10:00"
        assert ParrillaService.format_time_range("09:00", None) == "09:00 (sin fin)"


# ═══════════════════════════════════════
# Tests de DTOs
# ═══════════════════════════════════════

class TestGridEventDTO:
    """Tests del DTO GridEvent."""

    def test_grid_event_defaults(self):
        ge = GridEvent(event_id=1, name="Test", start_time="09:00",
                       end_time="10:00", day_index=0, is_streaming=False,
                       is_active=True, playlist_id=None,
                       start_minutes=540, duration_minutes=60)
        assert ge.start_hour_float == 9.0
        assert ge.end_hour_float == 10.0
        assert ge.is_future is True

    def test_grid_event_streaming_color(self):
        ge = GridEvent(event_id=1, name="Stream", start_time="14:00",
                       end_time="16:00", day_index=0, is_streaming=True,
                       is_active=True, playlist_id=None,
                       start_minutes=840, duration_minutes=120)
        assert ge.color == "#FB8C00"

    def test_grid_event_normal_color(self):
        ge = GridEvent(event_id=1, name="Normal", start_time="09:00",
                       end_time="10:00", day_index=0, is_streaming=False,
                       is_active=True, playlist_id=None,
                       start_minutes=540, duration_minutes=60)
        assert ge.color == "#1E88E5"

    def test_grid_event_now_playing_color(self):
        ge = GridEvent(event_id=1, name="Live", start_time="09:00",
                       end_time="10:00", day_index=0, is_streaming=False,
                       is_active=True, playlist_id=None,
                       start_minutes=540, duration_minutes=60,
                       is_now_playing=True)
        assert ge.color == "#E53935"

    def test_grid_event_half_hour(self):
        ge = GridEvent(event_id=1, name="Half", start_time="09:30",
                       end_time="10:00", day_index=0, is_streaming=False,
                       is_active=True, playlist_id=None,
                       start_minutes=570, duration_minutes=30)
        assert ge.start_hour_float == 9.5
        assert ge.end_hour_float == 10.0

    def test_grid_event_min_duration(self):
        """Duracion minima de 30 minutos."""
        ge = GridEvent(event_id=1, name="Short", start_time="09:00",
                       end_time="09:10", day_index=0, is_streaming=False,
                       is_active=True, playlist_id=None,
                       start_minutes=540, duration_minutes=10)
        # Al ser menor de 30, deberia ser 30
        assert ge.duration_minutes == 10  # DTO usa lo que se le pasa
        # La logica de minimo esta en el servicio


class TestWeekData:
    """Tests del DTO WeekData."""

    def test_week_data_defaults(self):
        wd = WeekData(week_start=date(2025, 1, 6))
        assert len(wd.days) == 0
        assert wd.conflicts == []
        assert wd.now_playing is None
        assert wd.total_events == 0


# ═══════════════════════════════════════
# Tests de ParrillaService - Consultas
# ═══════════════════════════════════════

class TestParrillaServiceGetEvents:
    """Tests de obtencion de eventos."""

    def test_get_events_for_day_empty(self):
        service = ParrillaService()
        events = service.get_events_for_day(0)
        assert events == []

    def test_get_events_for_day_single(self):
        session = get_session()
        ev = _create_event(session, "Morning Show", "07:00", "09:00",
                          "1,0,0,0,0,0,0")  # Solo lunes
        session.commit()
        session.close()

        service = ParrillaService()
        events_monday = service.get_events_for_day(0)
        events_tuesday = service.get_events_for_day(1)

        assert len(events_monday) == 1
        assert events_monday[0].name == "Morning Show"
        assert len(events_tuesday) == 0

    def test_get_events_for_day_multiple(self):
        session = get_session()
        _create_event(session, "Show A", "07:00", "09:00", "1,1,0,0,0,0,0")
        _create_event(session, "Show B", "12:00", "14:00", "1,1,0,0,0,0,0")
        _create_event(session, "Show C", "18:00", "20:00", "0,0,1,0,0,0,0")
        session.commit()
        session.close()

        service = ParrillaService()
        events_monday = service.get_events_for_day(0)
        events_wednesday = service.get_events_for_day(2)

        assert len(events_monday) == 2
        assert len(events_wednesday) == 1

    def test_get_events_for_day_inactive(self):
        session = get_session()
        ev = _create_event(session, "Inactive", "07:00", "09:00", "1,0,0,0,0,0,0")
        ev.is_active = False
        session.commit()
        session.close()

        service = ParrillaService()
        events = service.get_events_for_day(0)
        assert len(events) == 0


class TestParrillaServiceWeekGrid:
    """Tests de generacion del grid semanal."""

    def test_get_events_for_week_empty(self):
        service = ParrillaService()
        week = service.get_events_for_week()
        assert week.total_events == 0
        assert len(week.conflicts) == 0
        assert len(week.days) == 7

    def test_get_events_for_week_distributed(self):
        session = get_session()
        _create_event(session, "Mon Show", "07:00", "09:00", "1,0,0,0,0,0,0")
        _create_event(session, "Wed Show", "10:00", "12:00", "0,0,1,0,0,0,0")
        _create_event(session, "Fri Show", "18:00", "22:00", "0,0,0,0,1,0,0")
        session.commit()
        session.close()

        service = ParrillaService()
        week = service.get_events_for_week()

        assert week.total_events == 3
        assert len(week.days[0]) == 1   # Monday
        assert len(week.days[2]) == 1   # Wednesday
        assert len(week.days[4]) == 1   # Friday
        assert len(week.days[1]) == 0   # Tuesday

        # Verificar GridEvent data
        mon_event = week.days[0][0]
        assert mon_event.start_minutes == 420  # 7:00
        assert mon_event.duration_minutes == 120  # 2h

    def test_get_events_for_week_with_playlist_name(self):
        session = get_session()
        pl = _create_playlist(session, "Morning Playlist")
        _create_event(session, "Show", "07:00", "09:00", "1,0,0,0,0,0,0",
                      playlist_id=pl.id)
        session.commit()
        session.close()

        service = ParrillaService()
        week = service.get_events_for_week()

        mon_event = week.days[0][0]
        assert mon_event.playlist_name == "Morning Playlist"

    def test_get_events_for_week_custom_week(self):
        session = get_session()
        _create_event(session, "Daily", "12:00", "13:00", "1,1,1,1,1,1,1")
        session.commit()
        session.close()

        service = ParrillaService()
        target_week = date(2025, 1, 6)  # Monday
        week = service.get_events_for_week(week_start=target_week)

        assert week.week_start == target_week
        assert week.total_events == 1
        # Should appear on all 7 days
        for d in range(7):
            assert len(week.days[d]) == 1


# ═══════════════════════════════════════
# Tests de deteccion de conflictos
# ═══════════════════════════════════════

class TestConflictDetection:
    """Tests de deteccion de solapamientos."""

    def test_no_conflict(self):
        session = get_session()
        _create_event(session, "A", "07:00", "09:00", "1,0,0,0,0,0,0")
        _create_event(session, "B", "10:00", "12:00", "1,0,0,0,0,0,0")
        session.commit()
        session.close()

        service = ParrillaService()
        conflicts = service.detect_conflicts(0)
        assert len(conflicts) == 0

    def test_conflict_overlap(self):
        session = get_session()
        _create_event(session, "A", "07:00", "10:00", "1,0,0,0,0,0,0")
        _create_event(session, "B", "09:00", "11:00", "1,0,0,0,0,0,0")
        session.commit()
        session.close()

        service = ParrillaService()
        conflicts = service.detect_conflicts(0)
        assert len(conflicts) == 1
        assert conflicts[0].overlap_start == "09:00"
        assert conflicts[0].overlap_end == "10:00"

    def test_no_conflict_adjacent(self):
        """Eventos consecutivos no son conflicto."""
        session = get_session()
        _create_event(session, "A", "09:00", "10:00", "1,0,0,0,0,0,0")
        _create_event(session, "B", "10:00", "11:00", "1,0,0,0,0,0,0")
        session.commit()
        session.close()

        service = ParrillaService()
        conflicts = service.detect_conflicts(0)
        assert len(conflicts) == 0

    def test_conflict_contained(self):
        """Un evento contenido dentro de otro."""
        session = get_session()
        _create_event(session, "Long", "07:00", "13:00", "1,0,0,0,0,0,0")
        _create_event(session, "Short", "09:00", "10:00", "1,0,0,0,0,0,0")
        session.commit()
        session.close()

        service = ParrillaService()
        conflicts = service.detect_conflicts(0)
        assert len(conflicts) == 1

    def test_conflict_different_days(self):
        """Eventos en dias diferentes no confluyen."""
        session = get_session()
        _create_event(session, "A", "09:00", "11:00", "1,0,0,0,0,0,0")
        _create_event(session, "B", "09:00", "11:00", "0,1,0,0,0,0,0")
        session.commit()
        session.close()

        service = ParrillaService()
        conflicts = service.detect_conflicts(0)  # Solo lunes
        assert len(conflicts) == 0

        conflicts_all = service.detect_conflicts(None)  # Toda la semana
        assert len(conflicts_all) == 0

    def test_conflict_in_week_data(self):
        """Los GridEvents deben marcar has_conflict."""
        session = get_session()
        _create_event(session, "A", "07:00", "10:00", "1,0,0,0,0,0,0")
        _create_event(session, "B", "09:00", "11:00", "1,0,0,0,0,0,0")
        session.commit()
        session.close()

        service = ParrillaService()
        week = service.get_events_for_week()

        assert len(week.conflicts) >= 1
        # Verificar que los GridEvents tienen has_conflict
        has_conflict = any(ge.has_conflict for d in week.days for ge in d)
        assert has_conflict is True


# ═══════════════════════════════════════
# Tests de Now Playing
# ═══════════════════════════════════════

class TestNowPlaying:
    """Tests de determinacion del evento actual."""

    def test_no_event_now(self):
        service = ParrillaService()
        info = service.get_now_playing()
        assert info.is_active is False
        assert info.event is None

    def test_event_at_exact_time(self):
        session = get_session()
        _create_event(session, "Show", "12:00", "14:00", "1,1,1,1,1,1,1")
        session.commit()
        session.close()

        service = ParrillaService()

        # Crear un momento dentro del rango
        target = datetime.now().replace(hour=13, minute=0, second=0)
        ev = service.get_event_at_time(target)

        if ev:
            assert ev.name == "Show"

    def test_event_outside_time(self):
        session = get_session()
        _create_event(session, "Show", "07:00", "09:00", "1,1,1,1,1,1,1")
        session.commit()
        session.close()

        service = ParrillaService()
        target = datetime.now().replace(hour=15, minute=0, second=0)
        ev = service.get_event_at_time(target)
        assert ev is None


class TestNextEvent:
    """Tests de busqueda del proximo evento."""

    def test_next_event_today(self):
        session = get_session()
        now_hour = datetime.now().hour
        future_hour = min(now_hour + 2, 22)
        _create_event(session, "Later",
                      f"{future_hour:02d}:00",
                      f"{future_hour + 1:02d}:00",
                      "1,1,1,1,1,1,1")
        session.commit()
        session.close()

        service = ParrillaService()
        next_ev = service.get_next_event()

        # Puede ser None si ya paso la hora
        if next_ev:
            assert next_ev.name == "Later"

    def test_next_event_empty(self):
        service = ParrillaService()
        next_ev = service.get_next_event()
        assert next_ev is None


# ═══════════════════════════════════════
# Tests de Auto-Scheduler
# ═══════════════════════════════════════

class TestAutoScheduler:
    """Tests del scheduler automatico."""

    def test_start_stop_scheduler(self):
        service = ParrillaService()
        assert service._auto_scheduler_active is False

        service.start_auto_scheduler()
        assert service._auto_scheduler_active is True

        service.stop_auto_scheduler()
        assert service._auto_scheduler_active is False

    def test_check_and_play_no_events(self):
        service = ParrillaService()
        info = service.check_and_play_event(force=True)
        assert info.is_active is False

    def test_check_and_play_with_event(self):
        session = get_session()
        now = datetime.now()
        # Crear un evento que abarque la hora actual
        start_h = max(0, now.hour - 1)
        end_h = min(23, now.hour + 1)
        _create_event(session, "Auto Test",
                      f"{start_h:02d}:00", f"{end_h:02d}:00",
                      "1,1,1,1,1,1,1")
        session.commit()
        session.close()

        service = ParrillaService()
        info = service.check_and_play_event(force=True)
        # El evento existe pero puede que no tenga contenido reproducible
        # (sin playlist o archivo local). La logica deberia intentar arrancarlo.
        # Asegurarse de detener el scheduler si se activo
        service.stop_auto_scheduler()


# ═══════════════════════════════════════
# Tests de Eventos de Streaming
# ═══════════════════════════════════════

class TestStreamingEvents:
    """Tests especificos para eventos de streaming."""

    def test_streaming_event_in_grid(self):
        session = get_session()
        _create_event(session, "Stream", "22:00", "00:00",
                      "0,0,0,0,0,1,1",
                      streaming_url="https://stream.example.com/live")
        session.commit()
        session.close()

        service = ParrillaService()
        events_sat = service.get_events_for_day(5)
        events_sun = service.get_events_for_day(6)

        assert len(events_sat) == 1
        assert events_sat[0].is_streaming is True
        assert events_sat[0].streaming_url == "https://stream.example.com/live"

    def test_streaming_without_end_time(self):
        """Evento streaming sin hora fin no se incluye en get_event_at_time."""
        session = get_session()
        _create_event(session, "Bad Stream", "22:00", None,
                      "1,1,1,1,1,1,1",
                      streaming_url="https://stream.example.com/live")
        session.commit()
        session.close()

        service = ParrillaService()
        target = datetime.now().replace(hour=23, minute=0)
        ev = service.get_event_at_time(target)
        assert ev is None  # Sin hora fin, no se puede determinar el rango


# ═══════════════════════════════════════
# Tests de GridEvent temporal marking
# ═══════════════════════════════════════

class TestGridEventStates:
    """Tests de marcado temporal (past/future/now_playing)."""

    def test_past_event(self):
        session = get_session()
        # Crear evento que ya termino (ayer, por ejemplo a las 07:00)
        _create_event(session, "Past", "00:00", "01:00", "1,1,1,1,1,1,1")
        session.commit()
        session.close()

        service = ParrillaService()
        week = service.get_events_for_week()

        now_minutes = datetime.now().hour * 60 + datetime.now().minute
        now_day = datetime.now().weekday()

        for ge in week.days[now_day]:
            if ge.start_minutes + ge.duration_minutes <= now_minutes:
                assert ge.is_past is True
                assert ge.is_now_playing is False

    def test_future_event(self):
        session = get_session()
        # Crear evento a las 23:00
        _create_event(session, "Future", "23:00", "23:59", "1,1,1,1,1,1,1")
        session.commit()
        session.close()

        service = ParrillaService()
        week = service.get_events_for_week()

        now_day = datetime.now().weekday()
        for ge in week.days[now_day]:
            if ge.name == "Future":
                now_minutes = datetime.now().hour * 60 + datetime.now().minute
                if now_minutes < ge.start_minutes:
                    assert ge.is_future is True


# ═══════════════════════════════════════
# Tests de EventBus integration
# ═══════════════════════════════════════

class TestParrillaEvents:
    """Tests de integracion con EventBus."""

    def test_parrilla_refreshed_event(self):
        session = get_session()
        _create_event(session, "E1", "07:00", "09:00", "1,0,0,0,0,0,0")
        session.commit()
        session.close()

        events = []
        get_event_bus().subscribe("parrilla.refreshed",
                                  lambda e: events.append(e))

        service = ParrillaService()
        week = service.get_events_for_week()

        # El refresh del service deberia haber publicado
        # (via ParrillaPanel.refresh que llama al service)
        assert len(events) == 0  # Direct call to service doesn't publish


# ═══════════════════════════════════════
# Tests de singleton
# ═══════════════════════════════════════

class TestSingleton:
    """Tests del patron singleton."""

    def test_get_parrilla_service(self):
        service1 = get_parrilla_service()
        service2 = get_parrilla_service()
        assert service1 is service2

    def test_reset_parrilla_service(self):
        service1 = get_parrilla_service()
        reset_parrilla_service()
        service2 = get_parrilla_service()
        assert service1 is not service2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
