"""
Servicio de gestion de playlists.
CRUD de playlists y sus items, incluidas playlists anidables.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from radio_automator.core.database import (
    get_session, Session, Playlist, PlaylistItem, RadioEvent
)


# ═══════════════════════════════════════
# Excepciones
# ═══════════════════════════════════════

class PlaylistError(Exception):
    """Error general de playlist."""
    pass


class PlaylistNotFoundError(PlaylistError):
    pass


class PlaylistProtectedError(PlaylistError):
    """Intento de borrar/modificar la playlist Continuidad."""
    pass


class CircularReferenceError(PlaylistError):
    """Referencia circular entre playlists anidadas."""
    pass


# ═══════════════════════════════════════
# DTOs
# ═══════════════════════════════════════

class PlaylistDTO:
    """Representacion ligera de una playlist para la UI."""

    def __init__(self, id: int, name: str, mode: str, is_system: bool,
                 is_continuity: bool, item_count: int, created_at: str,
                 updated_at: str):
        self.id = id
        self.name = name
        self.mode = mode
        self.is_system = is_system
        self.is_continuity = is_continuity
        self.item_count = item_count
        self.created_at = created_at
        self.updated_at = updated_at

    @property
    def mode_label(self) -> str:
        return "Bucle" if self.mode == "loop" else "Una vez"

    @property
    def mode_badge_class(self) -> str:
        if self.is_system:
            return "ra-badge-system"
        return "ra-badge-loop" if self.mode == "loop" else "ra-badge-single"


class PlaylistItemDTO:
    """Representacion ligera de un item de playlist."""

    def __init__(self, id: int, position: int, item_type: str,
                 label: str, duration_hint: str = ""):
        self.id = id
        self.position = position
        self.item_type = item_type
        self.label = label
        self.duration_hint = duration_hint

    @property
    def type_icon(self) -> str:
        icons = {
            "track": "🎵",
            "folder": "📁",
            "playlist": "🔗",
            "time_announce": "🕐",
        }
        return icons.get(self.item_type, "❓")

    @property
    def type_label(self) -> str:
        labels = {
            "track": "Pista",
            "folder": "Carpeta",
            "playlist": "Playlist",
            "time_announce": "Hora",
        }
        return labels.get(self.item_type, self.item_type)


# ═══════════════════════════════════════
# Servicio de Playlists
# ═══════════════════════════════════════

class PlaylistService:
    """Servicio para gestionar playlists."""

    def get_all(self, session: Session | None = None) -> list[PlaylistDTO]:
        """Obtener todas las playlists ordenadas."""
        close = False
        if session is None:
            session = get_session()
            close = True
        try:
            playlists = (
                session.query(Playlist)
                .order_by(Playlist.is_system.desc(), Playlist.sort_order, Playlist.name)
                .all()
            )
            return [
                PlaylistDTO(
                    id=p.id,
                    name=p.name,
                    mode=p.mode,
                    is_system=p.is_system,
                    is_continuity=p.is_continuity,
                    item_count=len(p.items),
                    created_at=p.created_at.strftime("%Y-%m-%d %H:%M"),
                    updated_at=p.updated_at.strftime("%Y-%m-%d %H:%M"),
                )
                for p in playlists
            ]
        finally:
            if close:
                session.close()

    def get_by_id(self, playlist_id: int, session: Session | None = None) -> PlaylistDTO | None:
        """Obtener una playlist por ID."""
        close = False
        if session is None:
            session = get_session()
            close = True
        try:
            p = session.get(Playlist, playlist_id)
            if not p:
                return None
            return PlaylistDTO(
                id=p.id,
                name=p.name,
                mode=p.mode,
                is_system=p.is_system,
                is_continuity=p.is_continuity,
                item_count=len(p.items),
                created_at=p.created_at.strftime("%Y-%m-%d %H:%M"),
                updated_at=p.updated_at.strftime("%Y-%m-%d %H:%M"),
            )
        finally:
            if close:
                session.close()

    def get_continuity(self, session: Session | None = None) -> PlaylistDTO:
        """Obtener la playlist Continuidad."""
        close = False
        if session is None:
            session = get_session()
            close = True
        try:
            p = session.query(Playlist).filter_by(is_system=True, name="Continuidad").first()
            if not p:
                raise PlaylistNotFoundError("No se encuentra la playlist Continuidad")
            return PlaylistDTO(
                id=p.id,
                name=p.name,
                mode=p.mode,
                is_system=p.is_system,
                is_continuity=True,
                item_count=len(p.items),
                created_at=p.created_at.strftime("%Y-%m-%d %H:%M"),
                updated_at=p.updated_at.strftime("%Y-%m-%d %H:%M"),
            )
        finally:
            if close:
                session.close()

    def create(self, name: str, mode: str = "loop") -> PlaylistDTO:
        """Crear una nueva playlist."""
        session = get_session()
        try:
            # Verificar que no exista el nombre
            existing = session.query(Playlist).filter_by(name=name).first()
            if existing:
                raise PlaylistError(f"Ya existe una playlist con el nombre '{name}'")

            playlist = Playlist(name=name, mode=mode, is_system=False)
            session.add(playlist)
            session.flush()

            # Asignar sort_order al final
            max_order = session.query(Playlist).filter_by(is_system=False).count()
            playlist.sort_order = max_order

            session.commit()
            session.refresh(playlist)

            return PlaylistDTO(
                id=playlist.id,
                name=playlist.name,
                mode=playlist.mode,
                is_system=False,
                is_continuity=False,
                item_count=0,
                created_at=playlist.created_at.strftime("%Y-%m-%d %H:%M"),
                updated_at=playlist.updated_at.strftime("%Y-%m-%d %H:%M"),
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update(self, playlist_id: int, name: str | None = None,
               mode: str | None = None) -> PlaylistDTO:
        """Actualizar nombre y/o modo de una playlist."""
        session = get_session()
        try:
            p = session.get(Playlist, playlist_id)
            if not p:
                raise PlaylistNotFoundError(f"Playlist {playlist_id} no encontrada")

            if name is not None:
                # Verificar nombre duplicado
                existing = session.query(Playlist).filter(
                    Playlist.name == name, Playlist.id != playlist_id
                ).first()
                if existing:
                    raise PlaylistError(f"Ya existe una playlist con el nombre '{name}'")
                p.name = name

            if mode is not None and mode in ("loop", "single"):
                p.mode = mode

            session.commit()
            session.refresh(p)

            return PlaylistDTO(
                id=p.id, name=p.name, mode=p.mode,
                is_system=p.is_system, is_continuity=p.is_continuity,
                item_count=len(p.items),
                created_at=p.created_at.strftime("%Y-%m-%d %H:%M"),
                updated_at=p.updated_at.strftime("%Y-%m-%d %H:%M"),
            )
        except PlaylistNotFoundError:
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete(self, playlist_id: int):
        """Eliminar una playlist (no se puede eliminar Continuidad)."""
        session = get_session()
        try:
            p = session.get(Playlist, playlist_id)
            if not p:
                raise PlaylistNotFoundError(f"Playlist {playlist_id} no encontrada")

            if p.is_continuity:
                raise PlaylistProtectedError("La playlist Continuidad no se puede eliminar")

            # Verificar si es referenciada por eventos
            events = session.query(RadioEvent).filter_by(playlist_id=playlist_id).count()
            if events > 0:
                raise PlaylistError(
                    f"Esta playlist esta asignada a {events} evento(s) y no se puede eliminar. "
                    "Elimina primero las asignaciones."
                )

            session.delete(p)
            session.commit()
        except PlaylistNotFoundError:
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ── Items de playlist ──

    def get_items(self, playlist_id: int) -> list[PlaylistItemDTO]:
        """Obtener todos los items de una playlist ordenados por posicion."""
        session = get_session()
        try:
            items = (
                session.query(PlaylistItem)
                .filter_by(playlist_id=playlist_id)
                .order_by(PlaylistItem.position)
                .all()
            )
            result = []
            for item in items:
                label = self._item_label(item, session)
                result.append(PlaylistItemDTO(
                    id=item.id,
                    position=item.position,
                    item_type=item.item_type,
                    label=label,
                ))
            return result
        finally:
            session.close()

    def add_item(self, playlist_id: int, item_type: str,
                 filepath: str | None = None,
                 folder_path: str | None = None,
                 referenced_playlist_id: int | None = None,
                 position: int | None = None) -> PlaylistItemDTO:
        """Añadir un item a una playlist."""
        session = get_session()
        try:
            p = session.get(Playlist, playlist_id)
            if not p:
                raise PlaylistNotFoundError(f"Playlist {playlist_id} no encontrada")

            # Verificar referencia circular si es playlist anidada
            if item_type == "playlist" and referenced_playlist_id:
                self._check_circular(playlist_id, referenced_playlist_id, session)

            # Determinar posicion
            if position is None:
                max_pos = session.query(PlaylistItem).filter_by(
                    playlist_id=playlist_id
                ).count()
                position = max_pos
            else:
                # Reordenar items existentes
                existing = (
                    session.query(PlaylistItem)
                    .filter_by(playlist_id=playlist_id)
                    .filter(PlaylistItem.position >= position)
                    .order_by(PlaylistItem.position.desc())
                    .all()
                )
                for item in existing:
                    item.position += 1

            new_item = PlaylistItem(
                playlist_id=playlist_id,
                position=position,
                item_type=item_type,
                filepath=filepath,
                folder_path=folder_path,
                referenced_playlist_id=referenced_playlist_id,
            )
            session.add(new_item)
            session.flush()

            label = self._item_label(new_item, session)

            session.commit()
            session.refresh(new_item)

            return PlaylistItemDTO(
                id=new_item.id,
                position=new_item.position,
                item_type=new_item.item_type,
                label=label,
            )
        except PlaylistNotFoundError:
            raise
        except CircularReferenceError:
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def remove_item(self, item_id: int):
        """Eliminar un item de una playlist y reordenar posiciones."""
        session = get_session()
        try:
            item = session.get(PlaylistItem, item_id)
            if not item:
                raise PlaylistError(f"Item {item_id} no encontrado")

            playlist_id = item.playlist_id
            position = item.position

            session.delete(item)

            # Reordenar: bajar en 1 todos los items con posicion mayor
            remaining = (
                session.query(PlaylistItem)
                .filter_by(playlist_id=playlist_id)
                .filter(PlaylistItem.position > position)
                .order_by(PlaylistItem.position)
                .all()
            )
            for ri in remaining:
                ri.position -= 1

            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def reorder_item(self, item_id: int, new_position: int):
        """Mover un item a una nueva posicion dentro de su playlist."""
        session = get_session()
        try:
            item = session.get(PlaylistItem, item_id)
            if not item:
                raise PlaylistError(f"Item {item_id} no encontrado")

            playlist_id = item.playlist_id
            old_position = item.position

            if old_position == new_position:
                return

            # Obtener todos los items ordenados
            all_items = (
                session.query(PlaylistItem)
                .filter_by(playlist_id=playlist_id)
                .order_by(PlaylistItem.position)
                .all()
            )

            # Eliminar item de su posicion actual
            all_items = [i for i in all_items if i.id != item_id]

            # Insertar en nueva posicion
            new_pos = max(0, min(new_position, len(all_items)))
            all_items.insert(new_pos, item)

            # Reasignar posiciones
            for idx, i in enumerate(all_items):
                i.position = idx

            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def clear_items(self, playlist_id: int):
        """Eliminar todos los items de una playlist."""
        session = get_session()
        try:
            session.query(PlaylistItem).filter_by(playlist_id=playlist_id).delete()
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ── Metodos privados ──

    def _item_label(self, item: PlaylistItem, session: Session) -> str:
        """Generar una etiqueta legible para un item."""
        if item.item_type == "track":
            return Path(item.filepath or "").name if item.filepath else "Pista sin archivo"
        elif item.item_type == "folder":
            return Path(item.folder_path or "").name if item.folder_path else "Carpeta sin ruta"
        elif item.item_type == "playlist":
            if item.referenced_playlist_id:
                ref = session.get(Playlist, item.referenced_playlist_id)
                return f"Playlist: {ref.name if ref else '?'}"
            return "Playlist sin referencia"
        elif item.item_type == "time_announce":
            return "Insertar hora"
        return item.item_type

    def _check_circular(self, parent_id: int, child_id: int, session: Session):
        """Verificar que no haya referencia circular al anidar playlists.
        Recorre el grafo desde child_id hacia abajo. Si alguna rama llega a parent_id,
        hay referencia circular.
        """
        visited: set[int] = set()
        to_visit = [child_id]

        while to_visit:
            current = to_visit.pop()
            if current == parent_id:
                raise CircularReferenceError(
                    "Referencia circular detectada: una playlist no puede "
                    "contenerse a si misma directa ni indirectamente"
                )
            if current in visited:
                continue
            visited.add(current)

            # Buscar items de tipo playlist dentro de la actual
            sub_items = (
                session.query(PlaylistItem)
                .filter_by(playlist_id=current, item_type="playlist")
                .all()
            )
            for item in sub_items:
                if item.referenced_playlist_id is not None:
                    to_visit.append(item.referenced_playlist_id)


# ── Instancia global ──
_service: PlaylistService | None = None


def get_playlist_service() -> PlaylistService:
    global _service
    if _service is None:
        _service = PlaylistService()
    return _service
