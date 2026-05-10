"""
Barra de transporte (TransportBar).
Controles de reproduccion, VU meters, e info de pista.
Se ubica en la parte inferior de la ventana, encima de la StatusBar.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Pango

from radio_automator.services.audio_engine import (
    get_audio_engine, PlaybackState, TrackInfo, VUMeterData
)
from radio_automator.services.play_queue import get_play_queue
from radio_automator.services.automation_engine import get_automation_engine, PlaybackSource
from radio_automator.core.event_bus import get_event_bus, Event


# ═══════════════════════════════════════
# Barra de transporte
# ═══════════════════════════════════════

class TransportBar(Gtk.Box):
    """
    Barra de controles de reproduccion.
    Contiene: VU meters | controles (prev/play/next) | info | volumen
    """

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("ra-transport")
        self._engine = get_audio_engine()
        self._queue = get_play_queue()
        self._update_pending = False
        self._show_remaining = False  # Toggle: false=elapsed/total, true=remaining

        self._parrilla_event_name: str | None = None  # Nome do evento de parrilla actual

        self._build_controls()
        self._connect_engine()
        self._connect_queue()
        self._connect_event_bus()

    # ── Construccion de UI ──

    def _build_controls(self):
        """Fila principal: VU | controles | info | volumen."""
        main_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        main_row.set_margin_start(8)
        main_row.set_margin_end(8)
        main_row.set_margin_top(4)
        main_row.set_margin_bottom(2)
        self.append(main_row)

        # ── VU Meters (estilo LED segmentado, apilados verticalmente) ──
        vu_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)

        # Canal Esquerdo (E) - arriba
        vu_left_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        lbl_e = Gtk.Label(label="E")
        lbl_e.add_css_class("ra-label-dim")
        lbl_e.set_valign(Gtk.Align.CENTER)
        lbl_e.set_size_request(10, -1)
        vu_left_box.append(lbl_e)
        self._vu_left = self._create_vu_bar("L")
        vu_left_box.append(self._vu_left)

        # Canal Dereito (D) - abaixo
        vu_right_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        lbl_d = Gtk.Label(label="D")
        lbl_d.add_css_class("ra-label-dim")
        lbl_d.set_valign(Gtk.Align.CENTER)
        lbl_d.set_size_request(10, -1)
        vu_right_box.append(lbl_d)
        self._vu_right = self._create_vu_bar("R")
        vu_right_box.append(self._vu_right)

        vu_box.append(vu_left_box)
        vu_box.append(vu_right_box)

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

        # ── Display de tempo (clicábel: elapsed/total <-> restante) ──
        time_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        time_box.set_valign(Gtk.Align.CENTER)
        time_box.set_margin_start(4)
        time_box.set_margin_end(4)

        self._time_label = Gtk.Label(label="0:00 / 0:00")
        self._time_label.set_xalign(0.5)
        self._time_label.set_name("track-time")
        self._time_label.add_css_class("ra-time-display")
        # Cursor manina para indicar que é clicábel (Gdk en GTK 4.6)
        try:
            from gi.repository import Gdk
            display = Gdk.Display.get_default()
            if display:
                cursor = Gdk.Cursor.new_from_name(display, "pointer")
                self._time_label.set_cursor(cursor)
        except Exception:
            pass  # GTK 4.6 pode non soportar cursor por nome

        # GestureClick para toggle elapsed/remaining
        click_gesture = Gtk.GestureClick()
        click_gesture.set_button(1)
        click_gesture.connect("released", self._on_time_label_clicked)
        self._time_label.add_controller(click_gesture)

        time_box.append(self._time_label)
        main_row.append(time_box)

        # Separador
        sep2b = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        main_row.append(sep2b)

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
        self._volume_scale.set_draw_value(False)
        self._volume_scale.add_css_class("ra-volume-scale")
        self._volume_scale.set_size_request(80, -1)
        self._volume_scale.connect("value-changed", self._on_volume_changed)
        vol_box.append(self._volume_scale)

        main_row.append(vol_box)

    def _create_vu_bar(self, channel: str) -> Gtk.DrawingArea:
        """Crear un indicador de nivel (VU bar) estilo LED segmentado."""
        da = Gtk.DrawingArea()
        da.set_content_width(96)
        da.set_content_height(12)
        da.set_name(f"vu-{channel}")
        da.add_css_class("ra-vu-bar")
        da._level = 0.0          # type: ignore[attr-defined]
        da._peak = 0.0           # type: ignore[attr-defined]
        da._peak_counter = 0     # type: ignore[attr-defined]

        NUM_SEGMENTS = 10
        GAP = 2
        MARGIN = 2

        def _seg_color(seg_index, bright=True):
            """Cor para un segmento segundo a sua posicion."""
            ratio = seg_index / NUM_SEGMENTS
            if ratio < 0.60:
                return (0.1, 0.85, 0.3) if bright else (0.06, 0.16, 0.08)
            elif ratio < 0.85:
                return (1.0, 0.80, 0.0) if bright else (0.18, 0.14, 0.0)
            else:
                return (0.95, 0.15, 0.15) if bright else (0.18, 0.04, 0.04)

        def on_draw(drawing_area, cr, width, height):
            level = drawing_area._level  # type: ignore[attr-defined]
            peak = drawing_area._peak    # type: ignore[attr-defined]

            # Fondo negro
            cr.set_source_rgb(0.06, 0.06, 0.06)
            cr.rectangle(0, 0, width, height)
            cr.fill()

            # Bordo sutil
            cr.set_source_rgb(0.18, 0.18, 0.18)
            cr.set_line_width(1)
            cr.rectangle(0.5, 0.5, width - 1, height - 1)
            cr.stroke()

            # Calcular dimensons dos segmentos cadrados
            avail_w = width - 2 * MARGIN
            avail_h = height - 2 * MARGIN
            seg_size = max(1, (avail_w - (NUM_SEGMENTS - 1) * GAP) / NUM_SEGMENTS)
            # Limitar altura para manter aspecto cadrado
            if seg_size > avail_h:
                seg_size = avail_h
            bar_h = seg_size
            bar_w = seg_size
            # Centrar verticalmente
            bar_y = MARGIN + (avail_h - bar_h) / 2

            # Numero de segmentos iluminados
            lit = int(level * NUM_SEGMENTS)
            lit = max(0, min(lit, NUM_SEGMENTS))

            # Segmento do pico
            peak_seg = int(peak * NUM_SEGMENTS)
            peak_seg = max(0, min(peak_seg, NUM_SEGMENTS - 1))

            # Debuxar todos os segmentos (apagados primeiro)
            for i in range(NUM_SEGMENTS):
                x = MARGIN + i * (bar_w + GAP)
                r, g, b = _seg_color(i, bright=False)
                cr.set_source_rgb(r, g, b)
                cr.rectangle(x, bar_y, bar_w, bar_h)
                cr.fill()

            # Superpoer segmentos iluminados
            for i in range(lit):
                x = MARGIN + i * (bar_w + GAP)
                r, g, b = _seg_color(i, bright=True)
                cr.set_source_rgb(r, g, b)
                cr.rectangle(x, bar_y, bar_w, bar_h)
                cr.fill()

                # Brillo sutil (glow LED)
                cr.set_source_rgba(r, g, b, 0.12)
                cr.rectangle(x - 1, bar_y - 1, bar_w + 2, bar_h + 2)
                cr.fill()

            # Indicador de pico (peak hold)
            if peak > 0.02 and peak_seg >= 0:
                px = MARGIN + peak_seg * (bar_w + GAP)
                ratio = peak_seg / NUM_SEGMENTS
                if ratio < 0.60:
                    pr, pg, pb = 0.4, 1.0, 0.6
                elif ratio < 0.85:
                    pr, pg, pb = 1.0, 0.95, 0.3
                else:
                    pr, pg, pb = 1.0, 0.4, 0.4

                if peak_seg >= lit:
                    cr.set_source_rgb(pr, pg, pb)
                    cr.rectangle(px, bar_y, bar_w, bar_h)
                    cr.fill()
                    cr.set_source_rgba(pr, pg, pb, 0.2)
                    cr.rectangle(px - 1, bar_y - 1, bar_w + 2, bar_h + 2)
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

    def _connect_event_bus(self):
        """Conectar a eventos do AutomationEngine via EventBus."""
        bus = get_event_bus()
        bus.subscribe("automation.update_title", self._on_automation_update_title)
        bus.subscribe("automation.source_changed", self._on_automation_source_changed)
        bus.subscribe("automation.event_ended", self._on_automation_event_ended)

    def _on_automation_update_title(self, event: Event):
        """Actualizar o display cando a automatizacion inicia un evento."""
        def _update():
            title = event.data.get("title", "")
            artist = event.data.get("artist", "")
            if title:
                self._parrilla_event_name = title
                self._track_title.set_label(title)
                self._track_artist.set_label(artist)

        if self._engine.is_available:
            GLib.idle_add(_update)
        else:
            _update()

    def _on_automation_source_changed(self, event: Event):
        """Limpar o nome do evento cando a fonte cambia a non-Parrilla."""
        new_source = event.data.get("new_source", "")
        if new_source != PlaybackSource.PARRILLA.value:
            def _update():
                self._parrilla_event_name = None
            if self._engine.is_available:
                GLib.idle_add(_update)
            else:
                _update()

    def _on_automation_event_ended(self, event: Event):
        """Limpar o nome do evento cando remata un evento de parrilla."""
        def _update():
            self._parrilla_event_name = None
        if self._engine.is_available:
            GLib.idle_add(_update)
        else:
            _update()

    # ── Handlers de controles ──

    def _on_play_pause(self, _btn=None):
        engine = self._engine
        queue = self._queue

        if engine.state == PlaybackState.PLAYING:
            engine.pause()
        elif engine.state == PlaybackState.PAUSED:
            engine.resume()
        else:
            # Non hai reproducion: intentar a cola primeiro
            if not queue.is_empty and queue.current_item is None:
                queue.play_next()

            item = queue.current_item
            if item:
                # Hai pistas na cola, reproducir
                if item.is_streaming:
                    engine.play_stream(item.filepath)
                else:
                    engine.play_file(item.filepath)
            else:
                # Cola baleira: iniciar automatizacion (Parrilla -> Continuidad)
                automation = get_automation_engine()
                if not automation.is_active:
                    automation.start()
                else:
                    # Xa esta activa, forzar tick inmediato
                    automation.tick()

    def _on_prev(self, _btn=None):
        """Ir ao comezo da pista actual."""
        if self._engine.state == PlaybackState.PLAYING:
            self._engine.seek(0)

    def _on_next(self, _btn=None):
        """Avanzar: saltar o que esta a soar e reproducir Continuidad.

        - Se esta en Continuidad: saltar a seguinte pista inmediatamente.
        - Se esta nun evento de Parrilla: parar evento e pasar a Continuidad.
        - Se a automatizacion non esta activa: activala (Continuidad).
        """
        automation = get_automation_engine()

        if automation.is_active:
            if automation.source == PlaybackSource.CONTINUIDAD:
                # Saltar a seguinte pista de Continuidad inmediatamente.
                # on_track_finished() avanza a cola e reproduce a seguinte
                # (crea pipeline novo, cortando a pista actual).
                automation.on_track_finished(self._engine.track_info)

            elif automation.source == PlaybackSource.PARRILLA:
                # Parrilla: parar evento e cambiar a Continuidad directamente
                automation._stop_playback()
                automation._current_event_id = None
                automation._start_continuidad()

            else:
                # Outro estado (NONE etc): forzar tick
                automation.tick()
        else:
            # Automatizacion non activa: activala (reproducira Continuidad)
            automation.start()

    def _on_stop(self, _btn=None):
        self._engine.stop()

    def _on_mute(self, _btn=None):
        self._engine.toggle_mute()
        self._update_volume_icon()

    def _on_volume_changed(self, scale):
        self._engine.set_volume(scale.get_value())
        self._update_volume_icon()

    # ── Handlers de eventos del motor ──

    def _on_engine_state_changed(self, state: PlaybackState):
        """Actualizar UI cuando cambia el estado del motor."""
        def _update():
            if state == PlaybackState.PLAYING:
                self._btn_play.set_icon_name("media-playback-pause-symbolic")
                self._btn_play.set_tooltip_text("Pausar")
            elif state == PlaybackState.PAUSED:
                self._btn_play.set_icon_name("media-playback-start-symbolic")
                self._btn_play.set_tooltip_text("Reanudar")
            else:
                self._btn_play.set_icon_name("media-playback-start-symbolic")
                self._btn_play.set_tooltip_text("Reproducir")
                # Resetear display de tempo ao parar
                self._time_label.set_label("0:00 / 0:00")

            # Actualizar sidebar status
            self._update_sidebar_status(state)

        if self._engine.is_available:
            GLib.idle_add(_update)
        else:
            _update()

    def _on_engine_position_changed(self, info: TrackInfo):
        """Actualizar posicion e display de tempo."""
        def _update():
            self._update_time_display(info)

        if self._engine.is_available:
            GLib.idle_add(_update)
        else:
            _update()

    def _on_engine_track_finished(self, info: TrackInfo):
        """Pista terminada, avanzar en la cola ou delegar a automatizacao."""
        try:
            automation = get_automation_engine()

            if automation.is_active and automation.source in (
                PlaybackSource.PARRILLA,
                PlaybackSource.CONTINUIDAD,
                PlaybackSource.TIME_ANNOUNCE,
            ):
                automation.on_track_finished(info)
                return

            # Se a automatizacion esta activa pero en NONE
            # (p.e. despois de pulsar Next desde parrilla),
            # forzar tick inmediato para iniciar Continuidad sen silencio
            if automation.is_active and automation.source == PlaybackSource.NONE:
                automation.tick()
                return

        except Exception:
            pass

        # Reproduccion manual: avanzar na cola
        self._queue.on_track_finished(info)

    def _on_engine_vu_changed(self, vu: VUMeterData):
        """Actualizar indicadores VU con peak hold."""
        def _update():
            for bar, level, peak in [
                (self._vu_left, vu.level_left, vu.peak_left),
                (self._vu_right, vu.level_right, vu.peak_right),
            ]:
                bar._level = level                     # type: ignore[attr-defined]
                # Peak hold: manter o pico e decaer
                if level > bar._peak:                   # type: ignore[attr-defined]
                    bar._peak = level                    # type: ignore[attr-defined]
                    bar._peak_counter = 0                # type: ignore[attr-defined]
                else:
                    bar._peak_counter += 1               # type: ignore[attr-defined]
                    if bar._peak_counter >= 15:          # ~0.9s hold (60ms interval)
                        bar._peak = max(                 # type: ignore[attr-defined]
                            bar._peak - 0.035, level     # type: ignore[attr-defined]
                        )
                        bar._peak_counter = 8            # type: ignore[attr-defined]
                bar.queue_draw()

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
        """Actualizar info de pista desde tags.

        Se estamos en Parrilla (evento), o titulo mostra o nome do evento
        e o subtitulo mostra o nome do audio (dos tags).
        Se estamos en Continuidad ou manual, mostra os tags normalmente.
        """
        def _update():
            if self._parrilla_event_name:
                # En Parrilla: titulo = evento, subtitulo = info do audio
                artist_text = info.title or ""
                if info.artist:
                    if artist_text:
                        artist_text = f"{info.artist} - {artist_text}"
                    else:
                        artist_text = info.artist
                # Non cambiar _track_title (mantemos o nome do evento)
                self._track_artist.set_label(artist_text)
            else:
                # Continuidad ou manual: mostrar tags normalmente
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

    # ── Display de tempo ──

    def _update_time_display(self, info: TrackInfo):
        """Actualizar o label de tempo segundo o modo actual (elapsed/total ou restante)."""
        if info.is_streaming or info.duration_ms <= 0:
            # Streaming ou duracion descoñecida: so mostrar elapsed
            self._time_label.set_label(f"{info.position_str} / --:--")
            return

        if self._show_remaining:
            remaining_ms = max(0, info.duration_ms - info.position_ms)
            remaining_str = TrackInfo._format_ms(remaining_ms)
            self._time_label.set_label(f"-{remaining_str}")
        else:
            self._time_label.set_label(f"{info.position_str} / {info.duration_str}")

    def _on_time_label_clicked(self, gesture, n_press, x, y):
        """Toggle entre modo elapsed/total e modo restante."""
        self._show_remaining = not self._show_remaining
        # Actualizar inmediatamente coa info actual
        info = self._engine.track_info
        if info:
            self._update_time_display(info)

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
