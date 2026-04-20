"""
Panel de configuracion del sistema.
Ajustes basicos de la emisora y reproduccion.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GLib

from radio_automator.core.config import get_config

from radio_automator.ui.file_dialogs import open_file_chooser

class ConfigPanel(Gtk.Box):
    """Panel de configuracion del sistema."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("ra-panel")
        self._config = get_config()

        self._build_ui()
        self._load_values()

    def _build_ui(self):
        # Titulo
        title = Gtk.Label(label="Configuracion")
        title.add_css_class("ra-title")
        title.set_xalign(0)
        title.set_margin_bottom(4)
        self.append(title)

        subtitle = Gtk.Label(label="Ajustes generales del sistema")
        subtitle.add_css_class("ra-subheading")
        subtitle.set_xalign(0)
        subtitle.set_margin_bottom(16)
        self.append(subtitle)

        # Scroll para todo el contenido
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        scroll.set_child(content)
        self.append(scroll)

        # ── Seccion: Emisora ──
        content.append(self._section_label("📻 Emisora"))

        # Nombre de la emisora
        self._station_name_entry = self._text_row(
            "Nombre de la emisora:", "station_name", "Mi Emisora"
        )
        content.append(self._station_name_entry)

        # Carpeta de musica
        folder_row = self._folder_row(
            "Carpeta de musica:", "music_folder"
        )
        content.append(folder_row)

        # ── Seccion: Reproduccion ──
        content.append(self._section_label("🔊 Reproduccion"))

        # Duracion del crossfade
        self._crossfade_spin = self._spin_row(
            "Duracion del crossfade (seg):", "crossfade_duration", 0.0, 15.0, 0.5, 3.0
        )
        content.append(self._crossfade_spin)

        # Curva del crossfade
        self._crossfade_combo = self._combo_row(
            "Curva del crossfade:", "crossfade_curve",
            ["linear", "logarithmic", "sigmoid"],
            ["Lineal", "Logaritmica", "Sigmoide"],
        )
        content.append(self._crossfade_combo)

        # Deteccion de silencio
        self._silence_switch = self._switch_row(
            "Deteccion de silencio:", "silence_detection", True
        )
        content.append(self._silence_switch)

        # Normalizacion
        self._norm_switch = self._switch_row(
            "Normalizacion de audio:", "normalization", False
        )
        content.append(self._norm_switch)

        # ── Seccion: Podcasts ──
        content.append(self._section_label("📡 Podcasts"))

        # Intervalo de comprobacion
        self._podcast_interval = self._spin_row(
            "Intervalo de comprobacion (horas):", "podcast_check_interval_hours",
            1, 168, 1, 24
        )
        content.append(self._podcast_interval)

        # Descargas simultaneas
        self._podcast_downloads = self._spin_row(
            "Descargas simultaneas:", "podcast_max_concurrent_downloads",
            1, 10, 1, 3
        )
        content.append(self._podcast_downloads)

        # ── Boton guardar ──
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_margin_top(12)

        save_btn = Gtk.Button(label="💾 Guardar configuracion")
        save_btn.add_css_class("ra-button-primary")
        save_btn.add_css_class("ra-button")
        save_btn.connect("clicked", self._save)
        btn_box.append(save_btn)

        status = Gtk.Label(label="")
        status.add_css_class("ra-label")
        btn_box.append(status)
        self._status_label = status

        content.append(btn_box)

        # ── Separador ──
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(24)
        sep.set_margin_bottom(8)
        content.append(sep)

        # ── Seccion: Visor de Logs (Fase 6) ──
        from radio_automator.ui.log_viewer import LogViewer
        self._log_viewer = LogViewer()
        self._log_viewer.set_margin_top(16)
        content.append(self._log_viewer)

    def refresh(self):
        """Refrescar el panel de configuracion (incluye log viewer)."""
        if hasattr(self, '_log_viewer'):
            self._log_viewer.refresh()

    def _section_label(self, text: str) -> Gtk.Label:
        label = Gtk.Label(label=text)
        label.add_css_class("ra-heading")
        label.set_xalign(0)
        label.set_margin_top(8)
        label.set_margin_bottom(4)
        return label

    def _text_row(self, label_text: str, config_key: str,
                  placeholder: str = "") -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        label = Gtk.Label(label=label_text)
        label.set_width_chars(28)
        label.set_xalign(0)
        row.append(label)

        entry = Gtk.Entry()
        entry.set_placeholder_text(placeholder)
        entry.add_css_class("ra-entry")
        entry.set_hexpand(True)
        entry.config_key = config_key  # type: ignore[attr-defined]
        row.append(entry)

        return row

    def _folder_row(self, label_text: str, config_key: str) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        label = Gtk.Label(label=label_text)
        label.set_width_chars(28)
        label.set_xalign(0)
        row.append(label)

        path_label = Gtk.Label(label="")
        path_label.set_hexpand(True)
        path_label.set_xalign(0)
        path_label.set_ellipsize(3)  # Pango.EllipsizeMode.MIDDLE
        path_label.config_key = config_key  # type: ignore[attr-defined]
        row.append(path_label)

        browse_btn = Gtk.Button(label="📂")
        browse_btn.add_css_class("ra-button")
        browse_btn.set_tooltip_text("Seleccionar carpeta")

        def on_browse(btn):
            root = self.get_root() or None
            folders = open_file_chooser(
                root, "Seleccionar carpeta",
                action=Gtk.FileChooserAction.SELECT_FOLDER,
            )
            if folders:
                path_label.set_label(folders[0])

        browse_btn.connect("clicked", on_browse)
        row.append(browse_btn)

        return row

    def _spin_row(self, label_text: str, config_key: str,
                  min_val: float, max_val: float, step: float,
                  default: float) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        label = Gtk.Label(label=label_text)
        label.set_width_chars(28)
        label.set_xalign(0)
        row.append(label)

        spin = Gtk.SpinButton.new_with_range(min_val, max_val, step)
        spin.set_value(default)
        spin.add_css_class("ra-entry")
        spin.set_hexpand(False)
        spin.config_key = config_key  # type: ignore[attr-defined]
        row.append(spin)

        return row

    def _combo_row(self, label_text: str, config_key: str,
                   values: list[str], labels: list[str]) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        label = Gtk.Label(label=label_text)
        label.set_width_chars(28)
        label.set_xalign(0)
        row.append(label)

        combo = Gtk.DropDown.new_from_strings(labels)
        combo.config_key = config_key  # type: ignore[attr-defined]
        combo._values = values  # type: ignore[attr-defined]
        combo._labels = labels  # type: ignore[attr-defined]
        row.append(combo)

        return row

    def _switch_row(self, label_text: str, config_key: str,
                    default: bool) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        label = Gtk.Label(label=label_text)
        label.set_width_chars(28)
        label.set_xalign(0)
        row.append(label)

        switch = Gtk.Switch()
        switch.set_active(default)
        switch.config_key = config_key  # type: ignore[attr-defined]
        row.append(switch)

        return row

    def _load_values(self):
        """Cargar valores actuales de la configuracion."""
        # Station name - gardar referencia directa
        name = self._config.get("station_name", "Mi Emisora")
        self._name_entry = self._station_name_entry.get_last_child()  # type: ignore
        if self._name_entry:
            self._name_entry.set_text(name)

        # Music folder - gardar referencia directa
        folder = self._config.get("music_folder", "")
        self._folder_label = self._find_child_by_config_key("music_folder")
        if self._folder_label:
            self._folder_label.set_label(folder)

        # Crossfade duration
        self._crossfade_spin_widget = self._crossfade_spin.get_last_child()  # type: ignore
        if self._crossfade_spin_widget:
            self._crossfade_spin_widget.set_value(
                self._config.get_float("crossfade_duration", 3.0)
            )

        # Crossfade curve
        self._crossfade_combo_widget = self._crossfade_combo.get_last_child()  # type: ignore
        if self._crossfade_combo_widget:
            curve = self._config.get("crossfade_curve", "linear")
            values = self._crossfade_combo_widget._values if hasattr(self._crossfade_combo_widget, '_values') else ["linear", "logarithmic", "sigmoid"]  # type: ignore
            if curve in values:
                self._crossfade_combo_widget.set_selected(values.index(curve))

        # Switches
        self._silence_switch_widget = self._silence_switch.get_last_child()  # type: ignore
        if self._silence_switch_widget:
            self._silence_switch_widget.set_active(
                self._config.get_bool("silence_detection", True)
            )
        self._norm_switch_widget = self._norm_switch.get_last_child()  # type: ignore
        if self._norm_switch_widget:
            self._norm_switch_widget.set_active(
                self._config.get_bool("normalization", False)
            )

        # Podcast settings
        self._podcast_interval_widget = self._podcast_interval.get_last_child()  # type: ignore
        if self._podcast_interval_widget:
            self._podcast_interval_widget.set_value(
                self._config.get_int("podcast_check_interval_hours", 24)
            )
        self._podcast_downloads_widget = self._podcast_downloads.get_last_child()  # type: ignore
        if self._podcast_downloads_widget:
            self._podcast_downloads_widget.set_value(
                self._config.get_int("podcast_max_concurrent_downloads", 3)
            )

    def _find_child_by_config_key(self, key: str):
        """Buscar un widget hijo por su config_key."""
        def _search(widget):
            if hasattr(widget, 'config_key') and widget.config_key == key:
                return widget
            child = widget.get_first_child()
            while child:
                result = _search(child)
                if result:
                    return result
                child = child.get_next_sibling()
            return None

        child = self.get_first_child()
        while child:
            result = _search(child)
            if result:
                return result
            child = child.get_next_sibling()
        return None

    def _save(self, _btn):
        """Guardar todos los valores de configuracion."""
        try:
            # Station name - referencia directa
            if hasattr(self, '_name_entry') and self._name_entry:
                self._config.set("station_name", self._name_entry.get_text())

            # Music folder - referencia directa
            if hasattr(self, '_folder_label') and self._folder_label:
                self._config.set("music_folder", self._folder_label.get_label())

            # Crossfade
            if hasattr(self, '_crossfade_spin_widget') and self._crossfade_spin_widget:
                self._config.set_float("crossfade_duration", self._crossfade_spin_widget.get_value())

            if hasattr(self, '_crossfade_combo_widget') and self._crossfade_combo_widget:
                combo = self._crossfade_combo_widget
                if hasattr(combo, '_values'):
                    idx = combo.get_selected()
                    if 0 <= idx < len(combo._values):
                        self._config.set("crossfade_curve", combo._values[idx])

            # Switches
            if hasattr(self, '_silence_switch_widget') and self._silence_switch_widget:
                self._config.set_bool("silence_detection", self._silence_switch_widget.get_active())

            if hasattr(self, '_norm_switch_widget') and self._norm_switch_widget:
                self._config.set_bool("normalization", self._norm_switch_widget.get_active())

            # Podcasts
            if hasattr(self, '_podcast_interval_widget') and self._podcast_interval_widget:
                self._config.set_int("podcast_check_interval_hours", int(self._podcast_interval_widget.get_value()))

            if hasattr(self, '_podcast_downloads_widget') and self._podcast_downloads_widget:
                self._config.set_int("podcast_max_concurrent_downloads", int(self._podcast_downloads_widget.get_value()))

            self._status_label.set_label("✓ Configuracion guardada")
            self._status_label.add_css_class("ra-label-success")

            # Resetear mensaje despues de 3 segundos
            def clear_status():
                self._status_label.set_label("")
                self._status_label.remove_css_class("ra-label-success")

            GLib.timeout_add_seconds(3, clear_status)

        except Exception as e:
            self._status_label.set_label(f"Error: {e}")
            self._status_label.add_css_class("ra-label-error")
