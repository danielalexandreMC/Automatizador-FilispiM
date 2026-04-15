"""
Servicio de escaneo de carpetas de audio.
Soporta anti-repeticion persistente en SQLite.
"""

from __future__ import annotations

import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from radio_automator.core.database import get_session, Session, FolderTrack


# Extensiones de audio soportadas
AUDIO_EXTENSIONS = {
    '.mp3', '.wav', '.ogg', '.flac', '.opus', '.aac', '.m4a',
    '.wma', '.mp2', '.mp1', '.aiff', '.ape', '.wv',
}


class FolderScanner:
    """Escanea carpetas de audio y gestiona anti-repeticion."""

    @staticmethod
    def scan(folder_path: str) -> list[str]:
        """
        Escanear una carpeta recursivamente y devolver la lista de archivos
        de audio encontrados.
        """
        folder = Path(folder_path)
        if not folder.is_dir():
            raise FileNotFoundError(f"Carpeta no encontrada: {folder_path}")

        audio_files = []
        for root, _dirs, files in os.walk(folder):
            for f in sorted(files):
                ext = Path(f).suffix.lower()
                if ext in AUDIO_EXTENSIONS:
                    audio_files.append(str(Path(root) / f))

        return audio_files

    @staticmethod
    def register_folder(folder_path: str, session: Session | None = None) -> int:
        """
        Registrar (o actualizar) todos los archivos de una carpeta en la tabla
        FolderTrack. Devuelve el numero de archivos registrados.
        """
        close = False
        if session is None:
            session = get_session()
            close = True
        try:
            files = FolderScanner.scan(folder_path)
            if not files:
                return 0

            folder = Path(folder_path).resolve()
            count = 0

            for filepath in files:
                path = Path(filepath).resolve()
                filename = path.name
                filepath_str = str(path)

                # Buscar si ya existe
                existing = session.query(FolderTrack).filter_by(
                    folder_path=str(folder), filename=filename
                ).first()

                if existing:
                    # Actualizar filepath por si cambio (rename)
                    if existing.filepath != filepath_str:
                        existing.filepath = filepath_str
                else:
                    track = FolderTrack(
                        folder_path=str(folder),
                        filename=filename,
                        filepath=filepath_str,
                        played=False,
                    )
                    session.add(track)
                    count += 1

            session.commit()
            return count
        except Exception:
            session.rollback()
            raise
        finally:
            if close:
                session.close()

    @staticmethod
    def get_next_random(folder_path: str, session: Session | None = None) -> str | None:
        """
        Seleccionar aleatoriamente un archivo NO reproducido de la carpeta.
        Si todos estan reproducidos, resetear y volver a elegir.
        """
        close = False
        if session is None:
            session = get_session()
            close = True
        try:
            folder = str(Path(folder_path).resolve())

            # Buscar archivos no reproducidos
            available = session.query(FolderTrack).filter_by(
                folder_path=folder, played=False
            ).all()

            if not available:
                # Resetear todos los archivos de esta carpeta
                session.query(FolderTrack).filter_by(folder_path=folder).update(
                    {"played": False}
                )
                session.commit()

                available = session.query(FolderTrack).filter_by(
                    folder_path=folder, played=False
                ).all()

                if not available:
                    return None

            # Elegir aleatoriamente
            chosen = random.choice(available)
            chosen.played = True
            chosen.last_played_at = datetime.now(timezone.utc)
            session.commit()

            return chosen.filepath
        except Exception:
            session.rollback()
            raise
        finally:
            if close:
                session.close()

    @staticmethod
    def get_unplayed_count(folder_path: str) -> int:
        """Obtener el numero de archivos no reproducidos en una carpeta."""
        folder = str(Path(folder_path).resolve())
        session = get_session()
        try:
            return session.query(FolderTrack).filter_by(
                folder_path=folder, played=False
            ).count()
        finally:
            session.close()

    @staticmethod
    def get_total_count(folder_path: str) -> int:
        """Obtener el numero total de archivos registrados en una carpeta."""
        folder = str(Path(folder_path).resolve())
        session = get_session()
        try:
            return session.query(FolderTrack).filter_by(
                folder_path=folder
            ).count()
        finally:
            session.close()

    @staticmethod
    def reset_folder(folder_path: str):
        """Resetear el estado de reproduccion de todos los archivos de una carpeta."""
        folder = str(Path(folder_path).resolve())
        session = get_session()
        try:
            session.query(FolderTrack).filter_by(folder_path=folder).update(
                {"played": False, "last_played_at": None}
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def unregister_missing(folder_path: str) -> int:
        """
        Eliminar de la DB los registros de archivos que ya no existen en disco.
        Devuelve el numero de registros eliminados.
        """
        folder = str(Path(folder_path).resolve())
        session = get_session()
        try:
            tracks = session.query(FolderTrack).filter_by(folder_path=folder).all()
            removed = 0
            for track in tracks:
                if not Path(track.filepath).exists():
                    session.delete(track)
                    removed += 1
            session.commit()
            return removed
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
