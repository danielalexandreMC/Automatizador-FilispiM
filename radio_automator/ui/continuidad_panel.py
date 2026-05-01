"""
Panel de la playlist Continuidad.
Muestra y permite editar (pero no eliminar) la playlist Continuidad.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib
from pathlib import Path

from radio_automator.ui.playlist_editor import PlaylistEditor
from radio_automator.services.playlist_service import PlaylistService


class ContinuidadPanel(Gtk.Box):
    """
    Panel dedicado a la playlist Continuidad.
    Hereda del editor de playlist pero con contexto especial.
    """

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self._service = PlaylistService()
        self._highlight_timer = None
        self._last_playing_label = None  # Para evitar repaints innecesarios

        # Header informativo
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        header.set_margin_start(20)
        header.set_margin_end(20)
        header.set_margin_top(20)
        header.set_margin_bottom(8)

        title = Gtk.Label(label="Continuidad")
        title.add_css_class("ra-title")
        title.set_xalign(0)
        header.append(title)

        desc = Gtk.Label(
            label="Playlist del sistema que se reproduce automaticamente cuando "
                  "no hay eventos programados. Se reanuda desde el punto donde "
                  "se detuvo. No se puede eliminar."
        )
        desc.add_css_class("ra-label")
        desc.set_xalign(0)
        desc.set_wrap(True)
        desc.set_max_width_chars(80)
        header.append(desc)

        # Indicador de estado (soando / parado)
        self._status_badge = Gtk.Label(label="")
        self._status_badge.set_xalign(0)
        header.append(self._status_badge)

        badge = Gtk.Label(label="SISTEMA - Protegida")
        badge.add_css_class("ra-badge")
        badge.add_css_class("ra-badge-system")
        badge.set_xalign(0)
        header.append(badge)

        self.append(header)

        # Editor de playlist
        try:
            dto = self._service.get_continuity()
            self._editor = PlaylistEditor(dto, on_back=None)
        except Exception as e:
            # Si no existe, mostrar error
            error_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            error_box.add_css_class("ra-empty-state")
            error_box.set_vexpand(True)

            msg = Gtk.Label(
                label=f"No se pudo cargar la playlist Continuidad.\nError: {e}"
            )
            msg.add_css_class("ra-label-error")
            error_box.append(msg)
            self._editor = error_box

        self.append(self._editor)

        # Iniciar monitor de now-playing
        self._start_playing_monitor()

    def _start_playing_monitor(self):
        """Iniciar timer para monitorizar se Continuidad esta soando."""
        def _check():
            try:
                self._update_playing_state()
            except Exception:
                pass
            return True

        self._highlight_timer = GLib.timeout_add(2000, _check)

    def _update_playing_state(self):
        """Comprobar se Continuidad esta soando e resaltar a pista actual
        (ou a carpeta/playlist/hora que a contén)."""
        from radio_automator.services.automation_engine import (
            get_automation_engine, PlaybackSource
        )
        from radio_automator.services.audio_engine import (
            get_audio_engine, PlaybackState
        )
        from radio_automator.core.database import get_session, PlaylistItem as PI

        automation = get_automation_engine()
        engine = get_audio_engine()

        is_continuidad_playing = (
            automation.is_active
            and automation.source == PlaybackSource.CONTINUIDAD
            and engine.state == PlaybackState.PLAYING
        )

        # Actualizar badge de estado
        if is_continuidad_playing:
            self._status_badge.set_label("● EN REPRODUCCION")
            self._status_badge.remove_css_class("ra-label-dim")
            self._status_badge.add_css_class("ra-label-accent")
        else:
            self._status_badge.set_label("")
            self._status_badge.remove_css_class("ra-label-accent")
            self._status_badge.add_css_class("ra-label-dim")

        # Acceder a lista de items do editor
        if not hasattr(self._editor, '_items_list'):
            return

        items_list = self._editor._items_list
        current_filepath = engine.track_info.filepath or ""
        current_title = engine.track_info.title or ""

        # Normalizar o filepath actual (quitar file:// prefix)
        if current_filepath.startswith("file://"):
            current_real_path = current_filepath.replace("file://", "")
        else:
            current_real_path = current_filepath

        # Consultar os items reais da playlist Continuidad na BD
        # para ter acceso a filepath, folder_path, referenced_playlist_id
        matching_positions = set()  # Positions dos items que coinciden

        if is_continuidad_playing and current_real_path:
            # O dto esta no editor, non no panel
            playlist_id = None
            if hasattr(self._editor, '_dto') and hasattr(self._editor._dto, 'id'):
                playlist_id = self._editor._dto.id
            if not playlist_id:
                return

            session = get_session()
            try:
                items_db = (
                    session.query(PI)
                    .filter_by(playlist_id=playlist_id)
                    .order_by(PI.position)
                    .all()
                )

                for db_item in items_db:
                    matched = False

                    if db_item.item_type == "track":
                        # Comparar filepath exacto
                        if db_item.filepath:
                            if db_item.filepath == current_real_path:
                                matched = True
                            elif Path(current_real_path).name == Path(db_item.filepath).name:
                                matched = True

                    elif db_item.item_type == "folder":
                        # Comprobar se o audio que soa esta dentro desta carpeta
                        if db_item.folder_path and current_real_path:
                            folder = db_item.folder_path.rstrip("/")
                            if current_real_path.startswith(folder + "/"):
                                matched = True

                    elif db_item.item_type == "playlist":
                        # Comprobar se o audio pertence a playlist referenciada
                        if db_item.referenced_playlist_id:
                            ref_items = (
                                session.query(PI)
                                .filter_by(playlist_id=db_item.referenced_playlist_id)
                                .all()
                            )
                            for ref_item in ref_items:
                                if ref_item.filepath:
                                    if ref_item.filepath == current_real_path:
                                        matched = True
                                        break
                                    elif Path(current_real_path).name == Path(ref_item.filepath).name:
                                        matched = True
                                        break

                    elif db_item.item_type == "time_announce":
                        # Comprobar se o titulo suxire unha hora
                        if current_title and ("hora" in current_title.lower()
                                              or "son las" in current_title.lower()
                                              or ":00" in current_title
                                              or "reloj" in current_title.lower()):
                            matched = True

                    if matched:
                        matching_positions.add(db_item.position)

            finally:
                session.close()

        # Actualizar filas: resaltar as que coinciden
        child = items_list.get_first_child()
        while child is not None:
            if hasattr(child, '_item'):
                item = child._item
                match = item.position in matching_positions

                if match:
                    child.add_css_class("ra-row-playing")
                    # Engadir indicador "►" se non o ten
                    if not item.label.startswith("► "):
                        child._original_label = item.label
                        idx = 0
                        w = child.get_first_child()
                        while w is not None:
                            idx += 1
                            if idx == 3:  # Label do nome
                                if hasattr(w, 'set_label'):
                                    w.set_label(f"► {item.label}")
                                break
                            w = w.get_next_sibling()
                else:
                    child.remove_css_class("ra-row-playing")
                    # Restaurar label orixinal
                    if hasattr(child, '_original_label'):
                        idx = 0
                        w = child.get_first_child()
                        while w is not None:
                            idx += 1
                            if idx == 3:
                                if hasattr(w, 'set_label'):
                                    w.set_label(child._original_label)
                                break
                            w = w.get_next_sibling()
                        del child._original_label

            child = child.get_next_sibling()

    def refresh(self):
        """Recargar la playlist Continuidad."""
        if hasattr(self, '_editor') and hasattr(self._editor, 'refresh'):
            self._editor.refresh()
