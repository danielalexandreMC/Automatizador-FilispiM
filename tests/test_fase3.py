"""Tests de la Fase 3: Podcasts RSS, descargas, scheduler."""

import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from radio_automator.core.database import (
    init_db, get_session, reset_engine,
    PodcastFeed, PodcastEpisode
)
from radio_automator.services.podcast_service import (
    PodcastService, PodcastError, FeedNotFoundError, FeedLimitError
)
from radio_automator.services.podcast_scheduler import PodcastScheduler


# ── Contador para nombres unicos ──
_counter = 0


def unique_name(prefix="Feed") -> str:
    global _counter
    _counter += 1
    return f"{prefix}_{_counter}"


@pytest.fixture(autouse=True)
def fresh_db():
    """Crear una base de datos limpia para cada test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["RADIO_AUTOMATOR_DIR"] = tmpdir
        reset_engine()
        init_db()
        yield tmpdir
        reset_engine()


class TestPodcastServiceFeeds:
    """Tests del servicio de podcasts - CRUD de feeds."""

    def test_add_feed(self):
        service = PodcastService()
        with tempfile.TemporaryDirectory() as dl_dir:
            dto = service.add_feed(
                name=unique_name("Test"),
                url="https://example.com/feed.xml",
                folder_path=dl_dir,
                mode="replace",
                max_episodes=10,
            )
            assert dto.id > 0
            assert dto.name.startswith("Test")
            assert dto.mode == "replace"
            assert dto.max_episodes == 10
            assert dto.is_active is True
            assert dto.episode_count == 0

    def test_add_feed_creates_folder(self):
        service = PodcastService()
        with tempfile.TemporaryDirectory() as parent:
            new_dir = str(Path(parent) / "new_subdir" / "podcasts")
            service.add_feed(
                name=unique_name("Folder"),
                url="https://example.com/feed.xml",
                folder_path=new_dir,
            )
            assert Path(new_dir).is_dir()

    def test_add_duplicate_url_raises(self):
        service = PodcastService()
        with tempfile.TemporaryDirectory() as dl_dir:
            url = "https://example.com/feed.xml"
            service.add_feed(name=unique_name("A"), url=url, folder_path=dl_dir)
            with pytest.raises(PodcastError, match="Ya existe"):
                service.add_feed(name=unique_name("B"), url=url, folder_path=dl_dir)

    def test_get_all_feeds(self):
        service = PodcastService()
        with tempfile.TemporaryDirectory() as dl_dir:
            service.add_feed(name=unique_name("A"), url="https://a.com/feed", folder_path=dl_dir)
            service.add_feed(name=unique_name("B"), url="https://b.com/feed", folder_path=dl_dir)

            feeds = service.get_all_feeds()
            assert len(feeds) >= 2
            names = [f.name for f in feeds]
            assert any("A" in n for n in names)
            assert any("B" in n for n in names)

    def test_get_feed_by_id(self):
        service = PodcastService()
        with tempfile.TemporaryDirectory() as dl_dir:
            dto = service.add_feed(name=unique_name("Find"), url="https://find.com/feed", folder_path=dl_dir)
            found = service.get_feed(dto.id)
            assert found is not None
            assert found.name == dto.name

    def test_update_feed(self):
        service = PodcastService()
        with tempfile.TemporaryDirectory() as dl_dir:
            dto = service.add_feed(name="Original", url="https://old.com/feed", folder_path=dl_dir)
            updated = service.update_feed(dto.id, name="Nuevo", mode="accumulate")
            assert updated.name == "Nuevo"
            assert updated.mode == "accumulate"

    def test_update_feed_deactivate(self):
        service = PodcastService()
        with tempfile.TemporaryDirectory() as dl_dir:
            dto = service.add_feed(name=unique_name("Active"), url="https://a.com/feed", folder_path=dl_dir)
            updated = service.update_feed(dto.id, is_active=False)
            assert updated.is_active is False

    def test_delete_feed(self):
        service = PodcastService()
        with tempfile.TemporaryDirectory() as dl_dir:
            dto = service.add_feed(name=unique_name("Del"), url="https://del.com/feed", folder_path=dl_dir)
            service.delete_feed(dto.id)
            found = service.get_feed(dto.id)
            assert found is None

    def test_delete_feed_not_found_raises(self):
        service = PodcastService()
        with pytest.raises(FeedNotFoundError):
            service.delete_feed(99999)

    def test_feed_limit(self):
        """Verificar que no se pueden crear mas de 50 feeds."""
        service = PodcastService()
        with tempfile.TemporaryDirectory() as dl_dir:
            # Crear 50 feeds
            for i in range(50):
                service.add_feed(
                    name=unique_name(f"F{i}"),
                    url=f"https://example{i}.com/feed",
                    folder_path=dl_dir,
                )

            # El 51 deberia fallar
            with pytest.raises(FeedLimitError, match="limite"):
                service.add_feed(
                    name="OverLimit",
                    url="https://over.com/feed",
                    folder_path=dl_dir,
                )


class TestPodcastServiceEpisodes:
    """Tests del servicio de podcasts - episodios."""

    def test_get_episodes_empty(self):
        service = PodcastService()
        with tempfile.TemporaryDirectory() as dl_dir:
            dto = service.add_feed(name=unique_name("Empty"), url="https://empty.com/feed", folder_path=dl_dir)
            episodes = service.get_episodes(dto.id)
            assert len(episodes) == 0

    def test_get_episodes_feed_not_found(self):
        service = PodcastService()
        with pytest.raises(FeedNotFoundError):
            service.get_episodes(99999)

    def test_delete_episode(self):
        service = PodcastService()
        session = get_session()
        with tempfile.TemporaryDirectory() as dl_dir:
            dto = service.add_feed(name=unique_name("Ep"), url="https://ep.com/feed", folder_path=dl_dir)

            # Crear episodio manualmente
            ep_file = Path(dl_dir) / "test.mp3"
            ep_file.touch()

            ep = PodcastEpisode(
                feed_id=dto.id,
                title="Test Episode",
                url="https://ep.com/ep1.mp3",
                local_path=str(ep_file),
                file_size=1024,
            )
            session.add(ep)
            session.commit()
            ep_id = ep.id
            session.close()

            # Eliminar
            service.delete_episode(ep_id)

            # Verificar archivo eliminado
            assert not ep_file.exists()


class TestPodcastServiceCheckFeed:
    """Tests del servicio de podcasts - comprobacion de feeds (con mocks)."""

    def _mock_feedparser(self, entries=None):
        """Crear un mock de feedparser.parse con entradas simuladas."""
        parsed = MagicMock()
        parsed.entries = entries or []
        return parsed

    def _mock_entry(self, title="Episode", audio_url="https://example.com/ep.mp3"):
        """Crear una entrada RSS mock que se comporta como dict (feedparser)."""
        entry_data = {
            "title": title,
            "published_parsed": None,
            "updated_parsed": None,
            "enclosures": [{"href": audio_url, "type": "audio/mpeg", "length": "5000000"}],
            "media_content": [],
            "links": [],
        }
        entry = MagicMock()
        # feedparser entries son dict-like
        entry.__getitem__ = lambda self, key: entry_data[key]
        entry.get = lambda key, default=None: entry_data.get(key, default)
        entry.__contains__ = lambda self, key: key in entry_data
        entry.keys = lambda: entry_data.keys()
        for k, v in entry_data.items():
            setattr(entry, k, v)
        return entry

    @patch("radio_automator.services.podcast_service.feedparser.parse")
    @patch("radio_automator.services.podcast_service.requests.get")
    def test_check_feed_new_episode(self, mock_get, mock_parse):
        """Probar descarga de un episodio nuevo."""
        service = PodcastService()
        with tempfile.TemporaryDirectory() as dl_dir:
            dto = service.add_feed(name=unique_name("Check"), url="https://check.com/feed", folder_path=dl_dir)

            # Mock del feed RSS
            mock_parse.return_value = self._mock_feedparser([
                self._mock_entry("Nuevo Episodio", "https://check.com/ep1.mp3")
            ])

            # Mock de la descarga
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"Content-Type": "audio/mpeg"}
            mock_response.raise_for_status = MagicMock()
            mock_response.iter_content = MagicMock(return_value=iter([b"fake_audio_data"]))
            mock_get.return_value = mock_response

            result = service.check_feed(dto.id)
            assert result["new"] >= 1
            assert result["downloaded"] >= 1

    @patch("radio_automator.services.podcast_service.feedparser.parse")
    def test_check_feed_empty(self, mock_parse):
        """Probar feed sin entradas."""
        service = PodcastService()
        with tempfile.TemporaryDirectory() as dl_dir:
            dto = service.add_feed(name=unique_name("Empty"), url="https://empty.com/feed", folder_path=dl_dir)

            mock_parse.return_value = self._mock_feedparser([])

            result = service.check_feed(dto.id)
            assert result["new"] == 0
            assert result["downloaded"] == 0

    def test_check_feed_inactive(self):
        """Feed inactivo no se comprueba."""
        service = PodcastService()
        with tempfile.TemporaryDirectory() as dl_dir:
            dto = service.add_feed(name=unique_name("Inactive"), url="https://off.com/feed", folder_path=dl_dir)
            service.update_feed(dto.id, is_active=False)

            result = service.check_feed(dto.id)
            assert result["new"] == 0
            assert result["downloaded"] == 0

    @patch("radio_automator.services.podcast_service.feedparser.parse")
    def test_check_feed_not_found(self, mock_parse):
        """Feed que no existe en DB lanza error."""
        service = PodcastService()
        with pytest.raises(FeedNotFoundError):
            service.check_feed(99999)

    @patch("radio_automator.services.podcast_service.feedparser.parse")
    def test_check_feed_rss_error(self, mock_parse):
        """Error al parsear RSS."""
        service = PodcastService()
        with tempfile.TemporaryDirectory() as dl_dir:
            dto = service.add_feed(name=unique_name("Err"), url="https://err.com/feed", folder_path=dl_dir)
            mock_parse.side_effect = Exception("Network error")

            with pytest.raises(Exception):
                service.check_feed(dto.id)


class TestPodcastServiceHelpers:
    """Tests de metodos auxiliares."""

    def test_sanitize_filename(self):
        service = PodcastService()
        assert service._sanitize_filename("Normal Name") == "Normal Name"
        assert service._sanitize_filename('File:with/bad\\chars*?') == "File_with_bad_chars__"
        assert service._sanitize_filename("") == "episodio"
        assert service._sanitize_filename("A" * 300)[:200] == "A" * 200

    def test_extension_from_url(self):
        service = PodcastService()
        assert service._extension_from_url_or_type("https://a.com/ep.mp3", "") == ".mp3"
        assert service._extension_from_url_or_type("https://a.com/ep.m4a", "") == ".m4a"
        assert service._extension_from_url_or_type("https://a.com/ep", "audio/mpeg") == ".mp3"
        assert service._extension_from_url_or_type("https://a.com/ep", "audio/ogg") == ".ogg"
        assert service._extension_from_url_or_type("https://a.com/ep", "audio/mp4") == ".m4a"
        # Default
        assert service._extension_from_url_or_type("https://a.com/ep", "unknown") == ".mp3"

    def test_find_audio_enclosure(self):
        service = PodcastService()

        # Con enclosure de audio
        entry = MagicMock()
        entry.enclosures = [{"href": "https://a.com/ep.mp3", "type": "audio/mpeg"}]
        result = service._find_audio_enclosure(entry)
        assert result is not None
        assert result["href"] == "https://a.com/ep.mp3"

        # Sin enclosures de audio
        entry2 = MagicMock()
        entry2.enclosures = [{"href": "https://a.com/img.jpg", "type": "image/jpeg"}]
        entry2.media_content = []
        entry2.links = []
        result2 = service._find_audio_enclosure(entry2)
        assert result2 is None

    def test_find_audio_enclosure_from_links(self):
        service = PodcastService()
        entry = MagicMock()
        entry.enclosures = []
        entry.media_content = []
        entry.links = [{"href": "https://a.com/ep.flac", "type": ""}]
        result = service._find_audio_enclosure(entry)
        assert result is not None
        assert "ep.flac" in result["href"]

    def test_total_storage(self):
        service = PodcastService()
        with tempfile.TemporaryDirectory() as dl_dir:
            dto = service.add_feed(name=unique_name("Storage"), url="https://s.com/feed", folder_path=dl_dir)

            session = get_session()
            ep = PodcastEpisode(
                feed_id=dto.id,
                title="Big Episode",
                url="https://s.com/big.mp3",
                local_path=str(Path(dl_dir) / "big.mp3"),
                file_size=5 * 1024 * 1024,  # 5 MB
            )
            session.add(ep)
            session.commit()
            session.close()

            mb = service.get_total_storage_mb()
            assert mb >= 5.0


class TestPodcastScheduler:
    """Tests del scheduler de podcasts."""

    def test_scheduler_starts_and_stops(self):
        scheduler = PodcastScheduler()
        assert scheduler._running is False

        scheduler.start()
        assert scheduler._running is True

        scheduler.stop()
        assert scheduler._running is False

    def test_double_start(self):
        scheduler = PodcastScheduler()
        scheduler.start()
        scheduler.start()  # No deberia crear un segundo hilo
        assert scheduler._running is True
        scheduler.stop()

    def test_restart(self):
        scheduler = PodcastScheduler()
        scheduler.start()
        scheduler.restart()
        assert scheduler._running is True
        scheduler.stop()
        assert scheduler._running is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
