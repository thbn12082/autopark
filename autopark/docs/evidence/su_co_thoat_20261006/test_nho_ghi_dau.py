"""Thử plugin ghi_dau_tat trên một test nhỏ (không phải test của repo). Việc 8, 06/10/2026."""
import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_qt_va_luong():
    from PySide6.QtWidgets import QApplication, QLabel

    app = QApplication.instance() or QApplication([])
    lbl = QLabel("thu")
    lbl.show()
    app.processEvents()
    # một luồng daemon còn sống tới lúc tắt, để thấy plugin đếm được
    threading.Thread(target=time.sleep, args=(3,), daemon=True, name="ngu_3s").start()
    assert lbl.text() == "thu"
