"""
Tema visual oscuro personalizado para Radio Automator.
Colores: Fondo #1A1A1A, Superficie #2D2D2D, Texto #FFFFFF, Acento #E53935.
"""

DARK_CSS = """
/* Radio Automator - Tema Oscuro (GTK 4.6 compatible) */

/* Window */
window { background-color: #1A1A1A; color: #FFFFFF; }
window.background { background-color: #1A1A1A; }

/* HeaderBar */
headerbar { background-color: #2D2D2D; color: #FFFFFF; border-bottom: 1px solid #404040; min-height: 48px; padding: 0 8px; }
headerbar .title { font-weight: 700; font-size: 1.1em; }
headerbar button { border-radius: 4px; color: #FFFFFF; background-color: transparent; border: none; padding: 6px 12px; }
headerbar button:hover { background-color: #383838; }
headerbar button:checked { background-color: #E53935; color: #FFFFFF; }

/* Sidebar */
.ra-sidebar { background-color: #2D2D2D; border-right: 1px solid #404040; }
.ra-sidebar list { background-color: transparent; }
.ra-sidebar row { padding: 10px 16px; border-radius: 4px; margin: 2px 6px; }
.ra-sidebar row:hover { background-color: #383838; }
.ra-sidebar row:selected, .ra-sidebar row:checked { background-color: #E53935; color: #FFFFFF; }
.ra-sidebar row label { color: #FFFFFF; padding: 4px 0; }
.ra-sidebar separator { background-color: #404040; margin: 6px 12px; }

/* Panel */
.ra-panel { background-color: #1A1A1A; padding: 20px; }

/* Card */
.ra-card { background-color: #2D2D2D; border: 1px solid #404040; border-radius: 8px; padding: 16px; }
.ra-card:hover { border-color: #E53935; background-color: #383838; }
.ra-card.selected { border-color: #E53935; border-width: 2px; background-color: #2D1A1A; }
.ra-card-title { font-size: 1.1em; font-weight: 600; color: #FFFFFF; }
.ra-card-subtitle { font-size: 0.85em; color: #B0B0B0; }
.ra-card-info { font-size: 0.8em; color: #707070; margin-top: 4px; }

/* Buttons */
.ra-button { background-color: #2D2D2D; color: #FFFFFF; border: 1px solid #404040; border-radius: 4px; padding: 8px 16px; font-weight: 500; }
.ra-button:hover { background-color: #383838; border-color: #707070; }
.ra-button-primary { background-color: #E53935; color: #FFFFFF; border-color: #E53935; }
.ra-button-primary:hover { background-color: #EF5350; border-color: #EF5350; }
.ra-button-danger { background-color: transparent; color: #E53935; border-color: #E53935; }
.ra-button-danger:hover { background-color: #E53935; color: #FFFFFF; }
.ra-button-sm { padding: 4px 10px; font-size: 0.85em; }

/* Entry */
.ra-entry { background-color: #1A1A1A; color: #FFFFFF; border: 1px solid #404040; border-radius: 4px; padding: 8px 12px; }

/* ComboBox */
.ra-combo { background-color: #1A1A1A; color: #FFFFFF; border: 1px solid #404040; border-radius: 4px; padding: 6px 10px; }

/* ListView */
.ra-listview { background-color: #2D2D2D; border: 1px solid #404040; border-radius: 8px; }
.ra-listview row { padding: 8px 12px; border-bottom: 1px solid #404040; }
.ra-listview row:hover { background-color: #383838; }
.ra-listview row:selected { background-color: #2D1A1A; color: #FFFFFF; }
.ra-listview row:last-child { border-bottom: none; }

/* Scrollbar */
scrollbar { background-color: #1A1A1A; }
scrollbar trough { background-color: transparent; }
scrollbar slider { background-color: #404040; border-radius: 8px; min-width: 8px; min-height: 8px; }
scrollbar slider:hover { background-color: #707070; }
scrollbar button { background-color: transparent; border: none; min-width: 0; min-height: 0; }

/* Labels */
.ra-title { font-size: 1.8em; font-weight: 700; color: #FFFFFF; }
.ra-heading { font-size: 1.2em; font-weight: 600; color: #FFFFFF; }
.ra-subheading { font-size: 1.0em; font-weight: 500; color: #B0B0B0; }
.ra-label { font-size: 0.9em; color: #B0B0B0; }
.ra-label-dim { font-size: 0.85em; color: #707070; }
.ra-label-accent { font-size: 0.9em; color: #E53935; font-weight: 600; }
.ra-label-success { color: #43A047; }
.ra-label-warning { color: #FB8C00; }
.ra-label-error { color: #E53935; }

/* Separator */
.ra-separator { background-color: #404040; min-height: 1px; }

/* StatusBar */
.ra-statusbar { background-color: #2D2D2D; border-top: 1px solid #404040; padding: 4px 12px; font-size: 0.8em; color: #707070; }

/* Badges */
.ra-badge { padding: 2px 8px; border-radius: 12px; font-size: 0.75em; font-weight: 600; }
.ra-badge-loop { background-color: #222D3A; color: #1E88E5; border: 1px solid #2B3342; }
.ra-badge-single { background-color: #223324; color: #43A047; border: 1px solid #2B3B2C; }
.ra-badge-system { background-color: #3A2222; color: #E53935; border: 1px solid #422B2B; }
.ra-badge-streaming { background-color: #3A2E1A; color: #FB8C00; border: 1px solid #423322; }

/* Dialog */
dialog { background-color: #1A1A1A; color: #FFFFFF; border: 1px solid #404040; border-radius: 8px; }
dialog .dialog-vbox { padding: 20px; }
dialog .dialog-action-area { background-color: #2D2D2D; border-top: 1px solid #404040; padding: 12px 20px; }
dialog entry { background-color: #2D2D2D; color: #FFFFFF; border: 1px solid #404040; border-radius: 4px; padding: 8px 12px; }
dialog combobox { background-color: #2D2D2D; color: #FFFFFF; }

/* FileChooser */
filechooser { background-color: #1A1A1A; color: #FFFFFF; }
filechooser placessidebar { background-color: #2D2D2D; }
filechooser .sidebar-row:selected { background-color: #E53935; }

/* Empty state */
.ra-empty-state { color: #707070; font-size: 0.95em; padding: 40px 20px; }

/* Progress */
progressbar { background-color: #1A1A1A; border-radius: 4px; }
progressbar trough { background-color: #2D2D2D; border-radius: 4px; }
progressbar progress { background-color: #E53935; border-radius: 4px; }

/* Toast */
.ra-toast { background-color: #2D2D2D; color: #FFFFFF; border: 1px solid #404040; border-radius: 8px; padding: 10px 16px; font-size: 0.9em; }

/* Transport Bar */
.ra-transport { background-color: #2D2D2D; border-top: 2px solid #404040; padding: 0; }
.ra-transport separator { background-color: #404040; margin: 4px 2px; min-width: 1px; }
.ra-transport #track-title { font-size: 0.95em; font-weight: 600; color: #FFFFFF; }
.ra-transport #track-artist { font-size: 0.8em; color: #707070; }

/* VU Meter */
.ra-vu-bar { border-radius: 3px; border: 1px solid #404040; }

/* Progress Scale */
.ra-progress-scale { background-color: #1A1A1A; border-radius: 3px; min-height: 6px; }
.ra-progress-scale trough { background-color: #1A1A1A; border-radius: 3px; min-height: 6px; }
.ra-progress-scale highlight { background-color: #E53935; border-radius: 3px; min-height: 6px; }
.ra-progress-scale slider { background-color: #FFFFFF; border-radius: 50%; min-width: 12px; min-height: 12px; border: 2px solid #E53935; }

/* Volume Scale */
.ra-volume-scale { background-color: transparent; min-height: 4px; }
.ra-volume-scale trough { background-color: #1A1A1A; border-radius: 2px; min-height: 4px; }
.ra-volume-scale highlight { background-color: #1E88E5; border-radius: 2px; min-height: 4px; }
.ra-volume-scale slider { background-color: #FFFFFF; border-radius: 50%; min-width: 10px; min-height: 10px; border: none; }

/* Toast Overlay */
.ra-toast-overlay { }
.ra-toast-widget { background-color: #2D2D2D; border: 1px solid #404040; border-radius: 8px; padding: 10px 14px; }
.ra-toast-info { border-left: 4px solid #1E88E5; }
.ra-toast-success { border-left: 4px solid #43A047; }
.ra-toast-warning { border-left: 4px solid #FB8C00; }
.ra-toast-error { border-left: 4px solid #E53935; }
.ra-toast-title { font-size: 0.85em; font-weight: 600; color: #FFFFFF; }
.ra-toast-message { font-size: 0.8em; color: #B0B0B0; }
.ra-toast-close-btn { background: transparent; border: none; color: #707070; padding: 2px; min-width: 24px; min-height: 24px; border-radius: 50%; }

/* Enhanced Status Bar */
.ra-statusbar-text { font-size: 0.8em; color: #707070; }
.ra-statusbar-clock { font-size: 0.85em; font-weight: 600; color: #B0B0B0; font-family: monospace; }
.ra-statusbar-separator { color: #404040; font-size: 0.8em; }
.ra-statusbar-live { color: #43A047; font-weight: 500; }
.ra-statusbar-connected { color: #1E88E5; font-weight: 500; }

/* Log Viewer */
.ra-log-viewer { background-color: #1A1A1A; }
.ra-log-list { background-color: #2D2D2D; border: 1px solid #404040; border-radius: 4px; }
.ra-log-list row { padding: 3px 8px; border-bottom: 1px solid #2D2D2D; }
.ra-log-list row:hover { background-color: #383838; }
.ra-log-list row:last-child { border-bottom: none; }

/* Shortcuts */
.ra-shortcut-key { font-family: monospace; font-size: 0.9em; color: #FFFFFF; background-color: #2D2D2D; padding: 3px 8px; border-radius: 4px; border: 1px solid #404040; }

/* Menu Button */
.ra-menubutton { background-color: transparent; border: none; color: #FFFFFF; padding: 4px 8px; border-radius: 4px; }
.ra-menubutton:hover { background-color: #383838; }
.ra-menubutton popover { background-color: #2D2D2D; border: 1px solid #404040; border-radius: 8px; padding: 4px 0; }
.ra-menubutton popover box { background-color: #2D2D2D; }
.ra-menubutton popover button { background-color: transparent; border: none; color: #FFFFFF; padding: 8px 16px; font-size: 0.9em; }
.ra-menubutton popover button:hover { background-color: #383838; }
.ra-menubutton popover separator { background-color: #404040; margin: 4px 0; min-height: 1px; }
"""


def load_theme(provider=None):
    """Cargar el tema oscuro personalizado."""
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk, Gdk

    if provider is None:
        provider = Gtk.CssProvider()

    # Cargar CSS minimo para probar
    provider.load_from_data(DARK_CSS.encode('utf-8'))

    display = Gdk.Display.get_default()
    if display:
        Gtk.StyleContext.add_provider_for_display(
            display, provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    return provider
