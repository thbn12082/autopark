"""Cockpit typography, dark materials and mint/amber navigation accents."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QTextDocument
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

BG = "#0c131b"
SURFACE = "#15212c"
SURFACE_2 = "#1c2a36"
BORDER = "#334451"
BORDER_SOFT = "#273844"
TEXT = "#edf4fa"
TEXT_DIM = "#9cafbe"
TEXT_FAINT = "#6e8597"
ACCENT = "#8cf0d6"
OK = "#8cf0d6"
WARN = "#efb76b"
DANGER = "#ff8e8a"
SANS = '"Segoe UI", sans-serif'
MONO = '"Consolas", monospace'

STYLE = f"""
QWidget {{ color: {TEXT}; font-family: {SANS}; font-size: 13px; background: transparent; }}
QMainWindow {{ background: {BG}; }}
QLabel {{ background: transparent; border: none; }}
QLabel#wordmark {{ font-size: 17px; font-weight: 600; letter-spacing: 4px; }}
QLabel#eyebrow {{ color: {ACCENT}; font-size: 10px; font-weight: 600; letter-spacing: 2px; }}
QLabel#heroTitle {{ color: #f0f5fa; font-size: 46px; font-weight: 300; letter-spacing: -1.5px; }}
QLabel#hint, QLabel#planLine {{ color: {TEXT_DIM}; font-size: 12px; }}
QLabel#heroHint {{ color: {TEXT_DIM}; font-size: 14px; }}
QLabel#sectionTitle {{ color: {TEXT_FAINT}; font-size: 10px; font-weight: 600; letter-spacing: 1.5px; }}
QLabel#stepLine {{ color: {TEXT}; font-size: 14px; font-weight: 600; }}
QLabel#note {{ color: {TEXT_FAINT}; font-size: 11px; }}
QLabel#pageTitle {{ font-size: 21px; font-weight: 500; }}
QLabel#resultText {{ color: {OK}; font-size: 14px; }}
QFrame#actionDock {{ background: #182631; border: 1px solid #384b59; border-radius: 20px; }}
QFrame#modeMenu {{ background: #1b2a36; border: 1px solid #435866; border-radius: 16px; }}
QFrame#settingsDrawer {{ background: #121f2a; border: 1px solid #364958; border-radius: 18px; }}
QFrame#card {{ background: transparent; border: none; }}
QFrame#sep {{ background: {BORDER}; border: none; min-height: 1px; max-height: 1px; }}
QPushButton {{ background: transparent; color: {TEXT_DIM}; border: 1px solid {BORDER};
    border-radius: 10px; padding: 11px 16px; font-size: 12px; }}
QPushButton:hover {{ background: #263947; color: {TEXT}; border-color: #698092; }}
QPushButton:pressed {{ background: #304757; }}
QPushButton:disabled {{ color: #4d6373; border-color: #233441; }}
QPushButton#hudButton {{ border-color: transparent; border-radius: 8px; padding: 9px 14px; }}
QPushButton#hudButton:hover, QPushButton#hudButton:checked {{ background: #213340; color: {TEXT}; }}
QPushButton#primary {{ background: {ACCENT}; color: #10362d; border-color: {ACCENT};
    font-size: 14px; font-weight: 600; padding: 16px 24px; border-radius: 12px; }}
QPushButton#primary:hover {{ background: #b6ffe9; border-color: #b6ffe9; }}
QPushButton#primary:disabled {{ background: #293e49; color: #6f8795; border-color: #293e49; }}
QPushButton#danger {{ background: #462d34; border-color: #8e5159; color: #ffd4d1;
    font-size: 14px; font-weight: 600; padding: 16px 24px; border-radius: 12px; }}
QPushButton#danger:hover {{ background: #62333c; }}
QPushButton#modeOption {{ border: none; text-align: left; padding: 13px 14px; border-radius: 9px; }}
QPushButton#modeOption:checked {{ color: {ACCENT}; background: #29463f; }}
QPushButton#modeSelector {{ border: none; text-align: left; padding: 12px 8px; color: {TEXT}; }}
QPushButton#modeSelector:disabled {{ color: {TEXT_FAINT}; }}
QToolButton {{ background: #15232e; border: 1px solid #334957; border-radius: 10px; padding: 10px; }}
QToolButton:hover, QToolButton:checked {{ background: #27453f; border-color: #638e82; }}
QPushButton:focus, QToolButton:focus {{ border-color: {ACCENT}; }}
QProgressBar {{ background: #2c414e; border: none; border-radius: 2px; min-height: 3px; max-height: 3px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 2px; }}
QDoubleSpinBox, QComboBox, QListWidget {{ background: #0e1a24; color: {TEXT};
    border: 1px solid #314452; border-radius: 7px; padding: 7px 9px; font-size: 12px; }}
QDoubleSpinBox {{ font-family: {MONO}; }}
QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QDoubleSpinBox:disabled, QComboBox:disabled {{ color: #536c7c; }}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 19px; border: none; }}
QComboBox::drop-down {{ width: 22px; border: none; }}
QComboBox QAbstractItemView {{ background: #1c2d38; selection-background-color: #355d51; }}
QListWidget::item {{ padding: 7px; border-radius: 5px; }}
QListWidget::item:selected {{ color: {ACCENT}; background: #24463c; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 5px; }}
QScrollBar::handle:vertical {{ background: #3c5363; border-radius: 2px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent; height: 0; border: none; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ padding: 12px 13px; color: {TEXT_FAINT}; border-bottom: 1px solid {BORDER}; }}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; }}
QToolTip {{ background: #d4e9e1; color: #0c231c; border: none; padding: 8px; }}
QStatusBar {{ background: {BG}; color: {TEXT_DIM}; font-size: 11px; }}
"""


class WrapLabel(QLabel):
    """Word wrapping that reports its actual height inside scrollable panels."""
    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

    def setText(self, text: str) -> None:
        if text != self.text():
            super().setText(text)
            self.updateGeometry()

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        if not self.text():
            return 0
        doc = QTextDocument()
        doc.setDocumentMargin(0)
        doc.setDefaultFont(self.font())
        doc.setTextWidth(max(width, 100))
        if self.textFormat() == Qt.TextFormat.RichText:
            doc.setHtml(self.text())
        else:
            doc.setPlainText(self.text())
        return int(doc.size().height()) + 2

    def minimumSizeHint(self):
        return QSize(0, self.heightForWidth(self.contentsRect().width()))

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setHeight(self.heightForWidth(self.contentsRect().width()))
        return hint

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if event.oldSize().width() != event.size().width():
            self.updateGeometry()


def hline() -> QFrame:
    line = QFrame()
    line.setObjectName("sep")
    return line


class Card(QFrame):
    def __init__(self, title: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        if title:
            lab = QLabel(title.upper())
            lab.setObjectName("sectionTitle")
            outer.addWidget(lab)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        outer.addLayout(self.body)

    def add(self, *widgets) -> None:
        for w in widgets:
            self.body.addWidget(w)

    def add_layout(self, layout) -> None:
        self.body.addLayout(layout)




class StatusPill(QLabel):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("pill")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._appearance = None
        self.set("—", TEXT_DIM)

    def set(self, text: str, tone: str) -> None:
        if (text, tone) == self._appearance:
            return
        self._appearance = (text, tone)
        self.setText("●  " + text)
        self.setStyleSheet(f"background: {_tint(tone, 20)}; color: {tone}; padding: 8px 13px;"
                          "border-radius: 10px; font-size: 12px; font-weight: 600;")


def _tint(hex_color: str, alpha: int = 34) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"




def row(*widgets, spacing: int = 8) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    for w in widgets:
        lay.addWidget(w)
    return lay




def set_role(widget: QWidget, role: str) -> None:
    if widget.objectName() != role:
        widget.setObjectName(role)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()


def icon(name: str, color: str = ACCENT) -> QIcon:
    """Small vector icons drawn with Qt; no external assets or icon fonts."""
    pix = QPixmap(48, 48)
    pix.setDevicePixelRatio(2)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(color), 1.65, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                 Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if name in ("reverse_in", "head_in", "parallel"):
        p.drawPolyline(QPolygonF([QPointF(3, 5), QPointF(3, 21), QPointF(15, 21), QPointF(15, 5)]))
        p.drawRoundedRect(QRectF(6, 8, 6, 10), 1.5, 1.5)
        p.drawLine(7, 11, 11, 11)
        if name == "parallel":
            p.drawLine(17, 9, 22, 9)
            p.drawLine(20, 7, 22, 9)
            p.drawLine(20, 11, 22, 9)
        else:
            a, b = (4, 17) if name == "reverse_in" else (17, 4)
            p.drawLine(20, a, 20, b)
            d = -3 if b > a else 3
            p.drawLine(17, b + d, 20, b)
            p.drawLine(23, b + d, 20, b)
    elif name == "grid":
        p.drawRoundedRect(QRectF(3, 3, 18, 18), 2, 2)
        for x in (9, 15):
            p.drawLine(x, 3, x, 21)
            p.drawLine(3, x, 21, x)
    elif name == "focus":
        for x, y, sx, sy in ((3, 3, 1, 1), (21, 3, -1, 1), (3, 21, 1, -1), (21, 21, -1, -1)):
            p.drawLine(x, y, x + sx * 5, y)
            p.drawLine(x, y, x, y + sy * 5)
        p.drawEllipse(QPointF(12, 12), 3, 3)
    elif name == "play":
        p.setBrush(QColor(color))
        p.drawPolygon(QPolygonF([QPointF(8, 5), QPointF(19, 12), QPointF(8, 19)]))
    elif name == "route":
        p.drawEllipse(QPointF(5, 18), 2, 2)
        p.drawEllipse(QPointF(19, 6), 2, 2)
        path = QPainterPath(QPointF(5, 16))
        path.cubicTo(5, 4, 19, 20, 19, 8)
        p.drawPath(path)
    elif name == "eye":
        path = QPainterPath(QPointF(2, 12))
        path.cubicTo(7, 4, 17, 4, 22, 12)
        path.cubicTo(17, 20, 7, 20, 2, 12)
        p.drawPath(path)
        p.drawEllipse(QPointF(12, 12), 3, 3)
    elif name == "reset":
        p.drawArc(QRectF(5, 5, 15, 15), 40 * 16, 290 * 16)
        p.drawPolyline(QPolygonF([QPointF(5, 4), QPointF(5, 10), QPointF(11, 10)]))
    else:
        p.drawRoundedRect(QRectF(5, 5, 14, 14), 2, 2)
    p.end()
    return QIcon(pix)
