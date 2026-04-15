"""
Tema visual oscuro personalizado para Radio Automator.
Colores: Fondo #1A1A1A, Superficie #2D2D2D, Texto #FFFFFF, Acento #E53935.
"""

DARK_CSS = """
/* ═══════════════════════════════════════
   Radio Automator - Tema Oscuro
   ═══════════════════════════════════════ */

/* ── Variables globales ── */
:root {
    --ra-bg: #1A1A1A;
    --ra-surface: #2D2D2D;
    --ra-surface-hover: #383838;
    --ra-surface-active: #424242;
    --ra-border: #404040;
    --ra-text: #FFFFFF;
    --ra-text-secondary: #B0B0B0;
    --ra-text-dim: #707070;
    --ra-accent: #E53935;
    --ra-accent-hover: #EF5350;
    --ra-accent-active: #C62828;
    --ra-success: #43A047;
    --ra-warning: #FB8C00;
    --ra-error: #E53935;
    --ra-info: #1E88E5;
    --ra-radius: 8px;
    --ra-radius-sm: 4px;
    --ra-transition: 150ms ease;
}

/* ── Ventana principal ── */
window {
    background-color: var(--ra-bg);
    color: var(--ra-text);
}

window.background {
    background-color: var(--ra-bg);
}

/* ── HeaderBar ── */
headerbar {
    background-color: var(--ra-surface);
    color: var(--ra-text);
    border-bottom: 1px solid var(--ra-border);
    min-height: 48px;
    padding: 0 8px;
}

headerbar .title {
    font-weight: 700;
    font-size: 1.1em;
    letter-spacing: 0.5px;
}

headerbar button {
    border-radius: var(--ra-radius-sm);
    color: var(--ra-text);
    background-color: transparent;
    border: none;
    padding: 6px 12px;
    transition: all var(--ra-transition);
}

headerbar button:hover {
    background-color: var(--ra-surface-hover);
}

headerbar button:checked {
    background-color: var(--ra-accent);
    color: var(--ra-text);
}

/* ── Sidebar de navegacion ── */
.ra-sidebar {
    background-color: var(--ra-surface);
    border-right: 1px solid var(--ra-border);
}

.ra-sidebar list {
    background-color: transparent;
}

.ra-sidebar row {
    padding: 10px 16px;
    border-radius: var(--ra-radius-sm);
    margin: 2px 6px;
    transition: all var(--ra-transition);
    cursor: pointer;
}

.ra-sidebar row:hover {
    background-color: var(--ra-surface-hover);
}

.ra-sidebar row:selected,
.ra-sidebar row:checked {
    background-color: var(--ra-accent);
    color: var(--ra-text);
}

.ra-sidebar row label {
    color: var(--ra-text);
    padding: 4px 0;
}

.ra-sidebar separator {
    background-color: var(--ra-border);
    margin: 6px 12px;
}

/* ── Paneles de contenido ── */
.ra-panel {
    background-color: var(--ra-bg);
    padding: 20px;
}

.ra-panel-header {
    margin-bottom: 16px;
}

.ra-panel-header .title {
    font-size: 1.5em;
    font-weight: 700;
    color: var(--ra-text);
    margin-bottom: 4px;
}

.ra-panel-header .subtitle {
    font-size: 0.9em;
    color: var(--ra-text-secondary);
}

/* ── Tarjetas ── */
.ra-card {
    background-color: var(--ra-surface);
    border: 1px solid var(--ra-border);
    border-radius: var(--ra-radius);
    padding: 16px;
    transition: all var(--ra-transition);
}

.ra-card:hover {
    border-color: var(--ra-accent);
    background-color: var(--ra-surface-hover);
}

.ra-card.selected {
    border-color: var(--ra-accent);
    border-width: 2px;
    background-color: rgba(229, 57, 53, 0.1);
}

.ra-card-title {
    font-size: 1.1em;
    font-weight: 600;
    color: var(--ra-text);
    margin-bottom: 4px;
}

.ra-card-subtitle {
    font-size: 0.85em;
    color: var(--ra-text-secondary);
}

.ra-card-info {
    font-size: 0.8em;
    color: var(--ra-text-dim);
    margin-top: 4px;
}

/* ── Botones ── */
.ra-button {
    background-color: var(--ra-surface);
    color: var(--ra-text);
    border: 1px solid var(--ra-border);
    border-radius: var(--ra-radius-sm);
    padding: 8px 16px;
    font-weight: 500;
    transition: all var(--ra-transition);
}

.ra-button:hover {
    background-color: var(--ra-surface-hover);
    border-color: var(--ra-text-dim);
}

.ra-button:active {
    background-color: var(--ra-surface-active);
}

.ra-button-primary {
    background-color: var(--ra-accent);
    color: var(--ra-text);
    border-color: var(--ra-accent);
}

.ra-button-primary:hover {
    background-color: var(--ra-accent-hover);
    border-color: var(--ra-accent-hover);
}

.ra-button-primary:active {
    background-color: var(--ra-accent-active);
    border-color: var(--ra-accent-active);
}

.ra-button-danger {
    background-color: transparent;
    color: var(--ra-accent);
    border-color: var(--ra-accent);
}

.ra-button-danger:hover {
    background-color: var(--ra-accent);
    color: var(--ra-text);
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
    background-color: var(--ra-bg);
    color: var(--ra-text);
    border: 1px solid var(--ra-border);
    border-radius: var(--ra-radius-sm);
    padding: 8px 12px;
    caret-color: var(--ra-accent);
    transition: border-color var(--ra-transition);
}

.ra-entry:focus {
    border-color: var(--ra-accent);
    outline: none;
}

.ra-entry::placeholder {
    color: var(--ra-text-dim);
}

.ra-entry:disabled {
    opacity: 0.5;
}

/* ── TextView (multilinea) ── */
.ra-textview {
    background-color: var(--ra-bg);
    color: var(--ra-text);
    border: 1px solid var(--ra-border);
    border-radius: var(--ra-radius-sm);
}

.ra-textview text {
    background-color: transparent;
    color: var(--ra-text);
}

/* ── ComboBox / DropDown ── */
.ra-combo {
    background-color: var(--ra-bg);
    color: var(--ra-text);
    border: 1px solid var(--ra-border);
    border-radius: var(--ra-radius-sm);
    padding: 6px 10px;
}

.ra-combo:focus {
    border-color: var(--ra-accent);
}

/* ── Switch / Toggle ── */
.ra-switch {
    color: var(--ra-text-secondary);
}

/* ── TreeView / ListView ── */
.ra-listview {
    background-color: var(--ra-surface);
    border: 1px solid var(--ra-border);
    border-radius: var(--ra-radius);
}

.ra-listview row {
    padding: 8px 12px;
    border-bottom: 1px solid var(--ra-border);
    transition: background-color var(--ra-transition);
}

.ra-listview row:hover {
    background-color: var(--ra-surface-hover);
}

.ra-listview row:selected {
    background-color: rgba(229, 57, 53, 0.15);
    color: var(--ra-text);
}

.ra-listview row:last-child {
    border-bottom: none;
}

/* ── Drag & Drop visual ── */
.ra-listview row.drag-icon {
    background-color: var(--ra-accent);
    color: var(--ra-text);
    border-radius: var(--ra-radius-sm);
    padding: 4px 12px;
}

.ra-drop-indicator {
    border-top: 2px solid var(--ra-accent);
}

/* ── Scrollbar ── */
scrollbar {
    background-color: var(--ra-bg);
}

scrollbar trough {
    background-color: transparent;
}

scrollbar slider {
    background-color: var(--ra-border);
    border-radius: 8px;
    min-width: 8px;
    min-height: 8px;
}

scrollbar slider:hover {
    background-color: var(--ra-text-dim);
}

scrollbar slider:active {
    background-color: var(--ra-text-secondary);
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
    color: var(--ra-text);
}

.ra-heading {
    font-size: 1.2em;
    font-weight: 600;
    color: var(--ra-text);
}

.ra-subheading {
    font-size: 1.0em;
    font-weight: 500;
    color: var(--ra-text-secondary);
}

.ra-label {
    font-size: 0.9em;
    color: var(--ra-text-secondary);
}

.ra-label-dim {
    font-size: 0.85em;
    color: var(--ra-text-dim);
}

.ra-label-accent {
    font-size: 0.9em;
    color: var(--ra-accent);
    font-weight: 600;
}

.ra-label-success {
    color: var(--ra-success);
}

.ra-label-warning {
    color: var(--ra-warning);
}

.ra-label-error {
    color: var(--ra-error);
}

/* ── Separadores ── */
.ra-separator {
    background-color: var(--ra-border);
    min-height: 1px;
}

/* ── Barra de estado ── */
.ra-statusbar {
    background-color: var(--ra-surface);
    border-top: 1px solid var(--ra-border);
    padding: 4px 12px;
    font-size: 0.8em;
    color: var(--ra-text-dim);
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
    color: var(--ra-info);
    border: 1px solid rgba(30, 136, 229, 0.3);
}

.ra-badge-single {
    background-color: rgba(67, 160, 71, 0.2);
    color: var(--ra-success);
    border: 1px solid rgba(67, 160, 71, 0.3);
}

.ra-badge-system {
    background-color: rgba(229, 57, 53, 0.2);
    color: var(--ra-accent);
    border: 1px solid rgba(229, 57, 53, 0.3);
}

.ra-badge-streaming {
    background-color: rgba(251, 140, 0, 0.2);
    color: var(--ra-warning);
    border: 1px solid rgba(251, 140, 0, 0.3);
}

/* ── Diálogos ── */
dialog {
    background-color: var(--ra-bg);
    color: var(--ra-text);
    border: 1px solid var(--ra-border);
    border-radius: var(--ra-radius);
}

dialog .dialog-vbox {
    padding: 20px;
}

dialog .dialog-action-area {
    background-color: var(--ra-surface);
    border-top: 1px solid var(--ra-border);
    padding: 12px 20px;
}

dialog entry {
    background-color: var(--ra-surface);
    color: var(--ra-text);
    border: 1px solid var(--ra-border);
    border-radius: var(--ra-radius-sm);
    padding: 8px 12px;
}

dialog entry:focus {
    border-color: var(--ra-accent);
}

dialog combobox {
    background-color: var(--ra-surface);
    color: var(--ra-text);
}

/* ── FileChooser ── */
filechooser {
    background-color: var(--ra-bg);
    color: var(--ra-text);
}

filechooser placessidebar {
    background-color: var(--ra-surface);
}

filechooser .sidebar-row:selected {
    background-color: var(--ra-accent);
}

/* ── Empty state ── */
.ra-empty-state {
    color: var(--ra-text-dim);
    font-size: 0.95em;
    padding: 40px 20px;
    text-align: center;
}

.ra-empty-state icon {
    font-size: 3em;
    margin-bottom: 12px;
    opacity: 0.5;
}

/* ── Progreso ── */
progressbar {
    background-color: var(--ra-bg);
    border-radius: 4px;
    overflow: hidden;
}

progressbar trough {
    background-color: var(--ra-surface);
    border-radius: 4px;
}

progressbar progress {
    background-color: var(--ra-accent);
    border-radius: 4px;
}

/* ── Toast / notificaciones inline ── */
.ra-toast {
    background-color: var(--ra-surface);
    color: var(--ra-text);
    border: 1px solid var(--ra-border);
    border-radius: var(--ra-radius);
    padding: 10px 16px;
    font-size: 0.9em;
}

.ra-toast-success {
    border-left: 3px solid var(--ra-success);
}

.ra-toast-error {
    border-left: 3px solid var(--ra-error);
}

.ra-toast-info {
    border-left: 3px solid var(--ra-info);
}

/* ═══════════════════════════════════════
   Barra de transporte
   ═══════════════════════════════════════ */

.ra-transport {
    background-color: var(--ra-surface);
    border-top: 2px solid var(--ra-border);
    padding: 0;
}

.ra-transport separator {
    background-color: var(--ra-border);
    margin: 4px 2px;
    min-width: 1px;
}

.ra-transport #track-title {
    font-size: 0.95em;
    font-weight: 600;
    color: var(--ra-text);
}

.ra-transport #track-artist {
    font-size: 0.8em;
    color: var(--ra-text-dim);
}

/* ── VU Meter bars ── */
.ra-vu-bar {
    border-radius: 3px;
    border: 1px solid var(--ra-border);
    overflow: hidden;
}

/* ── Progress scale ── */
.ra-progress-scale {
    background-color: var(--ra-bg);
    border-radius: 3px;
    min-height: 6px;
}

.ra-progress-scale trough {
    background-color: var(--ra-bg);
    border-radius: 3px;
    min-height: 6px;
}

.ra-progress-scale highlight {
    background-color: var(--ra-accent);
    border-radius: 3px;
    min-height: 6px;
}

.ra-progress-scale slider {
    background-color: var(--ra-text);
    border-radius: 50%;
    min-width: 12px;
    min-height: 12px;
    border: 2px solid var(--ra-accent);
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
    background-color: var(--ra-bg);
    border-radius: 2px;
    min-height: 4px;
}

.ra-volume-scale highlight {
    background-color: var(--ra-info);
    border-radius: 2px;
    min-height: 4px;
}

.ra-volume-scale slider {
    background-color: var(--ra-text);
    border-radius: 50%;
    min-width: 10px;
    min-height: 10px;
    border: none;
}

/* ═══════════════════════════════════════
   Toast Overlay (Fase 6)
   ═══════════════════════════════════════ */

.ra-toast-overlay {
    pointer-events: none;
}

.ra-toast-overlay > box {
    pointer-events: auto;
}

/* ── Toast Widget individual ── */
.ra-toast-widget {
    background-color: var(--ra-surface);
    border: 1px solid var(--ra-border);
    border-radius: var(--ra-radius);
    padding: 10px 14px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
    transition: opacity 150ms ease, transform 200ms ease;
}

.ra-toast-widget image {
    margin-right: 2px;
}

/* ── Toast por tipo: borde de color ── */
.ra-toast-info {
    border-left: 4px solid var(--ra-info);
}
.ra-toast-info .ra-toast-icon-info {
    color: var(--ra-info);
}

.ra-toast-success {
    border-left: 4px solid var(--ra-success);
}
.ra-toast-success .ra-toast-icon-success {
    color: var(--ra-success);
}

.ra-toast-warning {
    border-left: 4px solid var(--ra-warning);
}
.ra-toast-warning .ra-toast-icon-warning {
    color: var(--ra-warning);
}

.ra-toast-error {
    border-left: 4px solid var(--ra-error);
}
.ra-toast-error .ra-toast-icon-error {
    color: var(--ra-error);
}

/* ── Toast interno ── */
.ra-toast-title {
    font-size: 0.85em;
    font-weight: 600;
    color: var(--ra-text);
}

.ra-toast-message {
    font-size: 0.8em;
    color: var(--ra-text-secondary);
}

.ra-toast-close-btn {
    background: transparent;
    border: none;
    color: var(--ra-text-dim);
    padding: 2px;
    min-width: 24px;
    min-height: 24px;
    border-radius: 50%;
}

.ra-toast-close-btn:hover {
    background-color: var(--ra-surface-hover);
    color: var(--ra-text);
}

/* ═══════════════════════════════════════
   Enhanced Status Bar (Fase 6)
   ═══════════════════════════════════════ */

.ra-statusbar-text {
    font-size: 0.8em;
    color: var(--ra-text-dim);
}

.ra-statusbar-clock {
    font-size: 0.85em;
    font-weight: 600;
    color: var(--ra-text-secondary);
    font-family: monospace;
    letter-spacing: 0.5px;
}

.ra-statusbar-separator {
    color: var(--ra-border);
    font-size: 0.8em;
}

.ra-statusbar-live {
    color: var(--ra-success);
    font-weight: 500;
}

.ra-statusbar-connected {
    color: var(--ra-info);
    font-weight: 500;
}

/* ═══════════════════════════════════════
   Log Viewer (Fase 6)
   ═══════════════════════════════════════ */

.ra-log-viewer {
    background-color: var(--ra-bg);
    padding: 0;
}

.ra-log-list {
    background-color: var(--ra-surface);
    border: 1px solid var(--ra-border);
    border-radius: var(--ra-radius-sm);
}

.ra-log-list row {
    padding: 3px 8px;
    border-bottom: 1px solid rgba(64, 64, 64, 0.3);
    transition: background-color var(--ra-transition);
}

.ra-log-list row:hover {
    background-color: var(--ra-surface-hover);
}

.ra-log-list row:last-child {
    border-bottom: none;
}

.ra-log-level-bar {
    border-radius: 2px;
}

/* ═══════════════════════════════════════
   Shortcuts Dialog (Fase 6)
   ═══════════════════════════════════════ */

.ra-shortcut-key {
    font-family: monospace;
    font-size: 0.9em;
    color: var(--ra-text);
    background-color: var(--ra-surface);
    padding: 3px 8px;
    border-radius: var(--ra-radius-sm);
    border: 1px solid var(--ra-border);
}

/* ═══════════════════════════════════════
   HeaderBar Menu (Fase 6)
   ═══════════════════════════════════════ */

.ra-menubutton {
    background-color: transparent;
    border: none;
    color: var(--ra-text);
    padding: 4px 8px;
    border-radius: var(--ra-radius-sm);
}

.ra-menubutton:hover {
    background-color: var(--ra-surface-hover);
}

.ra-menubutton popover {
    background-color: var(--ra-surface);
    border: 1px solid var(--ra-border);
    border-radius: var(--ra-radius);
    padding: 4px 0;
}

.ra-menubutton popover box {
    background-color: var(--ra-surface);
}

.ra-menubutton popover button {
    background-color: transparent;
    border: none;
    color: var(--ra-text);
    padding: 8px 16px;
    font-size: 0.9em;
    border-radius: 0;
}

.ra-menubutton popover button:hover {
    background-color: var(--ra-surface-hover);
}

.ra-menubutton popover separator {
    background-color: var(--ra-border);
    margin: 4px 0;
    min-height: 1px;
}
"""


def load_theme(provider: "Gtk.CssProvider | None" = None) -> "Gtk.CssProvider":
    """Cargar el tema oscuro personalizado y devolver el CssProvider."""
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk

    if provider is None:
        provider = Gtk.CssProvider()
    provider.load_from_data(DARK_CSS.encode('utf-8'))

    # Aplicar al display por defecto
    display = Gtk.Display.get_default()
    if display:
        style_context = Gtk.StyleContext()
        style_context.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    return provider
