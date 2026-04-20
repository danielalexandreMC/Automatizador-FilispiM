"""
Radio Automator - Punto de entrada principal.
Fase 6: Interfaz y UX - App pulida para uso diario.
- Sistema de logging con rotacion de archivos
- Notificaciones desktop + toast overlay
- HeaderBar con menu de aplicacion
- Barra de estado mejorada con reloj
- Titulo de ventana dinamico
- Dialogo Acerca De y Atajos de Teclado
"""

import sys
import signal

import gi
gi.require_version('Gtk', '4.0')

from gi.repository import Gtk, Gio, GLib

from radio_automator.core.database import init_db, DATA_DIR
from radio_automator.core.event_bus import get_event_bus
from radio_automator.core.config import get_config
from radio_automator.core.logger import (
    get_log_manager, get_logger, APP_NAME, APP_VERSION
)
from radio_automator.ui.theme import load_theme
from radio_automator.ui.layout import NavigationSidebar
from radio_automator.ui.status_bar import EnhancedStatusBar
from radio_automator.ui.playlists_panel import PlaylistsPanel
from radio_automator.ui.playlist_editor import PlaylistEditor
from radio_automator.ui.continuidad_panel import ContinuidadPanel
from radio_automator.ui.events_panel import EventsPanel
from radio_automator.ui.parrilla_panel import ParrillaPanel
from radio_automator.ui.podcasts_panel import PodcastsPanel
from radio_automator.ui.config_panel import ConfigPanel
from radio_automator.ui.transport_bar import TransportBar
from radio_automator.ui.toast_overlay import ToastOverlay
from radio_automator.ui.about_dialog import show_about_dialog
from radio_automator.ui.shortcuts_dialog import show_shortcuts_dialog
from radio_automator.services.podcast_scheduler import get_podcast_scheduler
from radio_automator.services.audio_engine import get_audio_engine, reset_audio_engine, PlaybackState
from radio_automator.services.play_queue import get_play_queue, reset_play_queue
from radio_automator.services.parrilla_service import get_parrilla_service, reset_parrilla_service
from radio_automator.services.automation_engine import get_automation_engine, reset_automation_engine
from radio_automator.services.notification_service import (
    get_notification_service, reset_notification_service
)


logger = get_logger("main")


class RadioAutomator(Gtk.Application):
    """Aplicacion principal del automatizador de radio."""

    def __init__(self):
        super().__init__(
            application_id='com.radioautomator.app',
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )
        self._window = None
        self._sidebar = None
        self._stack = None
        self._panels = {}
        self._toast_overlay = None
        self._statusbar = None
        self._transport_bar = None
        self._notification_service = None

    def do_shutdown(self):
        """Limpiar recursos al cerrar la aplicacion."""
        logger.info("Cerrando Radio Automator...")

        # Parar servicios
        get_podcast_scheduler().stop()
        get_automation_engine().stop()
        get_parrilla_service().stop_auto_scheduler()
        get_audio_engine().cleanup()

        # Parar notificaciones
        if self._notification_service:
            self._notification_service.unsubscribe_from_events()

        # Parar barra de estado
        if self._statusbar:
            self._statusbar.stop_clock()

        # Cerrar logging
        get_log_manager().shutdown()

        Gtk.Application.do_shutdown(self)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self._setup_actions()
        self._apply_dark_theme()
        # load_theme()

        # Inicializar sistema de logging
        bus = get_event_bus()
        get_log_manager().initialize(
            console_level=0,  # Mostrar todo en consola durante desarrollo
            file_level=10,    # DEBUG en archivo
            event_bus_publish=bus.publish,
        )

    def do_activate(self):
        if not self._window:
            load_theme()
            self._create_window()
        self._window.present()

    def _create_window(self):
        """Crear la ventana principal con HeaderBar, sidebar, stack, transport y toast."""
        self._window = Gtk.ApplicationWindow(
            application=self,
            title=f"{APP_NAME}",
            default_width=1200,
            default_height=800,
        )
        self._window.set_size_request(900, 650)

        # ── HeaderBar ──
        headerbar = Gtk.HeaderBar()
        headerbar.set_show_title_buttons(True)

        # Titulo de ventana
        self._window_title = Gtk.Label(label=APP_NAME)
        self._window_title.add_css_class("title")
        headerbar.set_title_widget(self._window_title)

        # Boton menu de aplicacion
        menu_btn = self._build_menu_button()
        headerbar.pack_end(menu_btn)

        self._window.set_titlebar(headerbar)

        # ── Layout principal con Toast Overlay ──
        # El ToastOverlay envuelve todo el contenido
        self._toast_overlay = ToastOverlay()

        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self._toast_overlay.set_child(main_box)

        # Sidebar
        self._sidebar = NavigationSidebar(on_navigate=self._on_navigate)
        self._sidebar.set_size_request(200, -1)
        main_box.append(self._sidebar)

        # Separador vertical
        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        main_box.append(sep)

        # Area de contenido con Stack
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self._stack.set_hexpand(True)
        self._stack.set_vexpand(True)

        # Crear todos los paneles
        self._panels["eventos"] = EventsPanel()
        self._panels["parrilla"] = ParrillaPanel(events_panel=self._panels["eventos"])
        self._panels["playlists"] = PlaylistsPanel(
            on_playlist_selected=self._on_playlist_selected
        )
        self._panels["continuidad"] = ContinuidadPanel()
        self._panels["podcasts"] = PodcastsPanel()
        self._panels["config"] = ConfigPanel()

        # Anadir paneles al stack
        for panel_id, panel in self._panels.items():
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scroll.set_child(panel)
            self._stack.add_named(scroll, panel_id)

        content_box.append(self._stack)

        # Barra de transporte (debajo del contenido, encima de la status bar)
        self._transport_bar = TransportBar()
        content_box.append(self._transport_bar)

        # Barra de estado mejorada (con reloj)
        self._statusbar = EnhancedStatusBar()
        content_box.append(self._statusbar)

        main_box.append(content_box)

        self._window.set_child(self._toast_overlay)

        # Activar primer panel
        self._stack.set_visible_child_name("playlists")
        self._sidebar.set_active("playlists")

        # ── Inicializar servicios ──
        get_audio_engine()
        get_play_queue()

        # Inicializar servicio de notificaciones y conectar toast overlay
        self._notification_service = get_notification_service()
        self._notification_service.set_on_toast_callback(self._on_toast_notification)
        self._notification_service.subscribe_to_events()

        # Conectar eventos de audio para titulo dinamico
        engine = get_audio_engine()
        engine.set_callbacks(
            on_state_changed=self._on_engine_state_changed,
            on_track_finished=None,
            on_vu_changed=None,
            on_error=self._on_engine_error,
            on_tags_changed=self._on_engine_tags_changed,
        )

        # Publicar evento de inicio
        bus = get_event_bus()
        bus.publish("app.started", {"version": APP_VERSION})

        # Iniciar scheduler de podcasts
        get_podcast_scheduler().start()

        # Notificacion de bienvenida
        self._notification_service.info(
            message="Sistema iniciado correctamente",
            title=APP_NAME,
            timeout_ms=2000,
        )

        logger.info("Aplicacion iniciada correctamente (v%s)", APP_VERSION)
        logger.info("Datos en: %s", DATA_DIR)

        # Parar servicios al cerrar
        self.connect("shutdown", lambda *a: self._on_shutdown())

    def _build_menu_button(self) -> Gtk.MenuButton:
        """Construir el boton de menu de la HeaderBar."""
        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu_btn.add_css_class("ra-menubutton")
        menu_btn.set_tooltip_text("Menu")

        # Crear menu popover
        menu_model = Gio.Menu()

        # Seccion Ayuda
        help_section = Gio.Menu()
        help_section.append("Atajos de teclado", "app.show-shortcuts")
        help_section.append("Acerca de", "app.show-about")
        menu_model.append_section(None, help_section)

        # Seccion Preferencias
        pref_section = Gio.Menu()
        pref_section.append("Configuracion", "app.nav.config")
        menu_model.append_section(None, pref_section)

        menu_btn.set_menu_model(menu_model)
        return menu_btn

    def _on_shutdown(self):
        """Limpieza al cerrar la aplicacion."""
        # Guardar estado de Continuidad si se esta reproduciendo
        automation = get_automation_engine()
        if automation.is_active:
            automation._save_continuidad_state()
            automation.stop()
        get_podcast_scheduler().stop()
        get_parrilla_service().stop_auto_scheduler()
        get_audio_engine().cleanup()
        if self._statusbar:
            self._statusbar.stop_clock()

    # ── Navegacion ──

    def _on_navigate(self, panel_id: str):
        """Cambiar el panel visible."""
        if panel_id in self._panels:
            self._stack.set_visible_child_name(panel_id)
            self._sidebar.set_active(panel_id)

            # Actualizar barra de estado
            names = {
                "parrilla": "Parrilla Semanal",
                "playlists": "Playlists",
                "continuidad": "Continuidad",
                "eventos": "Eventos Programados",
                "podcasts": "Podcasts",
                "config": "Configuracion",
            }
            panel_name = names.get(panel_id, panel_id)
            self._statusbar.set_panel(panel_name)

            # Refrescar panel si es necesario
            panel = self._panels[panel_id]
            if hasattr(panel, 'refresh'):
                panel.refresh()

    def _on_playlist_selected(self, dto):
        """Abrir el editor de una playlist seleccionada."""
        from radio_automator.ui.playlist_editor import PlaylistEditor

        editor = PlaylistEditor(dto, on_back=lambda: self._on_navigate("playlists"))

        old_child = self._stack.get_child_by_name("playlists")
        if old_child:
            self._stack.remove(old_child)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(editor)
        self._stack.add_named(scroll, "playlists")

        self._stack.set_visible_child_name("playlists")

        def restore():
            current_child = self._stack.get_child_by_name("playlists")
            if current_child:
                self._stack.remove(current_child)
            self._panels["playlists"] = PlaylistsPanel(
                on_playlist_selected=self._on_playlist_selected
            )
            new_scroll = Gtk.ScrolledWindow()
            new_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            new_scroll.set_child(self._panels["playlists"])
            self._stack.add_named(new_scroll, "playlists")
            self._on_navigate("playlists")

        editor._on_back = restore

    # ── Titulo de ventana dinamico ──

    def _update_window_title(self, track_title: str = "", track_artist: str = ""):
        """Actualizar el titulo de la ventana con info de reproduccion."""
        if track_title:
            if track_artist:
                title = f"{track_title} - {track_artist}"
            else:
                title = track_title
            self._window_title.set_label(f"{APP_NAME} | {title}")
            self._window.set_title(f"{APP_NAME} - {title}")
        else:
            station = get_config().get("station_name", APP_NAME)
            self._window_title.set_label(station)
            self._window.set_title(station)

    # ── Handlers de audio para titulo dinamico y estado ──

    def _on_engine_state_changed(self, state: PlaybackState):
        """Actualizar titulo y estado cuando cambia el estado del motor."""
        def _update():
            if state == PlaybackState.PLAYING:
                info = get_audio_engine().track_info
                if info and info.title:
                    self._update_window_title(info.title, info.artist or "")
                self._statusbar.set_playback_status("Reproduciendo")
            elif state == PlaybackState.PAUSED:
                self._update_window_title()
                self._statusbar.set_playback_status("En pausa")
            else:
                self._update_window_title()
                self._statusbar.set_playback_status("")

        try:
            GLib.idle_add(_update)
        except Exception:
            _update()

    def _on_engine_position_changed(self, info):
        """Nop para este handler (se usa en transport_bar)."""
        pass

    def _on_engine_error(self, error_msg: str):
        """Notificar errores del motor."""
        logger.error("Error del motor de audio: %s", error_msg)

    def _on_engine_tags_changed(self, info):
        """Actualizar titulo cuando se extraen tags de la pista."""
        def _update():
            if info and info.title:
                self._update_window_title(info.title, info.artist or "")
                self._statusbar.set_playback_status("Reproduciendo")

        try:
            GLib.idle_add(_update)
        except Exception:
            _update()

    # ── Toast notifications ──

    def _on_toast_notification(self, notification):
        """Recibir notificacion del NotificationService y mostrarla en el overlay."""
        if self._toast_overlay:
            self._toast_overlay.show_toast(notification)

    # ── Acciones y atajos ──

    def _setup_actions(self):
        """Configurar acciones de la aplicacion."""
        # Salir
        quit_action = Gio.SimpleAction(name='quit')
        quit_action.connect('activate', lambda *a: self.quit())
        self.add_action(quit_action)

        # Navegacion rapida
        for panel_id in ["parrilla", "playlists", "continuidad", "eventos", "podcasts", "config"]:
            action = Gio.SimpleAction(name=f'nav.{panel_id}')
            action.connect('activate', lambda *a, pid=panel_id: self._on_navigate(pid))
            self.add_action(action)

        # Transporte
        play_action = Gio.SimpleAction(name='transport.play-pause')
        play_action.connect('activate', lambda *a: self._transport_play_pause())
        self.add_action(play_action)

        next_action = Gio.SimpleAction(name='transport.next')
        next_action.connect('activate', lambda *a: self._transport_next())
        self.add_action(next_action)

        prev_action = Gio.SimpleAction(name='transport.prev')
        prev_action.connect('activate', lambda *a: self._transport_prev())
        self.add_action(prev_action)

        stop_action = Gio.SimpleAction(name='transport.stop')
        stop_action.connect('activate', lambda *a: self._transport_stop())
        self.add_action(stop_action)

        # Menu Ayuda
        shortcuts_action = Gio.SimpleAction(name='show-shortcuts')
        shortcuts_action.connect('activate', self._on_show_shortcuts)
        self.add_action(shortcuts_action)

        about_action = Gio.SimpleAction(name='show-about')
        about_action.connect('activate', self._on_show_about)
        self.add_action(about_action)

        # Atajos de teclado
        self.set_accels_for_action('app.quit', ['<Control>q'])
        self.set_accels_for_action('app.nav.parrilla', ['<Control>1'])
        self.set_accels_for_action('app.nav.playlists', ['<Control>2'])
        self.set_accels_for_action('app.nav.continuidad', ['<Control>3'])
        self.set_accels_for_action('app.nav.eventos', ['<Control>4'])
        self.set_accels_for_action('app.nav.podcasts', ['<Control>5'])
        self.set_accels_for_action('app.nav.config', ['<Control>6'])
        self.set_accels_for_action('app.transport.play-pause', ['<ctrl>space'])
        self.set_accels_for_action('app.transport.next', ['<Control>Right'])
        self.set_accels_for_action('app.transport.prev', ['<Control>Left'])
        self.set_accels_for_action('app.transport.stop', ['<Control>s'])
        self.set_accels_for_action('app.show-shortcuts', ['F1'])

    def _transport_play_pause(self):
        if self._transport_bar:
            self._transport_bar._on_play_pause()

    def _transport_next(self):
        if self._transport_bar:
            self._transport_bar._on_next()

    def _transport_prev(self):
        if self._transport_bar:
            self._transport_bar._on_prev()

    def _transport_stop(self):
        if self._transport_bar:
            self._transport_bar._on_stop()

    def _on_show_shortcuts(self, *args):
        show_shortcuts_dialog(self._window)

    def _on_show_about(self, *args):
        show_about_dialog(self._window)

    def _apply_dark_theme(self):
        """Forzar el tema oscuro de GTK."""
        settings = Gtk.Settings.get_default()
        if settings:
            settings.set_property('gtk-application-prefer-dark-theme', True)


def main():
    """Punto de entrada principal."""
    # Inicializar base de datos y datos iniciales
    init_db()

    # Crear y ejecutar la aplicacion
    app = RadioAutomator()

    # Manejar SIGINT (Ctrl+C) para salir limpiamente
    def sigint_handler(*args):
        app.quit()
    signal.signal(signal.SIGINT, sigint_handler)

    try:
        status = app.run(sys.argv)
        sys.exit(status)
    except KeyboardInterrupt:
        app.quit()
        sys.exit(0)


if __name__ == '__main__':
    main()
