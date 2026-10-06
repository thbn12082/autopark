"""Bộ thử TỔNG HỢP nhỏ của T4, dựng MỘT lần mỗi tiến trình pytest và dùng chung cho tests/test_overhead_*.py,
tests/test_sync_video.py và tests/test_overhead_app_ui.py (tệp này không phải test: tên không bắt đầu bằng test_).

Camera ảo 960×540 (Kannala–Brandt đã biết) cao 1,8 m trên sa bàn 2,5 × 1,5 m: 24 mốc kiểm soát + 8 điểm kiểm tra
(marker 100 mm, ≈ 5 điểm ảnh mỗi ô module ở giữa ảnh), xe giả hai marker 80 mm ở 0,10 m; lần chạy 40 khung, TC-1 10 tư
thế × 8 khung (test hạ yêu cầu ≥ 30 khung hợp lệ xuống 5). Mọi tệp nằm trong một thư mục tạm của tiến trình, xóa lúc
thoát. Test cần sửa tệp thì chép sang tmp_path của nó, không sửa bộ chung.
"""
import atexit
from functools import lru_cache
from pathlib import Path
import shutil
import tempfile

SMALL = dict(size=(960, 540), sandbox=(2.5, 1.5), height=1.8, frames=40, tc1_poses=10, tc1_frames=8, seed=1)
TC1_MIN_FRAMES = 5


@lru_cache(maxsize=1)
def small_set() -> dict:
    """Thông tin của bộ thử (đường dẫn tệp, camera, renderer, tư thế thật…), như `write_synthetic_set` trả."""
    from autopark.evaluation.overhead_synth import write_synthetic_set

    root = Path(tempfile.mkdtemp(prefix="autopark_t4_"))
    atexit.register(shutil.rmtree, root, True)
    return write_synthetic_set(root / "bo_thu", **SMALL)


@lru_cache(maxsize=1)
def floor_fit_path() -> Path:
    """Kết quả khớp mặt sàn của bộ thử (lệnh floor, ghi một lần)."""
    from autopark.evaluation import overhead_ref

    info = small_set()
    out = Path(info["out"]) / "mat_san.json"
    code = overhead_ref.main(["floor", "--intrinsics", info["intrinsics"], "--survey", info["survey"], "--image",
                              info["floor_image"], "--out", str(out)])
    assert code == 0, f"floor thoát mã {code}"
    return out


@lru_cache(maxsize=1)
def tc1_report_path() -> Path:
    """Biên bản TC-1 đầy đủ của bộ thử (lệnh tc1, ≥ 5 khung hợp lệ mỗi tư thế, ghi một lần)."""
    from autopark.evaluation import overhead_ref

    info = small_set()
    out = Path(info["out"]) / "tc1_tong_hop.json"
    code = overhead_ref.main(["tc1", "--floor", str(floor_fit_path()), "--markers", info["markers"], "--poses",
                              info["tc1_poses"], "--kind", "full", "--min-frames", str(TC1_MIN_FRAMES), "--out",
                              str(out)])
    assert code == 0, f"tc1 thoát mã {code}"
    return out


def copy_run(dest: Path, name: str = "chay_01") -> Path:
    """Chép video + frames.csv + events.csv + json của một lần ghi trong bộ thử sang `dest`; trả đường dẫn video."""
    src = Path(small_set()["out"])
    dest.mkdir(parents=True, exist_ok=True)
    for suffix in (".avi", ".frames.csv", ".events.csv", ".json"):
        shutil.copy2(src / f"{name}{suffix}", dest / f"{name}{suffix}")
    return dest / f"{name}.avi"
