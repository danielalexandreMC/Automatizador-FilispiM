"""
Barra de estado mejorada para Radio Automator.
Incluye reloj en tiempo real, indicador de panel activo,
info de reproduccion y conectores para notificaciones.

Reemplaza la StatusBar original de layout.py con funcionalidad extendida.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Pango

from datetime import datetime


class EnhancedStatusBar(Gtk.Box):
    """
    Barra de estado extendida con tres secciones:
    - Izquierda: Panel activo + estado del motor
    - Centro: Reloj en tiempo real
    - Derecha: Info adicional (conexion, duracion reproduccion)
    """

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.add_css_class("ra-statusbar")

        # ── Seccion izquierda: panel + estado ──
        left_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        left_box.set_hexpand(True)

        self._panel_label = Gtk.Label(label="Listo")
        self._panel_label.set_xalign(0)
        self._panel_label.add_css_class("ra-statusbar-text")
        left_box.append(self._panel_label)

        # Separador sutil
        sep = Gtk.Label(label="|")
        sep.add_css_class("ra-statusbar-separator")
        left_box.append(sep)

        self._playback_label = Gtk.Label(label="")
        self._playback_label.set_xalign(0)
        self._playback_label.add_css_class("ra-statusbar-text")
        left_box.append(self._playback_label)

        self.append(left_box)

        # ── Seccion central: reloj ──
        self._clock_label = Gtk.Label(label="")
        self._clock_label.set_xalign(0.5)
        self._clock_label.add_css_class("ra-statusbar-clock")
        self.append(self._clock_label)

        # ── Seccion derecha: info extra ──
        right_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self._connection_label = Gtk.Label(label="")
        self._connection_label.set_xalign(1)
        self._connection_label.add_css_class("ra-statusbar-text")
        right_box.append(self._connection_label)

        self.append(right_box)

        # ── Iniciar reloj ──
        self._clock_running = True
        self._update_clock()

    def _update_clock(self):
        """Actualizar el reloj cada segundo."""
        if not self._clock_running:
            return
        now = datetime.now()
        self._clock_label.set_label(now.strftime("%H:%M:%S"))
        GLib.timeout_add_seconds(1, self._update_clock)

    def set_panel(self, name: str):
        """Actualizar el nombre del panel activo."""
        self._panel_label.set_label(name)

    def set_playback_status(self, text: str):
        """Actualizar el estado de reproduccion."""
        self._playback_label.set_label(text)
        if text:
            self._playback_label.add_css_class("ra-statusbar-live")
        else:
            self._playback_label.remove_css_class("ra-statusbar-live")

    def set_connection_info(self, text: str):
        """Actualizar informacion de conexion (ej: stream activo)."""
        self._connection_label.set_label(text)
        if text:
            self._connection_label.add_css_class("ra-statusbar-connected")
        else:
            self._connection_label.remove_css_class("ra-statusbar-connected")

    def set_text(self, left: str = "", center: str = "", right: str = ""):
        """
        Compatibilidad con la interfaz anterior de StatusBar.
        left -> panel, center -> clock (no sobreescribir), right -> connection.
        """
        if left:
            self.set_panel(left)
        if right:
            self.set_connection_info(right)

    def stop_clock(self):
        """Detener el reloj (al cerrar la app)."""
        self._clock_running = False

    def start_clock(self):
        """Reanudar el reloj."""
        if not self._clock_running:
            self._clock_running = True
            self._update_clock()
