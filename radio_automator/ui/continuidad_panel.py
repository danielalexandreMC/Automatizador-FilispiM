"""
Panel de la playlist Continuidad.
Muestra y permite editar (pero no eliminar) la playlist Continuidad.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

from radio_automator.ui.playlist_editor import PlaylistEditor
from radio_automator.services.playlist_service import PlaylistService


class ContinuidadPanel(Gtk.Box):
    """
    Panel dedicado a la playlist Continuidad.
    Hereda del editor de playlist pero con contexto especial.
    """

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self._service = PlaylistService()

        # Header informativo
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        header.set_margin_start(20)
        header.set_margin_end(20)
        header.set_margin_top(20)
        header.set_margin_bottom(8)

        title = Gtk.Label(label="Continuidad")
        title.add_css_class("ra-title")
        title.set_xalign(0)
        header.append(title)

        desc = Gtk.Label(
            label="Playlist del sistema que se reproduce automaticamente cuando "
                  "no hay eventos programados. Se reanuda desde el punto donde "
                  "se detuvo. No se puede eliminar."
        )
        desc.add_css_class("ra-label")
        desc.set_xalign(0)
        desc.set_wrap(True)
        desc.set_max_width_chars(80)
        header.append(desc)

        badge = Gtk.Label(label="SISTEMA - Protegida")
        badge.add_css_class("ra-badge")
        badge.add_css_class("ra-badge-system")
        badge.set_xalign(0)
        header.append(badge)

        self.append(header)

        # Editor de playlist
        try:
            dto = self._service.get_continuity()
            self._editor = PlaylistEditor(dto, on_back=None)
        except Exception as e:
            # Si no existe, mostrar error
            error_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            error_box.add_css_class("ra-empty-state")
            error_box.set_vexpand(True)

            msg = Gtk.Label(
                label=f"No se pudo cargar la playlist Continuidad.\nError: {e}"
            )
            msg.add_css_class("ra-label-error")
            error_box.append(msg)
            self._editor = error_box

        self.append(self._editor)

    def refresh(self):
        """Recargar la playlist Continuidad."""
        if hasattr(self, '_editor') and hasattr(self._editor, 'refresh'):
            self._editor.refresh()
