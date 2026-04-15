"""
Visor de Logs - Widget para consultar los logs de la aplicacion.
Se integra en el panel de Configuracion como una seccion adicional.
Permite filtrar por nivel, ver las ultimas entradas y limpiar el archivo.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Pango

from radio_automator.core.logger import get_log_manager


class LogViewer(Gtk.Box):
    """
    Widget de visualizacion de logs de la aplicacion.
    Muestra las ultimas entradas del archivo de log con filtrado por nivel.
    """

    # Colores por nivel de log
    LEVEL_COLORS = {
        "DEBUG": "#1E88E5",
        "INFO": "#B0B0B0",
        "WARNING": "#FB8C00",
        "ERROR": "#E53935",
        "CRITICAL": "#E53935",
    }

    LEVEL_ICONS = {
        "DEBUG": "dialog-information-symbolic",
        "INFO": "dialog-information-symbolic",
        "WARNING": "dialog-warning-symbolic",
        "ERROR": "dialog-error-symbolic",
        "CRITICAL": "dialog-error-symbolic",
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class("ra-log-viewer")

        # Barra de herramientas
        toolbar = self._build_toolbar()
        self.append(toolbar)

        # Contenedor con scroll
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(250)

        # Lista de logs
        self._list_box = Gtk.ListBox()
        self._list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._list_box.add_css_class("ra-log-list")
        scrolled.set_child(self._list_box)

        self.append(scrolled)

        # Barra de informacion
        self._info_label = Gtk.Label(label="")
        self._info_label.set_xalign(0)
        self._info_label.add_css_class("ra-label-dim")
        self.append(self._info_label)

        # Estado
        self._current_level_filter = "DEBUG"
        self._entry_count = 0

    def _build_toolbar(self) -> Gtk.Box:
        """Construir la barra de herramientas del visor."""
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        # Titulo
        title = Gtk.Label(label="Registro de Actividad")
        title.add_css_class("ra-heading")
        title.set_xalign(0)
        title.set_hexpand(True)
        toolbar.append(title)

        # Filtro de nivel
        filter_label = Gtk.Label(label="Nivel:")
        filter_label.add_css_class("ra-label")
        toolbar.append(filter_label)

        self._filter_combo = Gtk.DropDown.new_from_strings([
            "DEBUG", "INFO", "WARNING", "ERROR"
        ])
        self._filter_combo.set_selected(0)  # DEBUG por defecto
        self._filter_combo.connect("notify::selected", self._on_filter_changed)
        self._filter_combo.set_size_request(100, -1)
        toolbar.append(self._filter_combo)

        # Boton refrescar
        refresh_btn = Gtk.Button()
        refresh_btn.set_icon_name("view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Recargar logs")
        refresh_btn.add_css_class("ra-button")
        refresh_btn.add_css_class("ra-button-icon")
        refresh_btn.connect("clicked", lambda *a: self.refresh())
        toolbar.append(refresh_btn)

        # Boton limpiar
        clear_btn = Gtk.Button(label="Limpiar")
        clear_btn.set_tooltip_text("Limpiar archivo de log")
        clear_btn.add_css_class("ra-button")
        clear_btn.add_css_class("ra-button-sm")
        clear_btn.connect("clicked", self._on_clear_clicked)
        toolbar.append(clear_btn)

        return toolbar

    def _on_filter_changed(self, dropdown, param):
        """Cambiar filtro de nivel."""
        selected = dropdown.get_selected()
        levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
        if 0 <= selected < len(levels):
            self._current_level_filter = levels[selected]
            self.refresh()

    def refresh(self):
        """Recargar las entradas de log desde el archivo."""
        # Limpiar lista actual
        child = self._list_box.get_first_child()
        while child:
            self._list_box.remove(child)
            child = self._list_box.get_first_child()

        # Obtener entradas
        manager = get_log_manager()
        entries = manager.get_recent_entries(
            count=100,
            min_level=self._current_level_filter
        )
        self._entry_count = len(entries)

        if not entries:
            empty_label = Gtk.Label(label="No hay entradas de log para este filtro.")
            empty_label.add_css_class("ra-label-dim")
            empty_label.set_xalign(0.5)
            empty_label.set_margin_top(20)
            empty_label.set_margin_bottom(20)
            row = Gtk.ListBoxRow()
            row.set_selectable(False)
            row.set_activatable(False)
            row.set_child(empty_label)
            self._list_box.append(row)
        else:
            for entry in entries:
                row = self._build_log_row(entry)
                self._list_box.append(row)

        # Actualizar info
        log_size = manager.get_log_size()
        size_str = self._format_size(log_size)
        self._info_label.set_label(
            f"{self._entry_count} entradas | Nivel minimo: {self._current_level_filter} | "
            f"Archivo: {size_str}"
        )

    def _build_log_row(self, entry) -> Gtk.ListBoxRow:
        """Construir una fila de log."""
        row = Gtk.ListBoxRow()
        row.set_selectable(False)
        row.set_activatable(False)

        # Asignar color segun nivel
        color = self.LEVEL_COLORS.get(entry.level, "#B0B0B0")

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(8)
        box.set_margin_end(8)

        # Indicador de nivel (barra de color)
        level_bar = Gtk.Box()
        level_bar.set_size_request(3, -1)
        level_bar.add_css_class("ra-log-level-bar")
        # Usar un DrawingArea simple como barra
        da = Gtk.DrawingArea()
        da.set_content_width(3)
        da.set_content_height(20)

        def draw_level_bar(drawing_area, cr, width, height):
            # Parsear color hex a RGB
            hex_color = color.lstrip('#')
            r = int(hex_color[0:2], 16) / 255.0
            g = int(hex_color[2:4], 16) / 255.0
            b = int(hex_color[4:6], 16) / 255.0
            cr.set_source_rgb(r, g, b)
            cr.rectangle(0, 0, width, height)
            cr.fill()

        da.set_draw_func(draw_level_bar)
        box.append(da)

        # Timestamp
        ts_label = Gtk.Label(label=entry.timestamp.split(" ")[1] if " " in entry.timestamp else entry.timestamp)
        ts_label.set_xalign(0)
        ts_label.add_css_class("ra-label-dim")
        ts_label.set_width_chars(8)
        ts_label.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(ts_label)

        # Nivel
        level_label = Gtk.Label(label=entry.level[:4])
        level_label.set_xalign(0)
        level_label.add_css_class("ra-label")
        level_label.set_width_chars(5)
        # Color al texto del nivel
        level_label.set_markup(f'<span foreground="{color}">{entry.level[:4]}</span>')
        box.append(level_label)

        # Logger
        logger_label = Gtk.Label(label=entry.logger_name)
        logger_label.set_xalign(0)
        logger_label.add_css_class("ra-label-dim")
        logger_label.set_width_chars(20)
        logger_label.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(logger_label)

        # Mensaje
        msg_label = Gtk.Label(label=entry.message)
        msg_label.set_xalign(0)
        msg_label.add_css_class("ra-label")
        msg_label.set_hexpand(True)
        msg_label.set_ellipsize(Pango.EllipsizeMode.END)
        msg_label.set_tooltip_text(entry.message)
        box.append(msg_label)

        row.set_child(box)
        return row

    def _on_clear_clicked(self, _btn):
        """Limpiar el archivo de log con confirmacion."""
        dialog = Gtk.MessageDialog(
            transient_for=self.get_root(),
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Limpiar registro de actividad",
            secondary_text="Se borrara todo el contenido del archivo de log. Esta accion no se puede deshacer."
        )
        dialog.connect("response", self._on_clear_response)
        dialog.present()

    def _on_clear_response(self, dialog, response):
        """Manejar respuesta del dialogo de confirmacion de limpieza."""
        dialog.destroy()
        if response == Gtk.ResponseType.YES:
            manager = get_log_manager()
            manager.clear_log_file()
            self.refresh()

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Formatear tamano en bytes a formato legible."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
