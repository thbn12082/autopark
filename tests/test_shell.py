"""Cửa sổ chung AutoPark (autopark.ui.shell): thanh chọn trang, dựng trang khi cần, trang lỗi, đóng cửa sổ."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel, QMainWindow  # noqa: E402

from autopark.ui import shell  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class Tool(QMainWindow):
    """Công cụ giả: đếm số lần dựng, cho phép hoặc từ chối đóng."""

    built = 0

    def __init__(self, allow_close=True):
        super().__init__()
        Tool.built += 1
        self.allow_close = allow_close
        self.closed = False
        self.setCentralWidget(QLabel("công cụ"))

    def closeEvent(self, event):
        if self.allow_close:
            self.closed = True
            event.accept()
        else:
            event.ignore()


def fake_pages(fail=None, refuse=None):
    def make(key):
        def factory(opts):
            if fail is not None and fail["on"] and key == "b":
                raise RuntimeError("thiếu thiết bị thử")
            return Tool(allow_close=key != refuse)
        return factory
    return (shell.Page("a", "NHÓM 1", "Trang A", "gợi ý A", make("a")),
            shell.Page("b", "NHÓM 2", "Trang B", "gợi ý B", make("b")))


def test_pages_are_built_lazily_and_embedded(qapp):
    Tool.built = 0
    window = shell.ShellWindow(pages=fake_pages())
    try:
        assert list(window.widgets) == ["a"] and Tool.built == 1          # chỉ trang đầu được dựng
        assert window.buttons["a"].isChecked() and window.hint.text() == "gợi ý A"
        page = window.show_page("b")
        assert isinstance(page, Tool) and Tool.built == 2 and window.stack.currentWidget() is page
        assert not page.isWindow()                                        # nhúng, không phải cửa sổ riêng
        assert window.show_page("b") is page and Tool.built == 2          # lần sau dùng lại
    finally:
        window.close()


def test_failed_page_shows_reason_and_retry_rebuilds(qapp):
    fail = {"on": True}
    window = shell.ShellWindow(pages=fake_pages(fail=fail))
    try:
        page = window.show_page("b")
        assert isinstance(page, shell.ErrorPage) and "thiếu thiết bị thử" in str(page.error)
        fail["on"] = False
        page.retry_button.click()
        assert isinstance(window.widgets["b"], Tool) and window.stack.currentWidget() is window.widgets["b"]
    finally:
        window.close()


def test_missing_package_points_to_train_env(qapp):
    def factory(opts):
        try:
            import khong_co_goi_nay  # noqa: F401
        except ModuleNotFoundError as exc:
            raise RuntimeError("cần gói thử") from exc

    window = shell.ShellWindow(pages=(shell.Page("x", "NHÓM", "Trang X", "", factory),))
    try:
        page = window.widgets["x"]
        assert isinstance(page, shell.ErrorPage)
        text = page.findChildren(QLabel)[1].text()
        assert "cần gói thử" in text and ".venv-train" in text
    finally:
        window.close()


def test_close_closes_every_tool_and_respects_refusal(qapp):
    window = shell.ShellWindow(pages=fake_pages(refuse="b"))
    window.show()
    a, b = window.widgets["a"], window.show_page("b")
    window.show_page("a")
    assert not window.close()                        # B từ chối: cửa sổ giữ nguyên, chuyển tới trang B
    assert window.current == "b" and a.closed
    b.allow_close = True
    assert window.close() and b.closed


def test_real_pages_registered_and_cli(qapp):
    keys = [p.key for p in shell.PAGES]
    assert keys[0] == "do_xe" and {"quan_sat_pi", "noi_tham", "ngoai_tham", "gan_nhan", "tren_cao"} <= set(keys)
    args = shell.parse_args(["--page", "quan_sat_pi", "--host", "10.0.0.2"])
    assert args.page == "quan_sat_pi" and args.host == "10.0.0.2"
    with pytest.raises(SystemExit):
        shell.parse_args(["--page", "khong_co"])


def test_parking_and_pi_pages_build_without_devices(qapp):
    """Hai trang chính dựng được mà không mở LiDAR, camera hay kết nối Pi."""
    window = shell.ShellWindow()
    try:
        parking = window.widgets["do_xe"]
        assert type(parking).__name__ == "BenchWindow" and parking.dock.source is None
        assert parking.session.scenario.name
        pi = window.show_page("quan_sat_pi")
        assert type(pi).__name__ == "RemoteSensorWindow" and pi.link is None
    finally:
        window.close()
