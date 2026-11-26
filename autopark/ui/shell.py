"""AutoPark: một cửa sổ chung cho mọi công cụ (thêm 26/11/2026).

    python run_app.py [--page do_xe|quan_sat_pi|lai_tay|noi_tham|ngoai_tham|bo_camera|gan_nhan|tren_cao]
                      [--scenario KỊCH_BẢN.json] [--host IP_PI]

Thanh bên trái chọn trang. Mỗi trang là một công cụ có sẵn (cửa sổ cũ nhúng vào), dựng lần đầu khi bấm tới nó:

```
AutoPark
├── Đỗ xe
│   └── Đỗ xe ............ mô phỏng, tìm ô đỗ, tính đường; ngăn LiDAR thật và ghi cảm biến (ui.lidar_app)
├── Xe thật
│   ├── Quan sát Pi ...... 4 camera + LiDAR từ Pi qua Wi-Fi, ghi LiDAR (ui.remote_sensor_view)
│   └── Lái tay .......... vô lăng, Space tiến, W lùi; qua Pi, USB hoặc mô phỏng (ui.manual_drive)
├── Hiệu chuẩn
│   ├── Nội tham camera .. bàn cờ, camera cắm laptop (ui.calib_app)
│   ├── Ngoại tham, ROI .. (ui.roi_app)
│   └── Bộ camera ........ 4 camera + AI trên laptop (ui.rig_app)
└── Dữ liệu
    ├── Gán nhãn ......... ảnh sa bàn cho AI (ui.label_app)
    └── Camera trên cao .. tham chiếu đánh giá (ui.overhead_app)
```

Không trang nào tự mở camera hay LiDAR khi dựng: thiết bị chỉ mở khi bấm nút trong trang. Trang dựng lỗi (thiếu dữ liệu,
thiếu thiết bị) hiện lý do và nút "Thử lại" thay vì làm sập cả ứng dụng. Các lệnh `python -m autopark.ui.<công cụ>` cũ
vẫn chạy được khi cần tham số riêng.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import sys
import traceback
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from autopark.power_throttling import apply_ecoqos_policy
from autopark.ui import theme

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIO = PROJECT_ROOT / "scenarios" / "thao_tac_cua_hep.json"


@dataclass(frozen=True)
class Page:
    key: str
    group: str
    title: str
    hint: str
    factory: Callable[["ShellOptions"], QWidget]


@dataclass(frozen=True)
class ShellOptions:
    scenario: Path | None = DEFAULT_SCENARIO
    host: str = ""


# ------------------------------------------------------------------------------------------------- dựng từng trang
def _parking(opts: ShellOptions) -> QWidget:
    from autopark.ui.lidar_app import build_window
    window, _dock = build_window(opts.scenario, port=None, recording=None)
    return window


def _pi_viewer(opts: ShellOptions) -> QWidget:
    from autopark.ui.remote_sensor_view import RemoteSensorWindow
    return RemoteSensorWindow(opts.host, camera_count=4)


def _manual_drive(opts: ShellOptions) -> QWidget:
    from PySide6.QtCore import QSettings

    from autopark.ui.manual_drive import ManualDriveWindow
    return ManualDriveWindow(opts.host, settings=QSettings("AutoPark", "AutoPark"))


def _intrinsics(opts: ShellOptions) -> QWidget:
    from autopark.ui.calib_app import build_window
    return build_window([], start=False)


def _extrinsics_roi(opts: ShellOptions) -> QWidget:
    from autopark.perception import extrinsics_calib as ec
    from autopark.perception import roi_tool as rt
    from autopark.perception.calib_board import BoardSpec
    from autopark.ui.calib_app import parse_size, usb_camera_factory
    from autopark.ui.roi_app import ExtrinsicsRoiWindow
    return ExtrinsicsRoiWindow(usb_camera_factory, port=1, spec=BoardSpec(9, 6, 30.0), intrinsics_path=None,
                               rig_out=ec.DEFAULT_OUT, rig_base=ec.DEFAULT_BASE, roi_dir=rt.DEFAULT_ROI_DIR,
                               live_size=parse_size("640x480"))


def _camera_rig(opts: ShellOptions) -> QWidget:
    from autopark.ui.rig_app import build_window
    return build_window([], start=False)


def _labeling(opts: ShellOptions) -> QWidget:
    from autopark.perception.labels import DEFAULT_PROJECT, LabelProject
    from autopark.ui.label_app import LabelWindow
    project = LabelProject(DEFAULT_PROJECT)
    if not project.ids():
        raise RuntimeError(f"Dự án gán nhãn {project.root} chưa có ảnh. Nhập ảnh trước:\n"
                           f"python -m autopark.perception.labels import runs/rig_snapshots")
    return LabelWindow(project)


def _overhead(opts: ShellOptions) -> QWidget:
    from autopark.ui.overhead_app import build_window
    return build_window([])


PAGES: tuple[Page, ...] = (
    Page("do_xe", "ĐỖ XE", "Đỗ xe", "Mô phỏng, tìm ô đỗ, tính đường, LiDAR thật", _parking),
    Page("quan_sat_pi", "XE THẬT", "Quan sát Pi", "4 camera + LiDAR qua Wi-Fi, ghi LiDAR", _pi_viewer),
    Page("lai_tay", "XE THẬT", "Lái tay", "Vô lăng, Space tiến, W lùi, Esc dừng", _manual_drive),
    Page("noi_tham", "HIỆU CHUẨN", "Nội tham camera", "Bàn cờ, camera cắm laptop", _intrinsics),
    Page("ngoai_tham", "HIỆU CHUẨN", "Ngoại tham, ROI", "Tư thế camera, vùng quan tâm", _extrinsics_roi),
    Page("bo_camera", "HIỆU CHUẨN", "Bộ camera", "4 camera + AI trên laptop", _camera_rig),
    Page("gan_nhan", "DỮ LIỆU", "Gán nhãn", "Ảnh sa bàn cho AI", _labeling),
    Page("tren_cao", "DỮ LIỆU", "Camera trên cao", "Tham chiếu đánh giá", _overhead),
)

NAV_STYLE = f"""
QFrame#shellNav {{ background: #0f1922; border: none; border-right: 1px solid {theme.BORDER_SOFT}; }}
QFrame#shellNav QLabel {{ color: {theme.TEXT}; background: transparent; }}
QLabel#shellBrand {{ font-size: 17px; font-weight: 600; letter-spacing: 4px; }}
QLabel#shellGroup {{ color: {theme.TEXT_FAINT}; font-size: 10px; font-weight: 600; letter-spacing: 1.5px;
    padding: 14px 0 4px 6px; }}
QPushButton#shellItem {{ background: transparent; color: {theme.TEXT_DIM}; border: none; border-radius: 9px;
    text-align: left; padding: 9px 10px; font-size: 13px; }}
QPushButton#shellItem:hover {{ background: #1b2a36; color: {theme.TEXT}; }}
QPushButton#shellItem:checked {{ background: #1f3a35; color: {theme.ACCENT}; font-weight: 600; }}
QLabel#shellHint {{ color: {theme.TEXT_FAINT}; font-size: 11px; }}
"""

ERROR_STYLE = f"""
QWidget#shellError {{ background: {theme.BG}; }}
QWidget#shellError QLabel {{ color: {theme.TEXT}; background: transparent; }}
QLabel#shellErrorTitle {{ font-size: 20px; font-weight: 500; }}
QLabel#shellErrorText {{ color: {theme.TEXT_DIM}; font-size: 13px; }}
QWidget#shellError QPushButton {{ color: {theme.TEXT}; background: #1b2a36; border: 1px solid {theme.BORDER};
    border-radius: 9px; padding: 9px 16px; }}
"""


class ErrorPage(QWidget):
    """Trang thay thế khi dựng công cụ lỗi: lý do và nút thử lại."""

    def __init__(self, page: Page, error: BaseException, retry: Callable[[], None]):
        super().__init__()
        self.setObjectName("shellError")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(ERROR_STYLE)
        self.error = error
        layout = QVBoxLayout(self)
        layout.setContentsMargins(60, 60, 60, 60)
        title = QLabel(f"Chưa mở được “{page.title}”")
        title.setObjectName("shellErrorTitle")
        message = str(error) or type(error).__name__
        cause = error
        while cause is not None and not isinstance(cause, ModuleNotFoundError):
            cause = cause.__cause__
        if cause is not None:
            message += ("\n\nThiếu gói Python. Trang này cần môi trường .venv-train: chạy cai_dat_train.cmd một lần, "
                        "rồi mở bằng .venv-train\\Scripts\\python.exe run_app.py.")
        text = QLabel(message)
        text.setObjectName("shellErrorText")
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.retry_button = QPushButton("Thử lại")
        self.retry_button.clicked.connect(retry)
        layout.addWidget(title)
        layout.addSpacing(10)
        layout.addWidget(text)
        layout.addSpacing(16)
        layout.addWidget(self.retry_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)


class ShellWindow(QMainWindow):
    """Cửa sổ AutoPark: thanh chọn trang bên trái, trang công cụ bên phải."""

    def __init__(self, options: ShellOptions | None = None, *, pages: tuple[Page, ...] = PAGES,
                 start_page: str | None = None):
        super().__init__()
        self.options = options or ShellOptions()
        self.pages = {p.key: p for p in pages}
        self.widgets: dict[str, QWidget] = {}
        self.current: str | None = None
        self.setWindowTitle("AutoPark")
        self.setStyleSheet(f"QMainWindow {{ background: {theme.BG}; }}")

        central = QWidget()
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        nav = QFrame()
        nav.setObjectName("shellNav")
        nav.setFixedWidth(240)
        nav.setStyleSheet(NAV_STYLE)
        col = QVBoxLayout(nav)
        col.setContentsMargins(14, 22, 14, 16)
        col.setSpacing(2)
        brand = QLabel("AUTOPARK")
        brand.setObjectName("shellBrand")
        col.addWidget(brand)
        self.buttons: dict[str, QPushButton] = {}
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        last_group = None
        for page in pages:
            if page.group != last_group:
                label = QLabel(page.group)
                label.setObjectName("shellGroup")
                col.addWidget(label)
                last_group = page.group
            button = QPushButton(page.title)
            button.setObjectName("shellItem")
            button.setCheckable(True)
            button.setToolTip(page.hint)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, key=page.key: self.show_page(key))
            self.group.addButton(button)
            self.buttons[page.key] = button
            col.addWidget(button)
        col.addStretch(1)
        self.hint = QLabel("")
        self.hint.setObjectName("shellHint")
        self.hint.setWordWrap(True)
        col.addWidget(self.hint)
        self.stack = QStackedWidget()
        row.addWidget(nav)
        row.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.resize(1700, 980)
        self.show_page(start_page or pages[0].key)

    # ------------------------------------------------------------------ trang
    def page_widget(self, key: str) -> QWidget:
        """Trang đã dựng (dựng nếu chưa có). Lỗi khi dựng thành ErrorPage, không ném ra ngoài."""
        widget = self.widgets.get(key)
        if widget is not None:
            return widget
        page = self.pages[key]
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            widget = page.factory(self.options)
            if isinstance(widget, QMainWindow):
                widget.setWindowFlags(Qt.WindowType.Widget)     # nhúng cửa sổ cũ, giữ menu, ngăn, thanh trạng thái
        except SystemExit as exc:                               # argparse của công cụ cũ báo lỗi bằng SystemExit
            widget = ErrorPage(page, RuntimeError(f"Tham số không hợp lệ (mã {exc.code})."), lambda: self.retry(key))
        except Exception as exc:
            traceback.print_exc()
            widget = ErrorPage(page, exc, lambda: self.retry(key))
        finally:
            QApplication.restoreOverrideCursor()
        self.widgets[key] = widget
        self.stack.addWidget(widget)
        return widget

    def show_page(self, key: str) -> QWidget:
        widget = self.page_widget(key)
        self.stack.setCurrentWidget(widget)
        self.buttons[key].setChecked(True)
        self.current = key
        self.hint.setText(self.pages[key].hint)
        return widget

    def retry(self, key: str) -> QWidget:
        old = self.widgets.pop(key, None)
        if old is not None:
            self.stack.removeWidget(old)
            old.deleteLater()
        return self.show_page(key)

    # ------------------------------------------------------------------ đóng
    def closeEvent(self, event) -> None:
        """Đóng từng công cụ đã mở (dừng camera, LiDAR, ghi tệp). Công cụ nào từ chối đóng thì giữ cửa sổ."""
        for key, widget in list(self.widgets.items()):
            if isinstance(widget, ErrorPage):
                continue
            if not widget.close():
                self.show_page(key)
                event.ignore()
                return
        super().closeEvent(event)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="run_app.py", description=__doc__.split("\n")[0])
    p.add_argument("--page", choices=[page.key for page in PAGES], default=PAGES[0].key, help="trang mở khi khởi động")
    p.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO, help="kịch bản cho trang Đỗ xe")
    p.add_argument("--host", default="", help="địa chỉ IP của Pi cho trang Quan sát Pi")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ecoqos = apply_ecoqos_policy("ui.shell")     # trước mọi việc khác (power_throttling.py)
    from autopark.ui.process_status import add_ecoqos_label

    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    app = QApplication.instance() or QApplication(sys.argv)
    window = ShellWindow(ShellOptions(args.scenario, args.host), start_page=args.page)
    window.show()
    add_ecoqos_label(window, ecoqos)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
