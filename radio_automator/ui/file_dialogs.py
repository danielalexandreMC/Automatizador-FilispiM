"""Dialogos de seleccion de archivos compatibles con GTK 4.6 (Debian)."""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib


def open_file_chooser(parent, title, action=Gtk.FileChooserAction.OPEN,
                      select_multiple=False, filters=None):
    """Abrir un dialogo de seleccion de archivos.

    Devolve unha lista de paths (str) seleccionados,
    ou lista baleira se se cancelou.
    """
    dialog = Gtk.FileChooserDialog(
        title=title,
        action=action,
        transient_for=parent,
    )
    dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
    dialog.add_button("Aceptar", Gtk.ResponseType.OK)
    dialog.set_modal(True)
    dialog.set_select_multiple(select_multiple)

    if filters:
        for name, patterns in filters:
            f = Gtk.FileFilter()
            f.set_name(name)
            for p in patterns:
                f.add_pattern(p)
            dialog.add_filter(f)

    result = []
    loop = GLib.MainLoop()

    def on_response(dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            if select_multiple:
                for f in dialog.get_files():
                    path = f.get_path()
                    if path:
                        result.append(path)
            else:
                f = dialog.get_file()
                if f:
                    result.append(f.get_path())
        dialog.destroy()
        loop.quit()

    dialog.connect("response", on_response)
    dialog.show()
    loop.run()

    return result


AUDIO_FILTERS = [
    ("Archivos de audio", ["*.mp3", "*.wav", "*.ogg", "*.flac",
                            "*.opus", "*.aac", "*.m4a", "*.wma"]),
    ("Todos los archivos", ["*"]),
]
