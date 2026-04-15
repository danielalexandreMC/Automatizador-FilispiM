"""Tests de la Fase 4: Motor de audio, cola de reproduccion, historial."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from radio_automator.core.database import (
    init_db, get_session, reset_engine,
    Playlist, PlaylistItem, PlayHistory, FolderTrack
)
from radio_automator.core.event_bus import get_event_bus, reset_event_bus
from radio_automator.services.audio_engine import (
    AudioEngine, PlaybackState, TrackInfo, VUMeterData,
    reset_audio_engine, get_audio_engine
)
from radio_automator.services.play_queue import (
    PlayQueue, QueueItem, reset_play_queue, get_play_queue
)


# ── Contador para nombres unicos ──
_counter = 0


def unique_name(prefix="Item") -> str:
    global _counter
    _counter += 1
    return f"{prefix}_{_counter}"


@pytest.fixture(autouse=True)
def fresh_db():
    """Crear una base de datos limpia para cada test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["RADIO_AUTOMATOR_DIR"] = tmpdir
        reset_engine()
        reset_event_bus()
        reset_audio_engine()
        reset_play_queue()
        init_db()
        yield tmpdir
        reset_engine()
        reset_event_bus()
        reset_audio_engine()
        reset_play_queue()


# ═══════════════════════════════════════
# Tests de AudioEngine (modo simulacion)
# ═══════════════════════════════════════

class TestAudioEngineInit:
    """Tests de inicializacion del motor de audio."""

    def test_create_engine(self):
        engine = AudioEngine()
        assert engine is not None
        assert engine.state == PlaybackState.STOPPED

    def test_initial_state(self):
        engine = AudioEngine()
        assert engine.state == PlaybackState.STOPPED
        assert engine.volume == 1.0
        assert engine.muted is False
        assert engine.track_info.filepath == ""

    def test_track_info_defaults(self):
        info = TrackInfo()
        assert info.filepath == ""
        assert info.title == ""
        assert info.duration_ms == 0
        assert info.position_ms == 0
        assert info.is_streaming is False
        assert info.duration_str == "0:00"

    def test_track_info_formatting(self):
        info = TrackInfo(duration_ms=185000)  # 3:05
        assert info.duration_str == "3:05"

        info2 = TrackInfo(duration_ms=3723000)  # 1:02:03
        assert info2.duration_str == "1:02:03"

    def test_vu_meter_data_defaults(self):
        vu = VUMeterData()
        assert vu.level_left == 0.0
        assert vu.level_right == 0.0
        assert vu.is_clipping is False


class TestAudioEnginePlayback:
    """Tests de control de reproduccion (modo simulacion)."""

    def test_play_file_nonexistent(self):
        engine = AudioEngine()
        errors = []
        engine.set_callbacks(on_error=lambda msg: errors.append(msg))
        result = engine.play_file("/nonexistent/file.mp3")
        assert result is False
        assert len(errors) > 0

    def test_play_file(self):
        engine = AudioEngine()
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_file = Path(tmpdir) / "test.mp3"
            audio_file.write_bytes(b"fake_audio_content")

            result = engine.play_file(str(audio_file))
            assert result is True
            assert engine.state == PlaybackState.PLAYING
            assert engine.track_info.filepath.startswith("file://")

    def test_pause_resume(self):
        engine = AudioEngine()
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_file = Path(tmpdir) / "test.mp3"
            audio_file.write_bytes(b"fake_audio")

            engine.play_file(str(audio_file))
            assert engine.state == PlaybackState.PLAYING

            engine.pause()
            assert engine.state == PlaybackState.PAUSED

            engine.resume()
            assert engine.state == PlaybackState.PLAYING

    def test_toggle_play_pause(self):
        engine = AudioEngine()
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_file = Path(tmpdir) / "test.mp3"
            audio_file.write_bytes(b"fake_audio")

            engine.play_file(str(audio_file))
            engine.toggle_play_pause()
            assert engine.state == PlaybackState.PAUSED
            engine.toggle_play_pause()
            assert engine.state == PlaybackState.PLAYING

    def test_stop(self):
        engine = AudioEngine()
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_file = Path(tmpdir) / "test.mp3"
            audio_file.write_bytes(b"fake_audio")

            engine.play_file(str(audio_file))
            engine.stop()
            assert engine.state == PlaybackState.STOPPED
            assert engine.track_info.filepath == ""

    def test_play_stream_invalid(self):
        engine = AudioEngine()
        errors = []
        engine.set_callbacks(on_error=lambda msg: errors.append(msg))
        result = engine.play_stream("ftp://invalid.com/stream")
        assert result is False

    def test_play_stream(self):
        engine = AudioEngine()
        result = engine.play_stream("https://stream.example.com/live.mp3")
        assert result is True
        assert engine.state == PlaybackState.PLAYING
        assert engine.track_info.is_streaming is True


class TestAudioEngineVolume:
    """Tests de control de volumen."""

    def test_set_volume(self):
        engine = AudioEngine()
        engine.set_volume(0.5)
        assert engine.volume == 0.5

    def test_set_volume_clamped(self):
        engine = AudioEngine()
        engine.set_volume(2.0)
        assert engine.volume == 1.0
        engine.set_volume(-0.5)
        assert engine.volume == 0.0

    def test_mute(self):
        engine = AudioEngine()
        engine.set_mute(True)
        assert engine.muted is True
        engine.toggle_mute()
        assert engine.muted is False

    def test_set_volume_event(self):
        engine = AudioEngine()
        events = []
        get_event_bus().subscribe("audio.volume_changed",
                                  lambda e: events.append(e))
        engine.set_volume(0.75)
        assert len(events) == 1
        assert events[0].data["volume"] == 0.75


class TestAudioEngineEvents:
    """Tests de eventos del EventBus."""

    def test_track_started_event(self):
        engine = AudioEngine()
        events = []
        get_event_bus().subscribe("audio.track_started",
                                  lambda e: events.append(e))

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_file = Path(tmpdir) / "test.mp3"
            audio_file.write_bytes(b"fake_audio")
            engine.play_file(str(audio_file))

        assert len(events) == 1
        assert "filepath" in events[0].data

    def test_paused_event(self):
        engine = AudioEngine()
        events = []
        get_event_bus().subscribe("audio.paused",
                                  lambda e: events.append(e))

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_file = Path(tmpdir) / "test.mp3"
            audio_file.write_bytes(b"fake_audio")
            engine.play_file(str(audio_file))
            engine.pause()

        assert len(events) == 1

    def test_stopped_event(self):
        engine = AudioEngine()
        events = []
        get_event_bus().subscribe("audio.stopped",
                                  lambda e: events.append(e))

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_file = Path(tmpdir) / "test.mp3"
            audio_file.write_bytes(b"fake_audio")
            engine.play_file(str(audio_file))
            engine.stop()

        assert len(events) == 1

    def test_state_changed_callback(self):
        engine = AudioEngine()
        states = []
        engine.set_callbacks(on_state_changed=lambda s: states.append(s))

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_file = Path(tmpdir) / "test.mp3"
            audio_file.write_bytes(b"fake_audio")
            engine.play_file(str(audio_file))

        assert PlaybackState.PLAYING in states


class TestAudioEngineCrossfade:
    """Tests de crossfade."""

    def test_crossfade_config(self):
        engine = AudioEngine()
        engine.set_crossfade(True, 5000)
        assert engine._crossfade_enabled is True
        assert engine._crossfade_duration_ms == 5000

    def test_crossfade_disabled(self):
        engine = AudioEngine()
        engine.set_crossfade(False)

        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "a.mp3"
            f1.write_bytes(b"audio_a")
            f2 = Path(tmpdir) / "b.mp3"
            f2.write_bytes(b"audio_b")

            engine.play_file(str(f1))
            result = engine.play_file_with_crossfade(str(f2))
            assert result is True
            assert engine.state == PlaybackState.PLAYING

    def test_crossfade_no_current_track(self):
        engine = AudioEngine()
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.mp3"
            f.write_bytes(b"audio")

            result = engine.play_file_with_crossfade(str(f))
            assert result is True  # Deberia usar play_file normal


class TestPlayHistory:
    """Tests del modelo PlayHistory."""

    def test_create_play_history(self):
        session = get_session()
        history = PlayHistory(
            filepath="/music/test.mp3",
            title="Test Song",
            artist="Test Artist",
            duration_ms=210000,
            source="playlist",
            source_id=1,
        )
        session.add(history)
        session.commit()

        records = session.query(PlayHistory).all()
        assert len(records) == 1
        assert records[0].title == "Test Song"
        assert records[0].duration_ms == 210000
        session.close()

    def test_play_history_defaults(self):
        session = get_session()
        history = PlayHistory(filepath="/music/test.mp3")
        session.add(history)
        session.commit()

        record = session.query(PlayHistory).first()
        assert record.title == ""
        assert record.artist == ""
        assert record.duration_ms == 0
        assert record.source == "playlist"
        assert record.source_id is None
        session.close()


# ═══════════════════════════════════════
# Tests de PlayQueue
# ═══════════════════════════════════════

class TestPlayQueueBasic:
    """Tests basicos de la cola de reproduccion."""

    def test_create_empty_queue(self):
        queue = PlayQueue()
        assert queue.is_empty is True
        assert queue.count == 0
        assert queue.current_item is None
        assert queue.progress_text == "0 / 0"

    def test_load_files(self):
        queue = PlayQueue()
        with tempfile.TemporaryDirectory() as tmpdir:
            files = []
            for i in range(3):
                f = Path(tmpdir) / f"track_{i}.mp3"
                f.write_bytes(b"audio")
                files.append(str(f))

            count = queue.load_files(files)
            assert count == 3
            assert queue.count == 3
            assert queue.is_empty is False

    def test_load_stream(self):
        queue = PlayQueue()
        count = queue.load_stream("https://stream.example.com/live")
        assert count == 1
        assert queue.items[0].is_streaming is True

    def test_clear_queue(self):
        queue = PlayQueue()
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.mp3"
            f.write_bytes(b"audio")
            queue.load_files([str(f)])
            assert queue.count == 1

            queue.clear()
            assert queue.is_empty is True

    def test_add_item(self):
        queue = PlayQueue()
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.mp3"
            f.write_bytes(b"audio")
            count = queue.add_item(str(f))
            assert count == 1

    def test_insert_item(self):
        queue = PlayQueue()
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                f = Path(tmpdir) / f"track_{i}.mp3"
                f.write_bytes(b"audio")
                queue.add_item(str(f))

            new_f = Path(tmpdir) / "inserted.mp3"
            new_f.write_bytes(b"audio")
            queue.insert_item(1, str(new_f))

            assert queue.count == 4
            assert "inserted" in queue.items[1].filepath

    def test_remove_item(self):
        queue = PlayQueue()
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                f = Path(tmpdir) / f"track_{i}.mp3"
                f.write_bytes(b"audio")
                queue.add_item(str(f))

            queue.remove_item(1)
            assert queue.count == 2

    def test_progress_text(self):
        queue = PlayQueue()
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(5):
                f = Path(tmpdir) / f"track_{i}.mp3"
                f.write_bytes(b"audio")
                queue.add_item(str(f))

            # No current item
            assert queue.progress_text == "0 / 5"

            # First item
            queue.play_next()
            assert queue.progress_text == "1 / 5"


class TestPlayQueueNavigation:
    """Tests de navegacion en la cola."""

    def test_play_next_loop(self):
        queue = PlayQueue()
        queue.set_mode("loop")
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                f = Path(tmpdir) / f"track_{i}.mp3"
                f.write_bytes(b"audio")
                queue.add_item(str(f))

            item1 = queue.play_next()
            assert item1 is not None
            assert queue.current_index == 0

            item2 = queue.play_next()
            assert queue.current_index == 1

            item3 = queue.play_next()
            assert queue.current_index == 2

            # Loop: vuelve al inicio
            item4 = queue.play_next()
            assert item4 is not None
            assert queue.current_index == 0

    def test_play_next_single(self):
        queue = PlayQueue()
        queue.set_mode("single")
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(2):
                f = Path(tmpdir) / f"track_{i}.mp3"
                f.write_bytes(b"audio")
                queue.add_item(str(f))

            queue.play_next()
            queue.play_next()
            # Al final en single mode, devuelve None
            item = queue.play_next()
            assert item is None

    def test_play_previous(self):
        queue = PlayQueue()
        queue.set_mode("loop")
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                f = Path(tmpdir) / f"track_{i}.mp3"
                f.write_bytes(b"audio")
                queue.add_item(str(f))

            queue.play_next()
            queue.play_next()
            assert queue.current_index == 1

            prev = queue.play_previous()
            assert prev is not None
            assert queue.current_index == 0

    def test_jump_to(self):
        queue = PlayQueue()
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(5):
                f = Path(tmpdir) / f"track_{i}.mp3"
                f.write_bytes(b"audio")
                queue.add_item(str(f))

            item = queue.jump_to(3)
            assert item is not None
            assert queue.current_index == 3

            # Invalid index
            item = queue.jump_to(99)
            assert item is None

    def test_next_item_preview(self):
        queue = PlayQueue()
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                f = Path(tmpdir) / f"track_{i}.mp3"
                f.write_bytes(b"audio")
                queue.add_item(str(f))

            queue.play_next()
            next_item = queue.next_item
            assert next_item is not None
            assert queue.items[1].filepath == next_item.filepath

    def test_previous_item_preview(self):
        queue = PlayQueue()
        queue.set_mode("loop")
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                f = Path(tmpdir) / f"track_{i}.mp3"
                f.write_bytes(b"audio")
                queue.add_item(str(f))

            queue.play_next()
            queue.play_next()
            prev = queue.previous_item
            assert prev is not None


class TestPlayQueuePlaylistResolution:
    """Tests de resolucion de playlists en la cola."""

    def _create_playlist_with_tracks(self, name, track_files):
        """Helper para crear playlist con pistas."""
        session = get_session()
        playlist = Playlist(name=name, mode="loop")
        session.add(playlist)
        session.flush()

        for pos, filepath in enumerate(track_files):
            item = PlaylistItem(
                playlist_id=playlist.id,
                position=pos,
                item_type="track",
                filepath=filepath,
            )
            session.add(item)

        session.commit()
        session.close()
        return playlist

    def test_load_playlist(self):
        queue = PlayQueue()
        with tempfile.TemporaryDirectory() as tmpdir:
            files = []
            for i in range(3):
                f = Path(tmpdir) / f"track_{i}.mp3"
                f.write_bytes(b"audio")
                files.append(str(f))

            pl = self._create_playlist_with_tracks(unique_name("TestPL"), files)
            count = queue.load_playlist(pl.id)

            assert count == 3
            assert queue.count == 3
            assert queue.mode == "loop"

    def test_load_nested_playlist(self):
        """Resolver playlist anidada."""
        queue = PlayQueue()
        with tempfile.TemporaryDirectory() as tmpdir:
            # Crear playlist hija con 2 pistas
            child_files = []
            for i in range(2):
                f = Path(tmpdir) / f"child_{i}.mp3"
                f.write_bytes(b"audio")
                child_files.append(str(f))

            child_pl = self._create_playlist_with_tracks("ChildPL", child_files)

            # Crear playlist padre que referencia a la hija
            parent_file = Path(tmpdir) / "parent.mp3"
            parent_file.write_bytes(b"audio")

            session = get_session()
            parent = Playlist(name="ParentPL", mode="loop")
            session.add(parent)
            session.flush()

            # Item 1: pista directa
            item1 = PlaylistItem(
                playlist_id=parent.id,
                position=0,
                item_type="track",
                filepath=str(parent_file),
            )
            session.add(item1)

            # Item 2: playlist anidada
            item2 = PlaylistItem(
                playlist_id=parent.id,
                position=1,
                item_type="playlist",
                referenced_playlist_id=child_pl.id,
            )
            session.add(item2)

            session.commit()
            session.close()

            # Cargar playlist padre
            count = queue.load_playlist(parent.id)
            assert count == 3  # 1 directa + 2 de la hija

    def test_circular_reference_detection(self):
        """Detectar referencia circular en playlists."""
        queue = PlayQueue()

        session = get_session()
        # Crear playlist A
        pl_a = Playlist(name="PL_A", mode="loop")
        session.add(pl_a)
        session.flush()

        # Crear playlist B
        pl_b = Playlist(name="PL_B", mode="loop")
        session.add(pl_b)
        session.flush()

        # A referencia a B
        ref_ab = PlaylistItem(
            playlist_id=pl_a.id,
            position=0,
            item_type="playlist",
            referenced_playlist_id=pl_b.id,
        )
        session.add(ref_ab)

        # B referencia a A (circular!)
        ref_ba = PlaylistItem(
            playlist_id=pl_b.id,
            position=0,
            item_type="playlist",
            referenced_playlist_id=pl_a.id,
        )
        session.add(ref_ba)

        session.commit()
        session.close()

        # No deberia colgar, simplemente no resolver ciclos
        count = queue.load_playlist(pl_a.id)
        assert count == 0  # No puede resolver por circularidad

    def test_folder_item_resolution(self):
        """Resolver item de tipo carpeta."""
        queue = PlayQueue()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Crear carpeta con archivos
            music_dir = Path(tmpdir) / "music"
            music_dir.mkdir()
            f = music_dir / "song.mp3"
            f.write_bytes(b"audio")

            # Registrar en FolderTrack (anti-repeticion)
            session = get_session()
            track = FolderTrack(
                folder_path=str(music_dir),
                filename="song.mp3",
                filepath=str(f),
                played=False,
            )
            session.add(track)
            session.commit()

            # Crear playlist con item de carpeta
            pl = Playlist(name="FolderPL", mode="loop")
            session.add(pl)
            session.flush()

            folder_item = PlaylistItem(
                playlist_id=pl.id,
                position=0,
                item_type="folder",
                folder_path=str(music_dir),
            )
            session.add(folder_item)
            session.commit()
            session.close()

            count = queue.load_playlist(pl.id)
            assert count >= 1


class TestPlayQueueMode:
    """Tests de modos de la cola."""

    def test_set_mode(self):
        queue = PlayQueue()
        queue.set_mode("single")
        assert queue.mode == "single"
        queue.set_mode("loop")
        assert queue.mode == "loop"
        queue.set_mode("invalid")  # No cambia
        assert queue.mode == "loop"

    def test_shuffle(self):
        queue = PlayQueue()
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(10):
                f = Path(tmpdir) / f"track_{i}.mp3"
                f.write_bytes(b"audio")
                queue.add_item(str(f))

            original_order = [item.filepath for item in queue.items]
            queue.set_shuffle(True)

            # Verificar que los items son los mismos (aunque en diferente orden)
            assert queue.count == 10
            shuffled = [item.filepath for item in queue.items]
            assert set(original_order) == set(shuffled)


class TestPlayQueueCallbacks:
    """Tests de callbacks de la cola."""

    def test_queue_changed_callback(self):
        queue = PlayQueue()
        changes = []
        queue.set_callbacks(on_queue_changed=lambda: changes.append(True))

        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.mp3"
            f.write_bytes(b"audio")
            queue.add_item(str(f))

        assert len(changes) >= 1

    def test_current_changed_callback(self):
        queue = PlayQueue()
        current_items = []
        queue.set_callbacks(on_current_changed=lambda i: current_items.append(i))

        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.mp3"
            f.write_bytes(b"audio")
            queue.add_item(str(f))
            queue.play_next()

        assert len(current_items) >= 1
        assert current_items[0] is not None


class TestPlayQueueItemDTO:
    """Tests del DTO QueueItem."""

    def test_queue_item_label(self):
        item = QueueItem(filepath="/music/test.mp3", title="Test Song")
        assert "Test Song" in item.label
        assert "test.mp3" in item.label

    def test_queue_item_label_no_title(self):
        item = QueueItem(filepath="/music/test.mp3")
        assert item.label == "test.mp3"

    def test_queue_item_streaming(self):
        item = QueueItem(filepath="https://stream.com/live", is_streaming=True)
        assert item.is_streaming is True


class TestAudioEngineSeek:
    """Tests de busqueda (seek)."""

    def test_seek_not_streaming(self):
        engine = AudioEngine()
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.mp3"
            f.write_bytes(b"audio")
            engine.play_file(str(f))
            # Simulacion: no lanza error
            engine.seek(5000)

    def test_seek_streaming_ignored(self):
        engine = AudioEngine()
        engine.play_stream("https://stream.com/live")
        # Seek en streaming deberia ser ignorado
        engine.seek(5000)

    def test_seek_relative(self):
        engine = AudioEngine()
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.mp3"
            f.write_bytes(b"audio")
            engine.play_file(str(f))
            # Simulacion: no lanza error
            engine.seek_relative(10000)
            engine.seek_relative(-5000)


class TestAudioEngineCleanup:
    """Tests de limpieza de recursos."""

    def test_cleanup(self):
        engine = AudioEngine()
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.mp3"
            f.write_bytes(b"audio")
            engine.play_file(str(f))

        engine.cleanup()
        assert engine.state == PlaybackState.STOPPED
        assert engine._pipeline is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
