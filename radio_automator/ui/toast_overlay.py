"""
Toast Overlay - Capa de notificaciones visuales inline.
Se muestra como overlay en la esquina superior derecha de la ventana principal.
Las notificaciones se apilan verticalmente y se auto-descartan con animacion.

Se integra con NotificationService para recibir notificaciones automaticamente.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Pango

from radio_automator.services.notification_service import (
    Notification, NotificationType, NOTIFICATION_COLORS
)


class ToastWidget(Gtk.Box):
    """
    Widget individual de notificacion toast.
    Muestra titulo, mensaje y boton de cierre con codificacion por color.
    """

    def __init__(self, notification: Notification, on_dismiss=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self._notification = notification
        self._on_dismiss = on_dismiss
        self._timeout_source = None

        # Estilo base
        self.add_css_class("ra-toast-widget")

        # Color por tipo
        colors = NOTIFICATION_COLORS.get(
            notification.type, NOTIFICATION_COLORS[NotificationType.INFO]
        )
        self.add_css_class(f"ra-toast-{notification.type.value}")

        # Margenes
        self.set_margin_start(0)
        self.set_margin_end(0)
        self.set_margin_top(2)
        self.set_margin_bottom(2)

        # Icono
        icon = Gtk.Image.new_from_icon_name(colors["icon"])
        icon.set_icon_size(Gtk.IconSize.NORMAL)
        icon.add_css_class(f"ra-toast-icon-{notification.type.value}")
        self.append(icon)

        # Contenido (titulo + mensaje)
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        content_box.set_hexpand(True)
        content_box.set_valign(Gtk.Align.CENTER)

        if notification.title:
            title_label = Gtk.Label(label=notification.title)
            title_label.set_xalign(0)
            title_label.add_css_class("ra-toast-title")
            title_label.set_ellipsize(Pango.EllipsizeMode.END)
            content_box.append(title_label)

        msg_label = Gtk.Label(label=notification.message)
        msg_label.set_xalign(0)
        msg_label.add_css_class("ra-toast-message")
        msg_label.set_ellipsize(Pango.EllipsizeMode.END)
        msg_label.set_max_width_chars(50)
        msg_label.set_wrap(True)
        msg_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        content_box.append(msg_label)

        self.append(content_box)

        # Boton cerrar
        close_btn = Gtk.Button()
        close_btn.set_icon_name("window-close-symbolic")
        close_btn.add_css_class("ra-toast-close-btn")
        close_btn.set_tooltip_text("Cerrar")
        close_btn.set_valign(Gtk.Align.CENTER)
        close_btn.connect("clicked", self._on_close_clicked)
        self.append(close_btn)

        # Opacidad inicial
        self.set_opacity(0.0)

        # Animacion de entrada
        self._animate_in()

        # Auto-descarte
        if not notification.persistent:
            self._schedule_dismiss(notification.timeout_ms)

    def _animate_in(self):
        """Animacion de entrada: fade in."""
        self._opacity_step = 0
        self._fade_in()

    def _fade_in(self):
        """Paso de animacion fade-in."""
        if self._opacity_step < 5:
            self._opacity_step += 1
            opacity = self._opacity_step / 5.0
            self.set_opacity(opacity)
            GLib.timeout_add(30, self._fade_in)
        else:
            self.set_opacity(1.0)

    def _animate_out(self, callback=None):
        """Animacion de salida: fade out."""
        self._opacity_step = 5
        self._fade_out_cb = callback
        self._fade_out()

    def _fade_out(self):
        """Paso de animacion fade-out."""
        if self._opacity_step > 0:
            self._opacity_step -= 1
            opacity = self._opacity_step / 5.0
            self.set_opacity(opacity)
            GLib.timeout_add(30, self._fade_out)
        else:
            self.set_opacity(0.0)
            if hasattr(self, '_fade_out_cb') and self._fade_out_cb:
                self._fade_out_cb()

    def _schedule_dismiss(self, timeout_ms: int):
        """Programar auto-descarte tras timeout_ms."""
        if timeout_ms > 0:
            self._timeout_source = GLib.timeout_add(timeout_ms, self._auto_dismiss)

    def _auto_dismiss(self) -> bool:
        """Descarte automatico con animacion."""
        self.dismiss()
        return GLib.SOURCE_REMOVE  # No repetir

    def _on_close_clicked(self, _btn=None):
        """Clic en boton de cierre."""
        self._cancel_timeout()
        self.dismiss()

    def _cancel_timeout(self):
        """Cancelar el timeout de auto-descarte."""
        if self._timeout_source is not None:
            GLib.source_remove(self._timeout_source)
            self._timeout_source = None

    def dismiss(self):
        """Iniciar animacion de salida y notificar al overlay."""
        self._cancel_timeout()
        if self._on_dismiss:
            callback = self._on_dismiss
            self._on_dismiss = None
            self._animate_out(callback)
        else:
            self._animate_out()

    @property
    def notification_id(self) -> str:
        return self._notification.id


class ToastOverlay(Gtk.Overlay):
    """
    Overlay de notificaciones toast.
    Se coloca como capa superior sobre el contenido principal y muestra
    las notificaciones en la esquina superior derecha, apiladas verticalmente.

    Uso:
        overlay = ToastOverlay()
        main_content = ...
        overlay.set_child(main_content)
        overlay.show_toast(notification)
    """

    MAX_VISIBLE = 5  # Maximo de toasts visibles simultaneamente
    TOAST_WIDTH = 360  # Ancho maximo de cada toast

    def __init__(self):
        super().__init__()
        self.add_css_class("ra-toast-overlay")

        # Contenedor de toasts (apilados arriba-derecha)
        self._toast_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._toast_box.set_halign(Gtk.Align.END)
        self._toast_box.set_valign(Gtk.Align.START)
        self._toast_box.set_margin_top(8)
        self._toast_box.set_margin_end(8)
        self._toast_box.set_size_request(self.TOAST_WIDTH, -1)

        # Añadir como overlay child
        self.add_overlay(self._toast_box)

        self._active_toasts: dict[str, ToastWidget] = {}

        # Suscribir a eventos de dismiss
        from radio_automator.core.event_bus import get_event_bus
        bus = get_event_bus()
        bus.subscribe("notification.dismiss", self._on_dismiss_event)
        bus.subscribe("notification.dismiss_all", self._on_dismiss_all_event)

    def show_toast(self, notification: Notification) -> ToastWidget:
        """
        Mostrar una notificacion toast.

        Args:
            notification: La notificacion a mostrar.

        Returns:
            El widget ToastWidget creado.
        """
        # Si ya existe, no duplicar
        if notification.id in self._active_toasts:
            return self._active_toasts[notification.id]

        # Limitar numero de toasts visibles
        while len(self._active_toasts) >= self.MAX_VISIBLE:
            oldest_id = next(iter(self._active_toasts))
            oldest = self._active_toasts.pop(oldest_id)
            oldest.dismiss()

        # Crear widget
        toast = ToastWidget(
            notification,
            on_dismiss=lambda nid=notification.id: self._remove_toast(nid)
        )
        toast.set_size_request(self.TOAST_WIDTH, -1)

        self._active_toasts[notification.id] = toast
        self._toast_box.append(toast)

        return toast

    def _remove_toast(self, notification_id: str):
        """Eliminar un toast del overlay tras su animacion de salida."""
        toast = self._active_toasts.pop(notification_id, None)
        if toast:
            try:
                self._toast_box.remove(toast)
            except Exception:
                pass

    def _on_dismiss_event(self, event):
        """Handler: descartar notificacion por ID."""
        nid = event.data.get("id", "")
        if nid and nid in self._active_toasts:
            self._active_toasts[nid].dismiss()

    def _on_dismiss_all_event(self, event):
        """Handler: descartar todas las notificaciones."""
        for toast in list(self._active_toasts.values()):
            toast.dismiss()

    def clear_all(self):
        """Forzar la limpieza de todas las notificaciones."""
        for toast in list(self._active_toasts.values()):
            toast._cancel_timeout()
            try:
                self._toast_box.remove(toast)
            except Exception:
                pass
        self._active_toasts.clear()
