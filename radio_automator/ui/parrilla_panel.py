"""
Panel de la Parrilla Semanal.
Vista tipo calendario semanal con bloques de eventos posicionados por hora y dia.
Soporta: navegacion por semanas, indicador de hora actual, highlight de evento activo,
deteccion de conflictos, y edicion rapida de eventos.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
from datetime import datetime, date, timedelta

from radio_automator.ui.layout import PanelContainer
from radio_automator.services.parrilla_service import (
    ParrillaService, get_parrilla_service,
    GridEvent, ConflictInfo, NowPlayingInfo,
    DAY_NAMES_SHORT, HOUR_START, HOUR_END,
    format_time_range,
)

from radio_automator.core.database import get_session, RadioEvent


# ═══════════════════════════════════════
# Bloque de evento en el grid
# ═══════════════════════════════════════

class EventBlock:
    """Datos de un evento para o grid semanal (sen widget visual)."""

    def __init__(self, grid_event: GridEvent, on_click=None, on_edit=None):
        self._ge = grid_event
        self._on_edit = on_edit


# ═══════════════════════════════════════
# Columna de dia del grid (DrawingArea puro - compatible GTK 4.6)
# ═══════════════════════════════════════

class DayColumn(Gtk.DrawingArea):
    """Columna vertical dun dia: debuxa o grid horario e os bloques de eventos."""

    def __init__(self, day_index: int, events: list[GridEvent],
                 on_edit_event=None):
        super().__init__()
        self._day_index = day_index
        self._events = sorted(events, key=lambda e: e.start_minutes)
        self._on_edit_event = on_edit_event
        self._event_rects = []  # [(GridEvent, x, y, w, h), ...]

        self.set_vexpand(True)
        self.set_hexpand(True)
        self.set_content_width(120)

        self.set_draw_func(self._on_draw)

        # Click para editar evento
        click = Gtk.GestureClick()
        click.connect("released", self._on_released)
        self.add_controller(click)

    def _on_released(self, gesture, n_press, x, y):
        """Detectar que evento se pulsou e editar."""
        for ge, ex, ey, ew, eh in self._event_rects:
            if ex <= x <= ex + ew and ey <= y <= ey + eh:
                if self._on_edit_event:
                    self._on_edit_event(ge)
                return

    def _on_draw(self, drawing_area, cr, width, height):
        """Debuxar o grid horario e os bloques de eventos."""
        self._event_rects = []

        # Fondo
        cr.set_source_rgb(0.16, 0.16, 0.16)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        # Lineas horarias completas
        cr.set_source_rgb(0.25, 0.25, 0.25)
        cr.set_line_width(0.5)
        for h in range(HOUR_START, HOUR_END + 1):
            y = (h / 24.0) * height
            cr.move_to(0, y)
            cr.line_to(width, y)
            cr.stroke()

        # Lineas de media hora
        cr.set_source_rgb(0.22, 0.22, 0.22)
        cr.set_line_width(0.3)
        for h in range(HOUR_START, HOUR_END):
            y = ((h + 0.5) / 24.0) * height
            cr.move_to(0, y)
            cr.line_to(width, y)
            cr.stroke()

        # Separador dereito entre columnas
        cr.set_source_rgb(0.20, 0.20, 0.20)
        cr.set_line_width(1.0)
        cr.move_to(width - 0.5, 0)
        cr.line_to(width - 0.5, height)
        cr.stroke()

        # Debuxar bloques de eventos
        margin = 2
        for ge in self._events:
            top_px = (ge.start_minutes / (24 * 60)) * height
            h_px = max((ge.duration_minutes / (24 * 60)) * height, 20)

            x = margin
            y = top_px
            w = width - margin * 2
            h = h_px

            # Gardar rect para deteccion de click
            self._event_rects.append((ge, x, y, w, h))

            # Cor e bordo
            if ge.is_now_playing:
                bg_r, bg_g, bg_b = 0.898, 0.224, 0.208
                br, bg_, bb = 0.775, 0.157, 0.157
                border_w = 2
            elif ge.has_conflict:
                bg_r, bg_g, bg_b = 0.985, 0.549, 0.0
                br, bg_, bb = 0.985, 0.549, 0.0
                border_w = 2
            elif ge.is_streaming:
                bg_r, bg_g, bg_b = 0.25, 0.30, 0.45
                br, bg_, bb = 0.40, 0.45, 0.60
                border_w = 1
            elif ge.is_past:
                bg_r, bg_g, bg_b = 0.15, 0.20, 0.30
                br, bg_, bb = 0.25, 0.30, 0.40
                border_w = 1
            else:
                bg_r, bg_g, bg_b = 0.20, 0.28, 0.45
                br, bg_, bb = 0.35, 0.43, 0.60
                border_w = 1

            # Fondo con bordes redondeados
            cr.set_source_rgba(bg_r, bg_g, bg_b, 0.85)
            self._rounded_rect(cr, x, y, w, h, 4)
            cr.fill()

            # Bordo
            cr.set_source_rgb(br, bg_, bb)
            cr.set_line_width(border_w)
            self._rounded_rect(cr, x, y, w, h, 4)
            cr.stroke()

            # Texto do evento (se hai espazo suficiente)
            if h > 18:
                text_x = x + 6
                text_y = y + 14

                # Nome
                cr.set_source_rgb(1.0, 1.0, 1.0)
                cr.select_font_face("sans-serif", 0, 1)
                cr.set_font_size(9)
                name = ge.name or ""
                if len(name) > 25:
                    name = name[:22] + "..."
                cr.move_to(text_x, text_y)
                cr.show_text(name)

                # Hora
                if h > 35:
                    cr.set_source_rgb(0.7, 0.7, 0.7)
                    cr.select_font_face("sans-serif", 0, 0)
                    cr.set_font_size(8)
                    time_str = format_time_range(ge.start_time, ge.end_time)
                    cr.move_to(text_x, text_y + 13)
                    cr.show_text(time_str)

                # EN VIVO
                if ge.is_now_playing and h > 25:
                    cr.set_source_rgb(1.0, 0.3, 0.3)
                    cr.select_font_face("sans-serif", 0, 1)
                    cr.set_font_size(8)
                    offset = 25 if h > 35 else 13
                    cr.move_to(text_x, text_y + offset)
                    cr.show_text("EN VIVO")

    def _rounded_rect(self, cr, x, y, w, h, r):
        """Debuxar un rectangulo con bordes redondeados."""
        cr.move_to(x + r, y)
        cr.line_to(x + w - r, y)
        cr.arc(x + w - r, y + r, r, -1.5708, 0)
        cr.line_to(x + w, y + h - r)
        cr.arc(x + w - r, y + h - r, r, 0, 1.5708)
        cr.line_to(x + r, y + h)
        cr.arc(x + r, y + h - r, r, 1.5708, 3.1416)
        cr.line_to(x, y + r)
        cr.arc(x + r, y + r, r, 3.1416, 4.7124)
        cr.close_path()


# ═══════════════════════════════════════
# Panel principal de la Parrilla
# ═══════════════════════════════════════

class ParrillaPanel(PanelContainer):
    """Panel de la parrilla semanal (interfaz tipo Google Calendar)."""

    def __init__(self):
        super().__init__(
            title="Parrilla Semanal",
            subtitle="Programacion semanal de la emisora",
            show_add=True,
        )

        self._service = get_parrilla_service()
        self._week_offset = 0
        self._show_today_only = False
        self._refresh_timer = None

        # Boton de nuevo evento
        if self.add_button:
            self.add_button.set_sensitive(True)
            self.add_button.set_tooltip_text("Crear nuevo evento programado")
            self.add_button.connect("clicked", self._on_create_event)

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        """Construir la interfaz del panel."""
        # Toolbar: navegacion de semanas
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_margin_bottom(12)

        # Boton semana anterior
        prev_btn = Gtk.Button(label="←")
        prev_btn.add_css_class("ra-button")
        prev_btn.add_css_class("ra-button-icon")
        prev_btn.set_tooltip_text("Semana anterior")
        prev_btn.connect("clicked", lambda b: self._change_week(-1))
        toolbar.append(prev_btn)

        # Label semana actual
        self._week_label = Gtk.Label()
        self._week_label.add_css_class("ra-heading")
        self._week_label.set_halign(Gtk.Align.CENTER)
        toolbar.append(self._week_label)

        # Boton semana siguiente
        next_btn = Gtk.Button(label="→")
        next_btn.add_css_class("ra-button")
        next_btn.add_css_class("ra-button-icon")
        next_btn.set_tooltip_text("Semana siguiente")
        next_btn.connect("clicked", lambda b: self._change_week(1))
        toolbar.append(next_btn)

        # Boton hoy
        today_btn = Gtk.Button(label="Hoy")
        today_btn.add_css_class("ra-button")
        today_btn.add_css_class("ra-button-sm")
        today_btn.connect("clicked", self._go_today)
        toolbar.append(today_btn)

        # Spacer
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        toolbar.append(spacer)

        self.content.append(toolbar)

        # Info de conflictos
        self._conflict_label = Gtk.Label()
        self._conflict_label.set_margin_bottom(8)
        self._conflict_label.set_xalign(0)
        self.content.append(self._conflict_label)

        # Contenedor con scroll para todo el grid
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.set_min_content_height(500)
        self.content.append(scroll)

        # Grid wrapper
        self._grid_wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._grid_wrapper.set_hexpand(True)
        self._grid_wrapper.set_vexpand(True)
        scroll.set_child(self._grid_wrapper)

    def refresh(self):
        """Recargar la parrilla completa."""
        # Calcular week_start a partir do offset (luns da semana correspondente)
        today = date.today()
        week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=self._week_offset)
        week_data = self._service.get_events_for_week(week_start=week_start)

        self._week_data = week_data

        # Actualizar label de semana
        ws = week_data.week_start
        we = ws + timedelta(days=6)
        self._week_label.set_label(
            f"{ws.day} {ws.strftime('%b')} - {we.day} {we.strftime('%b')} {we.year}"
        )

        # Info de conflictos
        if week_data.conflicts:
            n = len(week_data.conflicts)
            self._conflict_label.set_label(f"⚠ {n} conflicto(s) detectado(s)")
            self._conflict_label.add_css_class("ra-label-warning")
            self._conflict_label.remove_css_class("ra-label-dim")
            self._conflict_label.remove_css_class("ra-label-success")
        else:
            self._conflict_label.set_label(
                f"✓ {week_data.total_events} evento(s), sin conflictos"
            )
            self._conflict_label.add_css_class("ra-label-success")
            self._conflict_label.remove_css_class("ra-label-dim")
            self._conflict_label.remove_css_class("ra-label-warning")

        # Limpiar grid anterior
        while self._grid_wrapper.get_first_child():
            self._grid_wrapper.remove(self._grid_wrapper.get_first_child())

        # Crear header de dias + horas
        self._build_grid_header()

        # Crear grid con columnas de dia
        self._build_grid_columns(week_data)

        # Now playing info en toolbar o status
        if week_data.now_playing and week_data.now_playing.is_active:
            np = week_data.now_playing
            ev = np.event
            if ev:
                info = f"● EN VIVO: {ev.name}"
                if np.time_until_next:
                    mins = int(np.time_until_next.total_seconds() / 60)
                    info += f"  (siguiente en {mins} min)"
                self._status_label = info
        else:
            self._status_label = "Sin eventos activos"

        # Publicar evento
        try:
            from radio_automator.core.event_bus import get_event_bus
            get_event_bus().publish("parrilla.refreshed", {
                "events": week_data.total_events,
                "conflicts": len(week_data.conflicts),
            })
        except Exception:
            pass

    def _build_grid_header(self):
        """Crear la fila de cabecera con nombres de dias."""
        if self._show_today_only:
            return

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        header.set_size_request(-1, 30)

        # Columna de horas (espazo para alinear coa columna de labels)
        hour_col = Gtk.Box()
        hour_col.set_size_request(54, -1)
        header.append(hour_col)

        # Nombres de dias
        today_idx = datetime.now().weekday()
        for i in range(7):
            day_box = Gtk.Box()
            day_box.set_hexpand(True)
            day_box.set_homogeneous(True)

            label = Gtk.Label(label=DAY_NAMES_SHORT[i])
            label.set_xalign(0.5)

            if i == today_idx:
                label.add_css_class("ra-label-accent")

            day_box.append(label)
            header.append(day_box)

        self._grid_wrapper.append(header)

        # Separador
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self._grid_wrapper.append(sep)

    def _build_grid_columns(self, week_data):
        """Crear las columnas de dia con los bloques de eventos."""
        # Grid principal: hora labels + columnas
        grid = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        grid.set_vexpand(True)
        grid.set_hexpand(True)

        # Columna de horas
        hour_column = self._create_hour_labels()
        grid.append(hour_column)

        if self._show_today_only:
            # Modo HOY: mostrar solo a columna de hoxe
            today_idx = datetime.now().weekday()
            col = DayColumn(
                day_index=today_idx,
                events=week_data.days[today_idx],
                on_edit_event=self._on_edit_event,
            )
            col.set_hexpand(True)
            grid.append(col)
        else:
            # Modo semanal: 7 columnas
            for day_idx in range(7):
                col = DayColumn(
                    day_index=day_idx,
                    events=week_data.days[day_idx],
                    on_edit_event=self._on_edit_event,
                )
                col.set_hexpand(True)
                grid.append(col)

        self._grid_wrapper.append(grid)

    def _create_hour_labels(self) -> Gtk.Box:
        """Crear la columna con etiquetas de hora."""
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        col.set_size_request(54, -1)

        da = Gtk.DrawingArea()
        da.set_vexpand(True)

        def on_draw(drawing_area, cr, width, height):
            cr.set_source_rgb(0.43, 0.43, 0.43)  # #707070
            cr.select_font_face("sans-serif", 0, 0)
            cr.set_font_size(8)

            for h in range(HOUR_START, HOUR_END):
                y = (h / 24.0) * height
                text = f"{h:02d}:00"
                # text_extents retorna (x_bearing, y_bearing, width, height, x_advance, y_advance)
                extents = cr.text_extents(text)
                text_h = extents[3]  # height real do texto
                cr.move_to(4, y + text_h + 2)
                cr.show_text(text)

        da.set_draw_func(on_draw)
        col.append(da)
        return col

    # ── Navegacion ──

    def _go_today(self, _btn=None):
        """Volver a la semana actual y mostrar solo hoy."""
        self._week_offset = 0
        self._show_today_only = True
        self.refresh()

    def _change_week(self, delta: int):
        """Cambiar a la semana anterior o siguiente."""
        self._week_offset += delta
        self._show_today_only = False
        self.refresh()

    # ── Acciones ──

    def _on_create_event(self, _btn):
        """Crear un novo evento directamente."""
        self._show_event_dialog(edit_event=None)

    def _on_edit_event(self, grid_event: GridEvent):
        """Editar un evento del grid."""
        session = get_session()
        try:
            event = session.get(RadioEvent, grid_event.event_id)
            if event:
                self._show_event_dialog(edit_event=event, grid_event=grid_event)
        finally:
            session.close()

    def _show_event_dialog(self, edit_event=None, grid_event=None):
        """Dialogo para crear ou editar un evento."""
        is_edit = edit_event is not None
        title = f"Editar: {edit_event.name}" if is_edit else "Nuevo Evento"

        dialog = Gtk.Window()
        dialog.set_title(title)
        dialog.set_transient_for(self.get_root() if self.get_root() else None)
        dialog.set_modal(True)
        dialog.set_resizable(True)
        dialog.set_default_size(520, -1)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(400)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(16)
        box.set_margin_end(16)

        # Nombre
        name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        Gtk.Label(label="Nombre:").set_width_chars(14)
        name_label = Gtk.Label(label="Nombre:")
        name_label.set_width_chars(14)
        name_label.set_xalign(0)
        name_box.append(name_label)
        name_entry = Gtk.Entry()
        name_entry.set_text(edit_event.name if is_edit else "")
        name_entry.set_placeholder_text("Nombre del evento")
        name_entry.add_css_class("ra-entry")
        name_entry.set_hexpand(True)
        name_box.append(name_entry)
        box.append(name_box)

        # Hora inicio / fin
        time_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        start_label = Gtk.Label(label="Hora inicio:")
        start_label.set_width_chars(14)
        start_label.set_xalign(0)
        time_box.append(start_label)
        start_entry = Gtk.Entry()
        start_entry.set_text(edit_event.start_time if is_edit else "")
        start_entry.set_placeholder_text("HH:MM")
        start_entry.add_css_class("ra-entry")
        start_entry.set_max_width_chars(6)
        time_box.append(start_entry)
        end_label = Gtk.Label(label="Hora fin:")
        end_label.set_width_chars(10)
        end_label.set_xalign(0)
        time_box.append(end_label)
        end_entry = Gtk.Entry()
        end_entry.set_text(edit_event.end_time if is_edit and edit_event.end_time else "")
        end_entry.set_placeholder_text("Opcional")
        end_entry.add_css_class("ra-entry")
        end_entry.set_max_width_chars(6)
        time_box.append(end_entry)
        box.append(time_box)

        # Streaming URL
        stream_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        stream_label = Gtk.Label(label="Streaming URL:")
        stream_label.set_width_chars(14)
        stream_label.set_xalign(0)
        stream_box.append(stream_label)
        stream_entry = Gtk.Entry()
        stream_entry.set_text(edit_event.streaming_url if is_edit and edit_event.streaming_url else "")
        stream_entry.set_placeholder_text("URL del streaming (opcional)")
        stream_entry.add_css_class("ra-entry")
        stream_entry.set_hexpand(True)
        stream_box.append(stream_entry)
        box.append(stream_box)

        # Playlist
        from radio_automator.services.playlist_service import PlaylistService
        playlists = PlaylistService().get_all()
        playlist_names = ["(Ninguna)"] + [p.name for p in playlists]
        pl_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        pl_label = Gtk.Label(label="Playlist:")
        pl_label.set_width_chars(14)
        pl_label.set_xalign(0)
        pl_box.append(pl_label)
        playlist_combo = Gtk.DropDown.new_from_strings(playlist_names)
        playlist_combo.add_css_class("ra-combo")
        playlist_combo.set_hexpand(True)
        if is_edit and edit_event.playlist_id:
            for idx, p in enumerate(playlists):
                if p.id == edit_event.playlist_id:
                    playlist_combo.set_selected(idx + 1)
                    break
        pl_box.append(playlist_combo)
        box.append(pl_box)

        # Dias de la semana
        days_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        days_label = Gtk.Label(label="Dias:")
        days_label.set_width_chars(14)
        days_label.set_xalign(0)
        days_box.append(days_label)
        days_data = {}
        days_names = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]
        existing_days = edit_event.week_days_list if is_edit else [True] * 7
        for i, day_name in enumerate(days_names):
            day_btn = Gtk.ToggleButton(label=day_name)
            day_btn.set_active(existing_days[i])
            day_btn.add_css_class("ra-button")
            day_btn.add_css_class("ra-button-sm")
            days_data[i] = day_btn
            days_box.append(day_btn)
        box.append(days_box)

        # Patron de repeticion
        repeat_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        repeat_label = Gtk.Label(label="Repetir:")
        repeat_label.set_width_chars(14)
        repeat_label.set_xalign(0)
        repeat_box.append(repeat_label)
        repeat_combo = Gtk.DropDown.new_from_strings(["Semanal", "Diario", "Una vez", "Dias seleccionados"])
        repeat_combo.add_css_class("ra-combo")
        if is_edit:
            pattern_map = {"weekly": 0, "daily": 1, "once": 2, "selected_days": 3}
            idx = pattern_map.get(edit_event.repeat_pattern, 0)
            repeat_combo.set_selected(idx)
        repeat_box.append(repeat_combo)
        box.append(repeat_box)

        scroll.set_child(box)
        main_box.append(scroll)

        # Botóns
        btn_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_bar.set_margin_top(8)
        btn_bar.set_margin_bottom(8)
        btn_bar.set_margin_start(16)
        btn_bar.set_margin_end(16)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        btn_bar.append(spacer)
        cancel_btn = Gtk.Button(label="Cancelar")
        cancel_btn.add_css_class("ra-button")
        btn_bar.append(cancel_btn)
        save_btn = Gtk.Button(label="Guardar")
        save_btn.add_css_class("ra-button-primary")
        save_btn.add_css_class("ra-button")
        btn_bar.append(save_btn)
        main_box.append(btn_bar)

        dialog.set_child(main_box)
        name_entry.grab_focus()

        def do_save():
            name = name_entry.get_text().strip()
            start_time = start_entry.get_text().strip()
            end_time = end_entry.get_text().strip()
            streaming_url = stream_entry.get_text().strip()

            if not name:
                return
            if not start_time or len(start_time) != 5 or start_time[2] != ':':
                return
            if streaming_url and not end_time:
                return
            if end_time and (len(end_time) != 5 or end_time[2] != ':'):
                return

            pl_idx = playlist_combo.get_selected()
            playlist_id = playlists[pl_idx - 1].id if pl_idx > 0 and pl_idx - 1 < len(playlists) else None

            week_days = ",".join("1" if days_data[i].get_active() else "0" for i in range(7))
            pattern_map = {0: "weekly", 1: "daily", 2: "once", 3: "selected_days"}
            repeat_pattern = pattern_map.get(repeat_combo.get_selected(), "weekly")

            session = get_session()
            try:
                if is_edit:
                    # O obxecto edit_event foi cargado nunha sesion anterior
                    # e quedou detached. Usamos merge() para re-adscribilo
                    # a esta sesion antes de modificalo.
                    merged_event = session.merge(edit_event)
                    merged_event.name = name
                    merged_event.start_time = start_time
                    merged_event.end_time = end_time or None
                    merged_event.streaming_url = streaming_url or None
                    merged_event.playlist_id = playlist_id
                    merged_event.week_days = week_days
                    merged_event.repeat_pattern = repeat_pattern
                else:
                    new_event = RadioEvent(
                        name=name, start_time=start_time,
                        end_time=end_time or None,
                        streaming_url=streaming_url or None,
                        playlist_id=playlist_id,
                        week_days=week_days,
                        repeat_pattern=repeat_pattern,
                    )
                    session.add(new_event)
                session.commit()
                self.refresh()
            except Exception as e:
                session.rollback()
                print(f"[Parrilla] Error al guardar evento: {e}")
            finally:
                session.close()
            dialog.destroy()

        cancel_btn.connect("clicked", lambda b: dialog.destroy())
        save_btn.connect("clicked", lambda b: do_save())
        dialog.show()


