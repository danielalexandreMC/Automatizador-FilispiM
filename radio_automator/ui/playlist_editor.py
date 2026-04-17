"""
Editor de playlist individual.
Muestra los items de una playlist con drag & drop y opciones de añadir.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GLib, GObject, Pango

from radio_automator.services.playlist_service import (
    PlaylistService, PlaylistDTO, PlaylistItemDTO
)
from radio_automator.services.folder_scanner import FolderScanner

from radio_automator.ui.file_dialogs import open_file_chooser, AUDIO_FILTERS

# Función auxiliar (engadir despois dos imports)
def _clear_box(box):
    """Eliminar todos os fillows dun Box."""
    child = box.get_first_child()
    while child is not None:
        next_child = child.get_next_sibling()
        box.remove(child)
        child = next_child

# ═══════════════════════════════════════
# Fila de item en la lista de playlist
# ═══════════════════════════════════════

class PlaylistItemRow(Gtk.Box):
    """Fila visual para un item dentro de una playlist."""

    def __init__(self, item: PlaylistItemDTO, on_remove=None, on_move_up=None, on_move_down=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._item = item
        self._on_remove = on_remove
        self._on_move_up = on_move_up
        self._on_move_down = on_move_down

        self.set_margin_top(2)
        self.set_margin_bottom(2)
        self.set_margin_start(4)
        self.set_margin_end(4)
        self.set_cursor_from_name("grab")

        # Indicador de posicion
        pos_label = Gtk.Label(label=f"{item.position + 1}.")
        pos_label.add_css_class("ra-label-dim")
        pos_label.set_width_chars(3)
        pos_label.set_xalign(1)
        self.append(pos_label)

        # Icono de tipo
        icon = Gtk.Label(label=item.type_icon)
        icon.set_width_chars(2)
        self.append(icon)

        # Nombre del item
        name_label = Gtk.Label(label=item.label)
        name_label.set_hexpand(True)
        name_label.set_xalign(0)
        name_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.append(name_label)

        # Badge de tipo
        type_badge = Gtk.Label(label=item.type_label)
        type_badge.add_css_class("ra-badge")
        type_badge.add_css_class("ra-badge-single")
        type_badge.set_valign(Gtk.Align.CENTER)
        self.append(type_badge)

        # Botones
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)

        up_btn = Gtk.Button(label="▲")
        up_btn.add_css_class("ra-button-sm")
        up_btn.add_css_class("ra-button")
        up_btn.set_tooltip_text("Subir")
        if on_move_up:
            up_btn.connect("clicked", lambda b: on_move_up(item))
        actions.append(up_btn)

        down_btn = Gtk.Button(label="▼")
        down_btn.add_css_class("ra-button-sm")
        down_btn.add_css_class("ra-button")
        down_btn.set_tooltip_text("Bajar")
        if on_move_down:
            down_btn.connect("clicked", lambda b: on_move_down(item))
        actions.append(down_btn)

        remove_btn = Gtk.Button(label="✕")
        remove_btn.add_css_class("ra-button-sm")
        remove_btn.add_css_class("ra-button-danger")
        remove_btn.set_tooltip_text("Eliminar")
        if on_remove:
            remove_btn.connect("clicked", lambda b: on_remove(item))
        actions.append(remove_btn)

        self.append(actions)


# ═══════════════════════════════════════
# Editor de playlist
# ═══════════════════════════════════════

class PlaylistEditor(Gtk.Box):
    """Editor completo de una playlist con sus items."""

    def __init__(self, playlist_dto: PlaylistDTO, on_back=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("ra-panel")

        self._dto = playlist_dto
        self._service = PlaylistService()
        self._on_back = on_back
        self._items: list[PlaylistItemDTO] = []

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # Header con boton volver
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header.set_margin_bottom(16)

        back_btn = Gtk.Button(label="← Volver")
        back_btn.add_css_class("ra-button")
        if self._on_back:
            back_btn.connect("clicked", lambda b: self._on_back())
        header.append(back_btn)

        title = Gtk.Label(label=self._dto.name)
        title.add_css_class("ra-title")
        title.set_hexpand(True)
        title.set_xalign(0)
        header.append(title)

        # Badge de modo
        badge = Gtk.Label(label=self._dto.mode_label)
        badge.add_css_class("ra-badge")
        badge.add_css_class(self._dto.mode_badge_class)
        badge.set_valign(Gtk.Align.CENTER)
        header.append(badge)

        self.append(header)

        # Info de la playlist
        info_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        info_bar.set_margin_bottom(12)

        count_label = Gtk.Label(label=f"Elementos: {self._dto.item_count}")
        count_label.add_css_class("ra-label")
        info_bar.append(count_label)

        system_label = Gtk.Label(label="Sistema (Continuidad)")
        system_label.add_css_class("ra-badge-system")
        system_label.add_css_class("ra-badge")
        if not self._dto.is_system:
            system_label.set_visible(False)
        info_bar.append(system_label)

        info_bar.set_hexpand(True)
        self.append(info_bar)

        # Botones de accion
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_margin_bottom(8)

        add_track_btn = Gtk.Button(label="🎵 Añadir pista")
        add_track_btn.add_css_class("ra-button")
        add_track_btn.connect("clicked", self._add_track)
        toolbar.append(add_track_btn)

        add_folder_btn = Gtk.Button(label="📁 Añadir carpeta")
        add_folder_btn.add_css_class("ra-button")
        add_folder_btn.connect("clicked", self._add_folder)
        toolbar.append(add_folder_btn)

        add_playlist_btn = Gtk.Button(label="🔗 Añadir playlist")
        add_playlist_btn.add_css_class("ra-button")
        add_playlist_btn.connect("clicked", self._add_playlist)
        toolbar.append(add_playlist_btn)

        add_time_btn = Gtk.Button(label="🕐 Hora")
        add_time_btn.add_css_class("ra-button")
        add_time_btn.connect("clicked", self._add_time_announce)
        toolbar.append(add_time_btn)

        toolbar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        clear_btn = Gtk.Button(label="🗑️ Vaciar")
        clear_btn.add_css_class("ra-button-danger")
        clear_btn.add_css_class("ra-button")
        clear_btn.connect("clicked", self._clear_all)
        toolbar.append(clear_btn)

        self.append(toolbar)

        # Lista de items con scroll
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        self._items_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        scroll.set_child(self._items_list)
        self.append(scroll)

    def refresh(self):
        """Recargar los items de la playlist."""
        _clear_box(self._items_list)
        self._items = self._service.get_items(self._dto.id)

        if not self._items:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            box.add_css_class("ra-empty-state")
            box.set_valign(Gtk.Align.CENTER)
            box.set_vexpand(True)

            icon = Gtk.Label(label="📝")
            icon.set_xalign(0.5)
            box.append(icon)

            msg = Gtk.Label(label="Playlist vacia.\nAñade pistas, carpetas u otras playlists.")
            msg.add_css_class("ra-label-dim")
            msg.set_xalign(0.5)
            box.append(msg)

            self._items_list.append(box)
            return

        for item in self._items:
            row = PlaylistItemRow(
                item=item,
                on_remove=self._remove_item,
                on_move_up=self._move_up,
                on_move_down=self._move_down,
            )
            self._items_list.append(row)

    def _add_track(self, _btn):
        """Dialogo para seleccionar archivos de audio."""
        root = self.get_root() or None
        files = open_file_chooser(root, "Seleccionar pistas de audio",
                                  action=Gtk.FileChooserAction.OPEN,
                                  select_multiple=True,
                                  filters=AUDIO_FILTERS)
        for filepath in files:
            try:
                self._service.add_item(
                    playlist_id=self._dto.id,
                    item_type="track",
                    filepath=filepath,
                )
            except Exception as e:
                print(f"[PlaylistEditor] Error al anadir pista: {e}")
        if files:
            self.refresh()

    def _add_folder(self, _btn):
        """Dialogo para seleccionar una carpeta de audio."""
        root = self.get_root() or None
        folders = open_file_chooser(root, "Seleccionar carpeta de audio",
                                    action=Gtk.FileChooserAction.SELECT_FOLDER)
        for folder in folders:
            try:
                self._service.add_item(
                    playlist_id=self._dto.id,
                    item_type="folder",
                    filepath=folder,
                )
            except Exception as e:
                print(f"[PlaylistEditor] Error al anadir carpeta: {e}")
        if folders:
            self.refresh()

    def _add_playlist(self, _btn):
        """Dialogo para seleccionar una playlist existente como item."""
        playlists = self._service.get_all()
        # Filtrar la playlist actual y las que causarian referencia circular
        available = [p for p in playlists if p.id != self._dto.id]

        if not available:
            self._show_error("No hay otras playlists disponibles para anidar")
            return

        dialog = Gtk.MessageDialog(
            transient_for=self.get_root() if self.get_root() else None,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            title="Añadir Playlist",
        )

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(16)
        box.set_margin_end(16)

        info = Gtk.Label(
            label="Selecciona una playlist para anidar dentro de esta.\n"
                  "Cuando se reproduzca, se reproducira la playlist anidada completa."
        )
        info.add_css_class("ra-label-dim")
        info.set_xalign(0)
        info.set_wrap(True)
        box.append(info)

        # Combo con playlists disponibles
        combo = Gtk.DropDown.new_from_strings([p.name for p in available])
        combo.add_css_class("ra-combo")
        box.append(combo)

        dialog.set_child(box)

        def on_response(dialog, response_id):
            if response_id == Gtk.ResponseType.OK:
                idx = combo.get_selected()
                if 0 <= idx < len(available):
                    selected = available[idx]
                    try:
                        self._service.add_item(
                            playlist_id=self._dto.id,
                            item_type="playlist",
                            referenced_playlist_id=selected.id,
                        )
                        self.refresh()
                    except Exception as e:
                        self._show_error(f"Error al anadir playlist: {e}")
            dialog.destroy()

        dialog.connect("response", on_response)
        dialog.show()

    def _add_time_announce(self, _btn):
        """Añadir insertar hora como item."""
        try:
            self._service.add_item(
                playlist_id=self._dto.id,
                item_type="time_announce",
            )
            self.refresh()
        except Exception as e:
            self._show_error(f"Error al anadir: {e}")

    def _remove_item(self, item: PlaylistItemDTO):
        """Eliminar un item de la playlist."""
        try:
            self._service.remove_item(item.id)
            self.refresh()
        except Exception as e:
            self._show_error(f"Error al eliminar item: {e}")

    def _move_up(self, item: PlaylistItemDTO):
        """Mover item una posicion arriba."""
        if item.position > 0:
            try:
                self._service.reorder_item(item.id, item.position - 1)
                self.refresh()
            except Exception as e:
                self._show_error(f"Error al reordenar: {e}")

    def _move_down(self, item: PlaylistItemDTO):
        """Mover item una posicion abajo."""
        try:
            self._service.reorder_item(item.id, item.position + 1)
            self.refresh()
        except Exception as e:
            self._show_error(f"Error al reordenar: {e}")

    def _clear_all(self, _btn):
        """Confirmar vaciar toda la playlist."""
        dialog = Gtk.MessageDialog(
            transient_for=self.get_root() if self.get_root() else None,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            title="Vaciar Playlist",
            text=f"¿Seguro que quieres vaciar \"{self._dto.name}\"? Esta accion no se puede deshacer.",
        )

        def on_response(dialog, response_id):
            if response_id == Gtk.ResponseType.YES:
                try:
                    self._service.clear_items(self._dto.id)
                    self.refresh()
                except Exception as e:
                    self._show_error(f"Error al vaciar: {e}")
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
