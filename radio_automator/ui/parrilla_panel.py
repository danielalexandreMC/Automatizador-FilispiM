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
# Constantes
# ═══════════════════════════════════════

HOUR_HEIGHT = 50  # 50px por hora (fixo, para scroll consistente)
HOUR_COL_WIDTH = 70  # Ancho da columna de horas (maior para legibilidade)


# ═══════════════════════════════════════
# Columna de dia del grid (DrawingArea puro - compatible GTK 4.6)
# ═══════════════════════════════════════

class DayColumn(Gtk.DrawingArea):
    """Columna vertical dun dia: debuxa o grid horario e os bloques de eventos.

    Numa parrilla de radio, cada evento ocupa o ancho COMPLETO da columna.
    Non hai eventos superpostos.
    """

    def __init__(self, day_index: int, events: list[GridEvent],
                 on_edit_event=None):
        super().__init__()
        self._day_index = day_index
        self._events = sorted(events, key=lambda e: e.start_minutes)
        self._on_edit_event = on_edit_event
        self._event_rects = []  # [(GridEvent, x, y, w, h), ...]

        self.set_vexpand(True)
        self.set_hexpand(True)
        # MINIMO para que ScrolledWindow faga scroll
        self.set_size_request(80, HOUR_END * HOUR_HEIGHT)

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
        """Debuxar o grid horario e os bloques de eventos a ancho completo."""
        self._event_rects = []

        # Fondo
        cr.set_source_rgb(0.16, 0.16, 0.16)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        # Lineas horarias completas (cada hora)
        cr.set_source_rgb(0.25, 0.25, 0.25)
        cr.set_line_width(0.5)
        for h in range(HOUR_START, HOUR_END + 1):
            y = h * HOUR_HEIGHT
            cr.move_to(0, y)
            cr.line_to(width, y)
            cr.stroke()

        # Lineas de media hora (mais tenues)
        cr.set_source_rgb(0.20, 0.20, 0.20)
        cr.set_line_width(0.3)
        for h in range(HOUR_START, HOUR_END):
            y = (h + 0.5) * HOUR_HEIGHT
            cr.move_to(0, y)
            cr.line_to(width, y)
            cr.stroke()

        # Separador dereito entre columnas de dias
        cr.set_source_rgb(0.20, 0.20, 0.20)
        cr.set_line_width(1.0)
        cr.move_to(width - 0.5, 0)
        cr.line_to(width - 0.5, height)
        cr.stroke()

        # ── Bloques de Continuidad nos ocos horarios ──
        self._draw_continuity_blocks(cr, width)

        # Debuxar bloques de eventos a ancho completo
        margin = 2
        pad = 1
        for ge in self._events:
            # Posicion vertical: minutos a pixels usando HOUR_HEIGHT fixo
            top_px = (ge.start_minutes / 60.0) * HOUR_HEIGHT
            h_px = max((ge.duration_minutes / 60.0) * HOUR_HEIGHT, 18)

            x = margin + pad
            w = width - margin * 2 - pad * 2
            y = top_px
            h = h_px

            # Gardar rect para deteccion de click
            self._event_rects.append((ge, x, y, w, h))

            # Cor e bordo segun estado
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

                # Nome do evento
                cr.set_source_rgb(1.0, 1.0, 1.0)
                cr.select_font_face("sans-serif", 0, 1)
                cr.set_font_size(9)
                name = ge.name or ""
                if len(name) > 25:
                    name = name[:22] + "..."
                cr.move_to(text_x, text_y)
                cr.show_text(name)

                # Hora do evento (inicio - fin)
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

    def _draw_dashed_rounded_rect(self, cr, x, y, w, h, r):
        """Debuxar rectangulo con bordes redondeados e liña punteada."""
        cr.set_dash([4, 3])
        self._rounded_rect(cr, x, y, w, h, r)
        cr.stroke()
        cr.set_dash([])

    def _draw_continuity_blocks(self, cr, width):
        """Debuxar bloques sutiles de Continuidad nos ocos entre eventos.

        Identifica os periodos sen eventos programados e encheos
        cun bloque visual que indica que a Continuidad esta soando.
        """
        if not self._events:
            # Non hai eventos: toda a columna e Continuidad
            self._draw_single_cont_block(
                cr, width, 0, HOUR_END * HOUR_HEIGHT
            )
            return

        margin = 2
        pad = 1
        gaps = []
        day_start = 0  # minutos
        day_end = HOUR_END * 60  # 24h en minutos

        # Oco antes do primeiro evento
        first_end = self._events[0].start_minutes
        if first_end > 0:
            gaps.append((day_start, first_end))

        # Ocos entre eventos
        for i in range(len(self._events) - 1):
            ev_current = self._events[i]
            ev_next = self._events[i + 1]
            gap_start = ev_current.start_minutes + ev_current.duration_minutes
            gap_end = ev_next.start_minutes
            if gap_end > gap_start:
                gaps.append((gap_start, gap_end))

        # Oco despoids do ultimo evento
        last = self._events[-1]
        last_end = last.start_minutes + last.duration_minutes
        if last_end < day_end:
            gaps.append((last_end, day_end))

        # Debuxar cada oco
        for gap_start_min, gap_end_min in gaps:
            y_px = (gap_start_min / 60.0) * HOUR_HEIGHT
            h_px = ((gap_end_min - gap_start_min) / 60.0) * HOUR_HEIGHT
            x = margin + pad
            w = width - margin * 2 - pad * 2

            if h_px < 6:
                # Oco demasiado pequeno, non debuxar nada
                continue

            self._draw_single_cont_block(cr, width, y_px, h_px)

    def _draw_single_cont_block(self, cr, width, y, h):
        """Debuxar un unico bloque de Continuidad na posicion dada."""
        margin = 2
        pad = 1
        x = margin + pad
        w = width - margin * 2 - pad * 2

        # Fondo moi subtil (lixeiramente diferente do fondo do grid)
        cr.set_source_rgba(0.22, 0.25, 0.20, 0.35)
        self._rounded_rect(cr, x, y, w, h, 4)
        cr.fill()

        # Bordo punteado verde escuro
        cr.set_source_rgb(0.30, 0.38, 0.28)
        cr.set_line_width(0.8)
        self._draw_dashed_rounded_rect(cr, x, y, w, h, 4)

        # Icona e texto (so se hai espazo suficiente)
        if h > 20:
            # Icona pequena
            cr.set_source_rgb(0.40, 0.50, 0.38)
            cr.select_font_face("sans-serif", 0, 0)
            cr.set_font_size(8)

            # Texto centrado vertical e horizontalmente
            text = "\u21BB Continuidad"
            cr.set_source_rgb(0.42, 0.52, 0.40)
            cr.set_font_size(8)
            text_x = x + w / 2
            text_y = y + h / 2 + 3

            # Calcular anchura do texto para centrar
            (t_w, _) = cr.text_extents(text)[:2]
            cr.move_to(text_x - t_w / 2, text_y)
            cr.show_text(text)

            # Se o bloque e grande, amosar tamien o horario
            if h > 40:
                h_start = (y / HOUR_HEIGHT) * 60
                h_end = ((y + h) / HOUR_HEIGHT) * 60
                time_str = f"{int(h_start // 60):02d}:{int(h_start % 60):02d} - {int(h_end // 60):02d}:{int(h_end % 60):02d}"
                cr.set_source_rgb(0.35, 0.43, 0.33)
                cr.set_font_size(7)
                (t_w2, _) = cr.text_extents(time_str)[:2]
                cr.move_to(text_x - t_w2 / 2, text_y + 12)
                cr.show_text(time_str)


# ═══════════════════════════════════════
# Panel principal de la Parrilla
# ═══════════════════════════════════════

class ParrillaPanel(PanelContainer):
    """Panel de la parrilla semanal."""

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

        # Boton de novo evento
        if self.add_button:
            self.add_button.set_sensitive(True)
            self.add_button.set_tooltip_text("Crear novo evento programado")
            self.add_button.connect("clicked", self._on_create_event)

        # Referencia ao boton Hoy/Semana para poder cambiar o label
        self._today_btn = None

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        """Construir la interfaz del panel.

        Layout:
          toolbar (fixo)
          conflict_label (fixo)
          header_dias (fixo, fora do scroll)
          ScrolledWindow -> grid (hora labels + columnas de dia, con scroll vertical)
        """
        # Toolbar: navegacion de semanas
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_margin_bottom(12)

        prev_btn = Gtk.Button(label="<-")
        prev_btn.add_css_class("ra-button")
        prev_btn.add_css_class("ra-button-icon")
        prev_btn.set_tooltip_text("Semana anterior")
        prev_btn.connect("clicked", lambda b: self._change_week(-1))
        toolbar.append(prev_btn)

        self._week_label = Gtk.Label()
        self._week_label.add_css_class("ra-heading")
        self._week_label.set_halign(Gtk.Align.CENTER)
        toolbar.append(self._week_label)

        next_btn = Gtk.Button(label="->")
        next_btn.add_css_class("ra-button")
        next_btn.add_css_class("ra-button-icon")
        next_btn.set_tooltip_text("Semana siguiente")
        next_btn.connect("clicked", lambda b: self._change_week(1))
        toolbar.append(next_btn)

        self._today_btn = Gtk.Button(label="Hoy")
        self._today_btn.add_css_class("ra-button")
        self._today_btn.add_css_class("ra-button-sm")
        self._today_btn.connect("clicked", self._toggle_today)
        toolbar.append(self._today_btn)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        toolbar.append(spacer)

        self.content.append(toolbar)

        # Info de conflictos
        self._conflict_label = Gtk.Label()
        self._conflict_label.set_margin_bottom(8)
        self._conflict_label.set_xalign(0)
        self.content.append(self._conflict_label)

        # ── HEADER DOS DIAS (FIXO, fora do scroll) ──
        self._day_header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self._day_header_box.set_size_request(-1, 28)
        # Espazo en branco para alinear coa columna de horas
        hour_spacer = Gtk.Box()
        hour_spacer.set_size_request(HOUR_COL_WIDTH, -1)
        self._day_header_box.append(hour_spacer)
        self.content.append(self._day_header_box)

        # Separador debaixo do header
        header_sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.content.append(header_sep)

        # ── SCROLLED WINDOW (so o grid, co scroll vertical) ──
        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._scroll.set_vexpand(True)
        self._scroll.set_hexpand(True)
        self.content.append(self._scroll)

        # Grid wrapper (dentro do scroll)
        self._grid_wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._scroll.set_child(self._grid_wrapper)

    def refresh(self):
        """Recargar la parrilla completa."""
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

        # Actualizar boton Hoy/Semana
        if self._today_btn:
            if self._show_today_only:
                self._today_btn.set_label("Semana")
            else:
                self._today_btn.set_label("Hoy")

        # Info de conflictos
        if week_data.conflicts:
            n = len(week_data.conflicts)
            self._conflict_label.set_label(f"! {n} conflicto(s) detectado(s)")
            self._conflict_label.add_css_class("ra-label-warning")
            self._conflict_label.remove_css_class("ra-label-dim")
            self._conflict_label.remove_css_class("ra-label-success")
        else:
            self._conflict_label.set_label(
                f"OK {week_data.total_events} evento(s), sin conflictos"
            )
            self._conflict_label.add_css_class("ra-label-success")
            self._conflict_label.remove_css_class("ra-label-dim")
            self._conflict_label.remove_css_class("ra-label-warning")

        # ── Actualizar header dos dias (fixo) ──
        self._update_day_header()

        # ── Actualizar grid con scroll ──
        # Limpiar grid anterior
        while self._grid_wrapper.get_first_child():
            self._grid_wrapper.remove(self._grid_wrapper.get_first_child())

        # Crear grid con columnas de dia
        self._build_grid_columns(week_data)

        # Now playing info
        if week_data.now_playing and week_data.now_playing.is_active:
            np = week_data.now_playing
            ev = np.event
            if ev:
                info = f"- EN VIVO: {ev.name}"
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

    def _update_day_header(self):
        """Actualizar a cabecera dos nomes dos dias (fixa, fóra do scroll).

        O header ten un espazo en branco de HOUR_COL_WIDTH px a esquerda
        para alinear coa columna de horas do grid.
        """
        # Limpiar header actual (excepto o spacer da hora)
        child = self._day_header_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._day_header_box.remove(child)
            child = next_child

        # Re-engadir o spacer da hora
        hour_spacer = Gtk.Box()
        hour_spacer.set_size_request(HOUR_COL_WIDTH, -1)
        self._day_header_box.append(hour_spacer)

        if self._show_today_only:
            return

        today_idx = datetime.now().weekday()
        for i in range(7):
            day_box = Gtk.Box()
            day_box.set_hexpand(True)

            label = Gtk.Label(label=DAY_NAMES_SHORT[i])
            label.set_xalign(0.5)

            if i == today_idx:
                label.add_css_class("ra-label-accent")

            day_box.append(label)
            self._day_header_box.append(day_box)

    def _build_grid_columns(self, week_data):
        """Crear las columnas de dia con los bloques de eventos."""
        # Grid principal: hora labels + columnas
        grid = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        grid.set_vexpand(True)
        grid.set_hexpand(True)

        # Columna de horas: DrawingArea DIRECTO (sen Box wrapper)
        hour_da = Gtk.DrawingArea()
        hour_da.set_size_request(HOUR_COL_WIDTH, HOUR_END * HOUR_HEIGHT)
        hour_da.set_hexpand(False)
        hour_da.set_draw_func(self._draw_hour_column)
        grid.append(hour_da)

        if self._show_today_only:
            today_idx = datetime.now().weekday()
            col = DayColumn(
                day_index=today_idx,
                events=week_data.days[today_idx],
                on_edit_event=self._on_edit_event,
            )
            col.set_hexpand(True)
            grid.append(col)
        else:
            for day_idx in range(7):
                col = DayColumn(
                    day_index=day_idx,
                    events=week_data.days[day_idx],
                    on_edit_event=self._on_edit_event,
                )
                col.set_hexpand(True)
                grid.append(col)

        self._grid_wrapper.append(grid)

    def _draw_hour_column(self, drawing_area, cr, width, height):
        """Debuxar a columna de horas (00:00h - 24:00h).

        Usase como DrawingArea directo no grid para evitar problemas
        de allocation con Box wrappers.
        """
        # Fondo escuro para a columna de horas
        cr.set_source_rgb(0.13, 0.13, 0.13)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        # Bordo dereito
        cr.set_source_rgb(0.30, 0.30, 0.30)
        cr.set_line_width(1.0)
        cr.move_to(width - 0.5, 0)
        cr.line_to(width - 0.5, height)
        cr.stroke()

        # Fonte para as horas - maiores e mais brillantes
        cr.select_font_face("sans-serif", 0, 0)
        cr.set_font_size(10)

        for h in range(HOUR_START, HOUR_END):
            y = h * HOUR_HEIGHT

            # Liña horizontal (coincide coas lineas do grid)
            cr.set_source_rgb(0.25, 0.25, 0.25)
            cr.set_line_width(0.5)
            cr.move_to(0, y)
            cr.line_to(width, y)
            cr.stroke()

            # Etiqueta: aliñada a esquerda, texto brillante
            cr.set_source_rgb(0.75, 0.75, 0.75)
            text = f"{h:02d}:00h"
            cr.move_to(4, y + 14)  # Aliñado esquerda, 14px abaixo da liña
            cr.show_text(text)

        # Liña final 24:00h
        y = HOUR_END * HOUR_HEIGHT
        cr.set_source_rgb(0.25, 0.25, 0.25)
        cr.set_line_width(0.5)
        cr.move_to(0, y)
        cr.line_to(width, y)
        cr.stroke()
        # Etiqueta "24:00h"
        cr.set_source_rgb(0.75, 0.75, 0.75)
        cr.move_to(4, y + 14)
        cr.show_text("24:00h")

    # -- Navegacion --

    def _toggle_today(self, _btn=None):
        """Toggle entre vista de hoxe e vista semanal."""
        if self._show_today_only:
            self._show_today_only = False
            self.refresh()
        else:
            self._week_offset = 0
            self._show_today_only = True
            self.refresh()

    def _change_week(self, delta: int):
        """Cambiar a la semana anterior o siguiente."""
        self._week_offset += delta
        self._show_today_only = False
        self.refresh()

    # -- Acciones --

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
        title = f"Editar: {edit_event.name}" if is_edit else "Novo Evento"
        event_id = edit_event.id if is_edit else None  # Gardar o ID para usar noutra sesion

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

        # Botons
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
                print("[Parrilla] ERRO: Nome baleiro, non se garda")
                return
            if not start_time or len(start_time) != 5 or start_time[2] != ':':
                print(f"[Parrilla] ERRO: Hora inicio invalida: '{start_time}'")
                return
            if streaming_url and not end_time:
                print("[Parrilla] ERRO: Streaming necesita hora de fin")
                return
            if end_time and (len(end_time) != 5 or end_time[2] != ':'):
                print(f"[Parrilla] ERRO: Hora fin invalida: '{end_time}'")
                return

            pl_idx = playlist_combo.get_selected()
            playlist_id = playlists[pl_idx - 1].id if pl_idx > 0 and pl_idx - 1 < len(playlists) else None

            week_days = ",".join("1" if days_data[i].get_active() else "0" for i in range(7))
            pattern_map = {0: "weekly", 1: "daily", 2: "once", 3: "selected_days"}
            repeat_pattern = pattern_map.get(repeat_combo.get_selected(), "weekly")

            # Abrir NOVA sesion para gardar.
            # A sesion anterior pechouse en _on_edit_event, asi que
            # edit_event esta "detached". Usamos event_id para buscar
            # o obxeto na nova sesion.
            session = get_session()
            try:
                if is_edit and event_id:
                    event = session.get(RadioEvent, event_id)
                    if event:
                        print(f"[Parrilla] Gardando evento ID={event_id}: '{name}' {start_time}-{end_time}")
                        event.name = name
                        event.start_time = start_time
                        event.end_time = end_time or None
                        event.streaming_url = streaming_url or None
                        event.playlist_id = playlist_id
                        event.week_days = week_days
                        event.repeat_pattern = repeat_pattern
                    else:
                        print(f"[Parrilla] ERRO: Non se atopo evento con ID {event_id}")
                        session.close()
                        return
                else:
                    print(f"[Parrilla] Creando novo evento: '{name}' {start_time}-{end_time}")
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
                print("[Parrilla] Commit OK, recargando parrilla...")
                self.refresh()
            except Exception as e:
                session.rollback()
                print(f"[Parrilla] Erro ao gardar evento: {e}")
                import traceback
                traceback.print_exc()
            finally:
                session.close()
            dialog.destroy()

        cancel_btn.connect("clicked", lambda b: dialog.destroy())
        save_btn.connect("clicked", lambda b: do_save())
        dialog.show()
