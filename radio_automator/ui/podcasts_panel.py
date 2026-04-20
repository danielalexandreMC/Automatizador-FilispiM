"""
Panel de gestion de Podcasts RSS.
Lista feeds, vista de episodios, descargas, modos replace/accumulate.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Pango

from radio_automator.ui.layout import PanelContainer
from radio_automator.services.podcast_service import (
    PodcastService, FeedDTO, EpisodeDTO,
    PodcastError, FeedNotFoundError, FeedLimitError
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
# Fila de feed
# ═══════════════════════════════════════

class FeedRow(Gtk.Box):
    """Fila visual para un feed RSS."""

    def __init__(self, dto: FeedDTO, on_edit=None, on_delete=None,
                 on_check=None, on_view_episodes=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self._dto = dto

        self.set_margin_top(4)
        self.set_margin_bottom(4)
        self.set_margin_start(4)
        self.set_margin_end(4)
        self.add_css_class("ra-card")
        self.set_cursor_from_name("pointer")

        # Click para ver episodios
        click = Gtk.GestureClick()
        click.connect("released", lambda *a: on_view_episodes(dto) if on_view_episodes else None)
        self.add_controller(click)

        # Info
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info.set_hexpand(True)
        info.set_valign(Gtk.Align.CENTER)

        name = Gtk.Label(label=dto.name)
        name.add_css_class("ra-card-title")
        name.set_xalign(0)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        info.append(name)

        meta = Gtk.Label(
            label=f"{dto.episode_count} episodios  ·  {dto.mode_label}"
                  f"{f' (max {dto.max_label})' if dto.max_episodes else ''}"
                  f"  ·  Ultima revision: {dto.last_check_at}"
        )
        meta.add_css_class("ra-card-subtitle")
        meta.set_xalign(0)
        info.append(meta)

        self.append(info)

        # Badge de estado
        badge_text = f"{'● ' + dto.status_text}"
        badge = Gtk.Label(label=badge_text)
        badge.add_css_class("ra-badge")
        if dto.is_active:
            badge.add_css_class("ra-badge-loop")
        else:
            badge.add_css_class("ra-badge-single")
        badge.set_valign(Gtk.Align.CENTER)
        self.append(badge)

        # Botones
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        actions.set_valign(Gtk.Align.CENTER)

        check_btn = Gtk.Button(label="🔄")
        check_btn.add_css_class("ra-button-icon")
        check_btn.set_tooltip_text("Comprobar ahora")
        if on_check:
            check_btn.connect("clicked", lambda b: on_check(dto))
        actions.append(check_btn)

        edit_btn = Gtk.Button(label="✏️")
        edit_btn.add_css_class("ra-button-icon")
        edit_btn.set_tooltip_text("Editar feed")
        if on_edit:
            edit_btn.connect("clicked", lambda b: on_edit(dto))
        actions.append(edit_btn)

        delete_btn = Gtk.Button(label="🗑️")
        delete_btn.add_css_class("ra-button-icon")
        delete_btn.set_tooltip_text("Eliminar feed")
        if on_delete:
            delete_btn.connect("clicked", lambda b: on_delete(dto))
        actions.append(delete_btn)

        self.append(actions)


# ═══════════════════════════════════════
# Vista de episodios de un feed
# ═══════════════════════════════════════

class EpisodesView(Gtk.Box):
    """Vista de los episodios descargados de un feed."""

    def __init__(self, feed_dto: FeedDTO, on_back=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("ra-panel")

        self._dto = feed_dto
        self._service = PodcastService()
        self._on_back = on_back

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header.set_margin_bottom(16)

        if self._on_back:
            back_btn = Gtk.Button(label="← Volver")
            back_btn.add_css_class("ra-button")
            back_btn.connect("clicked", lambda b: self._on_back())
            header.append(back_btn)

        title = Gtk.Label(label=self._dto.name)
        title.add_css_class("ra-title")
        title.set_hexpand(True)
        title.set_xalign(0)
        header.append(title)

        self.append(header)

        # Info
        info = Gtk.Label(
            label=f"Modo: {self._dto.mode_label}  ·  "
                  f"Carpeta: {self._dto.folder_path}  ·  "
                  f"URL: {self._dto.url}"
        )
        info.add_css_class("ra-label-dim")
        info.set_xalign(0)
        info.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        info.set_margin_bottom(12)
        self.append(info)

        # Lista de episodios con scroll
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        self._list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        scroll.set_child(self._list)
        self.append(scroll)

    def refresh(self):
        _clear_box(self._list)
        episodes = self._service.get_episodes(self._dto.id)

        if not episodes:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            box.add_css_class("ra-empty-state")
            box.set_valign(Gtk.Align.CENTER)
            box.set_vexpand(True)

            icon = Gtk.Label(label="📡")
            icon.set_xalign(0.5)
            box.append(icon)

            msg = Gtk.Label(label="No hay episodios descargados.\nUsa 🔄 para comprobar el feed.")
            msg.add_css_class("ra-label-dim")
            msg.set_xalign(0.5)
            box.append(msg)

            self._list.append(box)
            return

        for ep in episodes:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.set_margin_top(3)
            row.set_margin_bottom(3)
            row.set_margin_start(6)
            row.set_margin_end(6)
            row.add_css_class("ra-card")

            # Info
            ep_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            ep_info.set_hexpand(True)
            ep_info.set_valign(Gtk.Align.CENTER)

            ep_title = Gtk.Label(label=ep.title)
            ep_title.set_xalign(0)
            ep_title.set_ellipsize(Pango.EllipsizeMode.END)
            ep_info.append(ep_title)

            ep_meta = Gtk.Label(
                label=f"📅 {ep.published_at}  ·  {ep.size_label}  ·  {ep.filename}"
            )
            ep_meta.add_css_class("ra-label-dim")
            ep_meta.set_xalign(0)
            ep_meta.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            ep_info.append(ep_meta)

            row.append(ep_info)

            # Boton eliminar
            del_btn = Gtk.Button(label="✕")
            del_btn.add_css_class("ra-button-sm")
            del_btn.add_css_class("ra-button-danger")
            del_btn.set_tooltip_text("Eliminar episodio")
            del_btn.connect("clicked", self._make_delete_handler(ep))
            row.append(del_btn)

            self._list.append(row)

    def _make_delete_handler(self, ep: EpisodeDTO):
        def handler(btn):
            self._service.delete_episode(ep.id)
            self.refresh()
        return handler


# ═══════════════════════════════════════
# Panel principal de Podcasts
# ═══════════════════════════════════════

class PodcastsPanel(PanelContainer):
    """Panel principal de gestion de podcasts."""

    def __init__(self):
        super().__init__(
            title="Podcasts",
            subtitle="Gestiona feeds RSS y descargas de episodios",
            show_add=True,
        )
        self._service = PodcastService()
        self._current_view = "feeds"  # feeds | episodes

        # Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_margin_bottom(8)

        check_all_btn = Gtk.Button(label="🔄 Comprobar todos")
        check_all_btn.add_css_class("ra-button")
        check_all_btn.connect("clicked", self._check_all_feeds)
        toolbar.append(check_all_btn)

        # Info de almacenamiento
        storage_label = Gtk.Label(label="")
        storage_label.add_css_class("ra-label-dim")
        storage_label.set_hexpand(True)
        storage_label.set_xalign(1)
        storage_label.set_name("storage-label")
        toolbar.append(storage_label)
        self._storage_label = storage_label

        self.content.append(toolbar)

        # Lista con scroll
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        self._feeds_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scroll.set_child(self._feeds_list)
        self.content.append(scroll)

        # Estado de comprobacion
        self._status_label = Gtk.Label(label="")
        self._status_label.add_css_class("ra-label")
        self._status_label.set_margin_top(4)
        self.content.append(self._status_label)

        if self.add_button:
            self.add_button.connect("clicked", self._show_add_dialog)

        # Stack interno para alternar feeds/episodios
        self._view_stack = Gtk.Stack()
        self._view_stack.set_vexpand(True)
        self._view_stack.set_hexpand(True)

        self.refresh()

    def refresh(self):
        self._update_storage_info()
        if self._current_view == "feeds":
            self._refresh_feeds()

    def _update_storage_info(self):
        try:
            mb = self._service.get_total_storage_mb()
            if mb < 1024:
                self._storage_label.set_label(f"💾 {mb:.1f} MB usados")
            else:
                self._storage_label.set_label(f"💾 {mb/1024:.2f} GB usados")
        except Exception:
            pass

    def _refresh_feeds(self):
        _clear_box(self._feeds_list)
        feeds = self._service.get_all_feeds()

        if not feeds:
            self.set_empty_state(
                "📡",
                "No hay feeds de podcast configurados.\n"
                "Añade un feed RSS para empezar a descargar episodios."
            )
            return

        for dto in feeds:
            row = FeedRow(
                dto=dto,
                on_edit=self._show_edit_dialog,
                on_delete=self._show_delete_confirm,
                on_check=self._check_single_feed,
                on_view_episodes=self._show_episodes,
            )
            self._feeds_list.append(row)

    def _show_episodes(self, dto: FeedDTO):
        """Mostrar la vista de episodios de un feed."""
        # Limpiar contenido actual
        _clear_box(self.content)

        # Crear vista de episodios
        view = EpisodesView(dto, on_back=self._back_to_feeds)
        self.content.append(view)

        # Ocultar toolbar y add button temporalmente
        self._current_view = "episodes"

    def _back_to_feeds(self):
        """Volver a la vista de feeds."""
        self._current_view = "feeds"
        _clear_box(self.content)

        # Restaurar toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_margin_bottom(8)

        check_all_btn = Gtk.Button(label="🔄 Comprobar todos")
        check_all_btn.add_css_class("ra-button")
        check_all_btn.connect("clicked", self._check_all_feeds)
        toolbar.append(check_all_btn)

        storage_label = Gtk.Label(label="")
        storage_label.add_css_class("ra-label-dim")
        storage_label.set_hexpand(True)
        storage_label.set_xalign(1)
        toolbar.append(storage_label)
        self._storage_label = storage_label
        self.content.append(toolbar)

        # Lista con scroll
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        self._feeds_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scroll.set_child(self._feeds_list)
        self.content.append(scroll)

        self._status_label = Gtk.Label(label="")
        self._status_label.add_css_class("ra-label")
        self._status_label.set_margin_top(4)
        self.content.append(self._status_label)

        self._refresh_feeds()

    def _check_single_feed(self, dto: FeedDTO):
        """Comprobar un feed individualmente."""
        self._status_label.set_text(f"🔄 Comprobando {dto.name}...")
        self._status_label.remove_css_class("ra-label-error")
        self._status_label.remove_css_class("ra-label-success")

        def do_check():
            try:
                result = self._service.check_feed(dto.id)
                GLib.idle_add(lambda: self._show_check_result(
                    dto.name, result
                ))
            except Exception as e:
                GLib.idle_add(lambda: self._show_check_error(dto.name, str(e)))

        import threading
        thread = threading.Thread(target=do_check, daemon=True)
        thread.start()

    def _check_all_feeds(self, _btn):
        """Comprobar todos los feeds en background."""
        self._status_label.set_text("🔄 Comprobando todos los feeds...")
        self._status_label.remove_css_class("ra-label-error")
        self._status_label.remove_css_class("ra-label-success")

        def do_check():
            try:
                result = self._service.check_all_feeds()
                GLib.idle_add(lambda: self._show_check_result(
                    "Todos los feeds", result
                ))
            except Exception as e:
                GLib.idle_add(lambda: self._show_check_error(
                    "Todos los feeds", str(e)
                ))

        import threading
        thread = threading.Thread(target=do_check, daemon=True)
        thread.start()

    def _show_check_result(self, name: str, result: dict):
        new = result.get("new", 0)
        downloaded = result.get("downloaded", 0)
        errors = result.get("errors", 0)
        skipped = result.get("skipped", 0)

        if errors > 0:
            msg = f"⚠ {name}: {new} nuevos, {downloaded} descargados, {errors} errores"
            self._status_label.add_css_class("ra-label-warning")
        else:
            msg = f"✓ {name}: {new} nuevos, {downloaded} descargados, {skipped} ya tenidos"
            self._status_label.add_css_class("ra-label-success")

        self._status_label.set_text(msg)
        self.refresh()

    def _show_check_error(self, name: str, error: str):
        self._status_label.set_text(f"✗ Error en {name}: {error}")
        self._status_label.add_css_class("ra-label-error")

    def _show_add_dialog(self, _btn=None, edit_dto: FeedDTO | None = None):
        """Dialogo para añadir o editar un feed."""
        is_edit = edit_dto is not None
        title = f"Editar: {edit_dto.name}" if is_edit else "Nuevo Feed RSS"

        dialog = Gtk.Window(
            transient_for=self.get_root() if self.get_root() else None,
            modal=True,
            title=title,
            default_width=500,
            default_height=420,
        )

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(16)
        box.set_margin_end(16)

        # Nombre
        name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        name_label = Gtk.Label(label="Nombre:")
        name_label.set_width_chars(14)
        name_label.set_xalign(0)
        name_box.append(name_label)
        name_entry = Gtk.Entry()
        name_entry.set_text(edit_dto.name if is_edit else "")
        name_entry.set_placeholder_text("Nombre del podcast")
        name_entry.add_css_class("ra-entry")
        name_entry.set_hexpand(True)
        name_box.append(name_entry)
        box.append(name_box)

        # URL
        url_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        url_label = Gtk.Label(label="URL RSS:")
        url_label.set_width_chars(14)
        url_label.set_xalign(0)
        url_box.append(url_label)
        url_entry = Gtk.Entry()
        url_entry.set_text(edit_dto.url if is_edit else "")
        url_entry.set_placeholder_text("https://ejemplo.com/feed.xml")
        url_entry.add_css_class("ra-entry")
        url_entry.set_hexpand(True)
        url_box.append(url_entry)
        box.append(url_box)

        # Carpeta de descarga
        folder_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        folder_label = Gtk.Label(label="Carpeta:")
        folder_label.set_width_chars(14)
        folder_label.set_xalign(0)
        folder_box.append(folder_label)

        folder_path_label = Gtk.Label(
            label=edit_dto.folder_path if is_edit else "(Seleccionar)"
        )
        folder_path_label.set_hexpand(True)
        folder_path_label.set_xalign(0)
        folder_path_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        folder_box.append(folder_path_label)

        browse_btn = Gtk.Button(label="📂")
        browse_btn.add_css_class("ra-button")

        selected_folder = {"path": edit_dto.folder_path if is_edit else ""}

        def on_browse(btn):
            dlg = Gtk.FileChooserNative(
                title="Seleccionar carpeta de descarga",
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

        browse_btn.connect("clicked", on_browse)
        folder_box.append(browse_btn)
        box.append(folder_box)

        # Modo
        mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        mode_label = Gtk.Label(label="Modo:")
        mode_label.set_width_chars(14)
        mode_label.set_xalign(0)
        mode_box.append(mode_label)

        replace_btn = Gtk.ToggleButton(label="🔄 Reemplazar")
        replace_btn.set_active(edit_dto.mode == "replace" if is_edit else True)
        replace_btn.add_css_class("ra-button")
        replace_btn.connect("toggled", lambda b: accumulate_btn.set_active(not b.get_active()))

        accumulate_btn = Gtk.ToggleButton(label="📥 Acumular")
        accumulate_btn.set_active(edit_dto.mode == "accumulate" if is_edit else False)
        accumulate_btn.add_css_class("ra-button")

        mode_box.append(replace_btn)
        mode_box.append(accumulate_btn)
        box.append(mode_box)

        # Descripcion de modos
        mode_desc = Gtk.Label(
            label="Reemplazar: solo mantiene los N ultimos episodios\n"
                  "Acumular: guarda todos los episodios descargados"
        )
        mode_desc.add_css_class("ra-label-dim")
        mode_desc.set_xalign(0)
        mode_desc.set_margin_start(14)
        box.append(mode_desc)

        # Max episodios (solo en modo replace)
        max_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        max_label = Gtk.Label(label="Max episodios:")
        max_label.set_width_chars(14)
        max_label.set_xalign(0)
        max_box.append(max_label)

        max_spin = Gtk.SpinButton.new_with_range(1, 999, 1)
        max_spin.add_css_class("ra-entry")
        max_val = edit_dto.max_episodes if is_edit and edit_dto.max_episodes else 10
        max_spin.set_value(max_val)
        max_box.append(max_spin)

        no_limit_label = Gtk.Label(label="(0 = sin limite)")
        no_limit_label.add_css_class("ra-label-dim")
        max_box.append(no_limit_label)
        box.append(max_box)

        dialog.set_child(box)
        name_entry.grab_focus()

        def on_response(dialog, response_id):
            if response_id == Gtk.ResponseType.OK:
                name = name_entry.get_text().strip()
                url = url_entry.get_text().strip()
                folder = selected_folder["path"].strip()
                mode = "replace" if replace_btn.get_active() else "accumulate"
                max_ep = int(max_spin.get_value())

                if not name:
                    self._show_error("El nombre es obligatorio")
                    return
                if not url:
                    self._show_error("La URL del feed es obligatoria")
                    return
                if not folder:
                    self._show_error("Selecciona una carpeta de descarga")
                    return

                try:
                    if is_edit:
                        self._service.update_feed(
                            feed_id=edit_dto.id,
                            name=name, url=url,
                            folder_path=folder,
                            mode=mode,
                            max_episodes=max_ep,
                        )
                    else:
                        self._service.add_feed(
                            name=name, url=url,
                            folder_path=folder,
                            mode=mode,
                            max_episodes=max_ep,
                        )
                    self.refresh()
                except FeedLimitError as e:
                    self._show_error(str(e))
                except PodcastError as e:
                    self._show_error(f"Error: {e}")
            dialog.destroy()

        dialog.connect("response", on_response)
        dialog.show()

    def _show_edit_dialog(self, dto: FeedDTO):
        self._show_add_dialog(edit_dto=dto)

    def _show_delete_confirm(self, dto: FeedDTO):
        dialog = Gtk.Window(
            transient_for=self.get_root() if self.get_root() else None,
            modal=True,
            title="Eliminar Feed",
            default_width=400,
            default_height=180,
        )

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)

        msg = Gtk.Label(
            label=f"¿Seguro que queres eliminar \"{dto.name}\"?\n"
                  f"Eliminaranse os {dto.episode_count} episodio(s) descargados\n"
                  f"e os seus ficheiros locais."
        )
        msg.set_xalign(0)
        box.append(msg)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(12)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        btn_box.append(spacer)

        cancel_btn = Gtk.Button(label="Cancelar")
        cancel_btn.add_css_class("ra-button")
        cancel_btn.connect("clicked", lambda b: dialog.destroy())
        btn_box.append(cancel_btn)

        delete_btn = Gtk.Button(label="Eliminar")
        delete_btn.add_css_class("destructive-action")

        def do_delete():
            try:
                self._service.delete_feed(dto.id)
                self.refresh()
            except Exception as e:
                self._show_error(f"Error ao eliminar: {e}")
            dialog.destroy()

        delete_btn.connect("clicked", lambda b: do_delete())
        btn_box.append(delete_btn)
        box.append(btn_box)

        dialog.set_child(box)
        dialog.show()

    def _show_error(self, message: str):
        dialog = Gtk.Window(
            transient_for=self.get_root() if self.get_root() else None,
            modal=True,
            title="Error",
            default_width=400,
            default_height=150,
        )

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_start(16)
        box.set_margin_end(16)
        box.set_margin_bottom(16)

        msg = Gtk.Label(label=message)
        msg.set_xalign(0)
        box.append(msg)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        close_btn = Gtk.Button(label="Pechar")
        close_btn.add_css_class("ra-button-primary")
        close_btn.connect("clicked", lambda b: dialog.destroy())
        btn_box.append(close_btn)
        box.append(btn_box)

        dialog.set_child(box)
        dialog.show()
