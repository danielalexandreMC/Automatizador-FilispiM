"""
Servizo de Insercions Horarias (Time Announcements).
Reproduce audios coa hora actual de forma automatica,
intrompindo a reproducion normal (como Zara Radio, Radit, etc.).

Audiros esperados na carpeta configurada:
  - HRS00.mp3 a HRS23.mp3: Horas para combinar con minutos
  - MIN01.mp3 a MIN59.mp3: Minutos para combinar con horas
  - HRS00_O.mp3 a HRS23_O.mp3: Horas en punto (para quando os minutos son 00)

Exemplo: Son as 13:12 -> reproducese HRS13.mp3 + MIN12.mp3
         Son as 09:00 -> reproducese HRS09_O.mp3
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Callable

from radio_automator.core.config import get_config
from radio_automator.core.event_bus import get_event_bus
from radio_automator.core.logger import get_logger

logger = get_logger("time_announce")


class TimeAnnounceService:
    """Xestiona as insercions horarias automaticas."""

    # Intervalos dispoñibles (minutos)
    INTERVALS = [15, 30, 60]

    def __init__(self):
        self._enabled: bool = False
        self._folder: str = ""
        self._interval: int = 60  # minutos
        self._last_announced_slot: str | None = None
        # Cola de audios pendentes para a insercion actual
        self._pending_files: list[str] = []
        self._is_announcing: bool = False
        # Timestamp de cando se iniciou a insercion (para safety reset)
        self._announce_start_time: datetime | None = None
        # Callback para reproducir o seguinte ficheiro da cola
        self._on_play_file: Callable[[str], None] | None = None
        self._on_announce_finished: Callable[[], None] | None = None

    def load_config(self):
        """Cargar configuracion desde o ConfigManager."""
        cfg = get_config()
        self._enabled = cfg.get_bool("time_announce_enabled", False)
        self._folder = cfg.get("time_announce_folder", "")
        try:
            self._interval = cfg.get_int("time_announce_interval", 60)
        except Exception:
            self._interval = 60

        # Validar intervalo
        if self._interval not in self.INTERVALS:
            self._interval = 60

        if self._enabled:
            logger.info(
                f"Insercions horarias activadas (cada {self._interval}min, "
                f"carpeta: {self._folder or 'non configurada'})"
            )
        else:
            logger.info("Insercions horarias desactivadas")

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def is_announcing(self) -> bool:
        """True se estamos a reproducir unha insercion horaria agora."""
        return self._is_announcing

    @property
    def pending_count(self) -> int:
        return len(self._pending_files)

    def set_callbacks(self, on_play_file: Callable[[str], None] | None = None,
                      on_announce_finished: Callable[[], None] | None = None):
        """Establecer callbacks para reproducir audios."""
        self._on_play_file = on_play_file
        self._on_announce_finished = on_announce_finished

    def check_and_announce(self, now: datetime | None = None) -> list[str] | None:
        """Comprobar se toca facer unha insercion horaria.

        Returns:
            Lista de ficheiros a reproducir, ou None se non toca.
            Devolve lista baleira se non se atopan os audios.
        """
        if not self._enabled:
            return None

        if not self._folder:
            return None

        if self._is_announcing:
            return None  # Xa estamos a reproducir unha insercion

        if now is None:
            now = datetime.now()

        # Calcular o slot actual (hora redondeada ao intervalo)
        total_minutes = now.hour * 60 + now.minute
        slot = total_minutes - (total_minutes % self._interval)

        # Comprobar se xa anunciamos este slot
        slot_key = f"{now.year}-{now.month:02d}-{now.day:02d}-{slot:04d}"
        if self._last_announced_slot == slot_key:
            return None  # Xa anunciamos este slot

        # Comprobar se estamos no momento exacto do slot
        # (dar unha marxe de 30 segundos para asegurar que o tick
        # de 5 segundos sempre alcanza a detectar o slot, incluso
        # se o sistema esta baixo carga)
        slot_seconds = slot * 60
        now_seconds = total_minutes * 60 + now.second
        diff = abs(now_seconds - slot_seconds)
        if diff > 30:
            # So imprimir se estamos relativamente cerca (para depurar)
            if diff < 60:
                print(f"[TA] Preparando: slot={slot:04d} ({slot//60:02d}:{slot%60:02d}), "
                      f"agora={now.strftime('%H:%M:%S')}, diff={diff}s, ventana=30s")
            return None  # Non estamos no momento exacto

        # Construir a lista de audios
        files = self._build_announcement_files(now.hour, now.minute)
        if not files:
            logger.warning("Non se atoparon os audios de insercion horaria")
            print(f"[TA] ERRO: Non se atoparon audios para {now.hour:02d}:{now.minute:02d} "
                  f"na carpeta: {self._folder}")
            return None

        # Marcar como anunciado
        self._last_announced_slot = slot_key
        self._pending_files = list(files)
        self._is_announcing = True
        self._announce_start_time = datetime.now()

        time_str = f"{now.hour:02d}:{now.minute:02d}"
        logger.info(f"Insercion horaria: {time_str} -> {files}")
        get_event_bus().publish("time_announce.started", {
            "time": time_str,
            "files": files,
        })

        return files

    def _build_announcement_files(self, hour: int, minute: int) -> list[str]:
        """Construir a lista de ficheiros para a hora actual.

        Se minute == 0: HRS{HH}_O.mp3 (hora en punto)
        Se minute > 0: HRS{HH}.mp3 + MIN{MM}.mp3 (hora + minutos)
        """
        folder = self._folder
        if not os.path.isdir(folder):
            logger.warning(f"Carpeta de insercions non existe: {folder}")
            return []

        files = []
        hh = f"{hour:02d}"
        mm = f"{minute:02d}"

        if minute == 0:
            # Hora en punto: so un ficheiro
            fpath = os.path.join(folder, f"HRS{hh}_O.mp3")
            if os.path.isfile(fpath):
                files.append(fpath)
            else:
                logger.warning(f"Audio non atopado: {fpath}")
        else:
            # Hora + minutos: dous ficheiros
            fpath_h = os.path.join(folder, f"HRS{hh}.mp3")
            fpath_m = os.path.join(folder, f"MIN{mm}.mp3")

            if os.path.isfile(fpath_h):
                files.append(fpath_h)
            else:
                logger.warning(f"Audio non atopado: {fpath_h}")

            if os.path.isfile(fpath_m):
                files.append(fpath_m)
            else:
                logger.warning(f"Audio non atopado: {fpath_m}")

        return files

    def get_next_pending_file(self) -> str | None:
        """Obter o seguinte ficheiro pendente da cola de insercion.

        Returns:
            Ruta do seguinte ficheiro, ou None se a cola esta baleira.
        """
        if not self._pending_files:
            return None
        return self._pending_files.pop(0)

    def finish_announcement(self):
        """Marcar que a insercion horaria rematou."""
        self._pending_files = []
        self._is_announcing = False
        self._announce_start_time = None
        logger.info("Insercion horaria rematada")
        get_event_bus().publish("time_announce.finished", {})

    def reset(self):
        """Reiniciar o estado (para tests ou cambio de config)."""
        self._last_announced_slot = None
        self._pending_files = []
        self._is_announcing = False
        self._announce_start_time = None
        self.load_config()

    def get_available_files(self) -> dict[str, list[str]]:
        """Verificar que audios estan dispoñibles na carpeta.

        Returns:
            Dict con categorias:
            - 'hours': lista de HRS00-HRS23 atopados
            - 'minutes': lista de MIN01-MIN59 atopados
            - 'on_the_hour': lista de HRS00_O-HRS23_O atopados
            - 'missing': lista de ficheiros esperados pero non atopados
        """
        result = {
            "hours": [],
            "minutes": [],
            "on_the_hour": [],
            "missing": [],
        }

        if not self._folder or not os.path.isdir(self._folder):
            result["missing"] = [f"HRS00.mp3..HRS23.mp3", "MIN01.mp3..MIN59.mp3", "HRS00_O.mp3..HRS23_O.mp3"]
            return result

        # Verificar horas
        for h in range(24):
            hh = f"{h:02d}"
            fpath = os.path.join(self._folder, f"HRS{hh}.mp3")
            if os.path.isfile(fpath):
                result["hours"].append(f"HRS{hh}.mp3")
            else:
                result["missing"].append(f"HRS{hh}.mp3")

        # Verificar minutos
        for m in range(1, 60):
            mm = f"{m:02d}"
            fpath = os.path.join(self._folder, f"MIN{mm}.mp3")
            if os.path.isfile(fpath):
                result["minutes"].append(f"MIN{mm}.mp3")
            else:
                result["missing"].append(f"MIN{mm}.mp3")

        # Verificar horas en punto
        for h in range(24):
            hh = f"{h:02d}"
            fpath = os.path.join(self._folder, f"HRS{hh}_O.mp3")
            if os.path.isfile(fpath):
                result["on_the_hour"].append(f"HRS{hh}_O.mp3")
            else:
                result["missing"].append(f"HRS{hh}_O.mp3")

        return result


# ── Instancia global ──
_service: TimeAnnounceService | None = None


def get_time_announce_service() -> TimeAnnounceService:
    """Obter a instancia singleton do TimeAnnounceService."""
    global _service
    if _service is None:
        _service = TimeAnnounceService()
    return _service


def reset_time_announce_service():
    """Reiniciar o servizo (para tests)."""
    global _service
    if _service:
        _service.reset()
    _service = None
