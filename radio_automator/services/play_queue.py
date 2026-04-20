"""
Cola de reproduccion (Play Queue).
Gestiona la lista de pistas por reproducir con soporte para:
- Resolucion de playlists anidadas (recursiva)
- Resolucion de carpetas con anti-repeticion
- Modos: loop (repite toda la cola) y single (para al finalizar)
- Callbacks de avance automatico (next track)
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from radio_automator.core.database import get_session, Session
from radio_automator.core.database import Playlist, PlaylistItem
from radio_automator.services.folder_scanner import FolderScanner
from radio_automator.services.audio_engine import get_audio_engine, TrackInfo


# ═══════════════════════════════════════
# DTOs
# ═══════════════════════════════════════

@dataclass
class QueueItem:
    """Elemento en la cola de reproduccion."""
    filepath: str
    title: str = ""
    artist: str = ""
    duration_ms: int = 0
    source: str = "playlist"  # playlist, folder, streaming, manual
    source_id: int | None = None  # playlist_id, event_id, etc.
    is_streaming: bool = False

    @property
    def mode_label(self) -> str:
        modes = {"loop": "Bucle", "single": "Unha vez"}
        return modes.get(self._mode, self._mode or "Bucle")

    @property
    def label(self) -> str:
        name = Path(self.filepath).name if self.filepath else "?"
        if self.title:
            return f"{self.title} - {name}"
        return name


# ═══════════════════════════════════════
# Excepciones
# ═══════════════════════════════════════

class QueueError(Exception):
    pass


class QueueEmptyError(QueueError):
    pass


# ═══════════════════════════════════════
# PlayQueue
# ═══════════════════════════════════════

class PlayQueue:
    """
    Cola de reproduccion. Resuelve playlists, carpetas y pistas individuales
    en una lista plana de archivos por reproducir.
    """

    def __init__(self):
        self._items: list[QueueItem] = []
        self._current_index: int = -1
        self._mode: str = "loop"  # loop | single
        self._shuffle: bool = False
        self._source_playlist_id: int | None = None

        # Callbacks
        self._on_queue_changed: Callable[[], None] | None = None
        self._on_current_changed: Callable[[QueueItem | None], None] | None = None

    @property
    def mode_label(self) -> str:
        modes = {"loop": "Bucle", "single": "Unha vez"}
        return modes.get(self._mode, self._mode or "Bucle")

    @property
    def items(self) -> list[QueueItem]:
        return list(self._items)

    @property
    def mode_label(self) -> str:
        modes = {"loop": "Bucle", "single": "Unha vez"}
        return modes.get(self._mode, self._mode or "Bucle")

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def mode_label(self) -> str:
        modes = {"loop": "Bucle", "single": "Unha vez"}
        return modes.get(self._mode, self._mode or "Bucle")

    @property
    def current_item(self) -> QueueItem | None:
        if 0 <= self._current_index < len(self._items):
            return self._items[self._current_index]
        return None

    @property
    def mode_label(self) -> str:
        modes = {"loop": "Bucle", "single": "Unha vez"}
        return modes.get(self._mode, self._mode or "Bucle")

    @property
    def next_item(self) -> QueueItem | None:
        """Previsualizar la siguiente pista."""
        if not self._items:
            return None

        if self._mode == "loop":
            next_idx = (self._current_index + 1) % len(self._items)
            return self._items[next_idx]

        # single mode: next only if not at end
        next_idx = self._current_index + 1
        if next_idx < len(self._items):
            return self._items[next_idx]
        return None

    @property
    def mode_label(self) -> str:
        modes = {"loop": "Bucle", "single": "Unha vez"}
        return modes.get(self._mode, self._mode or "Bucle")

    @property
    def previous_item(self) -> QueueItem | None:
        """Previsualizar la pista anterior."""
        if not self._items:
            return None

        prev_idx = self._current_index - 1
        if prev_idx < 0:
            if self._mode == "loop":
                return self._items[-1]
            return None
        return self._items[prev_idx]

    @property
    def mode_label(self) -> str:
        modes = {"loop": "Bucle", "single": "Unha vez"}
        return modes.get(self._mode, self._mode or "Bucle")

    @property
    def is_empty(self) -> bool:
        return len(self._items) == 0

    @property
    def mode_label(self) -> str:
        modes = {"loop": "Bucle", "single": "Unha vez"}
        return modes.get(self._mode, self._mode or "Bucle")

    @property
    def count(self) -> int:
        return len(self._items)

    @property
    def mode_label(self) -> str:
        modes = {"loop": "Bucle", "single": "Unha vez"}
        return modes.get(self._mode, self._mode or "Bucle")

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def mode_label(self) -> str:
        modes = {"loop": "Bucle", "single": "Unha vez"}
        return modes.get(self._mode, self._mode or "Bucle")

    @property
    def progress_text(self) -> str:
        """Texto de progreso: '3 / 10'."""
        if not self._items:
            return "0 / 0"
        current = max(0, self._current_index + 1)
        return f"{current} / {len(self._items)}"

    # ── Configuracion ──

    def set_mode(self, mode: str):
        """Establecer modo: 'loop' o 'single'."""
        if mode in ("loop", "single"):
            self._mode = mode

    def set_shuffle(self, enabled: bool):
        """Activar/desactivar reproduccion aleatoria."""
        self._shuffle = enabled
        if enabled and self._items:
            self._shuffle_remaining()

    def set_callbacks(self,
                     on_queue_changed: Callable[[], None] | None = None,
                     on_current_changed: Callable[[QueueItem | None], None] | None = None):
        self._on_queue_changed = on_queue_changed
        self._on_current_changed = on_current_changed

    # ── Carga de contenido ──

    def load_playlist(self, playlist_id: int, session: Session | None = None) -> int:
        """
        Cargar una playlist en la cola, resolviendo playlists anidadas y carpetas.
        Devuelve el numero de pistas resueltas.
        """
        close = False
        if session is None:
            session = get_session()
            close = True

        try:
            playlist = session.get(Playlist, playlist_id)
            if not playlist:
                raise QueueError(f"Playlist {playlist_id} no encontrada")

            self._source_playlist_id = playlist_id
            self._mode = playlist.mode
            self._current_index = -1

            # Resolver items recursivamente
            items = self._resolve_playlist_items(playlist_id, session, set())
            self._items = items

            # Shuffle si esta activado
            if self._shuffle:
                self._shuffle_remaining()

            self._notify_queue_changed()
            return len(items)

        finally:
            if close:
                session.close()

    def load_files(self, filepaths: list[str], source: str = "manual",
                   source_id: int | None = None) -> int:
        """
        Cargar una lista de archivos directamente en la cola.
        """
        self._items = []
        self._current_index = -1
        self._source_playlist_id = None

        for fp in filepaths:
            if Path(fp).exists():
                self._items.append(QueueItem(
                    filepath=fp,
                    title=Path(fp).stem,
                    source=source,
                    source_id=source_id,
                ))

        self._notify_queue_changed()
        return len(self._items)

    def load_stream(self, url: str, source: str = "streaming",
                    source_id: int | None = None) -> int:
        """Cargar una URL de streaming en la cola."""
        self._items = [QueueItem(
            filepath=url,
            title="Streaming",
            is_streaming=True,
            source=source,
            source_id=source_id,
        )]
        self._current_index = -1
        self._notify_queue_changed()
        return 1

    def add_item(self, filepath: str, source: str = "manual",
                 source_id: int | None = None) -> int:
        """Agregar una pista al final de la cola."""
        self._items.append(QueueItem(
            filepath=filepath,
            title=Path(filepath).stem,
            source=source,
            source_id=source_id,
        ))
        self._notify_queue_changed()
        return len(self._items)

    def insert_item(self, index: int, filepath: str, source: str = "manual",
                    source_id: int | None = None):
        """Insertar una pista en una posicion especifica."""
        index = max(0, min(index, len(self._items)))
        self._items.insert(index, QueueItem(
            filepath=filepath,
            title=Path(filepath).stem,
            source=source,
            source_id=source_id,
        ))
        self._notify_queue_changed()

    def remove_item(self, index: int):
        """Eliminar una pista de la cola."""
        if 0 <= index < len(self._items):
            self._items.pop(index)
            # Ajustar current_index si es necesario
            if index < self._current_index:
                self._current_index -= 1
            elif index == self._current_index:
                # La pista actual fue eliminada
                if self._current_index >= len(self._items):
                    self._current_index = len(self._items) - 1
                self._notify_current_changed()
            self._notify_queue_changed()

    def clear(self):
        """Vaciar la cola."""
        self._items = []
        self._current_index = -1
        self._source_playlist_id = None
        self._notify_queue_changed()

    # ── Navegacion ──

    def play_next(self) -> QueueItem | None:
        """
        Avanzar a la siguiente pista y devolverla.
        Retorna None si la cola esta vacia o en modo single y ya termino.
        """
        if not self._items:
            return None

        if self._mode == "loop":
            self._current_index = (self._current_index + 1) % len(self._items)
        else:
            # single mode
            next_idx = self._current_index + 1
            if next_idx >= len(self._items):
                # Fin de la cola
                self._current_index = -1
                self._notify_current_changed()
                return None
            self._current_index = next_idx

        self._notify_current_changed()
        return self.current_item

    def play_previous(self) -> QueueItem | None:
        """
        Retroceder a la pista anterior.
        Si estamos mas de 3 segundos en la pista actual, vuelve al inicio.
        """
        if not self._items:
            return None

        engine = get_audio_engine()

        # Si estamos mas de 3s, volver al inicio de la pista actual
        if (self._current_index >= 0 and
                engine.state.value in ("playing", "paused") and
                engine.track_info.position_ms > 3000):
            engine.seek(0)
            return self.current_item

        # Retroceder
        prev_idx = self._current_index - 1
        if prev_idx < 0:
            if self._mode == "loop":
                self._current_index = len(self._items) - 1
            else:
                self._current_index = 0
        else:
            self._current_index = prev_idx

        self._notify_current_changed()
        return self.current_item

    def jump_to(self, index: int) -> QueueItem | None:
        """Saltar a una pista especifica."""
        if 0 <= index < len(self._items):
            self._current_index = index
            self._notify_current_changed()
            return self.current_item
        return None

    # ── Auto-play (avance automatico) ──

    def on_track_finished(self, track_info: TrackInfo | None = None):
        """
        Callback para cuando termina una pista.
        Avanza automaticamente a la siguiente.
        """
        next_item = self.play_next()
        if next_item is None:
            # Cola terminada, parar
            engine = get_audio_engine()
            engine.stop()
            return

        # Reproducir siguiente pista
        engine = get_audio_engine()
        if next_item.is_streaming:
            engine.play_stream(next_item.filepath)
        else:
            # Intentar crossfade
            if (engine.state.value == "playing" and
                    not engine.track_info.is_streaming):
                engine.play_file_with_crossfade(next_item.filepath)
            else:
                engine.play_file(next_item.filepath)

    # ── Resolucion de playlists ──

    def _resolve_playlist_items(self, playlist_id: int, session: Session,
                                visited: set[int], depth: int = 0) -> list[QueueItem]:
        """
        Resolver recursivamente los items de una playlist en archivos planos.
        visited: conjunto de IDs visitados para detectar referencias circulares.
        """
        MAX_DEPTH = 10
        if depth > MAX_DEPTH:
            print(f"[PlayQueue] Maxima profundidad alcanzada en resolucion de playlist")
            return []

        if playlist_id in visited:
            print(f"[PlayQueue] Referencia circular detectada en playlist {playlist_id}")
            return []

        visited.add(playlist_id)

        items = session.query(PlaylistItem).filter_by(
            playlist_id=playlist_id
        ).order_by(PlaylistItem.position).all()

        result = []

        for item in items:
            if item.item_type == "track":
                if item.filepath and Path(item.filepath).exists():
                    result.append(QueueItem(
                        filepath=item.filepath,
                        title=Path(item.filepath).stem,
                        source="playlist",
                        source_id=playlist_id,
                    ))

            elif item.item_type == "folder":
                if item.folder_path:
                    folder_files = self._resolve_folder(item.folder_path, session)
                    result.extend(folder_files)

            elif item.item_type == "playlist":
                if item.referenced_playlist_id:
                    nested = self._resolve_playlist_items(
                        item.referenced_playlist_id, session, visited, depth + 1
                    )
                    result.extend(nested)

            elif item.item_type == "time_announce":
                # Los anuncios de hora se insertan como marcadores
                # (se manejaran en la Fase 5 - Parrilla)
                pass

        return result

    def _resolve_folder(self, folder_path: str, session: Session) -> list[QueueItem]:
        """
        Resolver una carpeta en archivos de audio.
        Usa FolderScanner para anti-repeticion.
        """
        scanner = FolderScanner()

        # Obtener siguiente archivo sin repetir
        next_filepath = scanner.get_next_random(folder_path, session=session)
        if next_filepath:
            return [QueueItem(
                filepath=next_filepath,
                title=Path(next_filepath).stem,
                source="folder",
                source_id=None,
            )]

        # Si no hay archivos registrados, hacer scan inicial
        scanner.register_folder(folder_path)
        next_filepath = scanner.get_next_random(folder_path, session=session)
        if next_filepath:
            return [QueueItem(
                filepath=next_filepath,
                title=Path(next_filepath).stem,
                source="folder",
                source_id=None,
            )]

        return []

    # ── Shuffle ──

    def _shuffle_remaining(self):
        """Mezclar las pistas que quedan por reproducir."""
        if self._current_index < 0:
            # Mezclar todo
            random.shuffle(self._items)
        else:
            # Mezclar solo las que quedan
            current = self._items[:self._current_index + 1]
            remaining = self._items[self._current_index + 1:]
            random.shuffle(remaining)
            self._items = current + remaining

        self._notify_queue_changed()

    # ── Notificaciones ──

    def _notify_queue_changed(self):
        if self._on_queue_changed:
            try:
                self._on_queue_changed()
            except Exception as e:
                print(f"[PlayQueue] Error en callback: {e}")

    def _notify_current_changed(self):
        if self._on_current_changed:
            try:
                self._on_current_changed(self.current_item)
            except Exception as e:
                print(f"[PlayQueue] Error en callback: {e}")


# ── Instancia global ──
_queue: PlayQueue | None = None


def get_play_queue() -> PlayQueue:
    """Obtener la instancia singleton del PlayQueue."""
    global _queue
    if _queue is None:
        _queue = PlayQueue()
    return _queue


def reset_play_queue():
    """Reiniciar la cola (para tests)."""
    global _queue
    _queue = None
