"""Tests de la Fase 2: UI, Playlists, FolderScanner y Eventos."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from radio_automator.core.database import (
    init_db, get_session, reset_engine,
    Playlist, PlaylistItem, RadioEvent
)
from radio_automator.services.playlist_service import (
    PlaylistService, PlaylistDTO, PlaylistError,
    PlaylistNotFoundError, PlaylistProtectedError, CircularReferenceError
)
from radio_automator.services.folder_scanner import FolderScanner


# ── Contador para nombres unicos ──
_counter = 0


def unique_name(prefix="Test") -> str:
    global _counter
    _counter += 1
    return f"{prefix}_{_counter}"


@pytest.fixture(autouse=True)
def fresh_db():
    """Crear una base de datos limpia para cada test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["RADIO_AUTOMATOR_DIR"] = tmpdir
        reset_engine()  # Reiniciar el engine para usar la nueva ruta
        init_db()
        yield tmpdir
        reset_engine()  # Limpiar despues


class TestPlaylistService:
    """Tests del servicio de playlists."""

    def test_create_playlist(self):
        service = PlaylistService()
        name = unique_name("Playlist")
        dto = service.create(name, "loop")
        assert dto.name == name
        assert dto.mode == "loop"
        assert dto.is_system is False
        assert dto.item_count == 0

    def test_create_duplicate_name_raises(self):
        service = PlaylistService()
        name = unique_name("Dup")
        service.create(name)
        with pytest.raises(PlaylistError, match="Ya existe"):
            service.create(name)

    def test_get_all_includes_continuity(self):
        service = PlaylistService()
        playlists = service.get_all()
        names = [p.name for p in playlists]
        assert "Continuidad" in names

    def test_update_playlist_name(self):
        service = PlaylistService()
        dto = service.create(unique_name("Original"))
        updated = service.update(dto.id, name="NuevoNombre")
        assert updated.name == "NuevoNombre"

    def test_update_playlist_mode(self):
        service = PlaylistService()
        dto = service.create(unique_name("ModeTest"), "loop")
        updated = service.update(dto.id, mode="single")
        assert updated.mode == "single"

    def test_delete_playlist(self):
        service = PlaylistService()
        dto = service.create(unique_name("Borrable"))
        service.delete(dto.id)
        result = service.get_by_id(dto.id)
        assert result is None

    def test_delete_continuity_raises(self):
        service = PlaylistService()
        cont = service.get_continuity()
        with pytest.raises(PlaylistProtectedError):
            service.delete(cont.id)

    def test_delete_playlist_with_events_raises(self):
        service = PlaylistService()
        dto = service.create(unique_name("ConEvento"))
        session = get_session()
        ev = RadioEvent(name="Evento", start_time="10:00", playlist_id=dto.id)
        session.add(ev)
        session.commit()
        session.close()
        with pytest.raises(PlaylistError, match="asignada"):
            service.delete(dto.id)

    def test_add_track_item(self):
        service = PlaylistService()
        dto = service.create(unique_name("Tracks"))
        item = service.add_item(
            playlist_id=dto.id,
            item_type="track",
            filepath="/music/cancion.mp3",
        )
        assert item.item_type == "track"
        assert item.position == 0
        assert "cancion.mp3" in item.label

    def test_add_folder_item(self):
        service = PlaylistService()
        dto = service.create(unique_name("Folders"))
        item = service.add_item(
            playlist_id=dto.id,
            item_type="folder",
            folder_path="/music/rock",
        )
        assert item.item_type == "folder"
        assert "rock" in item.label

    def test_add_time_announce_item(self):
        service = PlaylistService()
        dto = service.create(unique_name("Time"))
        item = service.add_item(
            playlist_id=dto.id,
            item_type="time_announce",
        )
        assert item.item_type == "time_announce"

    def test_add_nested_playlist_item(self):
        service = PlaylistService()
        parent = service.create(unique_name("Padre"))
        child = service.create(unique_name("Hija"))
        item = service.add_item(
            playlist_id=parent.id,
            item_type="playlist",
            referenced_playlist_id=child.id,
        )
        assert item.item_type == "playlist"
        assert "Hija" in item.label

    def test_circular_reference_raises(self):
        service = PlaylistService()
        p1 = service.create(unique_name("P1"))
        p2 = service.create(unique_name("P2"))
        # P2 contiene P1
        service.add_item(p2.id, "playlist", referenced_playlist_id=p1.id)
        # Intentar meter P2 dentro de P1 -> circular
        with pytest.raises(CircularReferenceError):
            service.add_item(p1.id, "playlist", referenced_playlist_id=p2.id)

    def test_circular_deep_raises(self):
        """Referencia circular de 3 niveles."""
        service = PlaylistService()
        a = service.create(unique_name("A"))
        b = service.create(unique_name("B"))
        c = service.create(unique_name("C"))
        # A -> B -> C
        service.add_item(a.id, "playlist", referenced_playlist_id=b.id)
        service.add_item(b.id, "playlist", referenced_playlist_id=c.id)
        # C -> A: circular!
        with pytest.raises(CircularReferenceError):
            service.add_item(c.id, "playlist", referenced_playlist_id=a.id)

    def test_remove_item_reorders(self):
        service = PlaylistService()
        dto = service.create(unique_name("Reorder"))
        i1 = service.add_item(dto.id, "track", filepath="/a.mp3")
        i2 = service.add_item(dto.id, "track", filepath="/b.mp3")
        i3 = service.add_item(dto.id, "track", filepath="/c.mp3")

        service.remove_item(i2.id)

        items = service.get_items(dto.id)
        assert len(items) == 2
        assert items[0].position == 0
        assert items[1].position == 1

    def test_reorder_items(self):
        service = PlaylistService()
        dto = service.create(unique_name("Mover"))
        i1 = service.add_item(dto.id, "track", filepath="/a.mp3")
        i2 = service.add_item(dto.id, "track", filepath="/b.mp3")

        service.reorder_item(i1.id, 1)

        items = service.get_items(dto.id)
        # Despues de mover i1 a posicion 1, deberia quedar al final
        assert len(items) == 2
        assert items[0].label == "b.mp3"
        assert items[1].label == "a.mp3"

    def test_clear_items(self):
        service = PlaylistService()
        dto = service.create(unique_name("Clear"))
        service.add_item(dto.id, "track", filepath="/a.mp3")
        service.add_item(dto.id, "track", filepath="/b.mp3")

        service.clear_items(dto.id)
        items = service.get_items(dto.id)
        assert len(items) == 0

    def test_get_items_ordered(self):
        service = PlaylistService()
        dto = service.create(unique_name("Orden"))
        service.add_item(dto.id, "track", filepath="/c.mp3")
        service.add_item(dto.id, "track", filepath="/a.mp3")
        service.add_item(dto.id, "track", filepath="/b.mp3")

        items = service.get_items(dto.id)
        positions = [i.position for i in items]
        assert positions == [0, 1, 2]

    def test_get_continuity(self):
        service = PlaylistService()
        cont = service.get_continuity()
        assert cont.is_continuity is True
        assert cont.is_system is True
        assert cont.name == "Continuidad"


class TestFolderScanner:
    """Tests del escaner de carpetas."""

    def test_scan_empty_folder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            files = FolderScanner.scan(tmpdir)
            assert len(files) == 0

    def test_scan_with_audio_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            music_dir = Path(tmpdir) / "music"
            music_dir.mkdir()
            (music_dir / "song1.mp3").touch()
            (music_dir / "song2.flac").touch()
            (music_dir / "readme.txt").touch()  # No es audio

            files = FolderScanner.scan(str(music_dir))
            assert len(files) == 2
            assert any("song1.mp3" in f for f in files)
            assert any("song2.flac" in f for f in files)
            assert not any("readme.txt" in f for f in files)

    def test_scan_subfolders(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sub = Path(tmpdir) / "sub" / "deep"
            sub.mkdir(parents=True)
            (sub / "track.ogg").touch()

            files = FolderScanner.scan(tmpdir)
            assert len(files) == 1
            assert "track.ogg" in files[0]

    def test_register_folder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            music_dir = Path(tmpdir) / "music"
            music_dir.mkdir()
            (music_dir / "song1.mp3").touch()
            (music_dir / "song2.mp3").touch()

            count = FolderScanner.register_folder(str(music_dir))
            assert count == 2

            # Registrar de nuevo no deberia duplicar
            count2 = FolderScanner.register_folder(str(music_dir))
            assert count2 == 0

    def test_get_next_random(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            music_dir = Path(tmpdir) / "music"
            music_dir.mkdir()
            (music_dir / "a.mp3").touch()
            (music_dir / "b.mp3").touch()

            FolderScanner.register_folder(str(music_dir))

            first = FolderScanner.get_next_random(str(music_dir))
            assert first is not None

            second = FolderScanner.get_next_random(str(music_dir))
            assert second is not None
            assert first != second

            # Tercera peticion: resetea y devuelve uno
            third = FolderScanner.get_next_random(str(music_dir))
            assert third is not None

    def test_unplayed_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            music_dir = Path(tmpdir) / "music"
            music_dir.mkdir()
            (music_dir / "a.mp3").touch()
            (music_dir / "b.mp3").touch()

            FolderScanner.register_folder(str(music_dir))
            assert FolderScanner.get_unplayed_count(str(music_dir)) == 2

            FolderScanner.get_next_random(str(music_dir))
            assert FolderScanner.get_unplayed_count(str(music_dir)) == 1

    def test_reset_folder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            music_dir = Path(tmpdir) / "music"
            music_dir.mkdir()
            (music_dir / "a.mp3").touch()

            FolderScanner.register_folder(str(music_dir))
            FolderScanner.get_next_random(str(music_dir))
            assert FolderScanner.get_unplayed_count(str(music_dir)) == 0

            FolderScanner.reset_folder(str(music_dir))
            assert FolderScanner.get_unplayed_count(str(music_dir)) == 1

    def test_unregister_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            music_dir = Path(tmpdir) / "music"
            music_dir.mkdir()
            (music_dir / "temp.mp3").touch()

            FolderScanner.register_folder(str(music_dir))
            os.unlink(music_dir / "temp.mp3")

            removed = FolderScanner.unregister_missing(str(music_dir))
            assert removed == 1


class TestRadioEvent:
    """Tests del modelo de eventos."""

    def test_normal_event_no_streaming(self):
        ev = RadioEvent(name="Normal", start_time="10:00")
        assert ev.is_streaming is False
        assert ev.has_end_time is False

    def test_streaming_event(self):
        ev = RadioEvent(
            name="Streaming",
            start_time="10:00",
            end_time="12:00",
            streaming_url="http://radio.example.com/stream",
        )
        assert ev.is_streaming is True
        assert ev.has_end_time is True

    def test_week_days_list(self):
        ev = RadioEvent(
            name="LunMieVie",
            start_time="10:00",
            week_days="1,0,1,0,1,0,0",
        )
        days = ev.week_days_list
        assert days == [True, False, True, False, True, False, False]
        assert len(days) == 7


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
