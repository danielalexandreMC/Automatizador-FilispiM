"""
Barra de transporte (TransportBar).
Controles de reproduccion, barra de progreso, VU meters, e info de pista.
Se ubica en la parte inferior de la ventana, encima de la StatusBar.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Pango

from radio_automator.services.audio_engine import (
    get_audio_engine, PlaybackState, TrackInfo, VUMeterData
)
from radio_automator.services.play_queue import get_play_queue


# ═══════════════════════════════════════
# Barra de transporte
# ═══════════════════════════════════════

class TransportBar(Gtk.Box):
    """
    Barra de controles de reproduccion.
    Contiene: VU meters | controles (prev/play/next) | info + progreso | volumen
    """

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("ra-transport")
        self._engine = get_audio_engine()
        self._queue = get_play_queue()
        self._update_pending = False

        self._build_controls()
        self._build_progress()
        self._connect_engine()
        self._connect_queue()

    # ── Construccion de UI ──

    def _build_controls(self):
        """Fila principal: VU | controles | info | volumen."""
        main_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        main_row.set_margin_start(8)
        main_row.set_margin_end(8)
        main_row.set_margin_top(4)
        main_row.set_margin_bottom(2)
        self.append(main_row)

        # ── VU Meters ──
        vu_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        vu_box.set_size_request(100, 28)

        self._vu_left = self._create_vu_bar("L")
        self._vu_right = self._create_vu_bar("R")
        vu_box.append(self._vu_left)
        vu_box.append(self._vu_right)

        main_row.append(vu_box)

        # Separador
        sep1 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        main_row.append(sep1)

        # ── Controles de transporte ──
        controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        # Boton Anterior
        self._btn_prev = Gtk.Button()
        self._btn_prev.set_icon_name("media-skip-backward-symbolic")
        self._btn_prev.set_tooltip_text("Pista anterior")
        self._btn_prev.add_css_class("ra-button")
        self._btn_prev.add_css_class("flat")
        self._btn_prev.connect("clicked", self._on_prev)
        controls_box.append(self._btn_prev)

        # Boton Play/Pause
        self._btn_play = Gtk.Button()
        self._btn_play.set_icon_name("media-playback-start-symbolic")
        self._btn_play.set_tooltip_text("Reproducir / Pausar")
        self._btn_play.add_css_class("ra-button-primary")
        self._btn_play.add_css_class("ra-button")
        self._btn_play.set_size_request(42, 36)
        self._btn_play.connect("clicked", self._on_play_pause)
        controls_box.append(self._btn_play)

        # Boton Siguiente
        self._btn_next = Gtk.Button()
        self._btn_next.set_icon_name("media-skip-forward-symbolic")
        self._btn_next.set_tooltip_text("Pista siguiente")
        self._btn_next.add_css_class("ra-button")
        self._btn_next.add_css_class("flat")
        self._btn_next.connect("clicked", self._on_next)
        controls_box.append(self._btn_next)

        # Boton Stop
        self._btn_stop = Gtk.Button()
        self._btn_stop.set_icon_name("media-playback-stop-symbolic")
        self._btn_stop.set_tooltip_text("Detener")
        self._btn_stop.add_css_class("ra-button")
        self._btn_stop.add_css_class("flat")
        self._btn_stop.connect("clicked", self._on_stop)
        controls_box.append(self._btn_stop)

        main_row.append(controls_box)

        # Separador
        sep2 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        main_row.append(sep2)

        # ── Info de pista ──
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        info_box.set_hexpand(True)
        info_box.set_valign(Gtk.Align.CENTER)
        info_box.set_margin_start(4)

        self._track_title = Gtk.Label(label="Sin reproduccion")
        self._track_title.set_xalign(0)
        self._track_title.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self._track_title.add_css_class("ra-label")
        self._track_title.set_name("track-title")
        info_box.append(self._track_title)

        self._track_artist = Gtk.Label(label="")
        self._track_artist.set_xalign(0)
        self._track_artist.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self._track_artist.add_css_class("ra-label-dim")
        self._track_artist.set_name("track-artist")
        info_box.append(self._track_artist)

        main_row.append(info_box)

        # ── Progreso tiempo ──
        time_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        time_box.set_valign(Gtk.Align.CENTER)

        self._time_pos = Gtk.Label(label="0:00")
        self._time_pos.set_xalign(1)
        self._time_pos.add_css_class("ra-label-dim")
        self._time_pos.set_width_chars(5)
        time_box.append(self._time_pos)

        self._time_sep = Gtk.Label(label="/")
        self._time_sep.add_css_class("ra-label-dim")
        time_box.append(self._time_sep)

        self._time_dur = Gtk.Label(label="0:00")
        self._time_dur.set_xalign(0)
        self._time_dur.add_css_class("ra-label-dim")
        self._time_dur.set_width_chars(5)
        time_box.append(self._time_dur)

        main_row.append(time_box)

        # Separador
        sep3 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        main_row.append(sep3)

        # ── Volumen ──
        vol_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        vol_box.set_valign(Gtk.Align.CENTER)

        self._btn_mute = Gtk.Button()
        self._btn_mute.set_icon_name("audio-volume-high-symbolic")
        self._btn_mute.set_tooltip_text("Silenciar")
        self._btn_mute.add_css_class("ra-button")
        self._btn_mute.add_css_class("flat")
        self._btn_mute.connect("clicked", self._on_mute)
        vol_box.append(self._btn_mute)

        self._volume_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.01
        )
        self._volume_scale.set_value(1.0)
        self._volume_scale.set_width_chars(3)
        self._volume_scale.set_draw_value(False)
        self._volume_scale.add_css_class("ra-volume-scale")
        self._volume_scale.set_size_request(80, -1)
        self._volume_scale.connect("value-changed", self._on_volume_changed)
        self._volume_scale.connect("button-press-event", self._on_volume_press)
        self._volume_scale.connect("button-release-event", self._on_volume_release)
        vol_box.append(self._volume_scale)

        main_row.append(vol_box)

    def _build_progress(self):
        """Barra de progreso de la pista."""
        progress_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        progress_box.set_margin_start(8)
        progress_box.set_margin_end(8)
        progress_box.set_margin_bottom(4)

        self._progress_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.0, 100.0, 1.0
        )
        self._progress_scale.set_value(0.0)
        self._progress_scale.set_draw_value(False)
        self._progress_scale.set_show_fill_level(True)
        self._progress_scale.add_css_class("ra-progress-scale")
        self._progress_scale.set_hexpand(True)
        self._progress_scale.set_sensitive(False)
        self._progress_scale.connect("value-changed", self._on_progress_changed)
        self._progress_scale.connect("button-press-event", self._on_progress_press)
        self._progress_scale.connect("button-release-event", self._on_progress_release)
        self._progress_scale._seeking = False  # type: ignore[attr-defined]

        progress_box.append(self._progress_scale)
        self.append(progress_box)

    def _create_vu_bar(self, channel: str) -> Gtk.DrawingArea:
        """Crear un indicador de nivel (VU bar) para un canal."""
        da = Gtk.DrawingArea()
        da.set_content_width(45)
        da.set_content_height(26)
        da.set_name(f"vu-{channel}")
        da.add_css_class("ra-vu-bar")
        da._level = 0.0  # type: ignore[attr-defined]
        da._peak = 0.0   # type: ignore[attr-defined]

        def on_draw(drawing_area, cr, width, height):
            level = drawing_area._level  # type: ignore[attr-defined]
            peak = drawing_area._peak    # type: ignore[attr-defined]

            # Fondo
            cr.set_source_rgb(0.13, 0.13, 0.13)
            cr.rectangle(0, 0, width, height)
            cr.fill()

            # Nivel (verde -> amarillo -> rojo)
            bar_width = max(0, level * width)
            for x in range(int(bar_width)):
                ratio = x / max(1, width)
                if ratio < 0.6:
                    # Verde
                    cr.set_source_rgb(0.18, 0.8, 0.44)
                elif ratio < 0.85:
                    # Amarillo
                    cr.set_source_rgb(1.0, 0.78, 0.0)
                else:
                    # Rojo
                    cr.set_source_rgb(0.9, 0.2, 0.2)
                cr.rectangle(x, 2, 1, height - 4)
                cr.fill()

            # Peak indicator
            if peak > 0.01:
                peak_x = max(0, min(int(peak * width), width - 2))
                ratio = peak
                if ratio < 0.6:
                    cr.set_source_rgb(0.3, 1.0, 0.5)
                elif ratio < 0.85:
                    cr.set_source_rgb(1.0, 0.9, 0.2)
                else:
                    cr.set_source_rgb(1.0, 0.3, 0.3)
                cr.rectangle(peak_x, 1, 2, height - 2)
                cr.fill()

        da.set_draw_func(on_draw)
        return da

    # ── Conexion con AudioEngine ──

    def _connect_engine(self):
        """Conectar callbacks del motor de audio."""
        self._engine.set_callbacks(
            on_state_changed=self._on_engine_state_changed,
            on_position_changed=self._on_engine_position_changed,
            on_track_finished=self._on_engine_track_finished,
            on_vu_changed=self._on_engine_vu_changed,
            on_error=self._on_engine_error,
            on_tags_changed=self._on_engine_tags_changed,
        )

    def _connect_queue(self):
        """Conectar callbacks de la cola de reproduccion."""
        self._queue.set_callbacks(
            on_queue_changed=self._on_queue_changed,
            on_current_changed=self._on_queue_current_changed,
        )

    # ── Handlers de controles ──

    def _on_play_pause(self, _btn=None):
        engine = self._engine
        queue = self._queue

        if engine.state == PlaybackState.PLAYING:
            engine.pause()
        elif engine.state == PlaybackState.PAUSED:
            engine.resume()
        else:
            # No hay reproduccion, intentar reproducir la cola
            if queue.is_empty:
                return

            if queue.current_item is None:
                queue.play_next()

            item = queue.current_item
            if item:
                if item.is_streaming:
                    engine.play_stream(item.filepath)
                else:
                    engine.play_file(item.filepath)

    def _on_prev(self, _btn=None):
        item = self._queue.play_previous()
        if item:
            engine = self._engine
            if item.is_streaming:
                engine.play_stream(item.filepath)
            else:
                engine.play_file(item.filepath)

    def _on_next(self, _btn=None):
        item = self._queue.play_next()
        if item:
            engine = self._engine
            if item.is_streaming:
                engine.play_stream(item.filepath)
            else:
                engine.play_file(item.filepath)
        else:
            self._engine.stop()

    def _on_stop(self, _btn=None):
        self._engine.stop()

    def _on_mute(self, _btn=None):
        self._engine.toggle_mute()
        self._update_volume_icon()

    def _on_volume_changed(self, scale):
        self._engine.set_volume(scale.get_value())
        self._update_volume_icon()

    def _on_volume_press(self, scale, event):
        pass  # El seek se maneja en release

    def _on_volume_release(self, scale, event):
        pass

    def _on_progress_changed(self, scale):
        """Manejar cambio de posicion en la barra de progreso."""
        if hasattr(scale, '_seeking') and scale._seeking:
            return

        if not scale.get_sensitive():
            return

        value = scale.get_value()
        self._engine.seek(int(value))

    def _on_progress_press(self, scale, event):
        """Iniciar seeking cuando el usuario presiona la barra."""
        scale._seeking = True  # type: ignore[attr-defined]

    def _on_progress_release(self, scale, event):
        """Finalizar seek cuando el usuario suelta la barra."""
        scale._seeking = False  # type: ignore[attr-defined]
        value = scale.get_value()
        self._engine.seek(int(value))

    # ── Handlers de eventos del motor ──

    def _on_engine_state_changed(self, state: PlaybackState):
        """Actualizar UI cuando cambia el estado del motor."""
        def _update():
            if state == PlaybackState.PLAYING:
                self._btn_play.set_icon_name("media-playback-pause-symbolic")
                self._btn_play.set_tooltip_text("Pausar")
                self._progress_scale.set_sensitive(True)
            elif state == PlaybackState.PAUSED:
                self._btn_play.set_icon_name("media-playback-start-symbolic")
                self._btn_play.set_tooltip_text("Reanudar")
            else:
                self._btn_play.set_icon_name("media-playback-start-symbolic")
                self._btn_play.set_tooltip_text("Reproducir")
                self._progress_scale.set_sensitive(False)
                self._progress_scale.set_value(0.0)
                self._time_pos.set_label("0:00")
                self._time_dur.set_label("0:00")

            # Actualizar sidebar status
            self._update_sidebar_status(state)

        if self._engine.is_available:
            GLib.idle_add(_update)
        else:
            _update()

    def _on_engine_position_changed(self, info: TrackInfo):
        """Actualizar posicion y progreso."""
        def _update():
            if hasattr(self._progress_scale, '_seeking') and self._progress_scale._seeking:
                return

            self._time_pos.set_label(info.position_str)
            if info.duration_ms > 0:
                self._time_dur.set_label(info.duration_str)
                self._progress_scale.set_range(0, info.duration_ms)
                self._progress_scale.set_value(float(info.position_ms))

        if self._engine.is_available:
            GLib.idle_add(_update)
        else:
            _update()

    def _on_engine_track_finished(self, info: TrackInfo):
        """Pista terminada, avanzar en la cola."""
        self._queue.on_track_finished(info)

    def _on_engine_vu_changed(self, vu: VUMeterData):
        """Actualizar indicadores VU."""
        def _update():
            self._vu_left._level = vu.level_left   # type: ignore[attr-defined]
            self._vu_left._peak = vu.peak_left      # type: ignore[attr-defined]
            self._vu_right._level = vu.level_right  # type: ignore[attr-defined]
            self._vu_right._peak = vu.peak_right    # type: ignore[attr-defined]
            self._vu_left.queue_draw()
            self._vu_right.queue_draw()

        if self._engine.is_available:
            GLib.idle_add(_update)
        else:
            _update()

    def _on_engine_error(self, error_msg: str):
        """Mostrar error."""
        def _update():
            self._track_title.set_label(f"Error: {error_msg[:50]}")
            self._track_artist.set_label("")

        if self._engine.is_available:
            GLib.idle_add(_update)
        else:
            _update()

    def _on_engine_tags_changed(self, info: TrackInfo):
        """Actualizar info de pista desde tags."""
        def _update():
            if info.title:
                self._track_title.set_label(info.title)
            if info.artist:
                self._track_artist.set_label(info.artist)

        if self._engine.is_available:
            GLib.idle_add(_update)
        else:
            _update()

    # ── Handlers de la cola ──

    def _on_queue_changed(self):
        """La cola ha cambiado (items agregados/eliminados)."""
        def _update():
            if self._engine.state == PlaybackState.STOPPED and not self._queue.is_empty:
                self._track_title.set_label("Cola lista")
                self._track_artist.set_label(
                    f"{self._queue.count} pistas | {self._queue.mode_label}"
                )

        if self._engine.is_available:
            GLib.idle_add(_update)
        else:
            _update()

    def _on_queue_current_changed(self, item):
        """Pista actual de la cola cambio."""
        pass  # Se actualiza cuando el motor empieza a reproducir

    # ── Utilidades ──

    def _update_volume_icon(self):
        """Actualizar icono del boton de volumen."""
        if self._engine.muted:
            self._btn_mute.set_icon_name("audio-volume-muted-symbolic")
        elif self._engine.volume == 0:
            self._btn_mute.set_icon_name("audio-volume-off-symbolic")
        elif self._engine.volume < 0.33:
            self._btn_mute.set_icon_name("audio-volume-low-symbolic")
        elif self._engine.volume < 0.66:
            self._btn_mute.set_icon_name("audio-volume-medium-symbolic")
        else:
            self._btn_mute.set_icon_name("audio-volume-high-symbolic")

    def _update_sidebar_status(self, state: PlaybackState):
        """Actualizar el indicador de estado en el sidebar."""
        # Buscar el sidebar en la jerarquia de widgets
        try:
            def _find_sidebar(widget):
                if hasattr(widget, 'update_status') and hasattr(widget, '_list_box'):
                    return widget
                parent = widget.get_parent()
                if parent:
                    return _find_sidebar(parent)
                return None

            root = self.get_root()
            if root:
                sidebar = _find_sidebar(root)
                if sidebar:
                    if state == PlaybackState.PLAYING:
                        info = self._engine.track_info
                        title = info.title or Path(info.filepath).stem if info.filepath else "Reproduciendo"
                        sidebar.update_status(f"● {title}", is_live=True)
                    elif state == PlaybackState.PAUSED:
                        sidebar.update_status("● En pausa", is_live=False)
                    else:
                        sidebar.update_status("● Sin reproduccion", is_live=False)
        except Exception:
            pass

    def update_from_external_play(self, title: str = "", artist: str = ""):
        """
        Actualizar la UI cuando se inicia reproduccion desde fuera
        (ej. desde la Parrilla o un Evento).
        """
        if title:
            self._track_title.set_label(title)
        if artist:
            self._track_artist.set_label(artist)
