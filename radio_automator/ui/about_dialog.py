"""
Dialogo "Acerca De" para Radio Automator.
Muestra informacion de la aplicacion: nombre, version, descripcion,
creditos y licencia. Utiliza Gtk.AboutDialog nativo de GTK4.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

from radio_automator.core.logger import APP_NAME, APP_VERSION


def show_about_dialog(parent: Gtk.Window | None = None):
    """
    Mostrar el dialogo "Acerca De" de la aplicacion.

    Args:
        parent: Ventana padre para el dialogo (modal).
    """
    dialog = Gtk.AboutDialog()
    dialog.set_transient_for(parent)
    dialog.set_modal(True)

    dialog.set_program_name(APP_NAME)
    dialog.set_version(APP_VERSION)
    dialog.set_comments(
        "Automatizador de radio de codigo abierto para Debian/Ubuntu.\n"
        "Playlists anidables, parrilla semanal interactiva, crossfade\n"
        "dual-deck, conexion streaming y descarga automatica de podcasts."
    )
    dialog.set_copyright("2026 Radio Automator Contributors")
    dialog.set_license_type(Gtk.License.GPL_3_0)
    dialog.set_website("https://github.com/radio-automator")
    dialog.set_website_label("Repositorio en GitHub")

    # Creditos
    dialog.set_authors([
        "Radio Automator Team",
        "",
        "Tecnologias:",
        "  Python 3.11+",
        "  GTK4 (PyGObject)",
        "  GStreamer 1.x",
        "  SQLite (SQLAlchemy)",
    ])
    dialog.set_artists(["Radio Automator Team"])

    # Logo (si existe)
    try:
        from gi.repository import GdkPixbuf
        logo_path = "/usr/share/icons/hicolor/256x256/apps/radio-automator.png"
        import os
        if os.path.exists(logo_path):
            logo = GdkPixbuf.Pixbuf.new_from_file(logo_path)
            dialog.set_logo(logo)
    except Exception:
        pass

    dialog.present()
