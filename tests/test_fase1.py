"""Tests de la Fase 1: Base de datos, EventBus y ConfigManager."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Asegurar que importa del proyecto
sys.path.insert(0, str(Path(__file__).parent.parent))

from radio_automator.core.event_bus import EventBus, Event, Priority, reset_event_bus
from radio_automator.core.config import ConfigManager


class TestEventBus:
    def setup_method(self):
        self.bus = EventBus()

    def test_subscribe_and_publish(self):
        received = []
        self.bus.subscribe("track.started", lambda e: received.append(e))
        self.bus.publish("track.started", {"track": "song.mp3"})
        assert len(received) == 1
        assert received[0].type == "track.started"
        assert received[0].data["track"] == "song.mp3"

    def test_multiple_subscribers(self):
        r1, r2 = [], []
        self.bus.subscribe("event", lambda e: r1.append(e))
        self.bus.subscribe("event", lambda e: r2.append(e))
        self.bus.publish("event")
        assert len(r1) == 1
        assert len(r2) == 1

    def test_unsubscribe(self):
        r = []
        handler = lambda e: r.append(e)
        self.bus.subscribe("event", handler)
        self.bus.publish("event")
        assert len(r) == 1
        self.bus.unsubscribe("event", handler)
        self.bus.publish("event")
        assert len(r) == 1  # No new event

    def test_subscribe_all(self):
        r = []
        self.bus.subscribe_all(lambda e: r.append(e))
        self.bus.publish("event_a")
        self.bus.publish("event_b")
        assert len(r) == 2

    def test_handler_error_doesnt_crash(self):
        def bad_handler(e):
            raise ValueError("test error")
        self.bus.subscribe("event", bad_handler)
        self.bus.publish("event")  # Should not raise

    def test_priority_ordering(self):
        order = []
        self.bus.subscribe("event", lambda e: order.append("low"), Priority.LOW)
        self.bus.subscribe("event", lambda e: order.append("high"), Priority.HIGH)
        self.bus.subscribe("event", lambda e: order.append("normal"), Priority.NORMAL)
        self.bus.publish("event")
        assert order == ["high", "normal", "low"]

    def test_event_log(self):
        self.bus.publish("event_a")
        self.bus.publish("event_b")
        events = self.bus.get_recent_events(10)
        assert len(events) == 2
        assert events[0].type == "event_a"

    def test_clear_subscribers(self):
        r = []
        self.bus.subscribe("event", lambda e: r.append(e))
        self.bus.clear_subscribers()
        self.bus.publish("event")
        assert len(r) == 0


class TestConfigManager:
    def test_get_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["RADIO_AUTOMATOR_DIR"] = tmpdir
            from radio_automator.core.database import init_db
            init_db()
            cfg = ConfigManager()
            assert cfg.get("station_name") == "Mi Emisora"

    def test_get_int_float_bool(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["RADIO_AUTOMATOR_DIR"] = tmpdir
            from radio_automator.core.database import init_db
            init_db()
            cfg = ConfigManager()
            assert isinstance(cfg.get_int("crossfade_duration"), int)
            assert cfg.get_float("crossfade_duration") == 3.0
            assert cfg.get_bool("silence_detection") is True

    def test_set_and_get(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["RADIO_AUTOMATOR_DIR"] = tmpdir
            from radio_automator.core.database import init_db
            init_db()
            cfg = ConfigManager()
            cfg.set("test.key", "hola")
            assert cfg.get("test.key") == "hola"
            cfg.set_int("test.int", 42)
            assert cfg.get_int("test.int") == 42
            cfg.set_bool("test.bool", True)
            assert cfg.get_bool("test.bool") is True


class TestDatabaseModels:
    def _init_db(self, tmpdir):
        os.environ["RADIO_AUTOMATOR_DIR"] = tmpdir
        from radio_automator.core.database import init_db, get_session
        init_db()
        return get_session()

    def test_continuity_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._init_db(tmpdir)
            from radio_automator.core.database import Playlist
            c = session.query(Playlist).filter_by(is_system=True).first()
            assert c is not None
            assert c.name == "Continuidad"
            assert c.mode == "loop"
            assert c.is_continuity is True
            session.close()

    def test_event_streaming_props(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._init_db(tmpdir)
            from radio_automator.core.database import RadioEvent
            ev = RadioEvent(
                name="Stream", start_time="10:00", end_time="12:00",
                streaming_url="http://radio.com/stream"
            )
            session.add(ev)
            session.flush()
            assert ev.is_streaming is True
            assert ev.has_end_time is True

            ev2 = RadioEvent(name="Local", start_time="14:00")
            session.add(ev2)
            session.flush()
            assert ev2.is_streaming is False
            assert ev2.has_end_time is False
            session.rollback()
            session.close()

    def test_event_week_days(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._init_db(tmpdir)
            from radio_automator.core.database import RadioEvent
            ev = RadioEvent(
                name="LunMieVie", start_time="10:00",
                week_days="1,0,1,0,1,0,0"
            )
            session.add(ev)
            session.flush()
            days = ev.week_days_list
            assert days == [True, False, True, False, True, False, False]
            assert len(days) == 7
            session.rollback()
            session.close()

    def test_playlist_item_types(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._init_db(tmpdir)
            from radio_automator.core.database import Playlist, PlaylistItem
            cont = session.query(Playlist).filter_by(is_system=True).first()

            item_track = PlaylistItem(
                playlist_id=cont.id, position=0,
                item_type="track", filepath="/music/song.mp3"
            )
            item_folder = PlaylistItem(
                playlist_id=cont.id, position=1,
                item_type="folder", folder_path="/music/rock"
            )
            item_time = PlaylistItem(
                playlist_id=cont.id, position=2,
                item_type="time_announce"
            )
            session.add_all([item_track, item_folder, item_time])
            session.flush()

            assert item_track.item_type == "track"
            assert item_folder.folder_path == "/music/rock"
            assert item_time.item_type == "time_announce"
            session.rollback()
            session.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
