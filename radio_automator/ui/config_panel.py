"""
Panel de configuracion del sistema.
Ajustes basicos de la emisora y reproduccion.
Deseño en 2 columnas: Emisora|Reproduccion, Podcasts|Insercions Horarias.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GLib

from radio_automator.core.config import get_config


class ConfigPanel(Gtk.Box):
    """Panel de configuracion del sistema."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("ra-panel")
        self._config = get_config()

        # Referencias directas aos widgets con valores
        self._music_folder_label: Gtk.Label | None = None
        self._ta_folder_label: Gtk.Label | None = None
        # Garantizar que o config ten cache limpa ao arrancar
        self._config.reload()

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

        # Scroll para todo el contenido (sen overlay sobre o contido)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.set_overlay_scrolling(False)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        scroll.set_child(content)
        self.append(scroll)

        # ═══════════════════════════════════════
        # FILA 1: EMISORA | REPRODUCCION
        # ═══════════════════════════════════════
        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        row1.set_homogeneous(True)

        col1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        col2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        # ── Columna 1: Emisora ──
        col1.append(self._section_label("📻 Emisora"))

        self._station_name_entry = self._text_row(
            "Nombre de la emisora:", "station_name", "Mi Emisora"
        )
        col1.append(self._station_name_entry)

        music_folder_row = self._folder_row(
            "Carpeta de musica:", "music_folder"
        )
        col1.append(music_folder_row)
        self._music_folder_label = music_folder_row._path_label

        row1.append(col1)

        # ── Columna 2: Reproduccion ──
        col2.append(self._section_label("🔊 Reproduccion"))

        self._crossfade_spin = self._spin_row(
            "Duracion del crossfade (seg):", "crossfade_duration", 0.0, 15.0, 0.5, 3.0
        )
        col2.append(self._crossfade_spin)

        self._crossfade_combo = self._combo_row(
            "Curva del crossfade:", "crossfade_curve",
            ["linear", "logarithmic", "sigmoid"],
            ["Lineal", "Logaritmica", "Sigmoide"],
        )
        col2.append(self._crossfade_combo)

        self._silence_switch = self._switch_row(
            "Deteccion de silencio:", "silence_detection", True
        )
        col2.append(self._silence_switch)

        self._norm_switch = self._switch_row(
            "Normalizacion de audio:", "normalization", False
        )
        col2.append(self._norm_switch)

        row1.append(col2)

        content.append(row1)

        # ═══════════════════════════════════════
        # FILA 2: PODCASTS | INSERCIÓNS HORARIAS
        # ═══════════════════════════════════════
        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        row2.set_homogeneous(True)

        col3 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        col4 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        # ── Columna 3: Podcasts ──
        col3.append(self._section_label("📡 Podcasts"))

        self._podcast_interval = self._spin_row(
            "Intervalo de comprobacion (horas):", "podcast_check_interval_hours",
            1, 168, 1, 24
        )
        col3.append(self._podcast_interval)

        self._podcast_downloads = self._spin_row(
            "Descargas simultaneas:", "podcast_max_concurrent_downloads",
            1, 10, 1, 3
        )
        col3.append(self._podcast_downloads)

        row2.append(col3)

        # ── Columna 4: Insercions Horarias ──
        col4.append(self._section_label("⏰ Insercions Horarias"))

        self._ta_switch = self._switch_row(
            "Insercions horarias:", "time_announce_enabled", False
        )
        col4.append(self._ta_switch)

        ta_folder_row = self._folder_row(
            "Carpeta de audios:", "time_announce_folder"
        )
        col4.append(ta_folder_row)
        self._ta_folder_label = ta_folder_row._path_label

        ta_interval_row = self._combo_row(
            "Intervalo (min):", "time_announce_interval",
            ["15", "30", "60"],
            ["Cada 15 minutos", "Cada 30 minutos", "Cada hora"],
        )
        col4.append(ta_interval_row)
        self._ta_interval_row = ta_interval_row

        row2.append(col4)

        content.append(row2)

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

        # ── Seccion: Visor de Logs ──
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
        label.set_width_chars(26)
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
        label.set_width_chars(26)
        label.set_xalign(0)
        row.append(label)

        path_label = Gtk.Label(label="")
        path_label.set_hexpand(True)
        path_label.set_xalign(0)
        path_label.set_ellipsize(3)  # Pango.EllipsizeMode.MIDDLE
        row.append(path_label)

        browse_btn = Gtk.Button(label="📂")
        browse_btn.add_css_class("ra-button")
        browse_btn.set_tooltip_text("Seleccionar carpeta")

        def on_browse(btn, _path_label=path_label, _key=config_key):
            dialog = Gtk.FileChooserDialog(
                title="Seleccionar carpeta",
                transient_for=self.get_root() if self.get_root() else None,
                modal=True,
                action=Gtk.FileChooserAction.SELECT_FOLDER,
            )
            dialog.add_button("_Cancelar", Gtk.ResponseType.CANCEL)
            dialog.add_button("_Seleccionar", Gtk.ResponseType.ACCEPT)

            def on_response(dialog, response_id):
                if response_id == Gtk.ResponseType.ACCEPT:
                    f = dialog.get_file()
                    if f:
                        selected_path = f.get_path()
                        _path_label.set_label(selected_path)
                        # Gardar inmediatamente na configuracion
                        self._config.set(_key, selected_path)
                        print(f"[ConfigPanel] Gardada {_key}: {selected_path}")
                dialog.destroy()

            dialog.connect("response", on_response)
            dialog.show()

        browse_btn.connect("clicked", on_browse)
        row.append(browse_btn)

        # Referencia directa ao path_label, accesible dende fora
        row._path_label = path_label  # type: ignore[attr-defined]
        return row

    def _spin_row(self, label_text: str, config_key: str,
                  min_val: float, max_val: float, step: float,
                  default: float) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        label = Gtk.Label(label=label_text)
        label.set_width_chars(26)
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
        label.set_width_chars(26)
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
        label.set_width_chars(26)
        label.set_xalign(0)
        row.append(label)

        switch = Gtk.Switch()
        switch.set_active(default)
        switch.config_key = config_key  # type: ignore[attr-defined]
        row.append(switch)

        return row

    def _load_values(self):
        """Cargar valores actuales de la configuracion."""
        # Station name
        name = self._config.get("station_name", "Mi Emisora")
        self._station_name_entry.get_last_child().set_text(name)  # type: ignore

        # Music folder - referencia directa
        if self._music_folder_label:
            folder = self._config.get("music_folder", "")
            self._music_folder_label.set_label(folder)

        # Crossfade duration
        self._crossfade_spin.get_last_child().set_value(  # type: ignore
            self._config.get_float("crossfade_duration", 3.0)
        )

        # Crossfade curve
        combo = self._crossfade_combo.get_last_child()
        if combo:
            curve = self._config.get("crossfade_curve", "linear")
            values = combo._values if hasattr(combo, '_values') else ["linear", "logarithmic", "sigmoid"]  # type: ignore
            if curve in values:
                combo.set_selected(values.index(curve))

        # Switches
        self._silence_switch.get_last_child().set_active(  # type: ignore
            self._config.get_bool("silence_detection", True)
        )
        self._norm_switch.get_last_child().set_active(  # type: ignore
            self._config.get_bool("normalization", False)
        )

        # Podcast settings
        self._podcast_interval.get_last_child().set_value(  # type: ignore
            self._config.get_int("podcast_check_interval_hours", 24)
        )
        self._podcast_downloads.get_last_child().set_value(  # type: ignore
            self._config.get_int("podcast_max_concurrent_downloads", 3)
        )

        # Insercions horarias - referencia directa
        self._ta_switch.get_last_child().set_active(  # type: ignore
            self._config.get_bool("time_announce_enabled", False)
        )
        if self._ta_folder_label:
            self._ta_folder_label.set_label(self._config.get("time_announce_folder", ""))
        ta_interval = self._ta_interval_row.get_last_child()
        if ta_interval:
            interval = self._config.get("time_announce_interval", "60")
            values = ["15", "30", "60"]
            if interval in values:
                ta_interval.set_selected(values.index(interval))

        # Cargar configuracion no servizo de insercions horarias
        try:
            from radio_automator.services.time_announce_service import get_time_announce_service
            get_time_announce_service().load_config()
        except Exception:
            pass

    def _save(self, _btn):
        """Guardar todos los valores de configuracion."""
        try:
            # Station name
            name_entry = self._station_name_entry.get_last_child()
            if name_entry:
                self._config.set("station_name", name_entry.get_text())

            # Music folder - referencia directa (tamén se garda automaticamente ao seleccionar)
            if self._music_folder_label:
                path = self._music_folder_label.get_label()
                if path:
                    self._config.set("music_folder", path)
                    print(f"[ConfigPanel] Gardada carpeta de musica: {path}")

            # Crossfade
            crossfade_spin = self._crossfade_spin.get_last_child()
            crossfade_duration = 3.0
            crossfade_curve = "linear"
            if crossfade_spin:
                crossfade_duration = crossfade_spin.get_value()
                self._config.set_float("crossfade_duration", crossfade_duration)

            combo = self._crossfade_combo.get_last_child()
            if combo and hasattr(combo, '_values'):
                idx = combo.get_selected()
                if 0 <= idx < len(combo._values):
                    crossfade_curve = combo._values[idx]
                    self._config.set("crossfade_curve", crossfade_curve)

            # Aplicar crossfade ao AudioEngine en tempo real
            try:
                from radio_automator.services.audio_engine import get_audio_engine
                engine = get_audio_engine()
                duration_ms = int(crossfade_duration * 1000)
                engine.set_crossfade(
                    enabled=(crossfade_duration > 0),
                    duration_ms=duration_ms,
                    curve=crossfade_curve,
                )
            except Exception as e:
                print(f"[ConfigPanel] Error aplicando crossfade: {e}")

            # Switches
            silence_switch = self._silence_switch.get_last_child()
            if silence_switch:
                self._config.set_bool("silence_detection", silence_switch.get_active())

            norm_switch = self._norm_switch.get_last_child()
            if norm_switch:
                self._config.set_bool("normalization", norm_switch.get_active())

            # Podcasts
            pod_interval = self._podcast_interval.get_last_child()
            if pod_interval:
                self._config.set_int("podcast_check_interval_hours", int(pod_interval.get_value()))

            pod_downloads = self._podcast_downloads.get_last_child()
            if pod_downloads:
                self._config.set_int("podcast_max_concurrent_downloads", int(pod_downloads.get_value()))

            # Insercions horarias - referencia directa
            ta_switch = self._ta_switch.get_last_child()
            if ta_switch:
                self._config.set_bool("time_announce_enabled", ta_switch.get_active())

            if self._ta_folder_label:
                ta_path = self._ta_folder_label.get_label()
                if ta_path:
                    self._config.set("time_announce_folder", ta_path)
                    print(f"[ConfigPanel] Gardada carpeta de insercions: {ta_path}")

            ta_interval = self._ta_interval_row.get_last_child()
            if ta_interval:
                idx = ta_interval.get_selected()
                values = ["15", "30", "60"]
                if 0 <= idx < len(values):
                    self._config.set("time_announce_interval", values[idx])

            self._status_label.set_label("Configuracion gardada")
            self._status_label.add_css_class("ra-label-success")

            # Resetear mensaje despues de 3 segundos
            def clear_status():
                self._status_label.set_label("")
                self._status_label.remove_css_class("ra-label-success")

            GLib.timeout_add_seconds(3, clear_status)

            # Notificar a outros compoñentes do cambio de configuracion
            try:
                from radio_automator.core.event_bus import get_event_bus
                get_event_bus().publish("config.saved", {})
            except Exception:
                pass

            # Recargar servizo de insercions horarias
            try:
                from radio_automator.services.time_announce_service import get_time_announce_service
                get_time_announce_service().load_config()
            except Exception:
                pass

        except Exception as e:
            self._status_label.set_label(f"Error: {e}")
            self._status_label.add_css_class("ra-label-error")
