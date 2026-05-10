"""
Tema visual oscuro personalizado para Radio Automator.
Colores: Fondo #1A1A1A, Superficie #2D2D2D, Texto #FFFFFF, Acento #E53935.
"""

DARK_CSS = """
/* ═══════════════════════════════════════
   Radio Automator - Tema Oscuro
   Compatible con GTK 4.6 (Debian 12)
   Colores literais (sen var() - GTK 4.6
   non soporta CSS custom properties)
   ═══════════════════════════════════════ */

/* ── Ventana principal ── */
window {
    background-color: #1A1A1A;
    color: #FFFFFF;
}

window.background {
    background-color: #1A1A1A;
}

/* ── HeaderBar ── */
headerbar {
    background-color: #2D2D2D;
    color: #FFFFFF;
    border-bottom: 1px solid #404040;
    min-height: 48px;
    padding: 0 8px;
}

headerbar .title {
    font-weight: 700;
    font-size: 1.1em;
    letter-spacing: 0.5px;
}

headerbar button {
    border-radius: 4px;
    color: #FFFFFF;
    background-color: transparent;
    border: none;
    padding: 6px 12px;
}

headerbar button:hover {
    background-color: #383838;
}

headerbar button:checked {
    background-color: #E53935;
    color: #FFFFFF;
}

/* ── Sidebar de navegacion ── */
.ra-sidebar {
    background-color: #2D2D2D;
    border-right: 1px solid #404040;
}

.ra-sidebar list {
    background-color: transparent;
}

.ra-sidebar row {
    padding: 10px 16px;
    border-radius: 4px;
    margin: 2px 6px;
}

.ra-sidebar row:hover {
    background-color: #383838;
}

.ra-sidebar row:selected,
.ra-sidebar row:checked {
    background-color: #E53935;
    color: #FFFFFF;
}

.ra-sidebar row label {
    color: #FFFFFF;
    padding: 4px 0;
}

.ra-sidebar separator {
    background-color: #404040;
    margin: 6px 12px;
}

/* ── Paneles de contenido ── */
.ra-panel {
    background-color: #1A1A1A;
    padding: 20px 28px;
}

.ra-panel-header {
    margin-bottom: 16px;
}

.ra-panel-header .title {
    font-size: 1.5em;
    font-weight: 700;
    color: #FFFFFF;
    margin-bottom: 4px;
}

.ra-panel-header .subtitle {
    font-size: 0.9em;
    color: #B0B0B0;
}

/* ── Tarjetas ── */
.ra-card {
    background-color: #2D2D2D;
    border: 1px solid #404040;
    border-radius: 8px;
    padding: 16px;
}

.ra-card:hover {
    border-color: #E53935;
    background-color: #383838;
}

.ra-card.selected {
    border-color: #E53935;
    border-width: 2px;
    background-color: rgba(229, 57, 53, 0.1);
}

/* ── Fila reproducíndose (Continuidad) ── */
.ra-row-playing {
    background-color: rgba(229, 57, 53, 0.20);
    border-left: 3px solid #E53935;
    border-radius: 4px;
}

.ra-row-playing .ra-label-dim {
    color: #E53935;
}

.ra-card-title {
    font-size: 1.1em;
    font-weight: 600;
    color: #FFFFFF;
    margin-bottom: 4px;
}

.ra-card-subtitle {
    font-size: 0.85em;
    color: #B0B0B0;
}

.ra-card-info {
    font-size: 0.8em;
    color: #707070;
    margin-top: 4px;
}

/* ── Botones ── */
.ra-button {
    background-color: #2D2D2D;
    color: #FFFFFF;
    border: 1px solid #404040;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: 500;
}

.ra-button:hover {
    background-color: #383838;
    border-color: #707070;
}

.ra-button:active {
    background-color: #424242;
}

.ra-button:checked {
    background-color: #E53935;
    color: #FFFFFF;
    border-color: #C62828;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.15);
}

.ra-button:checked:hover {
    background-color: #EF5350;
    border-color: #E53935;
}

.ra-button-primary {
    background-color: #E53935;
    color: #FFFFFF;
    border-color: #E53935;
}

.ra-button-primary:hover {
    background-color: #EF5350;
    border-color: #EF5350;
}

.ra-button-primary:active {
    background-color: #C62828;
    border-color: #C62828;
}

.ra-button-danger {
    background-color: transparent;
    color: #E53935;
    border-color: #E53935;
}

.ra-button-danger:hover {
    background-color: #E53935;
    color: #FFFFFF;
}

.ra-button-sm {
    padding: 4px 10px;
    font-size: 0.85em;
}

.ra-button-icon {
    padding: 6px;
    min-width: 32px;
    min-height: 32px;
}

/* ── Entradas de texto ── */
.ra-entry {
    background-color: #1A1A1A;
    color: #FFFFFF;
    border: 1px solid #404040;
    border-radius: 4px;
    padding: 8px 12px;
}

.ra-entry:disabled {
    opacity: 0.5;
}

/* ── TextView (multilinea) ── */
.ra-textview {
    background-color: #1A1A1A;
    color: #FFFFFF;
    border: 1px solid #404040;
    border-radius: 4px;
}

.ra-textview text {
    background-color: transparent;
    color: #FFFFFF;
}

/* ── ComboBox / DropDown ── */
.ra-combo {
    background-color: #1A1A1A;
    color: #FFFFFF;
    border: 1px solid #404040;
    border-radius: 4px;
    padding: 6px 10px;
}

/* ── Switch / Toggle ── */
.ra-switch {
    color: #B0B0B0;
}

/* ── TreeView / ListView ── */
.ra-listview {
    background-color: #2D2D2D;
    border: 1px solid #404040;
    border-radius: 8px;
}

.ra-listview row {
    padding: 8px 12px;
    border-bottom: 1px solid #404040;
}

.ra-listview row:hover {
    background-color: #383838;
}

.ra-listview row:selected {
    background-color: rgba(229, 57, 53, 0.15);
    color: #FFFFFF;
}

.ra-listview row:last-child {
    border-bottom: none;
}

/* ── Drag & Drop visual ── */
.ra-listview row.drag-icon {
    background-color: #E53935;
    color: #FFFFFF;
    border-radius: 4px;
    padding: 4px 12px;
}

.ra-drop-indicator {
    border-top: 2px solid #E53935;
}

/* ── Scrollbar ── */
scrollbar {
    background-color: #1A1A1A;
}

scrollbar trough {
    background-color: transparent;
}

scrollbar slider {
    background-color: #404040;
    border-radius: 8px;
    min-width: 8px;
    min-height: 8px;
}

scrollbar slider:hover {
    background-color: #707070;
}

scrollbar slider:active {
    background-color: #B0B0B0;
}

scrollbar button {
    background-color: transparent;
    border: none;
    min-width: 0;
    min-height: 0;
}

/* ── Label estilos ── */
.ra-title {
    font-size: 1.8em;
    font-weight: 700;
    color: #FFFFFF;
}

.ra-heading {
    font-size: 1.2em;
    font-weight: 600;
    color: #FFFFFF;
}

.ra-subheading {
    font-size: 1.0em;
    font-weight: 500;
    color: #B0B0B0;
}

.ra-label {
    font-size: 0.9em;
    color: #B0B0B0;
}

.ra-label-dim {
    font-size: 0.85em;
    color: #707070;
}

.ra-label-accent {
    font-size: 0.9em;
    color: #E53935;
    font-weight: 600;
}

.ra-label-success {
    color: #43A047;
}

.ra-label-warning {
    color: #FB8C00;
}

.ra-label-error {
    color: #E53935;
}

/* ── Separadores ── */
.ra-separator {
    background-color: #404040;
    min-height: 1px;
}

/* ── Barra de estado ── */
.ra-statusbar {
    background-color: #2D2D2D;
    border-top: 1px solid #404040;
    padding: 4px 12px;
    font-size: 0.8em;
    color: #707070;
}

/* ── Modo Playlist (loop/single) badge ── */
.ra-badge {
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.75em;
    font-weight: 600;
}

.ra-badge-loop {
    background-color: rgba(30, 136, 229, 0.2);
    color: #1E88E5;
    border: 1px solid rgba(30, 136, 229, 0.3);
}

.ra-badge-single {
    background-color: rgba(67, 160, 71, 0.2);
    color: #43A047;
    border: 1px solid rgba(67, 160, 71, 0.3);
}

.ra-badge-system {
    background-color: rgba(229, 57, 53, 0.2);
    color: #E53935;
    border: 1px solid rgba(229, 57, 53, 0.3);
}

.ra-badge-streaming {
    background-color: rgba(251, 140, 0, 0.2);
    color: #FB8C00;
    border: 1px solid rgba(251, 140, 0, 0.3);
}

/* ── Dialogos ── */
dialog {
    background-color: #1A1A1A;
    color: #FFFFFF;
    border: 1px solid #404040;
    border-radius: 8px;
}

dialog .dialog-vbox {
    padding: 20px;
}

dialog .dialog-action-area {
    background-color: #2D2D2D;
    border-top: 1px solid #404040;
    padding: 12px 20px;
}

dialog entry {
    background-color: #2D2D2D;
    color: #FFFFFF;
    border: 1px solid #404040;
    border-radius: 4px;
    padding: 8px 12px;
}

dialog combobox {
    background-color: #2D2D2D;
    color: #FFFFFF;
}

/* ── FileChooser ── */
filechooser {
    background-color: #1A1A1A;
    color: #FFFFFF;
}

filechooser placessidebar {
    background-color: #2D2D2D;
}

filechooser .sidebar-row:selected {
    background-color: #E53935;
}

/* ── Empty state ── */
.ra-empty-state {
    color: #707070;
    font-size: 0.95em;
    padding: 40px 20px;
}

.ra-empty-state icon {
    font-size: 3em;
    margin-bottom: 12px;
    opacity: 0.5;
}

/* ── Progreso ── */
progressbar {
    background-color: #1A1A1A;
    border-radius: 4px;
}

progressbar trough {
    background-color: #2D2D2D;
    border-radius: 4px;
}

progressbar progress {
    background-color: #E53935;
    border-radius: 4px;
}

/* ── Toast / notificaciones inline ── */
.ra-toast {
    background-color: #2D2D2D;
    color: #FFFFFF;
    border: 1px solid #404040;
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 0.9em;
}

.ra-toast-success {
    border-left: 3px solid #43A047;
}

.ra-toast-error {
    border-left: 3px solid #E53935;
}

.ra-toast-info {
    border-left: 3px solid #1E88E5;
}

/* ═══════════════════════════════════════
   Barra de transporte
   ═══════════════════════════════════════ */

.ra-transport {
    background-color: #2D2D2D;
    border-top: 2px solid #404040;
    padding: 0;
}

.ra-transport separator {
    background-color: #404040;
    margin: 4px 2px;
    min-width: 1px;
}

.ra-transport #track-title {
    font-size: 0.95em;
    font-weight: 600;
    color: #FFFFFF;
}

.ra-transport #track-artist {
    font-size: 0.8em;
    color: #707070;
}

/* ── Time display ── */
.ra-time-display {
    font-size: 1.15em;
    font-weight: 600;
    color: #B0B0B0;
    letter-spacing: 0.8px;
    padding: 2px 8px;
    border-radius: 4px;
}

.ra-time-display:hover {
    color: #FFFFFF;
    background-color: #383838;
}

/* ── VU Meter bars ── */
.ra-vu-bar {
    border-radius: 3px;
    border: 1px solid #404040;
}

/* ── Progress scale ── */
.ra-progress-scale {
    background-color: #1A1A1A;
    border-radius: 3px;
    min-height: 6px;
}

.ra-progress-scale trough {
    background-color: #1A1A1A;
    border-radius: 3px;
    min-height: 6px;
}

.ra-progress-scale highlight {
    background-color: #E53935;
    border-radius: 3px;
    min-height: 6px;
}

.ra-progress-scale slider {
    background-color: #FFFFFF;
    border-radius: 50%;
    min-width: 12px;
    min-height: 12px;
    border: 2px solid #E53935;
}

.ra-progress-scale:disabled {
    opacity: 0.5;
}

/* ── Volume scale ── */
.ra-volume-scale {
    background-color: transparent;
    min-height: 4px;
}

.ra-volume-scale trough {
    background-color: #1A1A1A;
    border-radius: 2px;
    min-height: 4px;
}

.ra-volume-scale highlight {
    background-color: #1E88E5;
    border-radius: 2px;
    min-height: 4px;
}

.ra-volume-scale slider {
    background-color: #FFFFFF;
    border-radius: 50%;
    min-width: 10px;
    min-height: 10px;
    border: none;
}

/* ═══════════════════════════════════════
   Toast Overlay
   ═══════════════════════════════════════ */

/* ── Toast Widget individual ── */
.ra-toast-widget {
    background-color: #2D2D2D;
    border: 1px solid #404040;
    border-radius: 8px;
    padding: 10px 14px;
}

.ra-toast-widget image {
    margin-right: 2px;
}

/* ── Toast por tipo: borde de color ── */
.ra-toast-info {
    border-left: 4px solid #1E88E5;
}

.ra-toast-info .ra-toast-icon-info {
    color: #1E88E5;
}

.ra-toast-success {
    border-left: 4px solid #43A047;
}

.ra-toast-success .ra-toast-icon-success {
    color: #43A047;
}

.ra-toast-warning {
    border-left: 4px solid #FB8C00;
}

.ra-toast-warning .ra-toast-icon-warning {
    color: #FB8C00;
}

.ra-toast-error {
    border-left: 4px solid #E53935;
}

.ra-toast-error .ra-toast-icon-error {
    color: #E53935;
}

/* ── Toast interno ── */
.ra-toast-title {
    font-size: 0.85em;
    font-weight: 600;
    color: #FFFFFF;
}

.ra-toast-message {
    font-size: 0.8em;
    color: #B0B0B0;
}

.ra-toast-close-btn {
    background: transparent;
    border: none;
    color: #707070;
    padding: 2px;
    min-width: 24px;
    min-height: 24px;
    border-radius: 50%;
}

.ra-toast-close-btn:hover {
    background-color: #383838;
    color: #FFFFFF;
}

/* ═══════════════════════════════════════
   Enhanced Status Bar
   ═══════════════════════════════════════ */

.ra-statusbar-text {
    font-size: 0.8em;
    color: #707070;
}

.ra-statusbar-clock {
    font-size: 0.85em;
    font-weight: 600;
    color: #B0B0B0;
    font-family: monospace;
    letter-spacing: 0.5px;
}

.ra-statusbar-separator {
    color: #404040;
    font-size: 0.8em;
}

.ra-statusbar-live {
    color: #43A047;
    font-weight: 500;
}

.ra-statusbar-connected {
    color: #1E88E5;
    font-weight: 500;
}

/* ═══════════════════════════════════════
   Log Viewer
   ═══════════════════════════════════════ */

.ra-log-viewer {
    background-color: #1A1A1A;
    padding: 0;
}

.ra-log-list {
    background-color: #2D2D2D;
    border: 1px solid #404040;
    border-radius: 4px;
}

.ra-log-list row {
    padding: 3px 8px;
    border-bottom: 1px solid rgba(64, 64, 64, 0.3);
}

.ra-log-list row:hover {
    background-color: #383838;
}

.ra-log-list row:last-child {
    border-bottom: none;
}

.ra-log-level-bar {
    border-radius: 2px;
}

/* ═══════════════════════════════════════
   Shortcuts Dialog
   ═══════════════════════════════════════ */

.ra-shortcut-key {
    font-family: monospace;
    font-size: 0.9em;
    color: #FFFFFF;
    background-color: #2D2D2D;
    padding: 3px 8px;
    border-radius: 4px;
    border: 1px solid #404040;
}

/* ═══════════════════════════════════════
   HeaderBar Menu
   ═══════════════════════════════════════ */

.ra-menubutton {
    background-color: transparent;
    border: none;
    color: #FFFFFF;
    padding: 4px 8px;
    border-radius: 4px;
}

.ra-menubutton:hover {
    background-color: #383838;
}

.ra-menubutton popover {
    background-color: #2D2D2D;
    border: 1px solid #404040;
    border-radius: 8px;
    padding: 4px 0;
}

.ra-menubutton popover box {
    background-color: #2D2D2D;
}

.ra-menubutton popover button {
    background-color: transparent;
    border: none;
    color: #FFFFFF;
    padding: 8px 16px;
    font-size: 0.9em;
    border-radius: 0;
}

.ra-menubutton popover button:hover {
    background-color: #383838;
}

.ra-menubutton popover separator {
    background-color: #404040;
    margin: 4px 0;
    min-height: 1px;
}
"""


def load_theme(provider: "Gtk.CssProvider | None" = None) -> "Gtk.CssProvider":
    """Cargar el tema oscuro personalizado y devolver el CssProvider."""
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk, Gdk

    if provider is None:
        provider = Gtk.CssProvider()
    provider.load_from_data(DARK_CSS.encode('utf-8'))

    # Aplicar al display por defecto (Gdk.Display en GTK 4)
    try:
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
    except Exception as e:
        print(f"[Theme] Aviso: non se puido aplicar o tema ao display: {e}")

    return provider
