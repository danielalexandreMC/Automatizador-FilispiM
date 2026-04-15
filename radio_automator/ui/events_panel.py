"""
Panel de eventos programados.
CRUD de eventos con soporte para eventos normales y de streaming.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Pango

from radio_automator.core.database import get_session, RadioEvent, Playlist
from radio_automator.services.playlist_service import PlaylistService
from radio_automator.ui.layout import PanelContainer


class EventRow(Gtk.Box):
    """Fila visual para un evento programado."""

    def __init__(self, event: RadioEvent, on_edit=None, on_delete=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self._event = event
        self._on_edit = on_edit
        self._on_delete = on_delete

        self.set_margin_top(4)
        self.set_margin_bottom(4)
        self.set_margin_start(4)
        self.set_margin_end(4)
        self.add_css_class("ra-card")

        # Info principal
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info.set_hexpand(True)
        info.set_valign(Gtk.Align.CENTER)

        name_label = Gtk.Label(label=event.name)
        name_label.add_css_class("ra-card-title")
        name_label.set_xalign(0)
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        info.append(name_label)

        # Horario
        time_str = event.start_time
        if event.end_time:
            time_str += f" - {event.end_time}"
        else:
            time_str += " (sin fin)"

        # Dias
        days_names = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]
        active_days = event.week_days_list
        days_str = " ".join(
            days_names[i] for i in range(7) if active_days[i]
        ) if active_days else "Todos los dias"

        meta = Gtk.Label(label=f"🕐 {time_str}  ·  {days_str}")
        meta.add_css_class("ra-card-subtitle")
        meta.set_xalign(0)
        info.append(meta)

        self.append(info)

        # Badge de tipo
        if event.is_streaming:
            badge = Gtk.Label(label="📡 Streaming")
            badge.add_css_class("ra-badge")
            badge.add_css_class("ra-badge-streaming")
        else:
            badge = Gtk.Label(label="🎵 Normal")
            badge.add_css_class("ra-badge")
            badge.add_css_class("ra-badge-loop")
        badge.set_valign(Gtk.Align.CENTER)
        self.append(badge)

        # Botones
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        actions.set_valign(Gtk.Align.CENTER)

        edit_btn = Gtk.Button(label="✏️")
        edit_btn.add_css_class("ra-button-icon")
        edit_btn.set_tooltip_text("Editar evento")
        if on_edit:
            edit_btn.connect("clicked", lambda b: on_edit(event))
        actions.append(edit_btn)

        delete_btn = Gtk.Button(label="🗑️")
        delete_btn.add_css_class("ra-button-icon")
        delete_btn.set_tooltip_text("Eliminar evento")
        if on_delete:
            delete_btn.connect("clicked", lambda b: on_delete(event))
        actions.append(delete_btn)

        self.append(actions)


class EventsPanel(PanelContainer):
    """Panel de gestion de eventos programados."""

    def __init__(self):
        super().__init__(
            title="Eventos Programados",
            subtitle="Gestiona los eventos de la parrilla",
            show_add=True,
        )
        self._session = get_session()

        if self.add_button:
            self.add_button.connect("clicked", self._show_create_dialog)

        # Lista con scroll
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        self._list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scroll.set_child(self._list)
        self.content.append(scroll)

        self.refresh()

    def refresh(self):
        """Recargar la lista de eventos."""
        self._list.remove_all()
        events = (
            self._session.query(RadioEvent)
            .filter_by(is_active=True)
            .order_by(RadioEvent.start_time)
            .all()
        )

        if not events:
            self.set_empty_state("📋", "No hay eventos programados.\nCrea uno nuevo.")
            return

        for ev in events:
            row = EventRow(
                event=ev,
                on_edit=self._show_edit_dialog,
                on_delete=self._show_delete_confirm,
            )
            self._list.append(row)

    def _show_create_dialog(self, _btn=None, edit_event: RadioEvent | None = None):
        """Mostrar dialogo para crear/editar un evento."""
        is_edit = edit_event is not None
        title = f"Editar: {edit_event.name}" if is_edit else "Nuevo Evento"

        dialog = Gtk.MessageDialog(
            transient_for=self.get_root() if self.get_root() else None,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            title=title,
        )

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_max_content_height(500)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(16)
        box.set_margin_end(16)

        # Nombre del evento
        name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        name_label = Gtk.Label(label="Nombre:")
        name_label.set_width_chars(14)
        name_label.set_xalign(0)
        name_box.append(name_label)
        name_entry = Gtk.Entry()
        name_entry.set_text(edit_event.name if is_edit else "")
        name_entry.set_placeholder_text("Nombre del evento")
        name_entry.add_css_class("ra-entry")
        name_entry.set_hexpand(True)
        name_box.append(name_entry)
        box.append(name_box)

        # Hora inicio
        time_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        start_label = Gtk.Label(label="Hora inicio:")
        start_label.set_width_chars(14)
        start_label.set_xalign(0)
        time_box.append(start_label)
        start_entry = Gtk.Entry()
        start_entry.set_text(edit_event.start_time if is_edit else "")
        start_entry.set_placeholder_text("HH:MM")
        start_entry.add_css_class("ra-entry")
        start_entry.set_max_width_chars(6)
        time_box.append(start_entry)

        # Hora fin
        end_label = Gtk.Label(label="Hora fin:")
        end_label.set_width_chars(10)
        end_label.set_xalign(0)
        time_box.append(end_label)
        end_entry = Gtk.Entry()
        end_entry.set_text(edit_event.end_time if is_edit and edit_event.end_time else "")
        end_entry.set_placeholder_text("Opcional")
        end_entry.add_css_class("ra-entry")
        end_entry.set_max_width_chars(6)
        end_entry.add_css_class("end-time-entry")
        time_box.append(end_entry)
        box.append(time_box)

        # Streaming URL
        stream_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        stream_label = Gtk.Label(label="Conexion Streaming:")
        stream_label.set_width_chars(14)
        stream_label.set_xalign(0)
        stream_box.append(stream_label)
        stream_entry = Gtk.Entry()
        stream_entry.set_text(edit_event.streaming_url if is_edit and edit_event.streaming_url else "")
        stream_entry.set_placeholder_text("URL del streaming (opcional)")
        stream_entry.add_css_class("ra-entry")
        stream_entry.set_hexpand(True)
        stream_box.append(stream_entry)
        box.append(stream_box)

        # Info de streaming
        stream_info = Gtk.Label(
            label="Si introduces una URL de streaming, el evento sera de tipo streaming "
                  "con hora de inicio y fin obligatoria.\n"
                  "Si se deja vacio, el evento es normal y reproduce playlist/pista/carpeta."
        )
        stream_info.add_css_class("ra-label-dim")
        stream_info.set_xalign(0)
        stream_info.set_wrap(True)
        stream_info.set_margin_start(14)
        box.append(stream_info)

        # Playlist asociada
        playlist_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        pl_label = Gtk.Label(label="Playlist:")
        pl_label.set_width_chars(14)
        pl_label.set_xalign(0)
        playlist_box.append(pl_label)

        playlists = PlaylistService().get_all()
        playlist_names = ["(Ninguna)"] + [p.name for p in playlists]
        playlist_combo = Gtk.DropDown.new_from_strings(playlist_names)
        playlist_combo.add_css_class("ra-combo")
        playlist_combo.set_hexpand(True)

        # Seleccionar playlist actual
        if is_edit and edit_event.playlist_id:
            for idx, p in enumerate(playlists):
                if p.id == edit_event.playlist_id:
                    playlist_combo.set_selected(idx + 1)
                    break

        playlist_box.append(playlist_combo)
        box.append(playlist_box)

        # Archivo local
        file_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        file_label = Gtk.Label(label="Archivo local:")
        file_label.set_width_chars(14)
        file_label.set_xalign(0)
        file_box.append(file_label)
        file_path_label = Gtk.Label(
            label=edit_event.local_file_path or "(Ninguno)",
        )
        file_path_label.set_hexpand(True)
        file_path_label.set_xalign(0)
        file_path_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        file_box.append(file_path_label)
        browse_file_btn = Gtk.Button(label="📂")
        browse_file_btn.add_css_class("ra-button")

        selected_file = {"path": edit_event.local_file_path or ""}

        def on_file_browse(btn):
            dlg = Gtk.FileChooserNative(
                title="Seleccionar archivo de audio",
                action=Gtk.FileChooserAction.OPEN,
                transient_for=self.get_root() if self.get_root() else None,
            )
            audio_filter = Gtk.FileFilter()
            audio_filter.set_name("Audio")
            for ext in ["*.mp3", "*.wav", "*.ogg", "*.flac", "*.opus", "*.m4a"]:
                audio_filter.add_pattern(ext)
            dlg.add_filter(audio_filter)

            def on_resp(d, r):
                if r == Gtk.ResponseType.ACCEPT:
                    f = d.get_file()
                    if f:
                        selected_file["path"] = f.get_path()
                        file_path_label.set_label(f.get_path())
                d.destroy()

            dlg.connect("response", on_resp)
            dlg.show()

        browse_file_btn.connect("clicked", on_file_browse)
        file_box.append(browse_file_btn)
        box.append(file_box)

        # Carpeta local
        folder_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        folder_label = Gtk.Label(label="Carpeta local:")
        folder_label.set_width_chars(14)
        folder_label.set_xalign(0)
        folder_box.append(folder_label)
        folder_path_label = Gtk.Label(
            label=edit_event.local_folder_path or "(Ninguna)",
        )
        folder_path_label.set_hexpand(True)
        folder_path_label.set_xalign(0)
        folder_path_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        folder_box.append(folder_path_label)
        browse_folder_btn = Gtk.Button(label="📂")
        browse_folder_btn.add_css_class("ra-button")

        selected_folder = {"path": edit_event.local_folder_path or ""}

        def on_folder_browse(btn):
            dlg = Gtk.FileChooserNative(
                title="Seleccionar carpeta",
                action=Gtk.FileChooserAction.SELECT_FOLDER,
                transient_for=self.get_root() if self.get_root() else None,
            )

            def on_resp(d, r):
                if r == Gtk.ResponseType.ACCEPT:
                    f = d.get_file()
                    if f:
                        selected_folder["path"] = f.get_path()
                        folder_path_label.set_label(f.get_path())
                d.destroy()

            dlg.connect("response", on_resp)
            dlg.show()

        browse_folder_btn.connect("clicked", on_folder_browse)
        folder_box.append(browse_folder_btn)
        box.append(folder_box)

        # Dias de la semana
        days_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        days_label = Gtk.Label(label="Dias:")
        days_label.set_width_chars(14)
        days_label.set_xalign(0)
        days_box.append(days_label)

        days_data = {}
        days_names = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]
        existing_days = edit_event.week_days_list if is_edit else [True] * 7

        for i, day_name in enumerate(days_names):
            day_btn = Gtk.ToggleButton(label=day_name)
            day_btn.set_active(existing_days[i])
            day_btn.add_css_class("ra-button")
            day_btn.add_css_class("ra-button-sm")
            days_data[i] = day_btn
            days_box.append(day_btn)

        box.append(days_box)

        # Patron de repeticion
        repeat_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        repeat_label = Gtk.Label(label="Repetir:")
        repeat_label.set_width_chars(14)
        repeat_label.set_xalign(0)
        repeat_box.append(repeat_label)

        repeat_patterns = ["Semanal", "Diario", "Una vez", "Dias seleccionados"]
        repeat_combo = Gtk.DropDown.new_from_strings(repeat_patterns)
        repeat_combo.add_css_class("ra-combo")
        repeat_box.append(repeat_combo)

        if is_edit:
            pattern_map = {
                "weekly": 0, "daily": 1, "once": 2, "selected_days": 3
            }
            idx = pattern_map.get(edit_event.repeat_pattern, 0)
            repeat_combo.set_selected(idx)

        box.append(repeat_box)

        scroll.set_child(box)
        dialog.set_child(scroll)
        name_entry.grab_focus()

        def on_response(dialog, response_id):
            if response_id == Gtk.ResponseType.OK:
                name = name_entry.get_text().strip()
                start_time = start_entry.get_text().strip()
                end_time = end_entry.get_text().strip()
                streaming_url = stream_entry.get_text().strip()

                if not name:
                    self._show_error("El nombre del evento es obligatorio")
                    return
                if not start_time or len(start_time) != 5 or start_time[2] != ':':
                    self._show_error("La hora de inicio debe tener formato HH:MM")
                    return

                # Si es streaming, la hora de fin es obligatoria
                if streaming_url and not end_time:
                    self._show_error(
                        "Los eventos de streaming deben tener hora de fin obligatoria"
                    )
                    return

                # Validar formato de hora de fin
                if end_time and (len(end_time) != 5 or end_time[2] != ':'):
                    self._show_error("La hora de fin debe tener formato HH:MM")
                    return

                # Playlist seleccionada
                pl_idx = playlist_combo.get_selected()
                playlist_id = None
                if pl_idx > 0 and pl_idx - 1 < len(playlists):
                    playlist_id = playlists[pl_idx - 1].id

                # Dias
                week_days = ",".join(
                    "1" if days_data[i].get_active() else "0"
                    for i in range(7)
                )

                # Patron
                pattern_map = {0: "weekly", 1: "daily", 2: "once", 3: "selected_days"}
                repeat_idx = repeat_combo.get_selected()
                repeat_pattern = pattern_map.get(repeat_idx, "weekly")

                try:
                    if is_edit:
                        edit_event.name = name
                        edit_event.start_time = start_time
                        edit_event.end_time = end_time or None
                        edit_event.streaming_url = streaming_url or None
                        edit_event.playlist_id = playlist_id
                        edit_event.week_days = week_days
                        edit_event.repeat_pattern = repeat_pattern
                        edit_event.local_file_path = selected_file["path"] or None
                        edit_event.local_folder_path = selected_folder["path"] or None
                    else:
                        new_event = RadioEvent(
                            name=name,
                            start_time=start_time,
                            end_time=end_time or None,
                            streaming_url=streaming_url or None,
                            playlist_id=playlist_id,
                            week_days=week_days,
                            repeat_pattern=repeat_pattern,
                            local_file_path=selected_file["path"] or None,
                            local_folder_path=selected_folder["path"] or None,
                        )
                        self._session.add(new_event)
                    self._session.commit()
                    self.refresh()
                except Exception as e:
                    self._session.rollback()
                    self._show_error(f"Error al guardar evento: {e}")
            dialog.destroy()

        dialog.connect("response", on_response)
        dialog.show()

    def _show_edit_dialog(self, event: RadioEvent):
        self._show_create_dialog(edit_event=event)

    def _show_delete_confirm(self, event: RadioEvent):
        dialog = Gtk.MessageDialog(
            transient_for=self.get_root() if self.get_root() else None,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            title="Eliminar Evento",
            text=f"¿Seguro que quieres eliminar el evento \"{event.name}\"?",
        )

        def on_response(dialog, response_id):
            if response_id == Gtk.ResponseType.YES:
                try:
                    self._session.delete(event)
                    self._session.commit()
                    self.refresh()
                except Exception as e:
                    self._session.rollback()
                    self._show_error(f"Error al eliminar: {e}")
            dialog.destroy()

        dialog.connect("response", on_response)
        dialog.show()

    def _show_error(self, message: str):
        dialog = Gtk.MessageDialog(
            transient_for=self.get_root() if self.get_root() else None,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            title="Error",
            text=message,
        )
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.show()
