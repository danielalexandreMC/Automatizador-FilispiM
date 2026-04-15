"""
Layout principal de la aplicacion.
Sidebar de navegacion + area de contenido con Gtk.Stack.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GLib, Pango


# ═══════════════════════════════════════
# Sidebar de navegacion
# ═══════════════════════════════════════

class NavigationSidebar(Gtk.Box):
    """
    Sidebar izquierdo con botones de navegacion.
    Cada boton cambia el panel visible en el Stack principal.
    """

    PANELS = [
        ("parrilla",    "📅", "Parrilla Semanal"),
        ("playlists",   "🎵", "Playlists"),
        ("continuidad", "🔄", "Continuidad"),
        ("eventos",     "📋", "Eventos"),
        ("podcasts",    "📡", "Podcasts"),
        ("config",      "⚙️", "Configuracion"),
    ]

    def __init__(self, on_navigate=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("ra-sidebar")
        self._on_navigate = on_navigate
        self._buttons: dict[str, Gtk.Button] = {}

        # Logo / titulo
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        header.set_margin_top(16)
        header.set_margin_bottom(12)
        header.set_margin_start(16)
        header.set_margin_end(16)

        title = Gtk.Label(label="Radio Automator")
        title.add_css_class("ra-heading")
        title.set_xalign(0)
        header.append(title)

        version = Gtk.Label(label="v0.2.0-alpha")
        version.add_css_class("ra-label-dim")
        version.set_xalign(0)
        header.append(version)

        self.append(header)

        # Separador
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.append(sep)

        # Contenedor con scroll para los botones
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        list_box = Gtk.ListBox()
        list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        list_box.add_css_class("ra-sidebar")

        for panel_id, icon_name, label_text in self.PANELS:
            row = Gtk.ListBoxRow()
            row.set_name(f"nav-{panel_id}")

            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            box.set_margin_top(8)
            box.set_margin_bottom(8)
            box.set_margin_start(12)
            box.set_margin_end(12)

            icon = Gtk.Label(label=icon_name)
            icon.set_xalign(0)

            label = Gtk.Label(label=label_text)
            label.set_xalign(0)
            label.add_css_class("ra-label")

            box.append(icon)
            box.append(label)
            row.set_child(box)
            row.panel_id = panel_id  # type: ignore[attr-defined]

            list_box.append(row)

        list_box.connect("row-activated", self._on_row_activated)
        scroll.set_child(list_box)
        self.append(scroll)

        self._list_box = list_box

        # Footer
        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        footer.set_margin_top(8)
        footer.set_margin_bottom(12)
        footer.set_margin_start(16)
        footer.set_margin_end(16)

        status_label = Gtk.Label(label="● Sin reproduccion")
        status_label.add_css_class("ra-label-dim")
        status_label.set_xalign(0)
        status_label.set_name("status-indicator")
        footer.append(status_label)

        self.append(footer)
        self._status_label = status_label

    def _on_row_activated(self, list_box: Gtk.ListBox, row: Gtk.ListBoxRow):
        panel_id = row.panel_id  # type: ignore[attr-defined]
        if self._on_navigate:
            self._on_navigate(panel_id)

    def set_active(self, panel_id: str):
        """Marcar un panel como activo en el sidebar."""
        row = self._list_box.get_row_at_index(0)
        while row is not None:
            if hasattr(row, 'panel_id') and row.panel_id == panel_id:  # type: ignore[attr-defined]
                self._list_box.select_row(row)
                break
            row = self._list_box.get_row_at_index(row.get_index() + 1) if row.get_index() >= 0 else None

    def update_status(self, text: str, is_live: bool = False):
        """Actualizar el texto de estado en el footer."""
        self._status_label.set_text(text)
        if is_live:
            self._status_label.remove_css_class("ra-label-dim")
            self._status_label.add_css_class("ra-label-accent")
        else:
            self._status_label.remove_css_class("ra-label-accent")
            self._status_label.add_css_class("ra-label-dim")


# ═══════════════════════════════════════
# Contenedor de panel base
# ═══════════════════════════════════════

class PanelContainer(Gtk.Box):
    """
    Contenedor base para cada panel.
    Proporciona un header estandar con titulo y boton de accion.
    """

    def __init__(self, title: str, subtitle: str = "", show_add: bool = True):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("ra-panel")

        # Header del panel
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header_box.set_margin_bottom(16)

        title_label = Gtk.Label(label=title)
        title_label.add_css_class("ra-title")
        title_label.set_xalign(0)
        title_label.set_hexpand(True)
        header_box.append(title_label)

        if show_add:
            add_btn = Gtk.Button(label="+ Nuevo")
            add_btn.add_css_class("ra-button-primary")
            add_btn.add_css_class("ra-button")
            add_btn.set_name("panel-add-button")
            header_box.append(add_btn)
            self._add_button = add_btn

        self.append(header_box)

        if subtitle:
            sub = Gtk.Label(label=subtitle)
            sub.add_css_class("ra-subheading")
            sub.set_xalign(0)
            sub.set_margin_bottom(12)
            self.append(sub)

        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.append(self._content)

    @property
    def content(self) -> Gtk.Box:
        """Acceder al contenedor de contenido del panel."""
        return self._content

    @property
    def add_button(self) -> Gtk.Button | None:
        """Acceder al boton de añadir."""
        return getattr(self, '_add_button', None)

    def set_empty_state(self, icon: str = "🎵", message: str = "No hay elementos"):
        """Mostrar un estado vacio cuando no hay items."""
        self._content.remove_all()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.add_css_class("ra-empty-state")
        box.set_valign(Gtk.Align.CENTER)
        box.set_halign(Gtk.Align.CENTER)
        box.set_vexpand(True)

        icon_label = Gtk.Label(label=icon)
        icon_label.set_xalign(0.5)
        box.append(icon_label)

        msg_label = Gtk.Label(label=message)
        msg_label.set_xalign(0.5)
        msg_label.add_css_class("ra-label-dim")
        box.append(msg_label)

        self._content.append(box)


# ═══════════════════════════════════════
# Barra de estado inferior
# ═══════════════════════════════════════

class StatusBar(Gtk.Box):
    """Barra de estado en la parte inferior de la ventana."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.add_css_class("ra-statusbar")

        self._left = Gtk.Label(label="Listo")
        self._left.set_xalign(0)
        self._left.set_hexpand(True)
        self.append(self._left)

        self._center = Gtk.Label(label="")
        self._center.set_xalign(0.5)
        self.append(self._center)

        self._right = Gtk.Label(label="")
        self._right.set_xalign(1)
        self.append(self._right)

    def set_text(self, left: str = "", center: str = "", right: str = ""):
        """Actualizar los textos de la barra de estado."""
        self._left.set_text(left)
        self._center.set_text(center)
        self._right.set_text(right)
