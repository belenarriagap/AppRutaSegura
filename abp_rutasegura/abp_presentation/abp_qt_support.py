from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImage, QPixmap

from abp_rutasegura.abp_application.abp_errors import abpOperationCancelled, abpUserFacingError

abp_UNEXPECTED_ERROR = "Ocurrió un error inesperado: {error}"


def abp_to_pixmap(abp_image: npt.NDArray[np.uint8]) -> QPixmap:
    abp_data = np.ascontiguousarray(abp_image)
    abp_h, abp_w = abp_data.shape[:2]
    if abp_data.ndim == 2:
        abp_fmt = QImage.Format.Format_Grayscale8
    elif abp_data.shape[2] == 4:
        abp_fmt = QImage.Format.Format_RGBA8888
    else:
        abp_fmt = QImage.Format.Format_RGB888
    abp_qimage = QImage(abp_data.data, abp_w, abp_h, abp_data.strides[0], abp_fmt)
    return QPixmap.fromImage(abp_qimage.copy())


class abp__TaskSignals(QObject):
    abp_done = Signal(object)
    abp_failed = Signal(str)


class abp__Task(QRunnable):
    def __init__(self, abp_fn: Callable[[], Any], abp_signals: abp__TaskSignals) -> None:
        super().__init__()
        self.abp__fn = abp_fn
        self.abp_signals = abp_signals

    def run(self) -> None:
        try:
            abp_result = self.abp__fn()
        except abpUserFacingError as abp_exc:
            self.abp_signals.abp_failed.emit(abp_exc.abp_message)
        except Exception as abp_exc:
            self.abp_signals.abp_failed.emit(abp_UNEXPECTED_ERROR.format(error=abp_exc))
        else:
            self.abp_signals.abp_done.emit(abp_result)


abp__running: set[abp__TaskSignals] = set()


def abp_run_in_background(
    abp_fn: Callable[[], Any],
    abp_on_done: Callable[[Any], None],
    abp_on_error: Callable[[str], None],
) -> None:
    abp_signals = abp__TaskSignals()
    abp__running.add(abp_signals)

    def abp_finished_ok(abp_result: object) -> None:
        abp__running.discard(abp_signals)
        abp_on_done(abp_result)

    def abp_finished_error(abp_message: str) -> None:
        abp__running.discard(abp_signals)
        abp_on_error(abp_message)

    abp_signals.abp_done.connect(abp_finished_ok)
    abp_signals.abp_failed.connect(abp_finished_error)
    QThreadPool.globalInstance().start(abp__Task(abp_fn, abp_signals))


class abpBackgroundJob(QObject):
    abp_progress = Signal(float)
    abp_done = Signal(object)
    abp_failed = Signal(str)
    abp_cancelled = Signal()

    def __init__(
        self,
        abp_fn: Callable[[Callable[[float], None], Callable[[], bool]], Any],
        abp_parent: QObject | None = None,
    ) -> None:
        super().__init__(abp_parent)
        self.abp__fn = abp_fn
        self.abp__cancel = threading.Event()
        self.abp_running = False

    def abp_start(self) -> None:
        self.abp__cancel.clear()
        self.abp_running = True
        QThreadPool.globalInstance().start(abp__JobRunnable(self))

    def abp_cancel(self) -> None:
        self.abp__cancel.set()

    def abp__execute(self) -> None:
        try:
            abp_result = self.abp__fn(self.abp_progress.emit, self.abp__cancel.is_set)
        except abpOperationCancelled:
            self.abp_running = False
            self.abp_cancelled.emit()
        except abpUserFacingError as abp_exc:
            self.abp_running = False
            self.abp_failed.emit(abp_exc.abp_message)
        except Exception as abp_exc:
            self.abp_running = False
            self.abp_failed.emit(abp_UNEXPECTED_ERROR.format(error=abp_exc))
        else:
            self.abp_running = False
            self.abp_done.emit(abp_result)


class abp__JobRunnable(QRunnable):
    def __init__(self, abp_job: abpBackgroundJob) -> None:
        super().__init__()
        self.abp__job = abp_job

    def run(self) -> None:
        self.abp__job.abp__execute()
