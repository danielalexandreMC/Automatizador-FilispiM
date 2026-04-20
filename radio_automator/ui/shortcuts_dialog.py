"""
Dialogo de Atajos de Teclado para Radio Automator.
Ventana de referencia que muestra todos los atajos de teclado disponibles,
agrupados por categoria. Incluye secciones para navegacion, transporte,
y generales.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Pango


# ── Datos de atajos ──
SHORTCUT_GROUPS = [
    {
        "title": "Navegacion entre paneles",
        "shortcuts": [
            ("Ctrl + 1", "Parrilla Semanal"),
            ("Ctrl + 2", "Playlists"),
            ("Ctrl + 3", "Continuidad"),
            ("Ctrl + 4", "Eventos"),
            ("Ctrl + 5", "Podcasts"),
            ("Ctrl + 6", "Configuracion"),
        ],
    },
    {
        "title": "Transporte de audio",
        "shortcuts": [
            ("Ctrl + Espacio", "Reproducir / Pausar"),
            ("Ctrl + Derecha", "Pista siguiente"),
            ("Ctrl + Izquierda", "Pista anterior"),
            ("Ctrl + S", "Detener"),
        ],
    },
    {
        "title": "General",
        "shortcuts": [
            ("Ctrl + Q", "Salir de la aplicacion"),
            ("Ctrl + W", "Cerrar ventana actual"),
            ("F1", "Atajos de teclado (esta ventana)"),
            ("F10", "Menu de la aplicacion"),
        ],
    },
]


class ShortcutsWindow(Gtk.Window):
    """Ventana de atajos de teclado con referencia visual."""

    def __init__(self, parent: Gtk.Window | None = None):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_title("Atajos de Teclado")
        self.set_default_size(520, 480)
        self.set_resizable(False)

        # Layout principal con scroll
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_child(self._build_content())
        self.set_child(scrolled)

        # HeaderBar con boton cerrar
        header = Gtk.HeaderBar()
        header.set_show_title_buttons(True)
        header.set_title_widget(Gtk.Label(label="Atajos de Teclado"))
        self.set_titlebar(header)

        # Shortcut: F1 para abrir esta ventana
        self._setup_shortcuts()

    def _build_content(self) -> Gtk.Widget:
        """Construir el contenido de la ventana."""
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(20)
        main_box.set_margin_bottom(20)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)

        # Titulo
        title = Gtk.Label(label="Atajos de Teclado")
        title.add_css_class("ra-title")
        title.set_xalign(0)
        title.set_margin_bottom(8)
        main_box.append(title)

        # Subtitulo
        subtitle = Gtk.Label(
            label="Lista de atajos disponibles para controlar Radio Automator"
        )
        subtitle.add_css_class("ra-subheading")
        subtitle.set_xalign(0)
        subtitle.set_margin_bottom(16)
        main_box.append(subtitle)

        # Grupos de atajos
        for group in SHORTCUT_GROUPS:
            group_box = self._build_group(group)
            main_box.append(group_box)

        # Nota al pie
        note = Gtk.Label(
            label="Tip: Puedes usar Ctrl+1 a Ctrl+6 para navegar rapidamente entre paneles."
        )
        note.add_css_class("ra-label-dim")
        note.set_xalign(0)
        note.set_margin_top(12)
        note.set_wrap(True)
        main_box.append(note)

        return main_box

    def _build_group(self, group: dict) -> Gtk.Box:
        """Construir un grupo de atajos."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        # Titulo del grupo
        group_title = Gtk.Label(label=group["title"])
        group_title.add_css_class("ra-heading")
        group_title.set_xalign(0)
        group_title.set_margin_top(8)
        group_title.set_margin_bottom(4)
        box.append(group_title)

        # Separador
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.add_css_class("ra-separator")
        box.append(sep)

        # Lista de atajos
        for key, description in group["shortcuts"]:
            row = self._build_shortcut_row(key, description)
            box.append(row)

        return box

    def _build_shortcut_row(self, key: str, description: str) -> Gtk.Box:
        """Construir una fila de atajo: [tecla] ---- descripcion."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.set_margin_start(8)
        row.set_margin_end(8)
        row.set_margin_top(3)
        row.set_margin_bottom(3)

        # Tecla
        key_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        key_box.set_size_request(160, -1)

        key_label = Gtk.Label(label=key)
        key_label.set_xalign(0)
        key_label.add_css_class("ra-shortcut-key")
        key_label.set_attributes(self._get_key_attributes())
        key_box.append(key_label)

        row.append(key_box)

        # Descripcion
        desc_label = Gtk.Label(label=description)
        desc_label.set_xalign(0)
        desc_label.add_css_class("ra-label")
        desc_label.set_hexpand(True)
        row.append(desc_label)

        return row

    def _get_key_attributes(self) -> Pango.AttrList:
        """Crear atributos Pango para la tecla (monospace, bold)."""
        attrs = Pango.AttrList()
        # Familia monospace
        family = Pango.attr_family_new("Monospace")
        attrs.insert(family)
        # Tamaño ligeramente mayor
        size = Pango.attr_scale_new(0.95)
        attrs.insert(size)
        return attrs

    def _setup_shortcuts(self):
        """Configurar atajos para esta ventana."""
        # Escape cierra la ventana
        esc_action = Gtk.ShortcutAction.new_signal("close")
        trigger = Gtk.ShortcutTrigger.parse_string("Escape")
        shortcut = Gtk.Shortcut.new(trigger, esc_action)
        self.add_shortcut(shortcut)


def show_shortcuts_dialog(parent: Gtk.Window | None = None):
    """
    Mostrar el dialogo de atajos de teclado.

    Args:
        parent: Ventana padre para el dialogo (modal).
    """
    dialog = ShortcutsWindow(parent)
    dialog.present()
