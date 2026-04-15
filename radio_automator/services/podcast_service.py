"""
Servicio de gestion de Podcasts.
Parseo de feeds RSS, descarga de episodios, modos replace/accumulate.
"""

from __future__ import annotations

import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

import feedparser
import requests

from radio_automator.core.database import (
    get_session, Session, PodcastFeed, PodcastEpisode
)
from radio_automator.core.config import get_config
from radio_automator.core.event_bus import get_event_bus


# ═══════════════════════════════════════
# Excepciones
# ═══════════════════════════════════════

class PodcastError(Exception):
    """Error general de podcast."""
    pass


class FeedNotFoundError(PodcastError):
    pass


class FeedURLError(PodcastError):
    """Error al acceder a la URL del feed."""
    pass


class FeedLimitError(PodcastError):
    """Limite de feeds alcanzado."""
    pass


# ═══════════════════════════════════════
# DTOs
# ═══════════════════════════════════════

@dataclass
class EpisodeDTO:
    """Representacion de un episodio descargado."""
    id: int
    feed_id: int
    feed_name: str
    title: str
    url: str
    local_path: str
    published_at: str
    downloaded_at: str
    file_size_mb: float
    filename: str

    @property
    def size_label(self) -> str:
        if self.file_size_mb < 1.0:
            return f"{self.file_size_mb * 1024:.0f} KB"
        return f"{self.file_size_mb:.1f} MB"


@dataclass
class FeedDTO:
    """Representacion de un feed RSS."""
    id: int
    name: str
    url: str
    folder_path: str
    mode: str
    max_episodes: int | None
    is_active: bool
    episode_count: int
    last_check_at: str
    created_at: str

    @property
    def mode_label(self) -> str:
        return "Reemplazar" if self.mode == "replace" else "Acumular"

    @property
    def max_label(self) -> str:
        if self.max_episodes is None:
            return "Sin limite"
        return str(self.max_episodes)

    @property
    def status_text(self) -> str:
        if not self.is_active:
            return "Inactivo"
        return "Activo"


# ═══════════════════════════════════════
# Servicio de Podcasts
# ═══════════════════════════════════════

MAX_FEEDS = 50
MIN_FEEDS = 0
USER_AGENT = "RadioAutomator/0.2 (Podcast Aggregator)"
REQUEST_TIMEOUT = 30


class PodcastService:
    """Servicio para gestionar feeds y episodios de podcasts."""

    def get_all_feeds(self, session: Session | None = None) -> list[FeedDTO]:
        """Obtener todos los feeds RSS."""
        close = False
        if session is None:
            session = get_session()
            close = True
        try:
            feeds = session.query(PodcastFeed).order_by(PodcastFeed.name).all()
            result = []
            for f in feeds:
                episode_count = session.query(PodcastEpisode).filter_by(
                    feed_id=f.id
                ).count()
                result.append(FeedDTO(
                    id=f.id,
                    name=f.name,
                    url=f.url,
                    folder_path=f.folder_path,
                    mode=f.mode,
                    max_episodes=f.max_episodes,
                    is_active=f.is_active,
                    episode_count=episode_count,
                    last_check_at=(
                        f.last_check_at.strftime("%Y-%m-%d %H:%M")
                        if f.last_check_at else "Nunca"
                    ),
                    created_at=f.created_at.strftime("%Y-%m-%d %H:%M"),
                ))
            return result
        finally:
            if close:
                session.close()

    def get_feed(self, feed_id: int, session: Session | None = None) -> FeedDTO | None:
        """Obtener un feed por ID."""
        close = False
        if session is None:
            session = get_session()
            close = True
        try:
            f = session.get(PodcastFeed, feed_id)
            if not f:
                return None
            episode_count = session.query(PodcastEpisode).filter_by(
                feed_id=f.id
            ).count()
            return FeedDTO(
                id=f.id,
                name=f.name,
                url=f.url,
                folder_path=f.folder_path,
                mode=f.mode,
                max_episodes=f.max_episodes,
                is_active=f.is_active,
                episode_count=episode_count,
                last_check_at=(
                    f.last_check_at.strftime("%Y-%m-%d %H:%M")
                    if f.last_check_at else "Nunca"
                ),
                created_at=f.created_at.strftime("%Y-%m-%d %H:%M"),
            )
        finally:
            if close:
                session.close()

    def add_feed(self, name: str, url: str, folder_path: str,
                 mode: str = "replace",
                 max_episodes: int | None = None) -> FeedDTO:
        """Crear un nuevo feed RSS."""
        session = get_session()
        try:
            # Verificar limite de feeds
            count = session.query(PodcastFeed).count()
            if count >= MAX_FEEDS:
                raise FeedLimitError(
                    f"Se ha alcanzado el limite de {MAX_FEEDS} feeds"
                )

            # Verificar URL duplicada
            existing = session.query(PodcastFeed).filter_by(url=url).first()
            if existing:
                raise PodcastError(f"Ya existe un feed con la URL: {url}")

            # Crear carpeta si no existe
            folder = Path(folder_path)
            folder.mkdir(parents=True, exist_ok=True)

            feed = PodcastFeed(
                name=name,
                url=url,
                folder_path=str(folder.resolve()),
                mode=mode,
                max_episodes=max_episodes,
            )
            session.add(feed)
            session.flush()
            session.commit()
            session.refresh(feed)

            dto = FeedDTO(
                id=feed.id,
                name=feed.name,
                url=feed.url,
                folder_path=feed.folder_path,
                mode=feed.mode,
                max_episodes=feed.max_episodes,
                is_active=True,
                episode_count=0,
                last_check_at="Nunca",
                created_at=feed.created_at.strftime("%Y-%m-%d %H:%M"),
            )

            # Publicar evento
            get_event_bus().publish("podcast.feed_added", {"feed_id": feed.id, "name": name})

            return dto
        except (FeedLimitError, PodcastError):
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_feed(self, feed_id: int, name: str | None = None,
                    url: str | None = None, folder_path: str | None = None,
                    mode: str | None = None,
                    max_episodes: int | None = None,
                    is_active: bool | None = None) -> FeedDTO:
        """Actualizar un feed RSS."""
        session = get_session()
        try:
            f = session.get(PodcastFeed, feed_id)
            if not f:
                raise FeedNotFoundError(f"Feed {feed_id} no encontrado")

            if name is not None:
                f.name = name
            if url is not None:
                f.url = url
            if folder_path is not None:
                f.folder_path = str(Path(folder_path).resolve())
                Path(folder_path).mkdir(parents=True, exist_ok=True)
            if mode is not None and mode in ("replace", "accumulate"):
                f.mode = mode
            if max_episodes is not None:
                f.max_episodes = max_episodes if max_episodes > 0 else None
            if is_active is not None:
                f.is_active = is_active

            session.commit()
            session.refresh(f)

            episode_count = session.query(PodcastEpisode).filter_by(
                feed_id=f.id
            ).count()

            return FeedDTO(
                id=f.id,
                name=f.name,
                url=f.url,
                folder_path=f.folder_path,
                mode=f.mode,
                max_episodes=f.max_episodes,
                is_active=f.is_active,
                episode_count=episode_count,
                last_check_at=(
                    f.last_check_at.strftime("%Y-%m-%d %H:%M")
                    if f.last_check_at else "Nunca"
                ),
                created_at=f.created_at.strftime("%Y-%m-%d %H:%M"),
            )
        except FeedNotFoundError:
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete_feed(self, feed_id: int):
        """Eliminar un feed y todos sus episodios (archivos locales incluidos)."""
        session = get_session()
        try:
            f = session.get(PodcastFeed, feed_id)
            if not f:
                raise FeedNotFoundError(f"Feed {feed_id} no encontrado")

            # Eliminar archivos locales de episodios
            episodes = session.query(PodcastEpisode).filter_by(feed_id=feed_id).all()
            for ep in episodes:
                local = Path(ep.local_path)
                if local.exists():
                    try:
                        local.unlink()
                    except OSError:
                        pass

            # Eliminar la carpeta del feed si esta vacia
            feed_folder = Path(f.folder_path)
            if feed_folder.exists() and feed_folder.is_dir():
                try:
                    # Solo eliminar si esta vacia
                    if not any(feed_folder.iterdir()):
                        feed_folder.rmdir()
                except OSError:
                    pass

            session.delete(f)
            session.commit()

            get_event_bus().publish("podcast.feed_deleted", {"feed_id": feed_id})
        except FeedNotFoundError:
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_episodes(self, feed_id: int, limit: int = 50) -> list[EpisodeDTO]:
        """Obtener los episodios de un feed ordenados por fecha de publicacion."""
        session = get_session()
        try:
            feed = session.get(PodcastFeed, feed_id)
            if not feed:
                raise FeedNotFoundError(f"Feed {feed_id} no encontrado")

            episodes = (
                session.query(PodcastEpisode)
                .filter_by(feed_id=feed_id)
                .order_by(PodcastEpisode.published_at.desc())
                .limit(limit)
                .all()
            )

            return [
                EpisodeDTO(
                    id=ep.id,
                    feed_id=feed_id,
                    feed_name=feed.name,
                    title=ep.title,
                    url=ep.url,
                    local_path=ep.local_path,
                    published_at=(
                        ep.published_at.strftime("%Y-%m-%d %H:%M")
                        if ep.published_at else "Desconocido"
                    ),
                    downloaded_at=ep.downloaded_at.strftime("%Y-%m-%d %H:%M"),
                    file_size_mb=(ep.file_size or 0) / (1024 * 1024),
                    filename=Path(ep.local_path).name if ep.local_path else "?",
                )
                for ep in episodes
            ]
        finally:
            session.close()

    def check_feed(self, feed_id: int) -> dict:
        """
        Comprobar un feed RSS y descargar episodios nuevos.
        Devuelve dict con resultados: {'new': N, 'downloaded': N, 'errors': N}
        """
        session = get_session()
        try:
            feed = session.get(PodcastFeed, feed_id)
            if not feed:
                raise FeedNotFoundError(f"Feed {feed_id} no encontrado")
            if not feed.is_active:
                return {"new": 0, "downloaded": 0, "errors": 0, "skipped": 0}

            # Parsear RSS
            result = {"new": 0, "downloaded": 0, "errors": 0, "skipped": 0}

            try:
                parsed = feedparser.parse(
                    feed.url,
                    request_headers={"User-Agent": USER_AGENT}
                )
            except Exception as e:
                raise FeedURLError(f"Error al parsear RSS: {e}")

            if not parsed.entries:
                feed.last_check_at = datetime.now(timezone.utc)
                session.commit()
                return result

            # Obtener URLs ya descargadas
            existing_urls = set()
            existing_eps = session.query(PodcastEpisode).filter_by(feed_id=feed_id).all()
            for ep in existing_eps:
                existing_urls.add(ep.url)

            # Procesar entradas
            entries = self._sort_entries(parsed.entries)

            for entry in entries:
                enclosure = self._find_audio_enclosure(entry)
                if not enclosure:
                    continue

                audio_url = enclosure.get("href", "")
                if not audio_url:
                    continue

                # Ya descargado?
                if audio_url in existing_urls:
                    result["skipped"] += 1
                    continue

                result["new"] += 1

                # Descargar
                try:
                    local_path = self._download_episode(
                        audio_url=audio_url,
                        feed_folder=feed.folder_path,
                        title=entry.get("title", "episodio"),
                    )

                    if local_path:
                        published = self._parse_date(entry)
                        file_size = Path(local_path).stat().st_size if Path(local_path).exists() else 0

                        episode = PodcastEpisode(
                            feed_id=feed_id,
                            title=entry.get("title", "Sin titulo"),
                            url=audio_url,
                            local_path=local_path,
                            published_at=published,
                            file_size=file_size,
                        )
                        session.add(episode)
                        result["downloaded"] += 1

                except Exception as e:
                    result["errors"] += 1
                    print(f"[PodcastService] Error descargando {audio_url}: {e}")

            # Modo replace: eliminar episodios excedentes
            if feed.mode == "replace" and feed.max_episodes is not None:
                self._apply_replace_mode(feed_id, feed.max_episodes, session)

            # Actualizar ultima comprobacion
            feed.last_check_at = datetime.now(timezone.utc)
            session.commit()

            # Publicar evento
            get_event_bus().publish("podcast.feed_checked", {
                "feed_id": feed_id,
                "feed_name": feed.name,
                **result,
            })

            return result
        finally:
            session.close()

    def check_all_feeds(self) -> dict:
        """Comprobar todos los feeds activos."""
        session = get_session()
        try:
            feeds = session.query(PodcastFeed).filter_by(is_active=True).all()
        finally:
            session.close()

        total = {"new": 0, "downloaded": 0, "errors": 0, "skipped": 0, "feeds": len(feeds)}
        for f in feeds:
            try:
                result = self.check_feed(f.id)
                total["new"] += result["new"]
                total["downloaded"] += result["downloaded"]
                total["errors"] += result["errors"]
                total["skipped"] += result["skipped"]
            except Exception as e:
                print(f"[PodcastService] Error en feed {f.name}: {e}")
                total["errors"] += 1

        get_event_bus().publish("podcast.all_feeds_checked", total)
        return total

    def check_all_feeds_async(self):
        """Comprobar todos los feeds en un hilo separado."""
        def _worker():
            try:
                self.check_all_feeds()
            except Exception as e:
                print(f"[PodcastService] Error en check async: {e}")

        thread = threading.Thread(target=_worker, daemon=True, name="podcast-checker")
        thread.start()
        return thread

    def delete_episode(self, episode_id: int):
        """Eliminar un episodio y su archivo local."""
        session = get_session()
        try:
            ep = session.get(PodcastEpisode, episode_id)
            if not ep:
                raise PodcastError(f"Episodio {episode_id} no encontrado")

            # Eliminar archivo local
            local = Path(ep.local_path)
            if local.exists():
                try:
                    local.unlink()
                except OSError:
                    pass

            session.delete(ep)
            session.commit()
        except PodcastError:
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_total_storage_mb(self) -> float:
        """Obtener el espacio total usado por episodios en MB."""
        session = get_session()
        try:
            total = session.query(
                PodcastEpisode
            ).all()
            size = sum(ep.file_size or 0 for ep in total)
            return size / (1024 * 1024)
        finally:
            session.close()

    # ── Metodos privados ──

    def _sort_entries(self, entries: list) -> list:
        """Ordenar entradas por fecha de publicacion (mas nuevas primero)."""
        def sort_key(entry):
            published = self._parse_date(entry)
            if published:
                return published.timestamp() if hasattr(published, 'timestamp') else 0
            return 0

        return sorted(entries, key=sort_key, reverse=True)

    def _find_audio_enclosure(self, entry) -> dict | None:
        """Encontrar el enlace de audio en una entrada RSS."""
        # Buscar en enclosures
        if hasattr(entry, "enclosures") and entry.enclosures:
            audio_types = {
                "audio/mpeg", "audio/mp3", "audio/x-m4a", "audio/mp4",
                "audio/ogg", "audio/vorbis", "audio/flac", "audio/wav",
                "audio/aac", "audio/x-mpegurl", "audio/mpegurl",
            }
            for enc in entry.enclosures:
                enc_type = enc.get("type", "").lower()
                href = enc.get("href", "")
                if href and (enc_type in audio_types or
                             any(href.lower().endswith(ext) for ext in
                                 [".mp3", ".m4a", ".ogg", ".mp4", ".opus",
                                  ".flac", ".wav", ".aac"])):
                    return enc

        # Buscar en media_content
        if hasattr(entry, "media_content") and entry.media_content:
            for media in entry.media_content:
                href = media.get("url", "")
                if href and any(href.lower().endswith(ext) for ext in
                               [".mp3", ".m4a", ".ogg", ".mp4", ".opus",
                                ".flac", ".wav", ".aac"]):
                    return {"href": href, "type": media.get("type", ""), "length": media.get("fileSize", "")}

        # Buscar en links
        if hasattr(entry, "links"):
            for link in entry.links:
                href = link.get("href", "")
                link_type = link.get("type", "").lower()
                if href and ("audio" in link_type or
                             any(href.lower().endswith(ext) for ext in
                                 [".mp3", ".m4a", ".ogg", ".mp4", ".opus",
                                  ".flac", ".wav", ".aac"])):
                    return {"href": href, "type": link_type, "length": ""}

        return None

    def _sanitize_filename(self, name: str) -> str:
        """Limpiar un nombre para usar como nombre de archivo."""
        # Eliminar caracteres problematicos
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
        # Limitar longitud
        name = name[:200].strip()
        if not name:
            name = "episodio"
        return name

    def _download_episode(self, audio_url: str, feed_folder: str,
                          title: str) -> str | None:
        """
        Descargar un episodio. Devuelve la ruta local o None.
        """
        try:
            resp = requests.get(
                audio_url,
                stream=True,
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
            )
            resp.raise_for_status()

            # Determinar extension del archivo
            content_type = resp.headers.get("Content-Type", "")
            ext = self._extension_from_url_or_type(audio_url, content_type)

            # Generar nombre de archivo
            safe_title = self._sanitize_filename(title)
            local_filename = f"{safe_title}{ext}"

            # Evitar colisiones
            local_path = Path(feed_folder) / local_filename
            counter = 1
            while local_path.exists():
                local_filename = f"{safe_title}_{counter}{ext}"
                local_path = Path(feed_folder) / local_filename
                counter += 1

            # Descargar con streaming
            with open(local_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            return str(local_path)

        except Exception as e:
            print(f"[PodcastService] Error descargando {audio_url}: {e}")
            return None

    def _extension_from_url_or_type(self, url: str, content_type: str) -> str:
        """Determinar extension de archivo desde URL o Content-Type."""
        # Primero intentar desde URL
        url_lower = url.lower().split("?")[0]
        for ext in [".mp3", ".m4a", ".ogg", ".mp4", ".opus", ".flac", ".wav", ".aac"]:
            if url_lower.endswith(ext):
                return ext

        # Despues desde Content-Type
        type_map = {
            "audio/mpeg": ".mp3",
            "audio/mp3": ".mp3",
            "audio/x-m4a": ".m4a",
            "audio/mp4": ".m4a",
            "audio/ogg": ".ogg",
            "audio/vorbis": ".ogg",
            "audio/opus": ".opus",
            "audio/flac": ".flac",
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
            "audio/aac": ".aac",
        }
        ct_lower = content_type.lower().split(";")[0].strip()
        return type_map.get(ct_lower, ".mp3")

    def _parse_date(self, entry) -> datetime | None:
        """Parsear la fecha de publicacion de una entrada RSS."""
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            import time
            try:
                ts = time.mktime(entry.published_parsed)
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except (TypeError, ValueError, OverflowError):
                pass

        if hasattr(entry, "updated_parsed") and entry.updated_parsed:
            import time
            try:
                ts = time.mktime(entry.updated_parsed)
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except (TypeError, ValueError, OverflowError):
                pass

        return None

    def _apply_replace_mode(self, feed_id: int, max_episodes: int,
                            session: Session):
        """En modo replace, eliminar los episodios mas antiguos que excedan el limite."""
        episodes = (
            session.query(PodcastEpisode)
            .filter_by(feed_id=feed_id)
            .order_by(PodcastEpisode.published_at.desc())
            .all()
        )

        if len(episodes) <= max_episodes:
            return

        # Eliminar los mas antiguos
        to_delete = episodes[max_episodes:]
        for ep in to_delete:
            local = Path(ep.local_path)
            if local.exists():
                try:
                    local.unlink()
                except OSError:
                    pass
            session.delete(ep)


# ── Instancia global ──
_service: PodcastService | None = None


def get_podcast_service() -> PodcastService:
    global _service
    if _service is None:
        _service = PodcastService()
    return _service
