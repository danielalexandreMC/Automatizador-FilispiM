"""
ConfigManager - Gestion de configuracion persistente.
Lee y escribe preferencias en la tabla system_config.
"""

from pathlib import Path
from radio_automator.core.database import get_session, SystemConfig


class ConfigManager:
    """
    Gestor de configuracion clave-valor.
    Valores por defecto si no existen en la base de datos.
    """

    DEFAULTS = {
        # Audio
        "crossfade_duration": "3.0",
        "crossfade_curve": "linear",       # linear | logarithmic | sigmoid
        "silence_detection": "true",
        "normalization": "false",
        "audio_output_device": "auto",

        # Emisora
        "station_name": "Mi Emisora",
        "music_folder": str(Path.home() / "Music"),

        # Interfaz
        "theme": "dark",
        "language": "es",

        # Podcasts
        "podcast_check_interval_hours": "24",
        "podcast_max_concurrent_downloads": "3",
    }

    def __init__(self):
        self._cache: dict[str, str] = {}

    def get(self, key: str, default: str | None = None) -> str:
        """Obtener un valor de configuracion."""
        if key in self._cache:
            return self._cache[key]

        session = get_session()
        try:
            config = session.get(SystemConfig, key)
            if config:
                value = config.value
            else:
                value = default if default is not None else self.DEFAULTS.get(key, "")
            self._cache[key] = value
            return value
        finally:
            session.close()

    def get_int(self, key: str, default: int = 0) -> int:
        """Obtener un valor entero."""
        try:
            return int(self.get(key, str(default)))
        except (ValueError, TypeError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        """Obtener un valor flotante."""
        try:
            return float(self.get(key, str(default)))
        except (ValueError, TypeError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Obtener un valor booleano."""
        return self.get(key, str(default)).lower() in ("true", "1", "yes", "si")

    def set(self, key: str, value: str):
        """Guardar un valor de configuracion."""
        self._cache[key] = value
        session = get_session()
        try:
            config = session.get(SystemConfig, key)
            if config:
                config.value = value
            else:
                config = SystemConfig(key=key, value=value)
                session.add(config)
            session.commit()
        finally:
            session.close()

    def set_int(self, key: str, value: int):
        self.set(key, str(value))

    def set_float(self, key: str, value: float):
        self.set(key, str(value))

    def set_bool(self, key: str, value: bool):
        self.set(key, "true" if value else "false")

    def get_all(self) -> dict[str, str]:
        """Obtener toda la configuracion."""
        session = get_session()
        try:
            configs = session.query(SystemConfig).all()
            result = {c.key: c.value for c in configs}
            # Anadir defaults que no existan
            for key, value in self.DEFAULTS.items():
                if key not in result:
                    result[key] = value
            return result
        finally:
            session.close()

    def reload(self):
        """Recargar la configuracion desde la base de datos."""
        self._cache.clear()


# ── Instancia global ──
_config: ConfigManager | None = None


def get_config() -> ConfigManager:
    global _config
    if _config is None:
        _config = ConfigManager()
    return _config
