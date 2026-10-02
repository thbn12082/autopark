"""Phát lại một gói lần chạy: `python -m autopark.evaluation.replay <thư mục gói>`.

Gói SIM: tái mô phỏng và đối chiếu kết quả (như trước), in "Replay OK: …". Gói của lần chạy qua VehicleIO (T9, thêm
02/10/2026): phát lại log (`run_store.replay_vehicle_run`), in báo cáo tiếng Việt; mã thoát 0 = KHỚP, 1 = KHÁC,
2 = không phát lại được (`ReplayNotSupported`: thiếu vehicle_io/, log ghi trước khi có băng phát lại, gói hỏng...).

Sau review 02/10/2026: 1 chỉ còn nghĩa là KHÁC. Lỗi bất ngờ khi phát lại gói VehicleIO (lỗi của mã, gói hỏng kiểu chưa
lường) → mã 3, in tên lỗi (traceback ra stderr); trước đó nó thoát bằng traceback với mã 1, như một lần phát lại KHÁC.
stdout và stderr thay ký tự không mã hóa được thay vì ném lỗi khi in báo cáo tiếng Việt (chuyển hướng ra tệp mà không có
-X utf8, bảng mã cp1252). Nhánh gói SIM giữ nguyên như trước.
"""
import argparse
import sys
import traceback
from pathlib import Path

from autopark.storage.run_store import ReplayNotSupported, is_vehicle_io_package, replay_run, replay_vehicle_run

EXIT_MATCH, EXIT_DIFFER, EXIT_NOT_SUPPORTED, EXIT_ERROR = 0, 1, 2, 3


def _safe_streams() -> None:
    """stdout/stderr ghi UTF-8 và thay ký tự không mã hóa được, không ném UnicodeEncodeError (lỗi in không được thành mã
    thoát 1 = KHÁC). Luồng không có `reconfigure` (đã bị thay bằng đối tượng khác) thì để nguyên."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def main(argv: list[str] | None = None) -> int:
    _safe_streams()
    parser = argparse.ArgumentParser(description="Chạy lại snapshot và đối chiếu kết quả mô phỏng; gói của lần chạy "
                                                 "qua VehicleIO: phát lại log và so với bản ghi")
    parser.add_argument("run_directory")
    args = parser.parse_args(argv)
    # Gói VehicleIO nhận cả qua vehicle_io/link.json: run.json thiếu hay hỏng thì is_vehicle_io_package trả False, và gói
    # khi đó phải thành mã 2 (ReplayNotSupported), không rơi xuống nhánh SIM rồi thoát bằng traceback, mã 1 như KHÁC.
    if is_vehicle_io_package(args.run_directory) or (Path(args.run_directory) / "vehicle_io" / "link.json").is_file():
        try:
            session, report = replay_vehicle_run(args.run_directory)
        except ReplayNotSupported as exc:
            print(exc)
            return EXIT_NOT_SUPPORTED
        except Exception as exc:  # noqa: BLE001 - không phải KHÁC: không có kết luận nào về quyết định của phần mềm
            traceback.print_exc()
            print(f"Không phát lại được (lỗi bất ngờ, mã thoát {EXIT_ERROR}): {type(exc).__name__}: {exc}")
            return EXIT_ERROR
        try:
            print("\n".join(report.lines()))
        finally:
            session.close()
        return EXIT_MATCH if report.ok else EXIT_DIFFER
    session = replay_run(args.run_directory)
    print(f"Replay OK: {session.state.value}, {session.world.step_count} steps")
    session.close()
    return EXIT_MATCH


if __name__ == "__main__":
    raise SystemExit(main())
