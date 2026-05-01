"""
Motor de audio basado en GStreamer.
Play, pause, stop, seek, volumen, crossfade, VU meters, streaming.

Arquitectura: Pipeline fresco por cada pista.
- Cada vez que se reproduce unha nova pista, o pipeline anterior
  destrúese por completo (NULL + cleanup de bus signals +_unref)
  e créase un novo desde cero.
- Isto garantiza que non se acumulen recursos internos de GStreamer
  (uridecodebin, decoders, buffers) que causaban entrecortado.
- O audio-filter (level para VU meter) tamén se crea novo por cada pista.
"""

from __future__ import annotations

import math
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

    ARQUITECTURA: Pipeline fresco por cada pista.
    - Cada vez que se reproduce unha nova pista:
      1. O pipeline anterior destrúese por completo
         (set_state(NULL) + remove_signal_watch + disconnect handlers)
      2. Créase un novo playbin + audio-filter desde cero
      3. Conéctanse os bus handlers ao novo pipeline
      4. Arranca a reproducion
    - Isto garantiza que non quedan recursos internos de GStreamer
      (uridecodebin, decoders, buffers) que causaban entrecortado
      que empeoraba con cada cambio de pista.

    - Soporta multiples listeners via set_callbacks().
    - Toda interaccion con GTK via GLib.idle_add.
    """

    # Extensiones de audio soportadas
    SUPPORTED_EXTENSIONS = {
        ".mp3", ".ogg", ".flac", ".wav", ".m4a", ".opus", ".aac",
        ".wma", ".mp4", ".webm", ".oga", ".spx", ".mp2"
    }

    def __init__(self):
        self._pipeline = None          # Gst.Element (playbin) - actual
        self._audio_filter = None      # Gst.Bin (level) - actual
        self._bus_handler_ids = []     # IDs de signal handlers para cleanup
        self._state = PlaybackState.STOPPED
        self._track_info = TrackInfo()
        self._volume = 1.0
        self._muted = False

        # Crossfade (lido desde config)
        self._crossfade_duration_ms = 3000  # 3s por defecto
        self._crossfade_enabled = True
        self._crossfade_curve = "linear"    # linear | logarithmic | sigmoid
        self._load_crossfade_config()

        # VU meter
        self._vu_data = VUMeterData()
        self._vu_level_id = None  # GLib timeout ID
        self._vu_update_interval_ms = 60

        # Callbacks (se ejecutan en hilo principal via GLib.idle_add)
        # Soporte multiples listeners: lista de dicts con callbacks
        self._callback_listeners: list[dict[str, Callable | None]] = []

        # Posicion polling
        self._position_poll_id = None
        self._position_poll_interval_ms = 250

        # Fade timeout IDs (para cancelar en stop/cleanup)
        self._fade_timeout_ids: list[int] = []

        # GStreamer availability
        self._gst_available = False
        self._init_gst()

    def _load_crossfade_config(self):
        """Cargar configuracion de crossfade desde ConfigManager."""
        try:
            cfg = get_config()
            duration = cfg.get_float("crossfade_duration", 3.0)
            self._crossfade_duration_ms = int(duration * 1000)
            self._crossfade_curve = cfg.get("crossfade_curve", "linear")
            # Crossfade habilitado se a duracion > 0
            self._crossfade_enabled = duration > 0
            print(f"[AudioEngine] Crossfade: enabled={self._crossfade_enabled}, "
                  f"duration={self._crossfade_duration_ms}ms, curve={self._crossfade_curve}")
        except Exception:
            pass

    def _init_gst(self):
        """Inicializar GStreamer. Si no esta disponible, funciona en modo mock."""
        try:
            import gi
            gi.require_version('Gst', '1.0')
            from gi.repository import Gst
            Gst.init(None)
            from gi.repository import GLib as _GLib
            self._gst_available = True
            self._Gst = Gst
            self._GLib = _GLib
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
        """Registrar callbacks para eventos del motor.

        Soporta multiples listeners: cada llamada a set_callbacks anade
        un novo conxunto de callbacks. Todos os listeners rexistrados seran
        notificados cando se produza un evento.
        """
        self._callback_listeners.append({
            'on_state_changed': on_state_changed,
            'on_position_changed': on_position_changed,
            'on_track_finished': on_track_finished,
            'on_vu_changed': on_vu_changed,
            'on_error': on_error,
            'on_tags_changed': on_tags_changed,
        })

    # ═══════════════════════════════════════
    # Pipeline: crear / destruir
    # ═══════════════════════════════════════

    def _create_fresh_pipeline(self):
        """Crear un pipeline e filtro de audio novos desde cero.

        Destruí previamente o pipeline actual se existe.
        Cada chamada produce un pipeline completamente limpo.
        """
        # 1. Destruír pipeline anterior se existe
        self._teardown_current_pipeline()

        # 2. Crear novo playbin
        self._pipeline = self._Gst.ElementFactory.make("playbin", "player")
        if not self._pipeline:
            print("[AudioEngine] ERRO: Non se puido crear playbin")
            return

        # 3. Crear novo filtro de audio (level para VU meter)
        self._audio_filter = self._create_audio_filter()
        if self._audio_filter:
            self._pipeline.set_property("audio-filter", self._audio_filter)

        # 4. Conectar signals do bus
        bus = self._pipeline.get_bus()
        bus.add_signal_watch()

        self._bus_handler_ids = []  # Resetear lista
        hid = bus.connect("message::eos", self._on_eos)
        self._bus_handler_ids.append(hid)
        hid = bus.connect("message::error", self._on_error_msg)
        self._bus_handler_ids.append(hid)
        hid = bus.connect("message::state-changed", self._on_gst_state_changed)
        self._bus_handler_ids.append(hid)
        hid = bus.connect("message::tag", self._on_tag_msg)
        self._bus_handler_ids.append(hid)
        hid = bus.connect("message::buffering", self._on_buffering_msg)
        self._bus_handler_ids.append(hid)
        hid = bus.connect("message::element", self._on_element_msg)
        self._bus_handler_ids.append(hid)

        print("[AudioEngine] Pipeline fresco creado (playbin + audio-filter)")

    def _teardown_current_pipeline(self):
        """Destruír completamente o pipeline actual e limpar todos os recursos.

        Faz:
        1. Parar polling (position + VU) para que non accedan ao pipeline
        2. Desconectar todos os signal handlers do bus
        3. Quitar signal watch do bus
        4. Poñer o pipeline a NULL
        5. Desreferenciar pipeline e audio_filter

        Isto garante que non quedan callbacks pendientes que accedan
        a un pipeline destruído ou a recursos liberados.
        """
        # 1. Parar polling para que non accedan ao pipeline
        self._stop_position_poll()
        self._stop_vu_poll()

        if self._pipeline is None:
            self._audio_filter = None
            self._bus_handler_ids = []
            return

        try:
            # 2. Desconectar signal handlers do bus
            bus = self._pipeline.get_bus()
            if bus:
                bus.remove_signal_watch()
                for handler_id in self._bus_handler_ids:
                    try:
                        bus.disconnect(handler_id)
                    except Exception:
                        pass

            # 3. Poñer a NULL e soltar referencias
            self._pipeline.set_state(self._Gst.State.NULL)
        except Exception as e:
            print(f"[AudioEngine] Erro en teardown: {e}")

        self._pipeline = None
        self._audio_filter = None
        self._bus_handler_ids = []

    def _create_audio_filter(self):
        """
        Crear un filtro de audio con elemento level para VU meter.
        Créase novo por cada pipeline (non se reutiliza).
        """
        if not self._gst_available:
            return None

        try:
            from gi.repository import Gst

            # Bin con level (sin volume redundante)
            gst_bin = Gst.Bin.new("audio_filter")

            # Elemento level para VU meter
            level = Gst.ElementFactory.make("level", "level")
            if level:
                level.set_property("interval", self._vu_update_interval_ms * 1_000_000)
                level.set_property("post-messages", True)

            if level:
                gst_bin.add(level)

                # Ghost pads (passthrough: sink -> level -> src)
                sink_pad = level.get_static_pad("sink")
                ghost_sink = Gst.GhostPad.new("sink", sink_pad)
                gst_bin.add_pad(ghost_sink)

                src_pad = level.get_static_pad("src")
                ghost_src = Gst.GhostPad.new("src", src_pad)
                gst_bin.add_pad(ghost_src)

                return gst_bin

        except Exception as e:
            print(f"[AudioEngine] Error creando filtro de audio: {e}")

        return None

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
        """Iniciar reproduccion de una URI (file:// ou http(s)://).

        Crea un pipeline completamente novo para cada pista:
        1. Destruí o pipeline anterior por completo (_create_fresh_pipeline)
        2. Establece a URI e volume
        3. Pasa a PLAYING

        Non reutiliza pipelines para evitar acumulación de recursos
        internos de GStreamer.
        """
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
            # 1. Crear pipeline fresco (destrúe o anterior automaticamente)
            self._create_fresh_pipeline()

            if self._pipeline is None:
                self._notify_error("No se pudo crear el pipeline de audio")
                return False

            # 2. Establecer URI e propiedades
            self._pipeline.set_property("uri", uri)
            self._pipeline.set_property("volume", 0.0 if self._muted else self._volume)

            # 3. Iniciar reproduccion
            result = self._pipeline.set_state(self._Gst.State.PLAYING)
            if result == self._Gst.StateChangeReturn.FAILURE:
                self._notify_error(f"No se pudo reproducir: {uri}")
                self._pipeline.set_state(self._Gst.State.NULL)
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

        # Cancelar fade timers activos (se hai crossfade en curso)
        self._cancel_fade_timers()

        # Destruír pipeline completamente
        if self._gst_available:
            self._teardown_current_pipeline()

        self._track_info = TrackInfo()
        self._set_state(PlaybackState.STOPPED)

        get_event_bus().publish("audio.stopped", {
            "filepath": old_info.filepath,
        })

    def set_volume(self, volume: float):
        """Establecer volumen (0.0 - 1.0)."""
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
        """Buscar una posicion en la pista (en milisegundos)."""
        if self._track_info.is_streaming:
            return

        if not self._gst_available or not self._pipeline:
            return

        if self._state != PlaybackState.PLAYING and self._state != PlaybackState.PAUSED:
            return

        try:
            position_ns = int(position_ms * 1_000_000)
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

        Usa un SEGUNDO pipeline temporal para a transicion,
        que se destrúe automaticamente ao rematar o fade.
        """
        if (not self._crossfade_enabled or
                self._state != PlaybackState.PLAYING or
                self._track_info.is_streaming):
            return self.play_file(filepath)

        if not self._gst_available:
            self.stop()
            return self.play_file(filepath)

        if not Path(filepath).exists():
            self._notify_error(f"Archivo no encontrado: {filepath}")
            return False

        fade_duration_ns = int(self._crossfade_duration_ms * 1_000_000)

        try:
            # Guardar referencia ao pipeline actual
            old_pipeline = self._pipeline

            # Crear pipeline TEMPORAL para o crossfade
            crossfade_pipeline = self._Gst.ElementFactory.make("playbin", "crossfade_tmp")
            crossfade_pipeline.set_property("uri", f"file://{filepath}")

            # Filtro de audio para VU no pipeline temporal
            audio_filter = self._create_audio_filter()
            if audio_filter:
                crossfade_pipeline.set_property("audio-filter", audio_filter)

            # Conectar bus do pipeline temporal
            bus = crossfade_pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message::eos", self._on_eos)
            bus.connect("message::error", self._on_error_msg)
            bus.connect("message::state-changed", self._on_gst_state_changed)
            bus.connect("message::tag", self._on_tag_msg)
            bus.connect("message::element", self._on_element_msg)

            crossfade_pipeline.set_property("volume", 0.0)

            # Iniciar novo pipeline
            crossfade_pipeline.set_state(self._Gst.State.PLAYING)

            # Fade-in do novo pipeline
            self._apply_fade_in(crossfade_pipeline, fade_duration_ns)

            # Fade-out do pipeline actual
            if old_pipeline:
                self._pipeline = crossfade_pipeline  # Temporalmente
                self._apply_fade_out_and_cleanup(
                    old_pipeline, fade_duration_ns,
                    on_complete=lambda: self._restore_main_pipeline(crossfade_pipeline)
                )

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
            # Se falla o crossfade, restaurar e usar play normal
            self._pipeline = old_pipeline if old_pipeline else self._pipeline
            self._notify_error(f"Error en crossfade, usando play normal: {e}")
            return self.play_file(filepath)

    def _restore_main_pipeline(self, crossfade_pipeline):
        """Restaurar self._pipeline tras crossfade."""
        # O pipeline de crossfade agora é o "principal"
        self._ensure_pipeline_exists(crossfade_pipeline)

    def _ensure_pipeline_exists(self, pipeline):
        """Asegurar que temos un pipeline valido."""
        if pipeline and self._pipeline != pipeline:
            return  # Outro pipeline xa se asignou

    def set_crossfade(self, enabled: bool, duration_ms: int | None = None,
                      curve: str | None = None):
        """Configurar crossfade. Tamén garda en ConfigManager."""
        self._crossfade_enabled = enabled
        if duration_ms is not None:
            self._crossfade_duration_ms = max(0, min(15000, duration_ms))
        if curve is not None:
            self._crossfade_curve = curve

        # Gardar en ConfigManager para persistencia
        try:
            cfg = get_config()
            cfg.set_float("crossfade_duration", self._crossfade_duration_ms / 1000.0)
            if curve:
                cfg.set("crossfade_curve", curve)
        except Exception:
            pass

    def _apply_fade_out_and_cleanup(self, pipeline, duration_ns: int,
                                     on_complete: Callable | None = None):
        """Aplicar fade-out a un pipeline e limpealo ao final."""
        steps = 20
        step_ms = (duration_ns // 1_000_000) // steps
        volume = self._volume

        def _step(current=0):
            if current >= steps:
                try:
                    pipeline.set_state(self._Gst.State.NULL)
                    bus = pipeline.get_bus()
                    if bus:
                        bus.remove_signal_watch()
                except Exception:
                    pass
                if self._pipeline != pipeline:
                    pass
                if on_complete:
                    try:
                        on_complete()
                    except Exception:
                        pass
                return False

            fraction = current / steps
            new_vol = self._apply_curve(volume, fraction, fade_out=True)
            try:
                if pipeline.get_state(0)[1] != self._Gst.State.NULL:
                    pipeline.set_property("volume", max(0.0, new_vol))
            except Exception:
                return False

            tid = self._GLib.timeout_add(step_ms, _step, current + 1)
            self._fade_timeout_ids.append(tid)
            return False

        _step(0)

    def _apply_fade_in(self, pipeline, duration_ns: int):
        """Aplicar fade-in a un pipeline."""
        steps = 20
        step_ms = (duration_ns // 1_000_000) // steps
        volume = self._volume

        def _step(current=0):
            if current >= steps:
                try:
                    pipeline.set_property("volume", volume)
                except Exception:
                    pass
                return False

            fraction = (current + 1) / steps
            new_vol = self._apply_curve(volume, fraction, fade_out=False)
            try:
                pipeline.set_property("volume", max(0.0, min(1.0, new_vol)))
            except Exception:
                return False

            tid = self._GLib.timeout_add(step_ms, _step, current + 1)
            self._fade_timeout_ids.append(tid)
            return False

        _step(0)

    def _cancel_fade_timers(self):
        """Cancelar todos os timers de fade activos."""
        for tid in self._fade_timeout_ids:
            try:
                self._GLib.source_remove(tid)
            except Exception:
                pass
        self._fade_timeout_ids.clear()

    def _apply_curve(self, volume: float, fraction: float,
                     fade_out: bool = False) -> float:
        """Aplicar curva de crossfade (linear, logarithmic, sigmoid)."""
        if fade_out:
            t = 1.0 - fraction  # 1.0 -> 0.0
        else:
            t = fraction        # 0.0 -> 1.0

        if self._crossfade_curve == "logarithmic":
            t = math.log(1 + t * 9) / math.log(10) if t > 0 else 0
        elif self._crossfade_curve == "sigmoid":
            k = 10
            t = 1 / (1 + math.exp(-k * (t - 0.5)))

        return volume * t

    # ── Pipeline lifecycle ──

    def _stop_pipeline(self):
        """Resetear o pipeline a NULL e limpar resources.

        Usado en situations de erro. Para reproducir unha nova pista,
        úsase _create_fresh_pipeline() que fai teardown completo.
        """
        if not self._gst_available or self._pipeline is None:
            return

        try:
            self._pipeline.set_state(self._Gst.State.NULL)
        except Exception:
            pass

    def cleanup(self):
        """Limpiar todos los recursos del motor."""
        self._cancel_fade_timers()
        self.stop()
        print("[AudioEngine] Recursos limpiados")

    # ── Handlers de senales GStreamer ──

    def _on_eos(self, bus, msg):
        """End of Stream: la pista ha terminado.

        Executase no fío de GStreamer. Todo o manipulado de pipeline
        e UI se despacha via GLib.idle_add.
        """
        # Filtrar: soamente mensaxes do pipeline actual
        try:
            current_bus = self._pipeline.get_bus() if self._pipeline else None
        except Exception:
            return
        if bus != current_bus:
            return

        info = self._track_info
        print(f"[AudioEngine] Fin de pista: {info.title}")

        # Parar polling de posicion e VU (xa non hai pista)
        # Despachado ao fío principal para evitar problemas de threading
        if self._gst_available:
            self._GLib.idle_add(self._stop_position_poll)
            self._GLib.idle_add(self._stop_vu_poll)

        # Registrar en historial via idle_add (non bloquea o fío de GStreamer)
        if self._gst_available:
            self._GLib.idle_add(self._record_play_history, info)
        else:
            self._record_play_history(info)

        # Publicar evento de bus (non manipula pipeline)
        get_event_bus().publish("audio.track_finished", {
            "filepath": info.filepath,
            "title": info.title,
        })

        # Despachar on_track_finished no filo principal (GTK thread)
        # para que play_file() poida manipular o pipeline de forma segura
        def _dispatch():
            self._safe_call('on_track_finished', info)

        if self._gst_available:
            self._GLib.idle_add(_dispatch)
        else:
            _dispatch()

    def _on_error_msg(self, bus, msg):
        """Error en el pipeline.

        Executase no fío de GStreamer. Despacha todo ao fío principal.
        """
        if not self._gst_available:
            return

        # Filtrar: soamente do pipeline actual
        try:
            current_bus = self._pipeline.get_bus() if self._pipeline else None
        except Exception:
            return
        if bus != current_bus:
            return

        err, debug = msg.parse_error()
        error_str = f"GStreamer: {err.message}"
        print(f"[AudioEngine] Error: {error_str}")
        if debug:
            print(f"[AudioEngine] Debug: {debug}")

        # Despachar todo ao fío principal (GTK thread)
        def _dispatch_error():
            self._stop_pipeline()
            self._stop_position_poll()
            self._stop_vu_poll()
            self._set_state(PlaybackState.ERROR)
            self._notify_error(error_str)

        if self._gst_available:
            self._GLib.idle_add(_dispatch_error)
        else:
            _dispatch_error()

    def _on_gst_state_changed(self, bus, msg):
        """Cambio de estado del pipeline.

        Executase no fío de GStreamer. Despacha notificacion ao fío principal.
        """
        if not self._gst_available:
            return

        # Filtrar: soamente do pipeline actual e top-level
        if self._pipeline is None or msg.src != self._pipeline:
            return

        old, new, pending = msg.parse_state_changed()

        # Ignorar estados intermedios (solo reaccionar cando a transicion e completa)
        if pending != self._Gst.State.VOID_PENDING:
            return

        # Solo nos interesamos los cambios top-level completados
        # Despachar ao fío principal para que a UI se actualice desde GTK
        def _dispatch_state():
            if new == self._Gst.State.PLAYING and self._state != PlaybackState.PLAYING:
                self._set_state(PlaybackState.PLAYING)
            elif new == self._Gst.State.PAUSED and self._state == PlaybackState.PLAYING:
                self._set_state(PlaybackState.PAUSED)

        if self._gst_available:
            self._GLib.idle_add(_dispatch_state)
        else:
            _dispatch_state()

    def _on_tag_msg(self, bus, msg):
        """Etiquetas del medio (titulo, artista, etc.).

        Executase no fío de GStreamer. Despacha notificacion ao fío principal.
        """
        if not self._gst_available:
            return

        # Filtrar: soamente do pipeline actual
        try:
            current_bus = self._pipeline.get_bus() if self._pipeline else None
        except Exception:
            return
        if bus != current_bus:
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
                pass  # Ignorar, usamos la duracion del pipeline

        if changed:
            # Capturar info antes do dispatch (pode cambiar)
            info_snapshot = TrackInfo(
                filepath=self._track_info.filepath,
                title=self._track_info.title,
                artist=self._track_info.artist,
                duration_ms=self._track_info.duration_ms,
                position_ms=self._track_info.position_ms,
                is_streaming=self._track_info.is_streaming,
            )

            def _dispatch_tags():
                self._safe_call('on_tags_changed', info_snapshot)

            if self._gst_available:
                self._GLib.idle_add(_dispatch_tags)
            else:
                _dispatch_tags()

    def _on_buffering_msg(self, bus, msg):
        """Buffering para streaming.

        Executase no fío de GStreamer. GStreamer permite set_state
        desde calquera fío para playbin, pero despachamos o estado
        da UI ao fío principal.
        """
        if not self._gst_available:
            return

        # Filtrar: soamente do pipeline actual
        try:
            current_bus = self._pipeline.get_bus() if self._pipeline else None
        except Exception:
            return
        if bus != current_bus:
            return

        percent = msg.parse_buffering()
        # set_state e thread-safe en GStreamer para playbin
        if percent < 100:
            if self._pipeline:
                self._pipeline.set_state(self._Gst.State.PAUSED)
            if self._gst_available:
                self._GLib.idle_add(self._set_state, PlaybackState.BUFFERING)
            else:
                self._set_state(PlaybackState.BUFFERING)
        else:
            if self._state == PlaybackState.BUFFERING:
                if self._pipeline:
                    self._pipeline.set_state(self._Gst.State.PLAYING)
                if self._gst_available:
                    self._GLib.idle_add(self._set_state, PlaybackState.PLAYING)
                else:
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
                    self._safe_call('on_position_changed', self._track_info)

                except Exception:
                    pass

            return True  # Repetir

        self._position_poll_id = self._GLib.timeout_add(
            self._position_poll_interval_ms, _poll
        )

    def _stop_position_poll(self):
        """Detener polling de posicion."""
        if self._position_poll_id is not None and self._gst_available:
            try:
                self._GLib.source_remove(self._position_poll_id)
            except Exception:
                pass
            self._position_poll_id = None

    # ── VU Meter polling ──

    def _on_element_msg(self, bus, msg):
        """Handle element messages (level/VU data) via signal watch.

        Executase no fío de GStreamer. A actualizacion de VU data
        e thread-safe porque soamente escribe en self._vu_data
        (os datos léense no poll do fío principal).
        """
        if not self._gst_available:
            return

        # Filtrar: soamente do pipeline actual
        try:
            current_bus = self._pipeline.get_bus() if self._pipeline else None
        except Exception:
            return
        if bus != current_bus:
            return

        try:
            structure = msg.get_structure()
            if structure and structure.get_name() == "level":
                self._update_vu_from_structure(structure)
        except Exception:
            pass

    def _start_vu_poll(self):
        """Iniciar monitoreo de niveles de audio.

        Os datos de VU chegan via signal watch (_on_element_msg).
        Este polling soamente dispara a actualizacion da UI.
        """
        self._stop_vu_poll()
        if not self._gst_available:
            return

        def _poll_vu():
            if self._pipeline and self._state == PlaybackState.PLAYING:
                self._safe_call('on_vu_changed', self._vu_data)
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
        """Actualizar datos VU desde un mensaje de nivel GStreamer.

        Mapeo piezo-linear: comprime o rango silencioso (-60 a -20 dB)
        e expande o rango audible (-20 a 0 dB) para mellor representacion visual.
        """
        try:
            # Leer valores rms (root mean square) para cada canal
            n_values = structure.get_value("rms")
            n_peaks = structure.get_value("peak")

            if n_values and len(n_values) > 0:
                # Mapeo piezo-linear optimizado para representacion visual:
                # - Comprime o rango silencioso (-60 a -20 dB) na metade inferior
                # - Expande o rango audible (-20 a 0 dB) na metade superior
                # Resultado: audio normal (~-20dB) enche ~50%, picos (~-6dB) ~85%
                def db_to_linear(db):
                    if db <= -60.0:
                        return 0.0
                    if db <= -20.0:
                        return (db + 60.0) / 80.0   # -60->0.0, -40->0.25, -20->0.50
                    return 0.5 + (db + 20.0) / 40.0   # -20->0.50, -10->0.75, -6->0.85, 0->1.0

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

                # Clipping detection
                self._vu_data.is_clipping = (
                    self._vu_data.peak_left > 0.95 or self._vu_data.peak_right > 0.95
                )

        except Exception as e:
            print(f"[AudioEngine] Error actualizando VU: {e}")

    # ═══════════════════════════════════════
    # Utiles internos
    # ═══════════════════════════════════════

    def _set_state(self, new_state: PlaybackState):
        """Cambiar estado interno e notificar listeners."""
        old_state = self._state
        self._state = new_state

        if old_state != new_state:
            self._safe_call('on_state_changed', new_state)

    def _safe_call(self, callback_name: str, *args):
        """Chamar un callback de forma segura en todos os listeners."""
        for listener in self._callback_listeners:
            callback = listener.get(callback_name)
            if callback:
                try:
                    callback(*args)
                except Exception as e:
                    print(f"[AudioEngine] Erro en callback '{callback_name}': {e}")

    def _notify_error(self, error_msg: str):
        """Notificar erro a todos os listeners."""
        print(f"[AudioEngine] Error: {error_msg}")
        self._safe_call('on_error', error_msg)

    def _record_play_history(self, track_info: TrackInfo):
        """Rexistrar pista no historial de reproduccion."""
        try:
            from radio_automator.core.database import get_session, PlayHistory
            session = get_session()
            try:
                history = PlayHistory(
                    filepath=track_info.filepath,
                    title=track_info.title or Path(track_info.filepath).stem if track_info.filepath else "Desconocido",
                    artist=track_info.artist or "",
                    played_at=datetime.now(),
                )
                session.add(history)
                session.commit()
            finally:
                session.close()
        except Exception as e:
            print(f"[AudioEngine] Erro gardando historial: {e}")


# ═══════════════════════════════════════
# Instancia global
# ═══════════════════════════════════════

_engine: AudioEngine | None = None


def get_audio_engine() -> AudioEngine:
    """Obtener la instancia singleton del AudioEngine."""
    global _engine
    if _engine is None:
        _engine = AudioEngine()
    return _engine


def reset_audio_engine():
    """Reiniciar el motor (para tests)."""
    global _engine
    if _engine:
        _engine.cleanup()
    _engine = None


# Necesario para _record_play_history
from datetime import datetime
