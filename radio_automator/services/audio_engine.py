"""
Motor de audio basado en GStreamer.
Play, pause, stop, seek, volumen, crossfade, VU meters, streaming.
Disenado para funcionar en el hilo principal de GTK con GLib.idle_add.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from radio_automator.core.config import get_config
from radio_automator.core.event_bus import get_event_bus, Event, Priority


# ═══════════════════════════════════════
# Enums y DTOs
# ═══════════════════════════════════════

class PlaybackState(Enum):
    """Estados del reproductor."""
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"
    BUFFERING = "buffering"
    ERROR = "error"


@dataclass
class TrackInfo:
    """Informacion de la pista actual."""
    filepath: str = ""
    title: str = ""
    artist: str = ""
    duration_ms: int = 0
    position_ms: int = 0
    is_streaming: bool = False

    @property
    def duration_str(self) -> str:
        return self._format_ms(self.duration_ms)

    @property
    def position_str(self) -> str:
        return self._format_ms(self.position_ms)

    @staticmethod
    def _format_ms(ms: int) -> str:
        if ms <= 0:
            return "0:00"
        total_sec = ms // 1000
        hours, remainder = divmod(total_sec, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"


@dataclass
class VUMeterData:
    """Datos del indicador de nivel."""
    level_left: float = 0.0   # 0.0 - 1.0
    level_right: float = 0.0  # 0.0 - 1.0
    peak_left: float = 0.0
    peak_right: float = 0.0
    is_clipping: bool = False


# ═══════════════════════════════════════
# Excepciones
# ═══════════════════════════════════════

class AudioEngineError(Exception):
    """Error general del motor de audio."""
    pass


class AudioNotAvailableError(AudioEngineError):
    """GStreamer no esta disponible."""
    pass


class UnsupportedFormatError(AudioEngineError):
    """Formato de audio no soportado."""
    pass


# ═══════════════════════════════════════
# AudioEngine
# ═══════════════════════════════════════

class AudioEngine:
    """
    Motor de reproduccion de audio basado en GStreamer.

    Gestiona un pipeline playbin con soporte para:
    - Archivos locales (mp3, ogg, flac, wav, m4a, opus, aac)
    - Streaming URL (http/https)
    - Control de volumen
    - Busqueda (seek)
    - Crossfade entre pistas
    - VU meter por canales
    - Deteccion de fin de pista (EOS)

    Toda la interaccion con GTK se hace via callbacks en el hilo principal.
    """

    # Extensiones de audio soportadas
    SUPPORTED_EXTENSIONS = {
        ".mp3", ".ogg", ".flac", ".wav", ".m4a", ".opus", ".aac",
        ".wma", ".mp4", ".webm", ".oga", ".spx", ".mp2"
    }

    def __init__(self):
        self._pipeline = None
        self._state = PlaybackState.STOPPED
        self._track_info = TrackInfo()
        self._volume = 1.0
        self._muted = False
        self._crossfade_duration_ms = 3000  # 3s por defecto
        self._crossfade_enabled = True

        # VU meter
        self._vu_data = VUMeterData()
        self._vu_level_id = None  # GLib timeout ID
        self._vu_update_interval_ms = 100

        # Callbacks (se ejecutan en hilo principal via GLib.idle_add)
        self._on_state_changed: Callable[[PlaybackState], None] | None = None
        self._on_position_changed: Callable[[TrackInfo], None] | None = None
        self._on_track_finished: Callable[[TrackInfo], None] | None = None
        self._on_vu_changed: Callable[[VUMeterData], None] | None = None
        self._on_error: Callable[[str], None] | None = None
        self._on_tags_changed: Callable[[TrackInfo], None] | None = None

        # Posicion polling
        self._position_poll_id = None
        self._position_poll_interval_ms = 250

        # GStreamer availability
        self._gst_available = False
        self._init_gst()

    def _init_gst(self):
        """Inicializar GStreamer. Si no esta disponible, funciona en modo mock."""
        try:
            import gi
            gi.require_version('Gst', '1.0')
            from gi.repository import Gst, GLib
            Gst.init(None)
            self._gst_available = True
            self._Gst = Gst
            self._GLib = GLib
            print("[AudioEngine] GStreamer inicializado correctamente")
        except (ImportError, ValueError) as e:
            print(f"[AudioEngine] GStreamer no disponible: {e}")
            print("[AudioEngine] Funcionando en modo simulacion (sin audio real)")
            self._gst_available = False

    @property
    def is_available(self) -> bool:
        """True si GStreamer esta disponible."""
        return self._gst_available

    @property
    def state(self) -> PlaybackState:
        return self._state

    @property
    def track_info(self) -> TrackInfo:
        return self._track_info

    @property
    def volume(self) -> float:
        return self._volume

    @property
    def muted(self) -> bool:
        return self._muted

    @property
    def vu_data(self) -> VUMeterData:
        return self._vu_data

    # ── Configuracion de callbacks ──

    def set_callbacks(self,
                     on_state_changed: Callable[[PlaybackState], None] | None = None,
                     on_position_changed: Callable[[TrackInfo], None] | None = None,
                     on_track_finished: Callable[[TrackInfo], None] | None = None,
                     on_vu_changed: Callable[[VUMeterData], None] | None = None,
                     on_error: Callable[[str], None] | None = None,
                     on_tags_changed: Callable[[TrackInfo], None] | None = None):
        """Configurar callbacks para eventos del motor. Se ejecutan en hilo principal."""
        self._on_state_changed = on_state_changed
        self._on_position_changed = on_position_changed
        self._on_track_finished = on_track_finished
        self._on_vu_changed = on_vu_changed
        self._on_error = on_error
        self._on_tags_changed = on_tags_changed

    # ── Control de reproduccion ──

    def play_file(self, filepath: str) -> bool:
        """
        Reproducir un archivo de audio local.
        Devuelve True si se inicio correctamente.
        """
        if not Path(filepath).exists():
            self._notify_error(f"Archivo no encontrado: {filepath}")
            return False

        return self._play_uri(f"file://{filepath}", is_streaming=False)

    def play_stream(self, url: str) -> bool:
        """
        Reproducir un stream de audio (URL HTTP/HTTPS).
        """
        if not url.startswith(("http://", "https://")):
            self._notify_error(f"URL de streaming invalida: {url}")
            return False

        return self._play_uri(url, is_streaming=True)

    def _play_uri(self, uri: str, is_streaming: bool = False) -> bool:
        """Iniciar reproduccion de una URI (file:// o http(s)://)."""
        if not self._gst_available:
            # Modo simulacion
            self._track_info = TrackInfo(
                filepath=uri,
                title=Path(uri.split("/")[-1]).stem if "/" in uri else "Stream",
                is_streaming=is_streaming,
            )
            self._set_state(PlaybackState.PLAYING)

            get_event_bus().publish("audio.track_started", {
                "filepath": uri,
                "is_streaming": is_streaming,
            })

            return True

        try:
            self._stop_pipeline()
            self._create_pipeline(uri)

            # Configurar volumen
            self._pipeline.set_property("volume", 0.0 if self._muted else self._volume)

            # Conectar senales
            bus = self._pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message::eos", self._on_eos)
            bus.connect("message::error", self._on_error_msg)
            bus.connect("message::state-changed", self._on_gst_state_changed)
            bus.connect("message::tag", self._on_tag_msg)
            bus.connect("message::buffering", self._on_buffering_msg)

            # Iniciar reproduccion
            result = self._pipeline.set_state(self._Gst.State.PLAYING)
            if result == self._Gst.StateChangeReturn.FAILURE:
                self._notify_error(f"No se pudo reproducir: {uri}")
                self._stop_pipeline()
                return False

            # Actualizar info de pista
            self._track_info = TrackInfo(
                filepath=uri,
                title=Path(uri.split("/")[-1]).stem if "/" in uri else "Stream",
                is_streaming=is_streaming,
            )

            self._set_state(PlaybackState.PLAYING)

            # Iniciar polling de posicion
            self._start_position_poll()
            # Iniciar VU meter
            self._start_vu_poll()

            # Publicar evento
            get_event_bus().publish("audio.track_started", {
                "filepath": uri,
                "is_streaming": is_streaming,
            })

            return True

        except Exception as e:
            self._notify_error(f"Error al reproducir: {e}")
            return False

    def pause(self):
        """Pausar la reproduccion."""
        if self._state != PlaybackState.PLAYING:
            return

        if self._gst_available and self._pipeline:
            self._pipeline.set_state(self._Gst.State.PAUSED)

        self._set_state(PlaybackState.PAUSED)
        get_event_bus().publish("audio.paused", {"filepath": self._track_info.filepath})

    def resume(self):
        """Reanudar la reproduccion."""
        if self._state != PlaybackState.PAUSED:
            return

        if self._gst_available and self._pipeline:
            self._pipeline.set_state(self._Gst.State.PLAYING)

        self._set_state(PlaybackState.PLAYING)
        get_event_bus().publish("audio.resumed", {"filepath": self._track_info.filepath})

    def toggle_play_pause(self):
        """Alternar entre play y pause."""
        if self._state == PlaybackState.PLAYING:
            self.pause()
        elif self._state == PlaybackState.PAUSED:
            self.resume()

    def stop(self):
        """Detener la reproduccion."""
        old_info = self._track_info
        self._stop_pipeline()
        self._stop_position_poll()
        self._stop_vu_poll()

        self._track_info = TrackInfo()
        self._set_state(PlaybackState.STOPPED)

        get_event_bus().publish("audio.stopped", {
            "filepath": old_info.filepath,
        })

    def set_volume(self, volume: float):
        """
        Establecer volumen (0.0 - 1.0).
        """
        self._volume = max(0.0, min(1.0, volume))

        if self._gst_available and self._pipeline:
            self._pipeline.set_property("volume", 0.0 if self._muted else self._volume)

        get_event_bus().publish("audio.volume_changed", {"volume": self._volume})

    def set_mute(self, muted: bool):
        """Silenciar o restaurar volumen."""
        self._muted = muted

        if self._gst_available and self._pipeline:
            self._pipeline.set_property("volume", 0.0 if self._muted else self._volume)

    def toggle_mute(self):
        """Alternar silencio."""
        self.set_mute(not self._muted)

    def seek(self, position_ms: int):
        """
        Buscar una posicion en la pista (en milisegundos).
        Solo funciona en archivos locales, no en streaming.
        """
        if self._track_info.is_streaming:
            return

        if not self._gst_available or not self._pipeline:
            return

        if self._state != PlaybackState.PLAYING and self._state != PlaybackState.PAUSED:
            return

        try:
            position_ns = int(position_ms * 1_000_000)  # ms -> ns
            # Usar seek con formato de flush
            self._pipeline.seek_simple(
                self._Gst.Format.TIME,
                self._Gst.SeekFlags.FLUSH | self._Gst.SeekFlags.KEY_UNIT,
                position_ns
            )
        except Exception as e:
            print(f"[AudioEngine] Error en seek: {e}")

    def seek_relative(self, delta_ms: int):
        """Buscar relativo a la posicion actual."""
        new_pos = self._track_info.position_ms + delta_ms
        new_pos = max(0, min(new_pos, self._track_info.duration_ms))
        self.seek(new_pos)

    # ── Crossfade ──

    def play_file_with_crossfade(self, filepath: str) -> bool:
        """
        Reproducir un archivo con crossfade desde la pista actual.
        Si crossfade esta deshabilitado o no hay pista actual, usa play_file normal.
        """
        if (not self._crossfade_enabled or
                self._state != PlaybackState.PLAYING or
                self._track_info.is_streaming):
            return self.play_file(filepath)

        if not self._gst_available:
            # Simulacion: simplemente cambiar pista
            self.stop()
            return self.play_file(filepath)

        fade_duration_ns = int(self._crossfade_duration_ms * 1_000_000)

        try:
            # Crear nuevo pipeline para la pista nueva
            old_pipeline = self._pipeline
            self._pipeline = None

            if not Path(filepath).exists():
                self._notify_error(f"Archivo no encontrado: {filepath}")
                return False

            self._create_pipeline(f"file://{filepath}")
            new_pipeline = self._pipeline
            new_pipeline.set_property("volume", 0.0)

            # Conectar senales al nuevo pipeline
            bus = new_pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message::eos", self._on_eos)
            bus.connect("message::error", self._on_error_msg)
            bus.connect("message::state-changed", self._on_gst_state_changed)
            bus.connect("message::tag", self._on_tag_msg)

            # Iniciar nuevo pipeline
            new_pipeline.set_state(self._Gst.State.PLAYING)

            # Fade-in del nuevo pipeline
            new_pipeline.set_property("volume", self._volume)
            self._apply_fade_in(new_pipeline, fade_duration_ns)

            # Fade-out del viejo pipeline
            if old_pipeline:
                self._apply_fade_out(old_pipeline, fade_duration_ns, stop_after=True)

            self._track_info = TrackInfo(
                filepath=filepath,
                title=Path(filepath).stem,
                is_streaming=False,
            )

            self._set_state(PlaybackState.PLAYING)
            get_event_bus().publish("audio.track_started", {
                "filepath": filepath, "crossfade": True,
            })
            return True

        except Exception as e:
            self._notify_error(f"Error en crossfade: {e}")
            return False

    def set_crossfade(self, enabled: bool, duration_ms: int | None = None):
        """Configurar crossfade."""
        self._crossfade_enabled = enabled
        if duration_ms is not None:
            self._crossfade_duration_ms = max(0, min(15000, duration_ms))

    def _apply_fade_out(self, pipeline, duration_ns: int, stop_after: bool = False):
        """Aplicar fade-out a un pipeline y detenerlo al final."""
        steps = 20
        step_ns = duration_ns // steps
        volume = self._volume

        def _step(current=0):
            if current >= steps:
                try:
                    pipeline.set_state(self._Gst.State.NULL)
                except Exception:
                    pass
                return False  # Detener timeout

            fraction = current / steps
            # Curva lineal (se puede mejorar con curva logaritmica)
            new_vol = volume * (1.0 - fraction)
            try:
                pipeline.set_property("volume", max(0.0, new_vol))
            except Exception:
                return False

            self._GLib.timeout_add(step_ns // 1_000_000, _step, current + 1)
            return False  # Detener este timeout, el proximo paso lo reprograma

        _step(0)

    def _apply_fade_in(self, pipeline, duration_ns: int):
        """Aplicar fade-in a un pipeline."""
        steps = 20
        step_ns = duration_ns // steps
        volume = self._volume

        def _step(current=0):
            if current >= steps:
                try:
                    pipeline.set_property("volume", volume)
                except Exception:
                    pass
                return False

            fraction = (current + 1) / steps
            new_vol = volume * fraction
            try:
                pipeline.set_property("volume", max(0.0, new_vol))
            except Exception:
                return False

            self._GLib.timeout_add(step_ns // 1_000_000, _step, current + 1)
            return False

        _step(0)

    # ── Pipeline GStreamer ──

    def _create_pipeline(self, uri: str):
        """Crear un pipeline playbin de GStreamer."""
        if not self._gst_available:
            return

        self._pipeline = self._Gst.ElementFactory.make("playbin", "player")
        self._pipeline.set_property("uri", uri)

        # Configurar elemento de salida de audio (volume + level para VU)
        # Usamos un bin personalizado con volume + level antes de autoaudiosink
        audio_filter = self._create_audio_filter()
        if audio_filter:
            self._pipeline.set_property("audio-filter", audio_filter)

    def _create_audio_filter(self):
        """
        Crear un filtro de audio con elementos de volumen y nivel.
        Esto permite medir los niveles para el VU meter.
        """
        if not self._gst_available:
            return None

        try:
            from gi.repository import Gst

            # Bin con volume + level
            bin = Gst.Bin.new("audio_filter")

            # Elemento level para VU meter
            level = Gst.ElementFactory.make("level", "level")
            if level:
                level.set_property("interval", self._vu_update_interval_ms * 1_000_000)
                level.set_property("post-messages", True)

            # Elemento volume
            volume = Gst.ElementFactory.make("volume", "vol")
            if volume:
                volume.set_property("volume", self._volume)

            if level and volume:
                bin.add(volume)
                bin.add(level)
                volume.link(level)

                # Ghost pads
                sink_pad = volume.get_static_pad("sink")
                ghost_sink = Gst.GhostPad.new("sink", sink_pad)
                bin.add_pad(ghost_sink)

                src_pad = level.get_static_pad("src")
                ghost_src = Gst.GhostPad.new("src", src_pad)
                bin.add_pad(ghost_src)

                return bin

        except Exception as e:
            print(f"[AudioEngine] Error creando filtro de audio: {e}")

        return None

    def _stop_pipeline(self):
        """Detener y limpiar el pipeline actual."""
        if self._gst_available and self._pipeline:
            try:
                bus = self._pipeline.get_bus()
                if bus:
                    bus.remove_signal_watch()
                self._pipeline.set_state(self._Gst.State.NULL)
            except Exception:
                pass
            self._pipeline = None

    # ── Handlers de senales GStreamer ──

    def _on_eos(self, bus, msg):
        """End of Stream: la pista ha terminado."""
        info = self._track_info
        print(f"[AudioEngine] Fin de pista: {info.title}")

        # Registrar en historial
        self._record_play_history(info)

        # Notificar via callback
        if self._on_track_finished:
            self._safe_call(self._on_track_finished, info)

        get_event_bus().publish("audio.track_finished", {
            "filepath": info.filepath,
            "title": info.title,
        })

    def _on_error_msg(self, bus, msg):
        """Error en el pipeline."""
        if not self._gst_available:
            return

        err, debug = msg.parse_error()
        error_str = f"GStreamer: {err.message}"
        print(f"[AudioEngine] Error: {error_str}")
        if debug:
            print(f"[AudioEngine] Debug: {debug}")

        self._stop_pipeline()
        self._stop_position_poll()
        self._stop_vu_poll()
        self._set_state(PlaybackState.ERROR)
        self._notify_error(error_str)

    def _on_gst_state_changed(self, bus, msg):
        """Cambio de estado del pipeline."""
        if not self._gst_available:
            return

        if msg.src != self._pipeline:
            return

        old, new, pending = msg.parse_state_changed()

        # Solo nos interesamos los cambios top-level
        if new == self._Gst.State.PLAYING and self._state != PlaybackState.PLAYING:
            self._set_state(PlaybackState.PLAYING)
        elif new == self._Gst.State.PAUSED and self._state != PlaybackState.PAUSED:
            self._set_state(PlaybackState.PAUSED)

    def _on_tag_msg(self, bus, msg):
        """Etiquetas del medio (titulo, artista, etc.)."""
        if not self._gst_available:
            return

        tags = msg.parse_tag()
        changed = False

        for i in range(tags.n_tags()):
            tag_name = tags.nth_tag_name(i)

            if tag_name == "title":
                success, value = tags.get_string(tag_name)
                if success and value:
                    self._track_info.title = value
                    changed = True

            elif tag_name == "artist":
                success, value = tags.get_string(tag_name)
                if success and value:
                    self._track_info.artist = value
                    changed = True

            elif tag_name == "duration":
                # Ignorar, usamos la duracion del pipeline
                pass

        if changed and self._on_tags_changed:
            self._safe_call(self._on_tags_changed, self._track_info)

    def _on_buffering_msg(self, bus, msg):
        """Buffering para streaming."""
        if not self._gst_available:
            return

        percent = msg.parse_buffering()
        if percent < 100:
            self._pipeline.set_state(self._Gst.State.PAUSED)
            self._set_state(PlaybackState.BUFFERING)
        else:
            if self._state == PlaybackState.BUFFERING:
                self._pipeline.set_state(self._Gst.State.PLAYING)
                self._set_state(PlaybackState.PLAYING)

    # ── Polling de posicion ──

    def _start_position_poll(self):
        """Iniciar polling periodico de posicion."""
        self._stop_position_poll()
        if not self._gst_available:
            return

        def _poll():
            if self._pipeline and self._state == PlaybackState.PLAYING:
                try:
                    success, position_ns = self._pipeline.query_position(self._Gst.Format.TIME)
                    if success:
                        self._track_info.position_ms = int(position_ns / 1_000_000)

                    # Actualizar duracion si no la tenemos
                    if self._track_info.duration_ms <= 0:
                        success, duration_ns = self._pipeline.query_duration(self._Gst.Format.TIME)
                        if success:
                            self._track_info.duration_ms = int(duration_ns / 1_000_000)

                    # Notificar cambio de posicion
                    if self._on_position_changed:
                        self._safe_call(self._on_position_changed, self._track_info)

                except Exception:
                    pass

            return True  # Repetir

        self._position_poll_id = self._GLib.timeout_add(
            self._position_poll_interval_ms, _poll
        )

    def _stop_position_poll(self):
        """Detener polling de posicion."""
        if self._vu_level_id is not None:
            pass  # Se limpia en _stop_vu_poll
        if self._position_poll_id is not None and self._gst_available:
            try:
                self._GLib.source_remove(self._position_poll_id)
            except Exception:
                pass
            self._position_poll_id = None

    # ── VU Meter polling ──

    def _start_vu_poll(self):
        """Iniciar monitoreo de niveles de audio."""
        self._stop_vu_poll()
        if not self._gst_available:
            return

        def _poll_vu():
            if self._pipeline and self._state == PlaybackState.PLAYING:
                try:
                    bus = self._pipeline.get_bus()
                    if bus:
                        # Pop level messages from the bus
                        while True:
                            msg = bus.pop_filtered(self._Gst.MessageType.ELEMENT)
                            if msg is None:
                                break
                            structure = msg.get_structure()
                            if structure and structure.get_name() == "level":
                                self._update_vu_from_structure(structure)
                except Exception:
                    pass

                if self._on_vu_changed:
                    self._safe_call(self._on_vu_changed, self._vu_data)

            return True

        self._vu_level_id = self._GLib.timeout_add(
            self._vu_update_interval_ms, _poll_vu
        )

    def _stop_vu_poll(self):
        """Detener monitoreo VU."""
        if self._vu_level_id is not None and self._gst_available:
            try:
                self._GLib.source_remove(self._vu_level_id)
            except Exception:
                pass
            self._vu_level_id = None

    def _update_vu_from_structure(self, structure):
        """Actualizar datos VU desde un mensaje de nivel GStreamer."""
        try:
            import math

            # Leer valores rms (root mean square) para cada canal
            n_values = structure.get_value("rms")
            n_peaks = structure.get_value("peak")

            if n_values and len(n_values) > 0:
                # Convertir dB a lineal (0.0 - 1.0)
                def db_to_linear(db):
                    if db <= -60.0:
                        return 0.0
                    return max(0.0, min(1.0, 10.0 ** (db / 20.0)))

                left_db = float(n_values[0]) if len(n_values) > 0 else -60.0
                right_db = float(n_values[1]) if len(n_values) > 1 else left_db

                self._vu_data.level_left = db_to_linear(left_db)
                self._vu_data.level_right = db_to_linear(right_db)

                # Peaks
                if n_peaks and len(n_peaks) > 0:
                    peak_left = float(n_peaks[0]) if len(n_peaks) > 0 else -60.0
                    peak_right = float(n_peaks[1]) if len(n_peaks) > 1 else peak_left

                    self._vu_data.peak_left = db_to_linear(peak_left)
                    self._vu_data.peak_right = db_to_linear(peak_right)

                    # Clipping si peak > 0 dB
                    self._vu_data.is_clipping = (peak_left > -0.1 or peak_right > -0.1)

        except Exception as e:
            pass  # Silenciar errores en VU meter

    # ── Utilidades ──

    def _set_state(self, new_state: PlaybackState):
        """Cambiar estado interno y notificar."""
        old_state = self._state
        self._state = new_state

        if old_state != new_state:
            print(f"[AudioEngine] Estado: {old_state.value} -> {new_state.value}")
            if self._on_state_changed:
                self._safe_call(self._on_state_changed, new_state)

    def _notify_error(self, error_str: str):
        """Notificar error via callback y EventBus."""
        print(f"[AudioEngine] ERROR: {error_str}")
        if self._on_error:
            self._safe_call(self._on_error, error_str)
        get_event_bus().publish("audio.error", {"message": error_str}, Priority.HIGH)

    def _safe_call(self, callback, *args):
        """Ejecutar callback en el hilo principal via GLib.idle_add."""
        try:
            self._GLib.idle_add(callback, *args)
        except Exception as e:
            print(f"[AudioEngine] Error en callback: {e}")

    def _record_play_history(self, info: TrackInfo, source: str = "playlist", source_id: int | None = None):
        """Registrar la pista en el historial de reproduccion."""
        try:
            from radio_automator.core.database import get_session, PlayHistory
            session = get_session()
            try:
                history = PlayHistory(
                    filepath=info.filepath,
                    title=info.title,
                    artist=info.artist,
                    duration_ms=info.duration_ms,
                    source=source,
                    source_id=source_id,
                )
                session.add(history)
                session.commit()
            finally:
                session.close()
        except Exception as e:
            print(f"[AudioEngine] Error registrando historial: {e}")

    def get_duration_for_file(self, filepath: str) -> int:
        """
        Obtener la duracion de un archivo de audio en milisegundos.
        Retorna 0 si no se puede determinar.
        """
        if not self._gst_available or not Path(filepath).exists():
            return 0

        try:
            pipeline = self._Gst.ElementFactory.make("playbin", "duration_probe")
            pipeline.set_property("uri", f"file://{filepath}")
            pipeline.set_state(self._Gst.State.PAUSED)

            # Esperar estado PAUSED
            self._Gst.Bus.timed_pop_filtered(
                pipeline.get_bus(),
                5 * self._Gst.SECOND,  # timeout 5s
                self._Gst.MessageType.ASYNC_DONE
            )

            success, duration_ns = pipeline.query_duration(self._Gst.Format.TIME)
            pipeline.set_state(self._Gst.State.NULL)

            if success:
                return int(duration_ns / 1_000_000)
        except Exception as e:
            print(f"[AudioEngine] Error obteniendo duracion: {e}")

        return 0

    def cleanup(self):
        """Limpiar todos los recursos del motor."""
        self.stop()
        self._stop_pipeline()
        print("[AudioEngine] Recursos limpiados")


# ── Instancia global ──
_engine: AudioEngine | None = None


def get_audio_engine() -> AudioEngine:
    """Obtener la instancia singleton del AudioEngine."""
    global _engine
    if _engine is None:
        _engine = AudioEngine()
    return _engine


def reset_audio_engine():
    """Reiniciar el motor de audio (para tests)."""
    global _engine
    if _engine:
        _engine.cleanup()
    _engine = None
