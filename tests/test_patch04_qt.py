"""Queued Qt receiver-signal regression: runs in GitHub CI with PySide6.

This deterministic test cannot substitute for real unplug/replug or GUI tests.
"""
import importlib.util
import os
import unittest

HAS_QT = importlib.util.find_spec('PySide6') is not None
if HAS_QT:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import QCoreApplication, QObject, Signal, Qt
    from hline.app import MainWindow


@unittest.skipUnless(HAS_QT, 'PySide6 unavailable in local test environment')
class ReceiverLifecycleQtTests(unittest.TestCase):
    if HAS_QT:
        class Worker(QObject):
            spectrum = Signal(int)
            status = Signal(str)

    def test_old_generation_queued_events_cannot_touch_new_receiver(self):
        app = QCoreApplication.instance() or QCoreApplication([])

        class State:
            _rx_generation = 4
            rx = object()
            accepted = []
            def on_spectrum(self, payload):
                self.accepted.append(('spectrum', payload))
            def on_status(self, message):
                self.accepted.append(('status', message))

        state = State()
        prior = self.Worker()
        prior.spectrum.connect(
            lambda value: MainWindow._receiver_event(state, 4, state.on_spectrum, value),
            Qt.ConnectionType.QueuedConnection)
        prior.status.connect(
            lambda msg: MainWindow._receiver_event(state, 4, state.on_status, msg),
            Qt.ConnectionType.QueuedConnection)
        prior.spectrum.emit(9)
        prior.status.emit('old error')
        # Stop/restart before processing any queued events.
        state._rx_generation = 6
        state.rx = object()
        QCoreApplication.processEvents()
        self.assertEqual(state.accepted, [])

        current = self.Worker()
        current.spectrum.connect(
            lambda value: MainWindow._receiver_event(state, 6, state.on_spectrum, value),
            Qt.ConnectionType.QueuedConnection)
        current.spectrum.emit(10)
        QCoreApplication.processEvents()
        self.assertEqual(state.accepted, [('spectrum', 10)])

        state.rx = None
        current.spectrum.emit(11)
        QCoreApplication.processEvents()
        self.assertEqual(state.accepted, [('spectrum', 10)])


if __name__ == '__main__':
    unittest.main()
