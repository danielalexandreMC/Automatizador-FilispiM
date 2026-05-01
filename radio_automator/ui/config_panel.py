"""
Panel de configuracion del sistema.
Ajustes basicos de la emisora y reproduccion.
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
        # AUTOMATIC en horizontal para que non se saia fora
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_start(8)
        content.set_margin_end(8)
        scroll.set_child(content)
        self.append(scroll)

        # ── Seccion: Emisora ──
        content.append(self._section_label("Emisora"))

        # Nombre de la emisora
        self._station_name_entry = self._text_row(
            "Nombre de la emisora:", "station_name", "Mi Emisora"
        )
        content.append(self._station_name_entry)

        # Logotipo da emisora
        logo_row = self._logo_row(
            "Logotipo da emisora:", "logo_path"
        )
        content.append(logo_row)

        # Carpeta de musica
        folder_row = self._folder_row(
            "Carpeta de musica:", "music_folder"
        )
        content.append(folder_row)

        # ── Seccion: Reproduccion ──
        content.append(self._section_label("Reproduccion"))

        # Duracion del crossfade
        self._crossfade_spin = self._spin_row(
            "Crossfade (seg):", "crossfade_duration", 0.0, 15.0, 0.5, 3.0
        )
        content.append(self._crossfade_spin)

        # Curva del crossfade
        self._crossfade_combo = self._combo_row(
            "Curva crossfade:", "crossfade_curve",
            ["linear", "logarithmic", "sigmoid"],
            ["Lineal", "Logaritmica", "Sigmoide"],
        )
        content.append(self._crossfade_combo)

        # Deteccion de silencio
        self._silence_switch = self._switch_row(
            "Deteccion silencio:", "silence_detection", True
        )
        content.append(self._silence_switch)

        # Normalizacion
        self._norm_switch = self._switch_row(
            "Normalizacion audio:", "normalization", False
        )
        content.append(self._norm_switch)

        # ── Seccion: Podcasts ──
        content.append(self._section_label("Podcasts"))

        # Intervalo de comprobacion
        self._podcast_interval = self._spin_row(
            "Intervalo (horas):", "podcast_check_interval_hours",
            1, 168, 1, 24
        )
        content.append(self._podcast_interval)

        # Descargas simultaneas
        self._podcast_downloads = self._spin_row(
            "Descargas simult.:", "podcast_max_concurrent_downloads",
            1, 10, 1, 3
        )
        content.append(self._podcast_downloads)

        # ── Boton guardar ──
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_margin_top(12)

        save_btn = Gtk.Button(label="Guardar configuracion")
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
        label.set_xalign(0)
        label.set_width_chars(20)
        label.set_max_width_chars(20)
        label.set_ellipsize(3)  # Pango.EllipsizeMode.END
        row.append(label)

        entry = Gtk.Entry()
        entry.set_placeholder_text(placeholder)
        entry.add_css_class("ra-entry")
        entry.set_hexpand(True)
        entry.config_key = config_key  # type: ignore[attr-defined]
        row.append(entry)

        return row

    def _folder_row(self, label_text: str, config_key: str) -> Gtk.Box:
        """Fila con selector de carpeta (FileChooserNative para GTK 4.6)."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        label = Gtk.Label(label=label_text)
        label.set_xalign(0)
        label.set_width_chars(20)
        label.set_max_width_chars(20)
        label.set_ellipsize(3)  # Pango.EllipsizeMode.END
        row.append(label)

        path_label = Gtk.Label(label="")
        path_label.set_hexpand(True)
        path_label.set_xalign(0)
        path_label.set_ellipsize(3)  # Pango.EllipsizeMode.MIDDLE
        path_label.config_key = config_key  # type: ignore[attr-defined]
        row.append(path_label)

        browse_btn = Gtk.Button(label="Seleccionar")
        browse_btn.add_css_class("ra-button")
        browse_btn.set_tooltip_text("Seleccionar carpeta")

        def on_browse(btn):
            self._open_file_chooser(
                title="Seleccionar carpeta",
                action=Gtk.FileChooserAction.SELECT_FOLDER,
                on_accept=lambda f: path_label.set_label(f.get_path()),
            )

        browse_btn.connect("clicked", on_browse)
        row.append(browse_btn)

        return row

    def _logo_row(self, label_text: str, config_key: str) -> Gtk.Box:
        """Fila para seleccionar logotipo da emisora."""
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        label = Gtk.Label(label=label_text)
        label.set_xalign(0)
        label.set_width_chars(20)
        label.set_max_width_chars(20)
        label.set_ellipsize(3)  # Pango.EllipsizeMode.END
        row.append(label)

        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        # Vista previa do logo
        import os
        logo_picture = Gtk.Picture()
        logo_picture.set_size_request(48, 48)  # GTK 4.6: usar set_size_request
        logo_picture.set_valign(Gtk.Align.CENTER)
        logo_picture.config_key = config_key  # type: ignore[attr-defined]
        inner.append(logo_picture)

        # Path do logo
        path_label = Gtk.Label(label="")
        path_label.set_hexpand(True)
        path_label.set_xalign(0)
        path_label.set_ellipsize(3)
        inner.append(path_label)

        browse_btn = Gtk.Button(label="Seleccionar")
        browse_btn.add_css_class("ra-button")
        browse_btn.set_tooltip_text("Seleccionar imaxe do logotipo")

        def on_browse(btn):
            def on_file_selected(f):
                fpath = f.get_path()
                path_label.set_label(fpath)
                if os.path.isfile(fpath):
                    try:
                        logo_picture.set_filename(fpath)
                    except Exception:
                        pass

            self._open_file_chooser(
                title="Seleccionar logotipo",
                action=Gtk.FileChooserAction.OPEN,
                on_accept=on_file_selected,
            )

        browse_btn.connect("clicked", on_browse)
        inner.append(browse_btn)

        row.append(inner)

        # Gardar referencia para carga
        self._logo_picture = logo_picture
        self._logo_path_label = path_label

        return row

    def _open_file_chooser(self, title="", action=Gtk.FileChooserAction.OPEN,
                           on_accept=None):
        """Abrir dialogo de seleccion de ficheiros (compatible GTK 4.6).

        Usa FileChooserNative como principal (param 'parent' non 'transient_for').
        """
        parent = None
        try:
            root = self.get_root()
            if root:
                parent = root
        except Exception:
            pass

        def _do_accept(dialog):
            try:
                f = dialog.get_file()
                if f and on_accept:
                    on_accept(f)
            except Exception as e:
                print(f"[ConfigPanel] Erro ao seleccionar ficheiro: {e}")
            dialog.destroy()

        def _do_cancel(dialog):
            dialog.destroy()

        try:
            # FileChooserNative: param 'parent' (non 'transient_for') en GTK 4.x
            dialog = Gtk.FileChooserNative(
                title=title,
                parent=parent,
                action=action,
            )
            dialog.set_modal(True)
            dialog.connect("response", lambda d, r: _do_accept(d) if r == Gtk.ResponseType.ACCEPT else _do_cancel(d))
            dialog.show()
        except Exception as e1:
            print(f"[ConfigPanel] FileChooserNative fallou ({e1}), tentando FileChooserDialog")
            try:
                # Fallback: FileChooserDialog (dispoñible en GTK 4.6, deprecated en 4.10)
                dialog = Gtk.FileChooserDialog(
                    title=title,
                    transient_for=parent,
                    action=action,
                )
                dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
                dialog.add_button("Aceptar", Gtk.ResponseType.ACCEPT)
                dialog.set_default_response(Gtk.ResponseType.ACCEPT)
                dialog.connect("response", lambda d, r: _do_accept(d) if r == Gtk.ResponseType.ACCEPT else _do_cancel(d))
                dialog.show()
            except Exception as e2:
                print(f"[ConfigPanel] FileChooserDialog tamén fallou: {e2}")

    def _spin_row(self, label_text: str, config_key: str,
                  min_val: float, max_val: float, step: float,
                  default: float) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        label = Gtk.Label(label=label_text)
        label.set_xalign(0)
        label.set_width_chars(20)
        label.set_max_width_chars(20)
        label.set_ellipsize(3)  # Pango.EllipsizeMode.END
        row.append(label)

        spin = Gtk.SpinButton.new_with_range(min_val, max_val, step)
        spin.set_value(default)
        spin.add_css_class("ra-entry")
        spin.config_key = config_key  # type: ignore[attr-defined]
        row.append(spin)

        return row

    def _combo_row(self, label_text: str, config_key: str,
                   values: list[str], labels: list[str]) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        label = Gtk.Label(label=label_text)
        label.set_xalign(0)
        label.set_width_chars(20)
        label.set_max_width_chars(20)
        label.set_ellipsize(3)  # Pango.EllipsizeMode.END
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
        label.set_xalign(0)
        label.set_width_chars(20)
        label.set_max_width_chars(20)
        label.set_ellipsize(3)  # Pango.EllipsizeMode.END
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

        # Logo
        import os
        logo_path = self._config.get("logo_path", "")
        if hasattr(self, '_logo_path_label') and self._logo_path_label:
            self._logo_path_label.set_label(logo_path)
        if hasattr(self, '_logo_picture') and self._logo_picture:
            if logo_path and os.path.isfile(logo_path):
                try:
                    self._logo_picture.set_filename(logo_path)
                except Exception:
                    pass

        # Music folder
        folder = self._config.get("music_folder", "")
        folder_label = self._find_child_by_config_key("music_folder")
        if folder_label:
            folder_label.set_label(folder)

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

    def _find_child_by_config_key(self, key: str):
        """Buscar un widget hijo por su config_key."""
        def _search(widget):
            if hasattr(widget, 'config_key') and widget.config_key == key:
                return widget
            if hasattr(widget, 'get_last_child'):
                child = widget.get_last_child()
                if child:
                    result = _search(child)
                    if result:
                        return result
            return None

        # Buscar en cada fila directa
        for i in range(self.get_first_child() is not None and 1 or 0):
            pass
        return None

    def _save(self, _btn):
        """Guardar todos los valores de configuracion."""
        try:
            # Station name
            name_entry = self._station_name_entry.get_last_child()
            if name_entry:
                self._config.set("station_name", name_entry.get_text())

            # Logo path
            if hasattr(self, '_logo_path_label') and self._logo_path_label:
                logo_path = self._logo_path_label.get_label()
                self._config.set("logo_path", logo_path)

            # Music folder
            folder_label = self._find_child_by_config_key("music_folder")
            if folder_label and hasattr(folder_label, 'get_label'):
                self._config.set("music_folder", folder_label.get_label())

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

            self._status_label.set_label("Configuracion guardada")
            self._status_label.add_css_class("ra-label-success")

            # Notificar a outros compoñentes do cambio de configuracion
            try:
                from radio_automator.core.event_bus import get_event_bus
                get_event_bus().publish("config.saved", {})
            except Exception:
                pass

            # Resetear mensaje despues de 3 segundos
            def clear_status():
                self._status_label.set_label("")
                self._status_label.remove_css_class("ra-label-success")

            GLib.timeout_add_seconds(3, clear_status)

        except Exception as e:
            self._status_label.set_label(f"Error: {e}")
            self._status_label.add_css_class("ra-label-error")
