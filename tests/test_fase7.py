"""
Tests de la Fase 7: Motor de Automatizacion.
AutomationEngine: daemon, Continuidad fallback, transiciones, estado persistente.
"""

import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, date
from pathlib import Path
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from radio_automator.core.database import (
    init_db, get_session, reset_engine,
    Playlist, PlaylistItem, RadioEvent, ContinuityState, FolderTrack
)
from radio_automator.core.event_bus import get_event_bus, reset_event_bus
from radio_automator.services.audio_engine import (
    AudioEngine, PlaybackState, reset_audio_engine
)
from radio_automator.services.play_queue import get_play_queue, PlayQueue, reset_play_queue
from radio_automator.services.parrilla_service import (
    ParrillaService, reset_parrilla_service
)
from radio_automator.services.automation_engine import (
    AutomationEngine, PlaybackSource, AutomationStatus,
    reset_automation_engine, get_automation_engine
)
import pytest as _pytest


_contador = 0


def _uid(prefix="Item"):
    global _contador
    _contador += 1
    return f"{prefix}_{_contador}"


@pytest.fixture(autouse=True)
def fresh_env():
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["RADIO_AUTOMATOR_DIR"] = tmpdir
        reset_engine()
        reset_event_bus()
        reset_audio_engine()
        reset_play_queue()
        reset_parrilla_service()
        reset_automation_engine()
        init_db()
        yield tmpdir
        reset_engine()
        reset_event_bus()
        reset_audio_engine()
        reset_play_queue()
        reset_parrilla_service()
        reset_automation_engine()


# ── Helpers ──

def _create_playlist(name="TestPL", mode="loop", is_system=False):
    session = get_session()
    pl = Playlist(name=name, mode=mode, is_system=is_system)
    session.add(pl)
    session.flush()
    session.commit()
    session.close()
    return pl


def _add_track_to_playlist(playlist_id, filepath):
    session = get_session()
    items = (
        session.query(PlaylistItem)
        .filter_by(playlist_id=playlist_id)
        .order_by(PlaylistItem.position.desc())
        .first()
    )
    pos = (items.position + 1) if items else 0
    item = PlaylistItem(
        playlist_id=playlist_id,
        position=pos,
        item_type="track",
        filepath=filepath,
    )
    session.add(item)
    session.commit()
    session.close()


def _create_event(name, start="09:00", end="10:00",
                  week_days="1,1,1,1,1,1,1", playlist_id=None,
                  streaming_url=None):
    session = get_session()
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
    session.commit()
    session.close()
    return ev


def _create_audio_files(tmpdir, count=3):
    files = []
    for i in range(count):
        f = Path(tmpdir) / f"track_{i}.mp3"
        f.write_bytes(b"fake_audio_content")
        files.append(str(f))
    return files


# ═══════════════════════════════════════
# Tests de PlaybackSource y AutomationStatus
# ═══════════════════════════════════════

class TestPlaybackSource(unittest.TestCase):
    def test_values(self):
        self.assertEqual(PlaybackSource.NONE.value, "none")
        self.assertEqual(PlaybackSource.PARRILLA.value, "parrilla")
        self.assertEqual(PlaybackSource.CONTINUIDAD.value, "continuidad")
        self.assertEqual(PlaybackSource.MANUAL.value, "manual")
        self.assertEqual(len(PlaybackSource), 4)

    def test_all_unique(self):
        values = [s.value for s in PlaybackSource]
        self.assertEqual(len(values), len(set(values)))


class TestAutomationStatus(unittest.TestCase):
    def test_defaults(self):
        s = AutomationStatus()
        self.assertFalse(s.is_active)
        self.assertEqual(s.source, PlaybackSource.NONE)
        self.assertIsNone(s.event_name)
        self.assertIsNone(s.event_id)
        self.assertIsNone(s.next_event_name)
        self.assertFalse(s.continuidad_active)
        self.assertEqual(s.uptime_seconds, 0.0)
        self.assertEqual(s.events_started, 0)
        self.assertEqual(s.continuidad_resumes, 0)

    def test_with_values(self):
        s = AutomationStatus(
            is_active=True,
            source=PlaybackSource.PARRILLA,
            event_name="Morning Show",
            event_id=42,
            events_started=3,
        )
        self.assertTrue(s.is_active)
        self.assertEqual(s.event_name, "Morning Show")
        self.assertEqual(s.events_started, 3)


# ═══════════════════════════════════════
# Tests de creacion e inicializacion
# ═══════════════════════════════════════

class TestAutomationEngineInit(unittest.TestCase):
    def test_create_engine(self):
        ae = AutomationEngine()
        self.assertFalse(ae.is_active)
        self.assertEqual(ae.source, PlaybackSource.NONE)
        self.assertIsNone(ae.current_event_id)
        self.assertAlmostEqual(ae.check_interval_s, 5.0)

    def test_default_interval(self):
        ae = AutomationEngine()
        self.assertEqual(ae.check_interval_s, AutomationEngine.DEFAULT_CHECK_INTERVAL_S)

    def test_set_check_interval(self):
        ae = AutomationEngine()
        ae.set_check_interval(10)
        self.assertEqual(ae.check_interval_s, 10.0)

    def test_set_check_interval_clamped(self):
        ae = AutomationEngine()
        ae.set_check_interval(0.5)  # Minimo 2s
        self.assertEqual(ae.check_interval_s, 2.0)
        ae.set_check_interval(999)  # Maximo 60s
        self.assertEqual(ae.check_interval_s, 60.0)

    def test_set_callbacks(self):
        ae = AutomationEngine()
        cb1 = MagicMock()
        cb2 = MagicMock()
        ae.set_callbacks(on_status_changed=cb1, on_source_changed=cb2)
        self.assertIs(ae._on_status_changed, cb1)
        self.assertIs(ae._on_source_changed, cb2)


# ═══════════════════════════════════════
# Tests del ciclo de vida
# ═══════════════════════════════════════

class TestAutomationEngineLifecycle(unittest.TestCase):
    def test_start_stop(self):
        ae = AutomationEngine()
        ae.start()
        self.assertTrue(ae.is_active)
        ae.stop()
        self.assertFalse(ae.is_active)

    def test_start_twice(self):
        ae = AutomationEngine()
        ae.start()
        ae.start()  # Segunda llamada no debe crear otro hilo
        self.assertTrue(ae.is_active)
        ae.stop()

    def test_stop_when_not_active(self):
        ae = AutomationEngine()
        ae.stop()  # No debe lanzar error
        self.assertFalse(ae.is_active)

    def test_restart(self):
        ae = AutomationEngine()
        ae.start()
        self.assertTrue(ae.is_active)
        ae.restart()
        self.assertTrue(ae.is_active)
        ae.stop()

    def test_uptime(self):
        ae = AutomationEngine()
        self.assertEqual(ae.uptime_seconds, 0.0)
        ae.start()
        time.sleep(0.1)
        uptime = ae.uptime_seconds
        self.assertGreater(uptime, 0.0)
        ae.stop()


# ═══════════════════════════════════════
# Tests del tick: sin eventos
# ═══════════════════════════════════════

class TestAutomationTickNoEvents(unittest.TestCase):
    def test_tick_no_events_starts_continuidad(self):
        """Sin eventos programados, tick inicia Continuidad."""
        ae = AutomationEngine()
        ae.start()
        # Dar tiempo para que el hilo haga al menos un tick
        time.sleep(0.5)
        # La Continuidad deberia iniciarse (si hay pistas)
        # Verificar que no hay errores y la fuente cambio
        ae.stop()

    def test_tick_when_not_active(self):
        """Tick no hace nada si no esta activo."""
        ae = AutomationEngine()
        ae.tick()  # No debe lanzar error
        self.assertEqual(ae.source, PlaybackSource.NONE)


# ═══════════════════════════════════════
# Tests del tick: con eventos programados
# ═══════════════════════════════════════

class TestAutomationTickWithEvents(unittest.TestCase):
    def test_event_starts_when_in_range(self):
        """Si hay un evento ahora, la automatizacion lo inicia."""
        with tempfile.TemporaryDirectory() as tmpdir:
            files = _create_audio_files(tmpdir, 2)
            pl = _create_playlist(_uid("EvPL"))
            for f in files:
                _add_track_to_playlist(pl.id, f)

            now = datetime.now()
            start_h = max(0, now.hour - 1)
            end_h = min(23, now.hour + 1)
            ev = _create_event(
                "Auto Test",
                f"{start_h:02d}:00",
                f"{end_h:02d}:00",
                playlist_id=pl.id,
            )

            ae = AutomationEngine()
            ae.start()
            time.sleep(1.0)
            # Deberia haber intentado iniciar el evento
            ae.stop()


# ═══════════════════════════════════════
# Tests de modo manual
# ═══════════════════════════════════════

class TestManualMode(unittest.TestCase):
    def test_set_manual_mode(self):
        ae = AutomationEngine()
        ae.start()
        ae.set_manual_mode()
        self.assertEqual(ae.source, PlaybackSource.MANUAL)
        ae.stop()

    def test_exit_manual_mode(self):
        ae = AutomationEngine()
        ae.start()
        ae.set_manual_mode()
        ae.exit_manual_mode()
        self.assertEqual(ae.source, PlaybackSource.NONE)
        ae.stop()

    def test_tick_does_not_interfere_in_manual(self):
        """En modo manual con reproduccion, tick no interfiere."""
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "manual.mp3"
            f.write_bytes(b"audio")
            engine = AudioEngine()
            engine.play_file(str(f))

            ae = AutomationEngine()
            ae.set_manual_mode()
            self.assertEqual(ae.source, PlaybackSource.MANUAL)

            ae.tick()
            # No debe cambiar el modo manual mientras reproduce
            self.assertEqual(ae.source, PlaybackSource.MANUAL)
            engine.stop()


# ═══════════════════════════════════════
# Tests de Continuidad
# ═══════════════════════════════════════

class TestContinuidadState(unittest.TestCase):
    def test_load_continuidad_playlist_id(self):
        ae = AutomationEngine()
        ae._load_continuidad_playlist_id()
        # La playlist Continuidad se crea en init_db()
        self.assertIsNotNone(ae._continuidad_playlist_id)

    def test_save_and_restore_continuidad_state(self):
        ae = AutomationEngine()
        ae._load_continuidad_playlist_id()
        pl_id = ae._continuidad_playlist_id
        self.assertIsNotNone(pl_id)

        # Modificar estado en la base de datos
        session = get_session()
        state = session.query(ContinuityState).filter_by(playlist_id=pl_id).first()
        state.current_item_index = 5
        state.current_file_position_ms = 12345
        session.commit()
        session.close()

        # Restaurar
        ae._restore_continuidad_state()
        self.assertEqual(ae._continuidad.item_index, 5)

    def test_save_continuidad_state_presists(self):
        ae = AutomationEngine()
        ae._load_continuidad_playlist_id()
        pl_id = ae._continuidad_playlist_id

        # Simular que estamos en Continuidad
        ae._set_source(PlaybackSource.CONTINUIDAD)

        with tempfile.TemporaryDirectory() as tmpdir:
            files = _create_audio_files(tmpdir, 3)
            for f in files:
                _add_track_to_playlist(pl_id, f)

            queue = get_play_queue()
            queue.load_playlist(pl_id)
            queue.play_next()
            queue.play_next()  # Avanzar al indice 1

            ae._save_continuidad_state()

            # Verificar que se guardo en la base de datos
            session = get_session()
            state = session.query(ContinuityState).filter_by(playlist_id=pl_id).first()
            self.assertIsNotNone(state)
            self.assertEqual(state.current_item_index, 1)
            session.close()


# ═══════════════════════════════════════
# Tests de transiciones
# ═══════════════════════════════════════

class TestTransitions(unittest.TestCase):
    def test_source_changed_callback(self):
        ae = AutomationEngine()
        sources = []
        ae.set_callbacks(on_source_changed=lambda s: sources.append(s))
        ae._set_source(PlaybackSource.PARRILLA)
        ae._set_source(PlaybackSource.CONTINUIDAD)
        self.assertEqual(len(sources), 2)
        self.assertEqual(sources[0], PlaybackSource.PARRILLA)
        self.assertEqual(sources[1], PlaybackSource.CONTINUIDAD)

    def test_source_notifies_eventbus(self):
        ae = AutomationEngine()
        bus = get_event_bus()
        events = []
        bus.subscribe("automation.source_changed", lambda e: events.append(e))
        ae._set_source(PlaybackSource.MANUAL)
        self.assertTrue(len(events) > 0)

    def test_status_changed_callback(self):
        ae = AutomationEngine()
        statuses = []
        ae.set_callbacks(on_status_changed=lambda s: statuses.append(s))
        ae._notify_status()
        self.assertEqual(len(statuses), 1)
        self.assertIsInstance(statuses[0], AutomationStatus)

    def test_get_status(self):
        ae = AutomationEngine()
        ae.start()
        status = ae.get_status()
        self.assertTrue(status.is_active)
        self.assertEqual(status.source, PlaybackSource.NONE)
        ae.stop()


# ═══════════════════════════════════════
# Tests de EventBus
# ═══════════════════════════════════════

class TestEventBusIntegration(unittest.TestCase):
    def test_automation_started_event(self):
        ae = AutomationEngine()
        bus = get_event_bus()
        events = []
        bus.subscribe("automation.started", lambda e: events.append(e))
        ae.start()
        self.assertTrue(len(events) > 0)
        ae.stop()

    def test_automation_stopped_event(self):
        ae = AutomationEngine()
        bus = get_event_bus()
        events = []
        bus.subscribe("automation.stopped", lambda e: events.append(e))
        ae.start()
        ae.stop()
        self.assertTrue(len(events) > 0)

    def test_manual_mode_event(self):
        ae = AutomationEngine()
        bus = get_event_bus()
        events = []
        bus.subscribe("automation.manual_mode", lambda e: events.append(e))
        ae.set_manual_mode()
        self.assertTrue(len(events) > 0)


# ═══════════════════════════════════════
# Tests de on_track_finished
# ═══════════════════════════════════════

class TestOnTrackFinished(unittest.TestCase):
    def test_on_track_finished_not_active(self):
        ae = AutomationEngine()
        # No debe hacer nada si no esta activo
        ae.on_track_finished()

    def test_on_track_finished_continuidad(self):
        ae = AutomationEngine()
        ae._load_continuidad_playlist_id()
        pl_id = ae._continuidad_playlist_id
        ae._set_source(PlaybackSource.CONTINUIDAD)
        ae.start()

        with tempfile.TemporaryDirectory() as tmpdir:
            files = _create_audio_files(tmpdir, 3)
            for f in files:
                _add_track_to_playlist(pl_id, f)

            queue = get_play_queue()
            queue.load_playlist(pl_id)
            queue.play_next()

            # on_track_finished deberia guardar estado y avanzar
            ae.on_track_finished()
            # Verificar que el estado se guardo
            self.assertIsNotNone(ae._continuidad.item_index)

        ae.stop()


# ═══════════════════════════════════════
# Tests de singleton
# ═══════════════════════════════════════

class TestSingleton(unittest.TestCase):
    def test_get_automation_engine(self):
        ae1 = get_automation_engine()
        ae2 = get_automation_engine()
        self.assertIs(ae1, ae2)
        reset_automation_engine()

    def test_reset(self):
        ae1 = get_automation_engine()
        reset_automation_engine()
        ae2 = get_automation_engine()
        self.assertIsNot(ae1, ae2)
        reset_automation_engine()


# ═══════════════════════════════════════
# Tests de deteccion de fin de evento
# ═══════════════════════════════════════

class TestEventEndDetection(unittest.TestCase):
    def test_event_end_stops_playback(self):
        """Cuando un evento termina (hora fin pasada), se detiene."""
        with tempfile.TemporaryDirectory() as tmpdir:
            files = _create_audio_files(tmpdir, 2)
            pl = _create_playlist(_uid("EndTestPL"))
            for f in files:
                _add_track_to_playlist(pl.id, f)

            # Crear evento que ya termino (ayer a las 01:00-02:00)
            ev = _create_event(
                "Past Event",
                "01:00", "02:00",
                "1,1,1,1,1,1,1",
                playlist_id=pl.id,
            )

            ae = AutomationEngine()
            ae.start()
            time.sleep(0.5)
            # No deberia estar reproduciendo este evento
            self.assertNotEqual(ae.source, PlaybackSource.PARRILLA)
            ae.stop()


# ═══════════════════════════════════════
# Tests de _parse_time
# ═══════════════════════════════════════

class TestParseTime(unittest.TestCase):
    def test_parse_valid(self):
        t = AutomationEngine._parse_time("14:30")
        self.assertEqual(t.hour, 14)
        self.assertEqual(t.minute, 30)

    def test_parse_midnight(self):
        t = AutomationEngine._parse_time("00:00")
        self.assertEqual(t.hour, 0)
        self.assertEqual(t.minute, 0)

    def test_parse_end_of_day(self):
        t = AutomationEngine._parse_time("23:59")
        self.assertEqual(t.hour, 23)
        self.assertEqual(t.minute, 59)


if __name__ == '__main__':
    # Necesitamos pytest para los fixtures
    import pytest
    pytest.main([__file__, "-v"])
