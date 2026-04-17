"""
Panel de listado de playlists.
Muestra todas las playlists con CRUD (excepto Continuidad que no se puede borrar).
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GLib, Pango

from radio_automator.ui.layout import PanelContainer
from radio_automator.services.playlist_service import (
    PlaylistService, PlaylistDTO, PlaylistProtectedError, PlaylistError
)

# Función auxiliar (engadir despois dos imports)
def _clear_box(box):
    """Eliminar todos os fillows dun Box."""
    child = box.get_first_child()
    while child is not None:
        next_child = child.get_next_sibling()
        box.remove(child)
        child = next_child

# ═══════════════════════════════════════
# Fila de playlist en la lista
# ═══════════════════════════════════════

class PlaylistRow(Gtk.Box):
    """Fila visual para una playlist en la lista."""

    def __init__(self, dto: PlaylistDTO, on_edit=None, on_delete=None,
                 on_select=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self._dto = dto
        self._on_edit = on_edit
        self._on_delete = on_delete
        self._on_select = on_select

        self.set_margin_top(4)
        self.set_margin_bottom(4)
        self.set_margin_start(4)
        self.set_margin_end(4)
        self.add_css_class("ra-card")
        self.set_cursor_from_name("pointer")

        # Click para seleccionar
        click_gesture = Gtk.GestureClick()
        click_gesture.connect("released", self._on_click)
        self.add_controller(click_gesture)

        # Info principal
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info.set_hexpand(True)
        info.set_valign(Gtk.Align.CENTER)

        name_label = Gtk.Label(label=dto.name)
        name_label.add_css_class("ra-card-title")
        name_label.set_xalign(0)
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        info.append(name_label)

        meta = Gtk.Label(
            label=f"{dto.item_count} elementos  ·  {dto.mode_label}  ·  {dto.updated_at}"
        )
        meta.add_css_class("ra-card-subtitle")
        meta.set_xalign(0)
        info.append(meta)

        self.append(info)

        # Badge de modo
        badge = Gtk.Label(label=dto.mode_label)
        badge.add_css_class("ra-badge")
        badge.add_css_class(dto.mode_badge_class)
        badge.set_valign(Gtk.Align.CENTER)
        self.append(badge)

        # Botones de accion
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        actions.set_valign(Gtk.Align.CENTER)

        edit_btn = Gtk.Button(label="✏️")
        edit_btn.add_css_class("ra-button-icon")
        edit_btn.set_tooltip_text("Editar playlist")
        edit_btn.connect("clicked", lambda b: self._on_edit(self._dto) if self._on_edit else None)
        actions.append(edit_btn)

        if not dto.is_system:
            delete_btn = Gtk.Button(label="🗑️")
            delete_btn.add_css_class("ra-button-icon")
            delete_btn.set_tooltip_text("Eliminar playlist")
            delete_btn.connect("clicked", lambda b: self._on_delete(self._dto) if self._on_delete else None)
            actions.append(delete_btn)

        self.append(actions)

    def _on_click(self, gesture, n_press, x, y):
        if self._on_select:
            self._on_select(self._dto)

    def update_dto(self, dto: PlaylistDTO):
        """Actualizar el DTO interno."""
        self._dto = dto


# ═══════════════════════════════════════
# Panel de listado
# ═══════════════════════════════════════

class PlaylistsPanel(PanelContainer):
    """Panel que muestra el listado de playlists del sistema."""

    def __init__(self, on_playlist_selected=None, on_playlist_edit=None):
        super().__init__(
            title="Playlists",
            subtitle="Gestiona tus playlists de audio",
            show_add=True,
        )
        self._service = PlaylistService()
        self._on_playlist_selected = on_playlist_selected
        self._on_playlist_edit = on_playlist_edit
        self._rows: list[tuple[PlaylistRow, int]] = []  # (row, playlist_id)

        # Boton de añadir
        if self.add_button:
            self.add_button.connect("clicked", self._show_create_dialog)

        # Contenedor con scroll
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        self._list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scroll.set_child(self._list)

        self.content.append(scroll)

        # Cargar playlists
        self.refresh()

    def refresh(self):
        """Recargar la lista de playlists."""
        # Limpiar lista existente
        _clear_box(self._list)
        self._rows.clear()

        playlists = self._service.get_all()

        if not playlists:
            self.set_empty_state("🎵", "No hay playlists creadas.\nCrea una nueva para empezar.")
            return

        for dto in playlists:
            row = PlaylistRow(
                dto=dto,
                on_edit=self._on_edit_clicked,
                on_delete=self._on_delete_clicked,
                on_select=self._on_select_clicked,
            )
            self._list.append(row)
            self._rows.append((row, dto.id))

    def _on_select_clicked(self, dto: PlaylistDTO):
        if self._on_playlist_selected:
            self._on_playlist_selected(dto)

    def _on_edit_clicked(self, dto: PlaylistDTO):
        self._show_edit_dialog(dto)

    def _on_delete_clicked(self, dto: PlaylistDTO):
        self._show_delete_confirm(dto)

    def _show_create_dialog(self):
        """Mostrar dialogo para crear nueva playlist."""
        dialog = Gtk.MessageDialog(
            transient_for=self.get_root() if self.get_root() else None,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            title="Nueva Playlist",
        )

        # Cambiar a layout personalizado
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(16)
        box.set_margin_end(16)

        # Nombre
        name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        name_label = Gtk.Label(label="Nombre:")
        name_label.set_width_chars(12)
        name_label.set_xalign(0)
        name_box.append(name_label)

        name_entry = Gtk.Entry()
        name_entry.set_placeholder_text("Nombre de la playlist")
        name_entry.add_css_class("ra-entry")
        name_entry.set_hexpand(True)
        name_entry.activate = lambda: dialog.response(Gtk.ResponseType.OK)  # type: ignore[assignment]
        name_box.append(name_entry)
        box.append(name_box)

        # Modo
        mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        mode_label = Gtk.Label(label="Modo:")
        mode_label.set_width_chars(12)
        mode_label.set_xalign(0)
        mode_box.append(mode_label)

        loop_btn = Gtk.ToggleButton(label="🔄 Bucle")
        loop_btn.set_active(True)
        loop_btn.add_css_class("ra-button")
        loop_btn.connect("toggled", lambda b: single_btn.set_active(not b.get_active()))

        single_btn = Gtk.ToggleButton(label="▶ Una vez")
        single_btn.add_css_class("ra-button")

        mode_box.append(loop_btn)
        mode_box.append(single_btn)
        box.append(mode_box)

        # Descripcion del modo
        desc = Gtk.Label(
            label="Bucle: se repite hasta que algo la interrumpa\n"
                  "Una vez: se reproduce de principio a fin una sola vez"
        )
        desc.add_css_class("ra-label-dim")
        desc.set_xalign(0)
        desc.set_margin_start(20)
        box.append(desc)

        dialog.set_child(box)
        name_entry.grab_focus()

        def on_response(dialog, response_id):
            if response_id == Gtk.ResponseType.OK:
                name = name_entry.get_text().strip()
                if not name:
                    return
                mode = "loop" if loop_btn.get_active() else "single"
                try:
                    self._service.create(name=name, mode=mode)
                    self.refresh()
                except PlaylistError as e:
                    self._show_error(f"Error al crear playlist: {e}")
            dialog.destroy()

        dialog.connect("response", on_response)
        dialog.show()

    def _show_edit_dialog(self, dto: PlaylistDTO):
        """Mostrar dialogo para editar una playlist existente."""
        dialog = Gtk.MessageDialog(
            transient_for=self.get_root() if self.get_root() else None,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            title=f"Editar: {dto.name}",
        )

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(16)
        box.set_margin_end(16)

        # Nombre
        name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        name_label = Gtk.Label(label="Nombre:")
        name_label.set_width_chars(12)
        name_label.set_xalign(0)
        name_box.append(name_label)

        name_entry = Gtk.Entry()
        name_entry.set_text(dto.name)
        name_entry.add_css_class("ra-entry")
        name_entry.set_hexpand(True)
        name_box.append(name_entry)
        box.append(name_box)

        # Modo (no editable para Continuidad? Si, editable)
        mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        mode_label = Gtk.Label(label="Modo:")
        mode_label.set_width_chars(12)
        mode_label.set_xalign(0)
        mode_box.append(mode_label)

        loop_btn = Gtk.ToggleButton(label="🔄 Bucle")
        loop_btn.set_active(dto.mode == "loop")
        loop_btn.add_css_class("ra-button")
        loop_btn.connect("toggled", lambda b: single_btn.set_active(not b.get_active()))

        single_btn = Gtk.ToggleButton(label="▶ Una vez")
        single_btn.set_active(dto.mode == "single")
        single_btn.add_css_class("ra-button")

        mode_box.append(loop_btn)
        mode_box.append(single_btn)
        box.append(mode_box)

        dialog.set_child(box)
        name_entry.grab_focus()

        def on_response(dialog, response_id):
            if response_id == Gtk.ResponseType.OK:
                name = name_entry.get_text().strip()
                if not name:
                    return
                mode = "loop" if loop_btn.get_active() else "single"
                try:
                    self._service.update(dto.id, name=name, mode=mode)
                    self.refresh()
                    if self._on_playlist_edit:
                        self._on_playlist_edit()
                except PlaylistError as e:
                    self._show_error(f"Error al actualizar: {e}")
            dialog.destroy()

        dialog.connect("response", on_response)
        dialog.show()

    def _show_delete_confirm(self, dto: PlaylistDTO):
        """Mostrar dialogo de confirmacion para eliminar."""
        dialog = Gtk.MessageDialog(
            transient_for=self.get_root() if self.get_root() else None,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            title="Eliminar Playlist",
        )

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(16)
        box.set_margin_end(16)

        msg = Gtk.Label(
            label=f"¿Seguro que quieres eliminar la playlist \"{dto.name}\"?\n"
                  f"Tiene {dto.item_count} elemento(s)."
        )
        msg.set_xalign(0)
        box.append(msg)
        dialog.set_child(box)

        def on_response(dialog, response_id):
            if response_id == Gtk.ResponseType.YES:
                try:
                    self._service.delete(dto.id)
                    self.refresh()
                except PlaylistProtectedError:
                    self._show_error("La playlist Continuidad no se puede eliminar")
                except PlaylistError as e:
                    self._show_error(f"Error al eliminar: {e}")
            dialog.destroy()

        dialog.connect("response", on_response)
        dialog.show()

    def _show_error(self, message: str):
        """Mostrar un dialogo de error."""
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
