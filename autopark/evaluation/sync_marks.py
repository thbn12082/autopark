"""Dấu đồng bộ video–log (T14 ở docs/KIEM_THU_VA_LO_TRINH.md; phương pháp R7 ở mục 2.1). Không dùng Qt.

Mỗi dấu (`SYNC_MARK`) là một lần nháy ô trắng lớn trên màn hình laptop (`ui/sync_flash.py`) — camera quay R3 thấy được —
cùng một dòng CSV có `t_perf` = `time.perf_counter()`, đúng đồng hồ của stamp bàn thử và bản ghi phiên (QPC trên Windows,
một gốc chung cho mọi tiến trình của MỘT máy; laptop và máy bàn thì không so được). Dòng `CLOCK` không nháy gì: giao diện
tự ghi khi phiên vào hay ra một lần chạy, để ghép `t_perf` với thời gian phiên. Cần dòng này vì ở nhánh SIM thời gian phiên
là thời gian mô phỏng, trôi so với đồng hồ thật (script tạm 01/10/2026, offscreen: cộng `QElapsedTimer.restart()/1000` qua
các nhịp 16,5 ms ra ít hơn `perf_counter` 3,9 %); CHƯA ĐO trên giao diện thật.

Cột (`SYNC_FIELDS`, thứ tự cố định — hợp đồng với công cụ chấm T5, đọc bằng `read_sync_marks`):

- `n`: số thứ tự dấu 1, 2, …, đúng số vẽ trong ô trắng; để trống ở dòng CLOCK.
- `kind`: `SYNC_MARK` hoặc `CLOCK`.
- `t_perf`: giây, làm tròn 6 chữ số. Ở dòng SYNC_MARK, đọc NGAY SAU khi ô đã được vẽ (`repaint()` trả về). Ô sáng trên màn
  hình thật muộn hơn một khoảng (bộ ghép hình DWM, vsync, tấm nền) CHƯA ĐO.
- `t_wall`: giờ máy, `datetime.now().isoformat(timespec="milliseconds")` (chỉ để đọc, không dùng để tính).
- `source`: `ui.app` | `ui.lidar_app` | `ui.rig_app` | `rig.bench`.
- `trigger`: `button` | `key_f8` | `console_key` | `periodic` | `auto_start` | `auto_end` | `state_change`.
- `state`: trạng thái phiên (`SessionState`) ở giao diện đỗ xe; ở bàn thử để trống, hoặc `recording` khi `ui.rig_app` đang
  ghi phiên.
- `t_session`: thời gian phiên (giây, 4 chữ số). Dòng SYNC_MARK chỉ có khi phiên đang mô phỏng (lái tay); dòng CLOCK có
  mỗi khi phiên có `world`.
- `t_io`: `io.now()` của liên kết VehicleIO (lần chạy vừa xong, hoặc lần Bắt đầu đỗ tới); trống khi không có.
- `io_clock`: `realtime` (`io.now()` = `perf_counter` − hằng số: bo thật / cổng serial) hoặc `sim` (đồng hồ mô phỏng của bo).
- `t_rig_s`: `t_perf − Rig.t_start` (bàn thử; trống khi Rig chưa bắt đầu).
- `flash_ms`: thời gian ô sáng; `paint_ms`: thời gian vẽ ô (từ lúc gọi tới lúc vẽ xong); `note`: chữ tự do.
- `time_scale` (thêm 02/10/2026, cột cuối): giây phiên trên một giây thật — "tốc độ chạy" của cockpit
  (`Session.realtime_factor`), hoặc 1 khi lần chạy đi qua VehicleIO thời gian thực (thời gian phiên bám `io.now()`, không
  theo hệ số). Có ở mọi dòng của `ui.app` và `ui.lidar_app`; trống ở `ui.rig_app` và `rig.bench`. Ô "tốc độ chạy" bị khóa
  khi xe đang chạy (RUNNING/STOPPING), nên mọi dòng CLOCK của một lần chạy cùng một hệ số; lúc lái tay hệ số đổi được, mỗi
  dấu mang hệ số lúc dấu. Tệp ghi trước cột này không có nó: `read_sync_marks` trả chuỗi rỗng (không biết hệ số).

Đổi đồng hồ (tóm tắt; tài liệu đầy đủ ở docs/KIEM_THU_VA_LO_TRINH.md):

- Video → perf: với mỗi dấu k, lấy khung đầu tiên có ít nhất nửa ô sáng; thời điểm v_k theo stamp của tệp video, không theo
  số khung/s danh định. Khớp `t_perf = a + b·v` (một dấu thì b = 1).
- Log → perf: VehicleIO thời gian thực: `t_perf = t_io + (t_perf − t_io)` lấy từ bất kỳ dòng CLOCK/SYNC_MARK nào của cùng
  liên kết. SIM hoặc bo mô phỏng: dùng dòng CLOCK gần nhất c, `t_perf ≈ c.t_perf − (c.t_session − t_sự_kiện) / c.time_scale`
  (thiếu `time_scale` thì công thức chỉ đúng khi chạy ở 1×); tốt hơn là nội suy tuyến tính giữa hai dòng CLOCK của cùng lần
  chạy ở hai phía sự kiện, đỡ cả độ trôi ≈ 3,9 %. KHÔNG cộng `t_session` vào lúc START (vì trôi). `rig.bench`: `t_s` của
  khung/vòng quét đã là `perf_counter`.
- Sai số: ± một khung video mỗi dấu, cộng độ trễ hiển thị L (CHƯA ĐO; bỏ qua L làm mọi hiệu log − video lớn thêm L, tức
  nghiêng về phía an toàn với ngưỡng "≤"); dòng CLOCK ghép trong một nhịp giao diện (≈ 16 ms, tới 100 ms khi giao diện khựng).

Tệp sống: `SyncMarkLog` ghi từng dòng xuống đĩa ngay khi thêm (mở, nối, đóng), nên tiến trình chết giữa chừng vẫn còn các
dòng đã có. Lỗi đĩa không làm mất dòng: dòng vẫn ở `rows` (bộ nhớ), `error` giữ lỗi gần nhất, `unwritten` đếm dòng tệp sống
còn thiếu; lần ghi sau (dòng mới, hay `flush()`) ghi lại cả tệp từ bộ nhớ, nên tệp sống đủ lại ngay khi đĩa ghi được (ví dụ
Excel đã đóng tệp; thêm 02/10/2026). Mặc định tệp nằm dưới `runs/sync_marks/` (git bỏ qua).
"""
from __future__ import annotations

import contextlib
import csv
from datetime import datetime
import os
from pathlib import Path
from typing import Callable

SYNC_MARK = "SYNC_MARK"
CLOCK = "CLOCK"
KINDS = (SYNC_MARK, CLOCK)
DEFAULT_SYNC_DIR = Path(__file__).resolve().parents[2] / "runs" / "sync_marks"
SYNC_FIELDS = ["n", "kind", "t_perf", "t_wall", "source", "trigger", "state", "t_session", "t_io", "io_clock",
               "t_rig_s", "flash_ms", "paint_ms", "note", "time_scale"]
AUTO_FIELDS = ("n", "kind", "t_perf", "t_wall", "source")      # do SyncMarkLog.add tự điền, người gọi không truyền
INT_FIELDS = ("n", "flash_ms")
FLOAT_FIELDS = ("t_perf", "t_session", "t_io", "t_rig_s", "paint_ms", "time_scale")


class SyncMarkLog:
    """Các dòng SYNC_MARK / CLOCK của một công cụ (một cửa sổ, một phiên `rig.bench`).

    Chưa có `path` thì dòng chỉ ở bộ nhớ; `open(path)` tạo tệp (không bao giờ ghi đè) và ghi mọi dòng đã có, từ đó mỗi
    `add()` nối ngay một dòng vào tệp. `marks`: số dòng SYNC_MARK. `error`: lỗi đĩa gần nhất (giữ lại cả khi lần ghi sau
    đạt), `failed_writes`: số lần ghi hỏng (nối dòng hay ghi lại cả tệp), `last_write_ok`: lần ghi gần nhất (None: chưa
    ghi lần nào). `unwritten`: số dòng có trong bộ nhớ mà tệp sống còn thiếu; khác 0 thì lần ghi sau ghi lại cả tệp."""

    def __init__(self, source: str, path: str | Path | None = None, *, wall: Callable[[], datetime] = datetime.now):
        self.source = source
        self.wall = wall
        self.rows: list[dict] = []
        self.marks = 0
        self.path: Path | None = None
        self.error: str | None = None
        self.failed_writes = 0
        self.last_write_ok: bool | None = None
        self.unwritten = 0
        if path is not None:
            self.open(path)

    def open(self, path: str | Path) -> Path:
        """Tạo tệp (thư mục cha tạo nếu thiếu; tệp đã có → FileExistsError, không ghi đè), ghi tiêu đề và mọi dòng đã có
        trong bộ nhớ. Lỗi (OSError) được ném ra cho người gọi."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=SYNC_FIELDS)
            writer.writeheader()
            writer.writerows(self.rows)
        self.path = path
        return path

    def add(self, kind: str, t_perf: float, **fields) -> dict:
        """Thêm một dòng (`kind` là SYNC_MARK hoặc CLOCK; `fields` là các cột khác của SYNC_FIELDS, None = trống). Dòng
        SYNC_MARK được đánh số `n`. Có tệp thì ghi ngay (nối dòng; tệp còn thiếu dòng trước thì ghi lại cả tệp); lỗi đĩa
        chỉ ghi vào `error` và `unwritten`, dòng vẫn ở `rows`."""
        if kind not in KINDS:
            raise ValueError(f"Loại dòng đồng bộ không hợp lệ: {kind!r} (chỉ {', '.join(KINDS)})")
        bad = [name for name in fields if name not in SYNC_FIELDS or name in AUTO_FIELDS]
        if bad:
            raise ValueError(f"Cột không nhận: {', '.join(bad)} (cột tự điền: {', '.join(AUTO_FIELDS)}; "
                             f"cột hợp lệ: {', '.join(SYNC_FIELDS)})")
        row = dict.fromkeys(SYNC_FIELDS, "")
        for name, value in fields.items():
            row[name] = "" if value is None else value
        row.update(kind=kind, t_perf=round(t_perf, 6), t_wall=self.wall().isoformat(timespec="milliseconds"),
                   source=self.source)
        if kind == SYNC_MARK:
            self.marks += 1
            row["n"] = self.marks
        self.rows.append(row)
        if self.path is not None:
            self._append(row)
        return row

    def _append(self, row: dict) -> None:
        """Nối `row` vào tệp sống. Tệp còn thiếu dòng trước (`unwritten`) thì ghi lại cả tệp từ bộ nhớ thay vì nối: tệp
        đủ lại ngay ở lần ghi được đầu tiên, không còn lỗ ở giữa (ví dụ các dòng CLOCK lúc Excel đang khóa tệp)."""
        try:
            if self.unwritten:
                self._rewrite()
            else:
                with self.path.open("a", newline="", encoding="utf-8") as f:
                    csv.DictWriter(f, fieldnames=SYNC_FIELDS).writerow(row)
        except OSError as exc:
            self._write_failed(exc)
            self.unwritten += 1
        else:
            self.unwritten = 0
            self.last_write_ok = True

    def _write_failed(self, exc: OSError) -> None:
        self.error = f"{type(exc).__name__}: {exc}"
        self.failed_writes += 1
        self.last_write_ok = False

    def _rewrite(self) -> None:
        """Ghi lại cả tệp sống từ bộ nhớ: ghi tệp tạm cạnh nó rồi thay (`os.replace`), nên lỗi giữa chừng không làm mất
        các dòng đã có trên đĩa. Lỗi (OSError) ném ra cho người gọi; tệp tạm được dọn."""
        tmp = self.path.with_name(self.path.name + ".tmp")
        try:
            self.write_csv(tmp)
            os.replace(tmp, self.path)
        except OSError:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
            raise

    def flush(self) -> bool:
        """Tệp sống còn thiếu dòng (`unwritten`) thì thử ghi lại cả tệp ngay (giao diện gọi khi đóng cửa sổ). True khi tệp
        sống có đủ mọi dòng; False khi chưa có tệp sống hoặc vẫn không ghi được (lỗi ở `error`)."""
        if self.path is None:
            return False
        if self.unwritten:
            try:
                self._rewrite()
            except OSError as exc:
                self._write_failed(exc)
                return False
            self.unwritten = 0
            self.last_write_ok = True
        return True

    def write_csv(self, path: str | Path) -> Path:
        """Bản đầy đủ mọi dòng (dùng khi xuất log): ghi đè tệp đích, tạo thư mục cha nếu thiếu."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=SYNC_FIELDS)
            writer.writeheader()
            writer.writerows(self.rows)
        return path


def sync_file_path(folder: str | Path, source: str, now: datetime | None = None) -> Path:
    """Tên tệp sống: `<folder>/<yyyymmdd_hhmmss_mmm>_<source với . thành _>.csv`, ví dụ
    `runs/sync_marks/20261001_142233_517_ui_app.csv`."""
    stamp = f"{now or datetime.now():%Y%m%d_%H%M%S_%f}"[:-3]
    return Path(folder) / f"{stamp}_{source.replace('.', '_')}.csv"


def read_sync_marks(path: str | Path) -> list[dict]:
    """Đọc tệp dấu đồng bộ. Ô không trống của `n`, `flash_ms` thành int; của `t_perf`, `t_session`, `t_io`, `t_rig_s`,
    `paint_ms`, `time_scale` thành float; ô trống giữ chuỗi rỗng. Cột của SYNC_FIELDS mà tệp không có (tệp ghi trước khi
    thêm cột, ví dụ `time_scale` trước 02/10/2026) hay dòng thiếu ô đọc ra chuỗi rỗng như ô trống."""
    with Path(path).open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for name in SYNC_FIELDS:
            if row.get(name) is None:
                row[name] = ""
        for name in INT_FIELDS:
            if row.get(name):
                row[name] = int(row[name])
        for name in FLOAT_FIELDS:
            if row.get(name):
                row[name] = float(row[name])
    return rows
