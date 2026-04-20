"""
Panel de la Parrilla Semanal.
Vista tipo calendario semanal con bloques de eventos posicionados por hora y dia.
Soporta: navegacion por semanas, indicador de hora actual, highlight de evento activo,
deteccion de conflictos, y edicion rapida de eventos.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Pango
from datetime import date, datetime, timedelta

from radio_automator.ui.layout import PanelContainer
from radio_automator.services.parrilla_service import (
    ParrillaService, get_parrilla_service,
    GridEvent, ConflictInfo, NowPlayingInfo,
    DAY_NAMES_SHORT, HOUR_START, HOUR_END,
)
from radio_automator.services.automation_engine import (
    get_automation_engine, PlaybackSource, AutomationStatus
)
from radio_automator.core.database import get_session, RadioEvent


# ═══════════════════════════════════════
# Bloque de evento en el grid
# ═══════════════════════════════════════

class EventBlock(Gtk.Box):
    """Bloque visual de un evento en el grid semanal."""

    def __init__(self, grid_event: GridEvent, on_click=None, on_edit=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._ge = grid_event
        self._on_click = on_click
        self._on_edit = on_edit

        self.set_margin_start(2)
        self.set_margin_end(2)
        self.set_margin_top(1)
        self.set_margin_bottom(1)

        # Estilo segun tipo
        if grid_event.is_now_playing:
            bg = "rgba(229, 57, 53, 0.3)"
            border_color = "#E53935"
            border_width = 2
        elif grid_event.has_conflict:
            bg = "rgba(251, 140, 0, 0.2)"
            border_color = "#FB8C00"
            border_width = 2
        elif grid_event.is_streaming:
            bg = "rgba(251, 140, 0, 0.15)"
            border_color = "rgba(251, 140, 0, 0.5)"
            border_width = 1
        elif grid_event.is_past:
            bg = "rgba(30, 136, 229, 0.08)"
            border_color = "rgba(30, 136, 229, 0.2)"
            border_width = 1
        else:
            bg = "rgba(30, 136, 229, 0.15)"
            border_color = "rgba(30, 136, 229, 0.4)"
            border_width = 1

        self.set_size_request(-1, max(28, grid_event.duration_minutes * 1.5))

        # Nombre del evento
        name_label = Gtk.Label(label=grid_event.name)
        name_label.set_xalign(0)
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        name_label.add_css_class("ra-label")

        # Wrap en label con margen
        name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        name_box.set_margin_start(4)
        name_box.set_margin_top(2)
        name_box.append(name_label)

        self.append(name_box)

        # Hora (solo si hay espacio suficiente)
        if grid_event.duration_minutes >= 45:
            time_str = ParrillaService.format_time_range(grid_event.start_time, grid_event.end_time)
            time_label = Gtk.Label(label=time_str)
            time_label.set_xalign(0)
            time_label.set_ellipsize(Pango.EllipsizeMode.END)
            time_label.set_margin_start(4)
            time_label.add_css_class("ra-label-dim")
            self.append(time_label)

        # Badge tipo (solo si hay espacio)
        if grid_event.duration_minutes >= 60:
            type_text = "📡 Stream" if grid_event.is_streaming else "🎵"
            type_label = Gtk.Label(label=type_text)
            type_label.set_xalign(0)
            type_label.set_margin_start(4)
            type_label.set_margin_bottom(2)
            type_label.add_css_class("ra-label-dim")
            self.append(type_label)

        # Indicador NOW
        if grid_event.is_now_playing:
            now_label = Gtk.Label(label="● EN VIVO")
            now_label.set_xalign(0)
            now_label.set_margin_start(4)
            now_label.set_margin_bottom(2)
            now_label.add_css_class("ra-label-accent")
            self.append(now_label)

        # Aplicar estilo visual
        self._apply_style(bg, border_color, border_width)

        # Click
        click = Gtk.GestureClick()
        click.connect("released", self._on_released)
        self.add_controller(click)

    def _apply_style(self, bg: str, border_color: str, border_width: int):
        """Aplicar estilo al bloque usando CSS provider inline."""
        css = f"""
        .event-block-{id(self)} {{
            background-color: {bg};
            border: {border_width}px solid {border_color};
            border-radius: 4px;
            padding: 2px;
            
        }}
        .event-block-{id(self)}:hover {{
            background-color: rgba(255, 255, 255, 0.1);
        }}
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode('utf-8'))
        self.add_css_class(f"event-block-{id(self)}")

        style_context = self.get_style_context()
        style_context.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

    def _on_released(self, gesture, n_press, x, y):
        if self._on_edit:
            self._on_edit(self._ge)


# ═══════════════════════════════════════
# Columna de dia del grid
# ═══════════════════════════════════════

class PositionedFixed(Gtk.Fixed):
    """Gtk.Fixed con reposicionamento automatico (GTK 4.6+)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._blocks = []
        self._last_size = None

    def add_event_block(self, block, grid_event):
        self.put(block, 0, 0)
        self._blocks.append((block, grid_event))

    def do_size_allocate(self, allocation):
        w = allocation.width
        h = allocation.height
        super().do_size_allocate(allocation)
        if h <= 1 or w <= 1:
            return
        if self._last_size == (w, h):
            return
        self._last_size = (w, h)
        first = self.get_first_child()
        if first:
            first.set_size_request(w, h)
        for block, ge in self._blocks:
            y = int((ge.start_minutes / (24 * 60)) * h)
            bh = max(28, int((ge.duration_minutes / (24 * 60)) * h))
            block.set_size_request(w - 4, bh)
            self.move(block, 2, y)


class DayColumn(Gtk.Box):
    """Columna vertical para un dia de la semana."""

    def __init__(self, day_index: int, events: list[GridEvent],
                 on_edit_event=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self._day_index = day_index
        self._events = events
        self._on_edit_event = on_edit_event

        self._fixed = PositionedFixed()
        self._fixed.set_vexpand(True)
        self._fixed.set_hexpand(True)
        self._fixed.set_overflow(Gtk.Overflow.VISIBLE)
        self.append(self._fixed)

        grid_widget = self._create_hour_grid()
        self._fixed.put(grid_widget, 0, 0)

        for ge in sorted(events, key=lambda e: e.start_minutes):
            block = EventBlock(ge, on_edit=on_edit_event)
            self._fixed.add_event_block(block, ge)

    def _create_hour_grid(self) -> Gtk.DrawingArea:
        """Crear el grid de fondo con lineas horarias."""
        da = Gtk.DrawingArea()
        da.set_content_width(120)
        da.set_vexpand(True)
        da.set_hexpand(True)
        da.set_name(f"day-grid-{self._day_index}")

        def on_draw(drawing_area, cr, width, height):
            # Fondo
            cr.set_source_rgb(0.16, 0.16, 0.16)  # #1A1A1A
            cr.rectangle(0, 0, width, height)
            cr.fill()

            # Lineas horarias (cada hora)
            cr.set_source_rgb(0.25, 0.25, 0.25)  # #404040
            cr.set_line_width(0.5)

            for h in range(HOUR_START, HOUR_END + 1):
                y = (h / 24.0) * height
                cr.move_to(0, y)
                cr.line_to(width, y)
                cr.stroke()

            # Lineas de media hora (mas tenues)
            cr.set_source_rgb(0.22, 0.22, 0.22)
            cr.set_line_width(0.3)
            for h in range(HOUR_START, HOUR_END):
                y = ((h + 0.5) / 24.0) * height
                cr.move_to(0, y)
                cr.line_to(width, y)
                cr.stroke()

        da.set_draw_func(on_draw)
        return da


# ═══════════════════════════════════════
# Panel principal de la Parrilla
# ═══════════════════════════════════════

class ParrillaPanel(PanelContainer):
    """Panel de la parrilla semanal (interfaz tipo Google Calendar)."""

    def __init__(self, events_panel=None):
        super().__init__(
            title="Parrilla Semanal",
            subtitle="Programacion semanal de la emisora",
            show_add=True,
        )
        self._events_panel = events_panel

        self._service = get_parrilla_service()
        self._week_offset = 0
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

        # Boton comprobar parrilla (auto-scheduler)
        check_btn = Gtk.Button(label="▶ Activar auto")
        check_btn.add_css_class("ra-button-primary")
        check_btn.add_css_class("ra-button")
        check_btn.set_tooltip_text("Activar reproduccion automatica de la parrilla")
        check_btn.connect("clicked", self._toggle_auto_scheduler)
        toolbar.append(check_btn)
        self._auto_btn = check_btn

        self.content.append(toolbar)

        # Info de conflictos
        self._conflict_label = Gtk.Label()
        self._conflict_label.set_margin_bottom(8)
        self._conflict_label.set_xalign(0)
        self.content.append(self._conflict_label)

        # Grid: header con dias + scroll con columnas
        self._grid_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._grid_container.set_vexpand(True)
        self.content.append(self._grid_container)

        # Contenedor con scroll para todo el grid
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        self.content.append(scroll)

        # Grid wrapper
        self._grid_wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        scroll.set_child(self._grid_wrapper)

    def refresh(self):
        """Recargar la parrilla completa."""
        from datetime import timedelta
        week_start = self._service._get_week_start(date.today()) + timedelta(weeks=self._week_offset)
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
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        header.set_size_request(-1, 30)

        # Columna de horas (vaciamos el header, solo label)
        hour_col = Gtk.Box()
        hour_col.set_size_request(60, -1)
        hour_label = Gtk.Label(label="")
        hour_label.add_css_class("ra-label-dim")
        hour_col.append(hour_label)
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
        """Crear las 7 columnas de dia con los bloques de eventos."""
        # Grid principal: hora labels + 7 columnas
        grid = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        grid.set_vexpand(True)

        # Columna de horas
        hour_column = self._create_hour_labels()
        grid.append(hour_column)

        # 7 columnas de dias
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
        col.set_size_request(60, -1)

        # We need enough height to space labels correctly
        # Use a DrawingArea for precise control
        da = Gtk.DrawingArea()
        da.set_content_width(50)
        da.set_vexpand(True)

        def on_draw(drawing_area, cr, width, height):
            cr.set_source_rgb(0.43, 0.43, 0.43)  # #707070
            cr.select_font_face("sans-serif", 0, 0)
            cr.set_font_size(10)

            for h in range(HOUR_START, HOUR_END):
                y = (h / 24.0) * height
                text = f"{h:02d}:00"
                (tw, th) = cr.text_extents(text)[:2]
                cr.move_to(width - tw - 4, y + th + 2)
                cr.show_text(text)

        da.set_draw_func(on_draw)
        col.append(da)
        return col

    # ── Navegacion ──

    def _change_week(self, delta: int):
        """Cambiar a la semana anterior o siguiente."""
        self._week_offset += delta
        self.refresh()

    def _go_today(self, _btn=None):
        """Volver a la semana actual."""
        self._week_offset = 0
        self.refresh()

    # ── Acciones ──

    def _on_create_event(self, _btn):
        """Abrir dialogo para crear un novo evento."""
        if self._events_panel:
            self._events_panel._show_create_dialog()
            self.refresh()

    def _on_edit_event(self, grid_event: GridEvent):
        """Editar un evento del grid."""
        session = get_session()
        try:
            event = session.get(RadioEvent, grid_event.event_id)
            if event:
                self._show_event_details(event, grid_event)
        finally:
            session.close()

    def _show_event_details(self, event: RadioEvent, ge: GridEvent):
        """Mostrar dialogo con detalles do evento."""
        dialog = Gtk.Window(
            transient_for=self.get_root() if self.get_root() else None,
            modal=True,
            title=ge.name,
            default_width=400,
            default_height=350,
        )

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(12)
        box.set_margin_start(16)
        box.set_margin_end(16)
        box.set_margin_bottom(12)

        tipo_stream = "📡 Streaming"
        tipo_normal = "🎵 Normal"

        info_lines = [
            f"Evento: {ge.name}",
            f"Horario: {ParrillaService.format_time_range(ge.start_time, ge.end_time)}",
            f"Dia: {DAY_NAMES_SHORT[ge.day_index]}",
            f"Tipo: {tipo_stream if ge.is_streaming else tipo_normal}",
        ]

        if ge.playlist_name:
            info_lines.append(f"Playlist: {ge.playlist_name}")
        if ge.streaming_url:
            info_lines.append(f"URL: {ge.streaming_url}")
        if ge.is_now_playing:
            info_lines.append("")
            info_lines.append("● ESTE EVENTO ESTA EN VIVO")
        if ge.has_conflict:
            info_lines.append("")
            info_lines.append("⚠ HAY CONFLICTOS CON OTROS EVENTOS")

        info_text = "\n".join(info_lines)
        info_label = Gtk.Label(label=info_text)
        info_label.set_xalign(0)
        info_label.add_css_class("ra-label")
        box.append(info_label)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(8)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        btn_box.append(spacer)

        if self._events_panel:
            edit_btn = Gtk.Button(label="Editar")
            edit_btn.add_css_class("ra-button")
            edit_btn.connect("clicked", lambda b: self._open_edit_event(event, dialog))
            btn_box.append(edit_btn)

        close_btn = Gtk.Button(label="Pechar")
        close_btn.add_css_class("ra-button-primary")
        close_btn.connect("clicked", lambda b: dialog.destroy())
        btn_box.append(close_btn)

        dialog.set_child(box)
        dialog.show()

    def _open_edit_event(self, event, details_dialog):
        """Abrir dialogo de edicion do evento."""
        details_dialog.destroy()
        if self._events_panel:
            self._events_panel._show_create_dialog(edit_event=event)
            self.refresh()

    def _toggle_auto_scheduler(self, _btn):
        """Activar/desactivar el motor de automatizacion."""
        automation = get_automation_engine()
        if automation.is_active:
            automation.stop()
            self._auto_btn.set_label("▶ Activar auto")
        else:
            automation.set_callbacks(
                on_status_changed=self._on_automation_status_changed
            )
            automation.start()
            self._auto_btn.set_label("⏹ Detener auto")
            self.refresh()

    def _on_automation_status_changed(self, status: AutomationStatus):
        """Callback cuando cambia el estado del motor de automatizacion."""
        def _update():
            self.refresh()
        try:
            GLib.idle_add(_update)
        except Exception:
            pass
