"""
Sistema de Logging para Radio Automator.
Logging estructurado con rotacion de archivos, multiples handlers y
integracion con EventBus para registrar automaticamente eventos del sistema.

Log a archivo: ~/.config/radio-automator/logs/radio-automator.log
Rotacion: 5 MB por archivo, maximo 3 archivos retenidos.
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from radio_automator.core.database import _get_data_dir


# ── Constantes ──
APP_NAME = "Radio Automator"
APP_VERSION = "0.6.0"

def _get_log_dir() -> Path:
    """Obtener directorio de logs (respecta RADIO_AUTOMATOR_DIR)."""
    return _get_data_dir() / "logs"

LOG_DIR = _get_log_dir()
LOG_FILE = LOG_DIR / "radio-automator.log"

# Tamano maximo de archivo: 5 MB
MAX_LOG_BYTES = 5 * 1024 * 1024
# Numero de archivos de backup retenidos
BACKUP_COUNT = 3

# Formato de log para archivo
FILE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Formato de log para consola (mas compacto)
CONSOLE_FORMAT = "%(levelname)s: %(message)s"


class ColoredFormatter(logging.Formatter):
    """Formatter que anade colores ANSI para la salida por consola."""

    COLORS = {
        "DEBUG": "\033[36m",      # Cyan
        "INFO": "\033[32m",       # Verde
        "WARNING": "\033[33m",    # Amarillo
        "ERROR": "\033[31m",      # Rojo
        "CRITICAL": "\033[1;31m", # Rojo brillante
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Formatear el record con colores ANSI."""
        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


class EventBusLogHandler(logging.Handler):
    """
    Handler que publica eventos de log en el EventBus.
    Permite que los modulos suscritos reciban notificaciones de log
    sin acoplamiento directo al sistema de logging.
    """

    def __init__(self, event_bus_publish: Callable[[str, dict[str, Any]], None]):
        super().__init__()
        self._publish = event_bus_publish
        # Solo reenviar WARNING, ERROR y CRITICAL
        self.setLevel(logging.WARNING)

    def emit(self, record: logging.LogRecord):
        """Publicar el record como evento en el EventBus."""
        try:
            self._publish("log.message", {
                "level": record.levelname,
                "logger": record.name,
                "message": self.format(record),
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            })
        except Exception:
            # Nunca fallar el logging por un error en el handler
            self.handleError(record)


class LogEntry:
    """Representa una entrada de log para el visor."""

    __slots__ = ('timestamp', 'level', 'logger_name', 'message')

    def __init__(self, timestamp: str, level: str, logger_name: str, message: str):
        self.timestamp = timestamp
        self.level = level
        self.logger_name = logger_name
        self.message = message

    def __repr__(self) -> str:
        return f"LogEntry({self.level}: {self.message[:50]})"

    def to_dict(self) -> dict[str, str]:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "logger": self.logger_name,
            "message": self.message,
        }


class LogManager:
    """
    Gestor centralizado de logging de la aplicacion.

    Proporciona:
    - Logger raiz configurado con handlers (archivo + consola)
    - Rotacion automatica de archivos
    - EventBus handler para notificaciones de errores
    - Acceso al historial reciente de logs para el visor
    - Nivel de log configurable en tiempo de ejecucion
    """

    def __init__(self):
        self._root_logger: logging.Logger | None = None
        self._file_handler: logging.handlers.RotatingFileHandler | None = None
        self._console_handler: logging.StreamHandler | None = None
        self._event_bus_handler: EventBusLogHandler | None = None
        self._recent_entries: list[LogEntry] = []
        self._max_recent = 500
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        """True si el logging ha sido inicializado."""
        return self._initialized

    @property
    def log_file_path(self) -> Path:
        """Ruta al archivo de log actual."""
        return LOG_FILE

    def initialize(
        self,
        console_level: int = logging.INFO,
        file_level: int = logging.DEBUG,
        event_bus_publish: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        """
        Inicializar el sistema de logging.

        Args:
            console_level: Nivel minimo para la salida por consola (default INFO).
            file_level: Nivel minimo para el archivo de log (default DEBUG).
            event_bus_publish: Funcion publish del EventBus para notificaciones.
        """
        if self._initialized:
            return

        # Crear directorio de logs si no existe
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        # Logger raiz
        self._root_logger = logging.getLogger("radio_automator")
        self._root_logger.setLevel(logging.DEBUG)
        self._root_logger.handlers.clear()

        # ── Handler de archivo con rotacion ──
        self._file_handler = logging.handlers.RotatingFileHandler(
            filename=str(LOG_FILE),
            maxBytes=MAX_LOG_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
            delay=False,
        )
        self._file_handler.setLevel(file_level)
        self._file_handler.setFormatter(
            logging.Formatter(FILE_FORMAT, datefmt=DATE_FORMAT)
        )
        self._root_logger.addHandler(self._file_handler)

        # ── Handler de consola con colores ──
        self._console_handler = logging.StreamHandler(sys.stdout)
        self._console_handler.setLevel(console_level)
        console_fmt = ColoredFormatter(CONSOLE_FORMAT)
        self._console_handler.setFormatter(console_fmt)
        self._root_logger.addHandler(self._console_handler)

        # ── Handler de EventBus (errores y warnings) ──
        if event_bus_publish is not None:
            self._event_bus_handler = EventBusLogHandler(event_bus_publish)
            self._root_logger.addHandler(self._event_bus_handler)

        self._initialized = True
        self._root_logger.info(
            f"Radio Automator v{APP_VERSION} - Logging inicializado "
            f"(archivo: {LOG_FILE})"
        )

    def get_logger(self, name: str) -> logging.Logger:
        """
        Obtener un logger para un modulo especifico.

        Args:
            name: Nombre del modulo (ej: 'audio_engine', 'parrilla_service').

        Returns:
            Logger configurado del modulo.
        """
        if not self._initialized:
            self.initialize()

        full_name = f"radio_automator.{name}" if not name.startswith("radio_automator") else name
        return logging.getLogger(full_name)

    def set_level(self, level: int) -> None:
        """
        Cambiar el nivel de log de todos los handlers en tiempo de ejecucion.

        Args:
            level: Nuevo nivel de log (logging.DEBUG, logging.INFO, etc.)
        """
        if not self._initialized:
            return

        if self._console_handler:
            self._console_handler.setLevel(level)

        if self._file_handler:
            # El archivo siempre es DEBUG para diagnostico
            self._file_handler.setLevel(logging.DEBUG)

    def set_console_level(self, level: int) -> None:
        """Cambiar solo el nivel de la consola."""
        if self._console_handler:
            self._console_handler.setLevel(level)

    def get_recent_entries(self, count: int = 50, min_level: str = "DEBUG") -> list[LogEntry]:
        """
        Obtener las ultimas entradas de log desde el archivo.

        Args:
            count: Numero maximo de entradas a devolver.
            min_level: Nivel minimo para filtrar (DEBUG, INFO, WARNING, ERROR).

        Returns:
            Lista de LogEntry ordenadas cronologicamente.
        """
        if not LOG_FILE.exists():
            return []

        level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
        min_level_num = level_order.get(min_level.upper(), 0)

        entries = []
        try:
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                # Leer ultimas lineas (invertido para eficiencia)
                lines = f.readlines()

            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue

                entry = self._parse_log_line(line)
                if entry and level_order.get(entry.level, 0) >= min_level_num:
                    entries.append(entry)
                    if len(entries) >= count:
                        break

            # Devolver en orden cronologico
            entries.reverse()

        except Exception:
            pass

        return entries

    def _parse_log_line(self, line: str) -> LogEntry | None:
        """
        Parsear una linea de log en formato FILE_FORMAT.

        Formato esperado: "2025-01-15 10:30:45 | INFO     | audio_engine | Mensaje"
        """
        try:
            # Intentar parsear el formato estandar
            parts = line.split(" | ", 3)
            if len(parts) >= 4:
                timestamp = parts[0].strip()
                level = parts[1].strip()
                logger_name = parts[2].strip()
                message = parts[3].strip()
                return LogEntry(timestamp, level, logger_name, message)
        except Exception:
            pass
        return None

    def clear_recent_cache(self) -> None:
        """Limpiar la cache de entradas recientes."""
        self._recent_entries.clear()

    def get_log_size(self) -> int:
        """Obtener el tamano del archivo de log en bytes."""
        if LOG_FILE.exists():
            return LOG_FILE.stat().st_size
        return 0

    def clear_log_file(self) -> bool:
        """
        Limpiar el archivo de log (truncar).

        Returns:
            True si se limpio correctamente.
        """
        try:
            if LOG_FILE.exists():
                LOG_FILE.write_text("", encoding="utf-8")
                if self._root_logger:
                    self._root_logger.info("Archivo de log limpiado")
                return True
        except Exception:
            pass
        return False

    def shutdown(self) -> None:
        """Cerrar todos los handlers de logging de forma ordenada."""
        if self._root_logger:
            self._root_logger.info("Radio Automator - Cerrando sistema de logging")
            for handler in self._root_logger.handlers[:]:
                try:
                    handler.close()
                except Exception:
                    pass
                self._root_logger.removeHandler(handler)
        self._initialized = False


# ── Instancia global del gestor de logging ──
_log_manager: LogManager | None = None


def get_log_manager() -> LogManager:
    """Obtener la instancia singleton del LogManager."""
    global _log_manager
    if _log_manager is None:
        _log_manager = LogManager()
    return _log_manager


def reset_log_manager():
    """Reiniciar el gestor de logging (util para pruebas)."""
    global _log_manager
    if _log_manager and _log_manager.is_initialized:
        _log_manager.shutdown()
    _log_manager = None


def get_logger(name: str) -> logging.Logger:
    """
    Atajo para obtener un logger con nombre completo.

    Usage:
        from radio_automator.core.logger import get_logger
        logger = get_logger("audio_engine")
        logger.info("Pista iniciada: %s", title)
    """
    return get_log_manager().get_logger(name)
