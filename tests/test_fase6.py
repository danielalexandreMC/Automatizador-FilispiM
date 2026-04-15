"""
Tests para Fase 6 - Interfaz y UX.
Sistema de logging, servicio de notificaciones, widgets de toast,
dialogo about, atajos de teclado, barra de estado, visor de logs.
"""

import logging
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# Asegurar que el paquete esta en el path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mockear gi/GLib para tests sin GTK
gi_mock = MagicMock()
sys.modules['gi'] = gi_mock
sys.modules['gi.repository'] = MagicMock()
sys.modules['gi.repository.Gtk'] = MagicMock()
sys.modules['gi.repository.GLib'] = MagicMock()
sys.modules['gi.repository.Gio'] = MagicMock()
sys.modules['gi.repository.Pango'] = MagicMock()

from radio_automator.core.database import init_db, reset_engine, DATA_DIR
from radio_automator.core.event_bus import EventBus, Event, Priority, get_event_bus, reset_event_bus
from radio_automator.core.logger import (
    LogManager, LogEntry, EventBusLogHandler,
    get_log_manager, reset_log_manager, get_logger, APP_VERSION
)
from radio_automator.services.notification_service import (
    Notification, NotificationService, NotificationType, NOTIFICATION_COLORS,
    get_notification_service, reset_notification_service
)


class TestLogManager(unittest.TestCase):
    """Tests del sistema de logging."""

    def setUp(self):
        reset_log_manager()
        reset_event_bus()
        # Usar directorio temporal para logs
        self._tmp_dir = tempfile.mkdtemp()
        self._original_log_dir = None

    def tearDown(self):
        reset_log_manager()
        reset_event_bus()
        # Limpiar directorio temporal
        import shutil
        if self._tmp_dir and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_singleton(self):
        """El LogManager es un singleton."""
        lm1 = get_log_manager()
        lm2 = get_log_manager()
        self.assertIs(lm1, lm2)

    def test_reset(self):
        """reset_log_manager() devuelve una nueva instancia."""
        lm1 = get_log_manager()
        reset_log_manager()
        lm2 = get_log_manager()
        self.assertIsNot(lm1, lm2)

    def test_initialize_creates_log_file(self):
        """La inicializacion crea el directorio y archivo de log."""
        lm = get_log_manager()

        # Parchear LOG_DIR para usar directorio temporal
        import radio_automator.core.logger as logger_mod
        original_log_dir = logger_mod.LOG_DIR
        logger_mod.LOG_DIR = Path(self._tmp_dir) / "logs"
        logger_mod.LOG_FILE = logger_mod.LOG_DIR / "radio-automator.log"

        try:
            lm.initialize()
            self.assertTrue(lm.is_initialized)
            self.assertTrue(logger_mod.LOG_DIR.exists())
        finally:
            logger_mod.LOG_DIR = original_log_dir
            logger_mod.LOG_FILE = original_log_dir / "radio-automator.log"

    def test_initialize_with_event_bus(self):
        """La inicializacion con EventBus crea el handler correcto."""
        bus = get_event_bus()
        lm = get_log_manager()

        import radio_automator.core.logger as logger_mod
        original_log_dir = logger_mod.LOG_DIR
        logger_mod.LOG_DIR = Path(self._tmp_dir) / "logs"
        logger_mod.LOG_FILE = logger_mod.LOG_DIR / "radio-automator.log"

        try:
            lm.initialize(event_bus_publish=bus.publish)
            # El EventBusLogHandler debe estar suscrito a WARNING+
            logger_instance = get_logger("test")
            logger_instance.warning("Test warning")
            # Verificar que se publico el evento
            events = bus.get_recent_events(5)
            log_events = [e for e in events if e.type == "log.message"]
            self.assertTrue(len(log_events) > 0)
        finally:
            logger_mod.LOG_DIR = original_log_dir
            logger_mod.LOG_FILE = original_log_dir / "radio-automator.log"

    def test_get_logger(self):
        """get_logger devuelve un logger con nombre correcto."""
        lm = get_log_manager()
        import radio_automator.core.logger as logger_mod
        original_log_dir = logger_mod.LOG_DIR
        logger_mod.LOG_DIR = Path(self._tmp_dir) / "logs"
        logger_mod.LOG_FILE = logger_mod.LOG_DIR / "radio-automator.log"

        try:
            lm.initialize()
            logger = get_logger("audio_engine")
            self.assertEqual(logger.name, "radio_automator.audio_engine")
        finally:
            logger_mod.LOG_DIR = original_log_dir
            logger_mod.LOG_FILE = original_log_dir / "radio-automator.log"

    def test_get_logger_full_name(self):
        """get_logger con nombre completo funciona correctamente."""
        lm = get_log_manager()
        import radio_automator.core.logger as logger_mod
        original_log_dir = logger_mod.LOG_DIR
        logger_mod.LOG_DIR = Path(self._tmp_dir) / "logs"
        logger_mod.LOG_FILE = logger_mod.LOG_DIR / "radio-automator.log"

        try:
            lm.initialize()
            logger = get_logger("radio_automator.custom")
            self.assertEqual(logger.name, "radio_automator.custom")
        finally:
            logger_mod.LOG_DIR = original_log_dir
            logger_mod.LOG_FILE = original_log_dir / "radio-automator.log"

    def test_shutdown(self):
        """shutdown cierra el logging correctamente."""
        lm = get_log_manager()
        import radio_automator.core.logger as logger_mod
        original_log_dir = logger_mod.LOG_DIR
        logger_mod.LOG_DIR = Path(self._tmp_dir) / "logs"
        logger_mod.LOG_FILE = logger_mod.LOG_DIR / "radio-automator.log"

        try:
            lm.initialize()
            self.assertTrue(lm.is_initialized)
            lm.shutdown()
            self.assertFalse(lm.is_initialized)
        finally:
            logger_mod.LOG_DIR = original_log_dir
            logger_mod.LOG_FILE = original_log_dir / "radio-automator.log"

    def test_set_level(self):
        """set_level cambia el nivel de consola."""
        lm = get_log_manager()
        import radio_automator.core.logger as logger_mod
        original_log_dir = logger_mod.LOG_DIR
        logger_mod.LOG_DIR = Path(self._tmp_dir) / "logs"
        logger_mod.LOG_FILE = logger_mod.LOG_DIR / "radio-automator.log"

        try:
            lm.initialize(console_level=logging.INFO)
            lm.set_level(logging.WARNING)
            # No lanza excepcion
            lm.set_level(logging.DEBUG)
        finally:
            logger_mod.LOG_DIR = original_log_dir
            logger_mod.LOG_FILE = original_log_dir / "radio-automator.log"

    def test_log_file_path(self):
        """log_file_path devuelve la ruta correcta."""
        lm = get_log_manager()
        self.assertIsInstance(lm.log_file_path, Path)


class TestLogEntry(unittest.TestCase):
    """Tests de la clase LogEntry."""

    def test_creation(self):
        """LogEntry se crea con los campos correctos."""
        entry = LogEntry(
            timestamp="2025-01-15 10:30:45",
            level="INFO",
            logger_name="audio_engine",
            message="Pista iniciada"
        )
        self.assertEqual(entry.timestamp, "2025-01-15 10:30:45")
        self.assertEqual(entry.level, "INFO")
        self.assertEqual(entry.logger_name, "audio_engine")
        self.assertEqual(entry.message, "Pista iniciada")

    def test_to_dict(self):
        """to_dict devuelve un diccionario con los campos correctos."""
        entry = LogEntry("2025-01-15 10:30:45", "ERROR", "test", "Error msg")
        d = entry.to_dict()
        self.assertEqual(d["timestamp"], "2025-01-15 10:30:45")
        self.assertEqual(d["level"], "ERROR")
        self.assertEqual(d["logger"], "test")
        self.assertEqual(d["message"], "Error msg")

    def test_repr(self):
        """repr muestra informacion util."""
        entry = LogEntry("2025-01-15 10:30:45", "INFO", "test", "Mensaje de prueba largo")
        r = repr(entry)
        self.assertIn("INFO", r)
        self.assertIn("Mensaje de prueba", r)


class TestEventBusLogHandler(unittest.TestCase):
    """Tests del handler de log para EventBus."""

    def test_only_warning_and_above(self):
        """El handler solo publica WARNING, ERROR y CRITICAL."""
        publish_mock = MagicMock()
        handler = EventBusLogHandler(publish_mock)
        self.assertEqual(handler.level, logging.WARNING)

    def test_publishes_event(self):
        """El handler publica un evento en el bus."""
        publish_mock = MagicMock()
        handler = EventBusLogHandler(publish_mock)

        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="test.py",
            lineno=1, msg="Error de prueba", args=(), exc_info=None
        )
        handler.emit(record)

        publish_mock.assert_called_once()
        call_args = publish_mock.call_args
        self.assertEqual(call_args[0][0], "log.message")
        self.assertEqual(call_args[0][1]["level"], "ERROR")

    def test_handle_error_does_not_crash(self):
        """handleError no lanza excepcion."""
        publish_mock = MagicMock(side_effect=Exception("Test error"))
        handler = EventBusLogHandler(publish_mock)

        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="test.py",
            lineno=1, msg="Error", args=(), exc_info=None
        )
        # No debe lanzar excepcion
        try:
            handler.emit(record)
        except Exception:
            self.fail("EventBusLogHandler.emit no deberia propagar excepciones")


class TestNotification(unittest.TestCase):
    """Tests de la clase Notification."""

    def test_creation(self):
        """Notification se crea con campos correctos."""
        n = Notification(
            message="Test message",
            title="Test Title",
            type=NotificationType.INFO,
            timeout_ms=3000,
        )
        self.assertEqual(n.message, "Test message")
        self.assertEqual(n.title, "Test Title")
        self.assertEqual(n.type, NotificationType.INFO)
        self.assertEqual(n.timeout_ms, 3000)
        self.assertFalse(n.persistent)
        self.assertTrue(len(n.id) > 0)
        self.assertTrue(n.created_at > 0)

    def test_auto_id(self):
        """Se genera un ID automatico si no se proporciona."""
        n1 = Notification(message="msg1")
        n2 = Notification(message="msg2")
        self.assertNotEqual(n1.id, n2.id)

    def test_auto_timestamp(self):
        """Se asigna timestamp automatico."""
        before = time.time()
        n = Notification(message="msg")
        after = time.time()
        self.assertTrue(before <= n.created_at <= after)

    def test_persistent_flag(self):
        """Notificaciones persistentes no se auto-descartan."""
        n = Notification(message="persistent", persistent=True)
        self.assertTrue(n.persistent)


class TestNotificationService(unittest.TestCase):
    """Tests del servicio de notificaciones."""

    def setUp(self):
        reset_notification_service()
        reset_event_bus()

    def tearDown(self):
        reset_notification_service()
        reset_event_bus()

    def test_singleton(self):
        """El NotificationService es un singleton."""
        ns1 = get_notification_service()
        ns2 = get_notification_service()
        self.assertIs(ns1, ns2)

    def test_reset(self):
        """reset_notification_service() devuelve una nueva instancia."""
        ns1 = get_notification_service()
        reset_notification_service()
        ns2 = get_notification_service()
        self.assertIsNot(ns1, ns2)

    def test_notify_returns_notification(self):
        """notify() devuelve un objeto Notification."""
        ns = get_notification_service()
        n = ns.notify("Test message", title="Test")
        self.assertIsInstance(n, Notification)
        self.assertEqual(n.message, "Test message")
        self.assertEqual(n.title, "Test")

    def test_notify_history(self):
        """Las notificaciones se guardan en el historial."""
        ns = get_notification_service()
        ns.info("Info 1")
        ns.info("Info 2")
        ns.warning("Warning 1")

        history = ns.history
        self.assertEqual(len(history), 3)

    def test_notify_history_max(self):
        """El historial tiene un maximo de entradas."""
        ns = get_notification_service()
        for i in range(150):
            ns.info(f"Message {i}")

        history = ns.history
        self.assertTrue(len(history) <= 100)

    def test_convenience_methods(self):
        """Los metodos de conveniencia crean notificaciones del tipo correcto."""
        ns = get_notification_service()

        n_info = ns.info("Info")
        self.assertEqual(n_info.type, NotificationType.INFO)

        n_success = ns.success("Success")
        self.assertEqual(n_success.type, NotificationType.SUCCESS)

        n_warning = ns.warning("Warning")
        self.assertEqual(n_warning.type, NotificationType.WARNING)

        n_error = ns.error("Error")
        self.assertEqual(n_error.type, NotificationType.ERROR)
        self.assertTrue(n_error.persistent)

    def test_default_title(self):
        """Si no se especifica titulo, se usa 'Radio Automator'."""
        ns = get_notification_service()
        n = ns.info("Mensaje")
        self.assertEqual(n.title, "Radio Automator")

    def test_desktop_enabled(self):
        """Se puede activar/desactivar notificaciones desktop."""
        ns = get_notification_service()
        self.assertTrue(ns.desktop_enabled)
        ns.set_desktop_enabled(False)
        self.assertFalse(ns.desktop_enabled)
        ns.set_desktop_enabled(True)
        self.assertTrue(ns.desktop_enabled)

    def test_toast_enabled(self):
        """Se puede activar/desactivar notificaciones toast."""
        ns = get_notification_service()
        self.assertTrue(ns.toast_enabled)
        ns.set_toast_enabled(False)
        self.assertFalse(ns.toast_enabled)

    def test_toast_callback(self):
        """Se establece callback de toast correctamente."""
        ns = get_notification_service()
        callback = MagicMock()
        ns.set_on_toast_callback(callback)
        # La callback se asigna (no se ejecuta directamente en tests sin GLib)
        self.assertEqual(ns._on_toast_callback, callback)

    def test_mute_unmute_event(self):
        """mute_event y unmute_event funcionan correctamente."""
        ns = get_notification_service()
        ns.mute_event("audio.error")
        self.assertIn("audio.error", ns._muted_event_types)
        ns.unmute_event("audio.error")
        self.assertNotIn("audio.error", ns._muted_event_types)

    def test_clear_history(self):
        """clear_history vacia el historial."""
        ns = get_notification_service()
        ns.info("Msg 1")
        ns.info("Msg 2")
        self.assertEqual(len(ns.history), 2)
        ns.clear_history()
        self.assertEqual(len(ns.history), 0)

    def test_dismiss_sends_event(self):
        """dismiss publica un evento de dismiss en el EventBus."""
        bus = get_event_bus()
        ns = get_notification_service()
        ns.dismiss("test-id")
        events = bus.get_recent_events(5)
        dismiss_events = [e for e in events if e.type == "notification.dismiss"]
        self.assertTrue(len(dismiss_events) > 0)
        self.assertEqual(dismiss_events[0].data["id"], "test-id")

    def test_dismiss_all(self):
        """dismiss_all publica evento dismiss_all."""
        bus = get_event_bus()
        ns = get_notification_service()
        ns.dismiss_all()
        events = bus.get_recent_events(5)
        dismiss_all_events = [e for e in events if e.type == "notification.dismiss_all"]
        self.assertTrue(len(dismiss_all_events) > 0)

    def test_subscribe_to_events(self):
        """subscribe_to_events suscribe handlers al EventBus."""
        bus = get_event_bus()
        ns = get_notification_service()
        ns.subscribe_to_events()
        # Deberia tener suscripciones registradas
        self.assertTrue(len(ns._event_bus_subscriptions) > 0)
        ns.unsubscribe_from_events()
        self.assertEqual(len(ns._event_bus_subscriptions), 0)


class TestNotificationColors(unittest.TestCase):
    """Tests de los colores de notificacion."""

    def test_all_types_have_colors(self):
        """Todos los tipos de notificacion tienen colores definidos."""
        for ntype in NotificationType:
            self.assertIn(ntype, NOTIFICATION_COLORS)
            colors = NOTIFICATION_COLORS[ntype]
            self.assertIn("border", colors)
            self.assertIn("icon", colors)
            self.assertIn("label", colors)


class TestAppConstants(unittest.TestCase):
    """Tests de constantes de la aplicacion."""

    def test_app_version(self):
        """APP_VERSION es un string valido."""
        self.assertIsInstance(APP_VERSION, str)
        self.assertTrue(len(APP_VERSION) > 0)
        # Verificar formato semver basico
        parts = APP_VERSION.split(".")
        self.assertTrue(len(parts) >= 2)

    def test_app_name(self):
        """APP_NAME es un string valido."""
        from radio_automator.core.logger import APP_NAME
        self.assertIsInstance(APP_NAME, str)
        self.assertEqual(APP_NAME, "Radio Automator")


if __name__ == '__main__':
    unittest.main()
