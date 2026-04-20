"""
Base de datos y modelos ORM del sistema.
Utiliza SQLAlchemy 2.0 con SQLite.
Soporta re-inicializacion para tests.
"""

import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship,
    sessionmaker, Session, scoped_session
)
from sqlalchemy import ForeignKey, Text, DateTime, Boolean, Float
from datetime import datetime, timezone


class Base(DeclarativeBase):
    pass


def _get_data_dir() -> Path:
    """Obtener el directorio de datos actual (respetando env var)."""
    return Path(os.environ.get(
        "RADIO_AUTOMATOR_DIR",
        Path.home() / ".config" / "radio-automator"
    ))


# ── Motor y sesion (lazy singleton) ──
_engine = None
_session_factory = None


def _init_engine():
    """Inicializar o re-inicializar el motor de base de datos."""
    global _engine, _session_factory
    data_dir = _get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "radio_automator.db"
    database_url = f"sqlite:///{db_path}"

    _engine = create_engine(database_url, echo=False)

    @event.listens_for(_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        """Activar foreign keys y WAL mode en SQLite."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)


def get_engine():
    """Obtener el motor de base de datos (lazy init)."""
    global _engine
    if _engine is None:
        _init_engine()
    return _engine


def get_session() -> Session:
    """Obtener una sesion de base de datos."""
    if _session_factory is None:
        _init_engine()
    return _session_factory()


def reset_engine():
    """Resetear el motor (para tests)."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None


# Propiedades de conveniencia para compatibilidad con el resto del codigo
def DATA_DIR() -> Path:
    return _get_data_dir()


def DB_PATH() -> Path:
    return _get_data_dir() / "radio_automator.db"


# ═══════════════════════════════════════
# MODELOS
# ═══════════════════════════════════════

class User(Base):
    """Operador del sistema (maximo 3)."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(nullable=False)
    display_name: Mapped[str] = mapped_column(nullable=False)
    role: Mapped[str] = mapped_column(default="operator")  # admin, operator, readonly
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class Playlist(Base):
    """Playlist del sistema."""
    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)
    mode: Mapped[str] = mapped_column(default="loop")  # loop | single
    is_system: Mapped[bool] = mapped_column(default=False)  # True solo para "Continuidad"
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relaciones
    items: Mapped[list["PlaylistItem"]] = relationship(
        back_populates="playlist", order_by="PlaylistItem.position",
        foreign_keys="[PlaylistItem.playlist_id]",
        cascade="all, delete-orphan"
    )

    @property
    def is_continuity(self) -> bool:
        return self.is_system and self.name == "Continuidad"


class PlaylistItem(Base):
    """Elemento dentro de una playlist."""
    __tablename__ = "playlist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    playlist_id: Mapped[int] = mapped_column(ForeignKey("playlists.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(default=0)
    item_type: Mapped[str] = mapped_column(nullable=False)
    # item_type: "track", "folder", "playlist", "time_announce"

    # Datos segun tipo:
    # track -> filepath
    # folder -> folder_path
    # playlist -> referenced_playlist_id
    # time_announce -> (sin datos extra)
    filepath: Mapped[str | None] = mapped_column(Text, nullable=True)
    folder_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    referenced_playlist_id: Mapped[int | None] = mapped_column(
        ForeignKey("playlists.id", ondelete="SET NULL"), nullable=True
    )

    playlist: Mapped["Playlist"] = relationship(
        back_populates="items", foreign_keys=[playlist_id]
    )
    referenced_playlist: Mapped["Playlist | None"] = relationship(
        foreign_keys=[referenced_playlist_id], remote_side="Playlist.id"
    )


class RadioEvent(Base):
    """Evento programado en la parrilla semanal."""
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)
    playlist_id: Mapped[int | None] = mapped_column(
        ForeignKey("playlists.id", ondelete="SET NULL"), nullable=True
    )
    # Hora de inicio (HH:MM) - siempre obligatoria
    start_time: Mapped[str] = mapped_column(nullable=False)  # "HH:MM"
    # Hora de fin (HH:MM) - opcional para eventos normales, obligatoria para streaming
    end_time: Mapped[str | None] = mapped_column(nullable=True)  # "HH:MM"

    # Dias de la semana (lun-dom), lista de 7 bools: "0,0,1,0,0,1,0"
    week_days: Mapped[str] = mapped_column(default="1,1,1,1,1,1,1")

    # Patron de repeticion: once, daily, weekly, selected_days, every_n_days, date_range
    repeat_pattern: Mapped[str] = mapped_column(default="weekly")
    repeat_interval: Mapped[int | None] = mapped_column(nullable=True)  # cada N dias

    # Rango de fechas para repeat_pattern = date_range
    repeat_start_date: Mapped[str | None] = mapped_column(nullable=True)  # "YYYY-MM-DD"
    repeat_end_date: Mapped[str | None] = mapped_column(nullable=True)  # "YYYY-MM-DD"

    # Conexion streaming
    streaming_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Contenido local (alternativa a playlist_id)
    local_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_folder_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    playlist: Mapped["Playlist | None"] = relationship()

    @property
    def is_streaming(self) -> bool:
        """True si el evento tiene URL de streaming."""
        return bool(self.streaming_url and self.streaming_url.strip())

    @property
    def has_end_time(self) -> bool:
        return bool(self.end_time and self.end_time.strip())

    @property
    def week_days_list(self) -> list[bool]:
        """Devuelve la lista de dias como [bool, bool, ...] (lun-dom)."""
        return [d == "1" for d in self.week_days.split(",")]


class FolderTrack(Base):
    """Estado de reproduccion de archivos en carpetas (anti-repeticion)."""
    __tablename__ = "folder_tracks"

    id: Mapped[int] = mapped_column(primary_key=True)
    folder_path: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    filepath: Mapped[str] = mapped_column(Text, nullable=False)
    played: Mapped[bool] = mapped_column(default=False)
    last_played_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        # Unico: misma carpeta + mismo archivo
        {"sqlite_autoincrement": True},
    )


class ContinuityState(Base):
    """Estado persistente de la playlist Continuidad."""
    __tablename__ = "continuity_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    playlist_id: Mapped[int] = mapped_column(ForeignKey("playlists.id"), unique=True)
    current_item_index: Mapped[int] = mapped_column(default=0)
    current_file_position_ms: Mapped[int] = mapped_column(default=0)  # milisegundos
    is_playing: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )


class PodcastFeed(Base):
    """Fuente RSS de podcast."""
    __tablename__ = "podcast_feeds"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    folder_path: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(default="replace")  # replace | accumulate
    max_episodes: Mapped[int | None] = mapped_column(nullable=True)  # None = sin limite
    is_active: Mapped[bool] = mapped_column(default=True)
    last_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    episodes: Mapped[list["PodcastEpisode"]] = relationship(
        back_populates="feed", cascade="all, delete-orphan"
    )


class PodcastEpisode(Base):
    """Episodio descargado de un podcast."""
    __tablename__ = "podcast_episodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    feed_id: Mapped[int] = mapped_column(ForeignKey("podcast_feeds.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    local_path: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    downloaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    file_size: Mapped[int | None] = mapped_column(nullable=True)  # bytes

    feed: Mapped["PodcastFeed"] = relationship(back_populates="episodes")


class PlayHistory(Base):
    """Registro de pistas reproducidas."""
    __tablename__ = "play_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    filepath: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(default="")
    artist: Mapped[str] = mapped_column(default="")
    duration_ms: Mapped[int] = mapped_column(default=0)  # duracion total en ms
    played_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    source: Mapped[str] = mapped_column(default="playlist")  # playlist, folder, streaming, manual
    source_id: Mapped[int | None] = mapped_column(nullable=True)  # playlist_id, event_id, etc.


class SystemConfig(Base):
    """Configuracion general del sistema (clave-valor)."""
    __tablename__ = "system_config"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )


# ═══════════════════════════════════════
# INICIALIZACION
# ═══════════════════════════════════════

def init_db():
    """Crear todas las tablas y datos iniciales."""
    Base.metadata.create_all(get_engine())
    _seed_continuity()
    _seed_default_config()


def _seed_continuity():
    """Crear la playlist Continuidad si no existe."""
    session = get_session()
    try:
        existing = session.query(Playlist).filter_by(is_system=True, name="Continuidad").first()
        if not existing:
            cont = Playlist(
                name="Continuidad",
                mode="loop",
                is_system=True,
                sort_order=0
            )
            session.add(cont)
            session.flush()

            # Crear estado de Continuidad
            state = ContinuityState(playlist_id=cont.id)
            session.add(state)

            session.commit()
    finally:
        session.close()


def _seed_default_config():
    """Insertar configuracion por defecto si no existe."""
    defaults = {
        "crossfade_duration": "3.0",
        "crossfade_curve": "linear",
        "silence_detection": "true",
        "normalization": "false",
        "audio_output_device": "auto",
        "station_name": "Mi Emisora",
        "music_folder": str(Path.home() / "Music"),
        "theme": "dark",
    }
    session = get_session()
    try:
        for key, value in defaults.items():
            existing = session.get(SystemConfig, key)
            if not existing:
                session.add(SystemConfig(key=key, value=value))
        session.commit()
    finally:
        session.close()
