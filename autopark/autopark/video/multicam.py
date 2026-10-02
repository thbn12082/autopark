"""Nhiều camera USB chạy song song: mỗi camera một luồng đọc, ghép bộ ảnh theo thời gian, bỏ bộ ảnh lệch quá ngưỡng.

Đây là `MultiCameraManager` mà kế hoạch giai đoạn 2 yêu cầu ("hàng đợi giới hạn và logic bỏ bộ ảnh quá lệch thời
gian"). Không cần torch hay Qt.

- Camera được gọi theo **cổng hub**, không theo index OpenCV: index đổi sau khi khởi động lại máy (đo ngày 23/09,
  docs/usb_topology.md), còn cổng thì không. `resolve_ports()` hỏi Windows (PnP + DirectShow) để đổi cổng → index
  ngay lúc mở.
- Mỗi camera giữ vài khung gần nhất trong một vòng đệm có giới hạn (không hàng đợi vô hạn, không tích lũy độ trễ).
- `latest_set()` ghép một bộ: mốc thời gian = khung mới nhất của camera *chậm nhất* (camera có khung mới nhất sớm
  nhất; khi bật chờ và các camera khác nhịp: chỉ xét camera định nhịp, xem dưới), rồi mỗi camera chọn khung gần mốc đó
  nhất. Độ lệch của bộ (`skew_s`) = stamp lớn nhất − nhỏ nhất. Bộ lệch quá `max_skew_s` bị bỏ và đếm. Một bộ
  chỉ được coi là mới khi MỌI camera trong bộ đều có khung khác bộ trước, nên số bộ mỗi giây ≤ tốc độ camera chậm
  nhất; khi khung đến không đều, quy tắc này bỏ mất một phần khung của camera chậm — đếm ở `frames_skipped` và
  `sets_blocked_not_new` (bản đầu chỉ đòi mốc tiến, nên AI chấm lại 43 bộ/s gần trùng nhau khi camera có 24 khung/s).
- **Chờ camera chậm có giới hạn (`max_wait_s`, mặc định tắt ở lớp này; `RigConfig` bật 60 ms).** Mục đích: camera đang
  có đợt khung hỏng hay bị treo không kéo cả chuỗi chậm theo nó (đo 23/09: cổng 1 ở 480p có đợt 26–36 % khung hỏng, còn
  ≈ 15–18 khung tốt/s so với 24, và theo quy tắc trên cả chuỗi chậm theo nó). `max_wait_s` None hay ≤ 0: đúng quy tắc
  cũ, từng bộ một.
  **Quy tắc hiện hành (bản thứ ba, 24/09, người dùng duyệt): mỗi camera xét theo nhịp của CHÍNH nó.** P_p = chu kỳ khung
  TRUNG BÌNH của camera p, đo từ 26 lần khung tới gần nhất, gồm cả khung cắt/xé mà nguồn đã loại
  (`CameraWorker.frame_interval_s`, `CameraWorker.arrivals`; chưa đủ 3 lần thì chưa rõ). Ngưỡng riêng
  L_p = max(`max_wait_s`, 1,5 × P_p) (`wait_limits_s`; P_p chưa rõ thì max(`max_wait_s`, 1,5 × chu kỳ camera nhanh
  nhất đã rõ)). Nhịp 24 khung/s đo được KHÔNG đều: khoảng cách xen kẽ ≈ 31/48 ms, trung bình 41,9 ms
  (GIAI_DOAN_1_CAMERA.md mục 4.1), nên L_p ≈ 63 ms; ở 15 khung/s ≈ 100 ms. Khi vài camera đã có khung mới mà camera
  khác chưa, bộ chờ; bộ được phát KHÔNG CÓ các camera đang chờ khi không camera nào trong số đó còn đáng chờ
  (`worth_waiting`). Một camera đang chờ hết đáng chờ khi:
  (a) khung mới cũ nhất đang chờ đã chờ quá L_p của nó; hoặc
  (b) nó lỡ nhịp của chính nó: khung "đúng lượt" dự đoán = khung tốt cuối + m·P_p (m ≥ 1) đã trễ quá P_p/2 — với m = 1
      đúng là "không có khung tốt mới trong 1,5 × P_p kể từ khung tốt cuối". m chọn để khung dự đoán gần nhất với khung
      mới cũ nhất của các camera đã có khung mới CÙNG NHỊP với nó (chu kỳ lớn / nhỏ ≤ SAME_CADENCE, `due_reference`);
      không có camera như thế thì gần khung mới cũ nhất của mọi camera (t_old). (Sửa 24/09, mô phỏng đồng hồ giả, CHƯA
      đo trên phần cứng: khung dư chưa dùng của camera nhanh làm t_old sớm, và camera chậm hơn vừa mất một khung bị so
      với đúng lượt nó VỪA lỡ — bị bỏ thêm một bộ rồi ghép trễ một chu kỳ mãi.) Hoặc
  (b') khung đúng lượt đã TỚI nhưng hỏng (lần tới cắt/xé ghi trong `arrivals`, đọc CÙNG khóa với vòng đệm —
      `CameraWorker.snapshot_with_arrival`; đọc riêng sau đó thì khung tốt tới giữa hai lần đọc bị tưởng là hỏng, sửa
      24/09): thôi chờ ngay, không đợi thêm P_p/2; hoặc
  (b'') nó treo: không có lần tới nào (tốt hay hỏng) trong STALL_PERIODS = 2,5 × P_p — thôi chờ nó ở mọi bộ cho tới lần
      tới kế.
  Camera KHỎE chạy chậm hơn (phơi sáng dài: 15, 12 khung/s; 23,85 so với 29,3 khung/s ở 720p) không lỡ nhịp của nó nên
  không bị bỏ: nó "định nhịp" cả chuỗi (số bộ/s ≈ tốc độ của nó, như quy tắc cũ) và khung dư của camera nhanh không vào
  bộ nào (`frames_skipped`). Hệ quả phải biết: camera khỏe mà chậm CỐ ĐỊNH (ví dụ chỗ tối 8 khung/s) làm cả chuỗi chậm
  theo; quy tắc chờ chỉ giúp khi một camera lỡ nhịp của chính nó. Khi các camera trong bộ khác nhịp (chu kỳ chênh quá
  SAME_CADENCE = 1,15 lần), mốc bộ lấy trong các camera định nhịp (cùng nhịp với camera chậm nhất, `pacing_ports`), camera
  nhanh chọn khung mới gần mốc đó nhất.
  Sau đó (c) sửa "khóa lệch pha" (`out_of_phase`), chỉ giữa các camera định nhịp (có đúng một khung mới mỗi bộ): độ lệch
  pha của từng camera = trung vị, qua REGROUP_SETS = 5 bộ ứng viên đủ liên tiếp cùng thành phần, của stamp camera đó trừ
  stamp trung bình của các camera định nhịp; nếu các độ lệch này chia hai cụm — khe lớn nhất g đủ lớn để bộ sau lệch
  ≈ P − g, ít hơn độ lệch S hiện tại quá P/3 — và trong chính bộ sắp phát mọi khung của cụm mới tới sau mọi khung của
  cụm cũ, thì cụm mới được để dành cho bộ sau (`FrameSet.deferred`, đếm ở `sets_regrouped`; chỉ ở bộ không có camera
  đang chờ, khi mọi camera trong bộ đã rõ nhịp — camera mới vào được sửa sau 5 bộ). Quyết trên MỘT bộ thì với nhịp xen
  kẽ 31/48 ms, stamp của hai camera cùng chu kỳ dao động ±8 ms, cỡ ngưỡng P/3, và (c) tách liên tục những bộ vốn đúng
  nhóm (người kiểm tra, 24/09).
  **Vì sao đổi sang nhịp riêng (đo trên phần cứng 24/09).** `runs/may_moi_20260924_may_ban/m02_720p_chi_camera.rig.json`
  (bản sao số: docs/evidence/may_ban/tham_chieu_20260924.json): ở 720p cổng 1 chạy 29,3 khung/s (phơi sáng tự động), cổng
  2–4 23,85 khung/s, cả bốn 0 khung hỏng. Bản thứ hai — một ngưỡng chung L = max(`max_wait_s`, 1,5 × chu kỳ camera NHANH
  nhất) và (b) coi khung dự đoán tới sau khung mới cũ nhất quá một chu kỳ của camera nhanh nhất là "thuộc nhóm sau" — bỏ
  camera 24 khung/s khỏe ở 263 / 855 bộ (cổng 2 / 3 / 4: 106 / 137 / 106), 28,5 bộ/s; ở 480p (bốn camera ≈ 23,85) bỏ camera
  khỏe ở 3 / 2861 bộ (m01, cùng thư mục). Với nhịp khác nhau, khung đúng lượt của camera 24 khung/s thường tới sau khung
  của camera 29 khung/s hơn 34 ms nên bị coi là "nhóm sau". (c) bản thứ hai xét cả bộ, P = chu kỳ camera nhanh nhất và
  "cùng nhịp" ≤ 1,25 lần: 41,9/34,1 = 1,23 lọt ngưỡng nên nó cũng để dành oan cổng 2–4.
  **Mô phỏng đồng hồ giả 24/09** (phát lại khoảng cách khung THẬT của runs/camera_bench/20260923; pha ngẫu nhiên, rung stamp
  0–2 hay 0–3 ms, ghép bộ mỗi 2 ms, tính 20 s sau 3 s, 6 hạt, max_skew 60 ms; KHÔNG đo trên phần cứng), bản thứ hai →
  bản thứ ba (tắt chờ):
  720p, cổng 1 29,3 khung/s (m02_cam0_720p_exp-6) + cổng 2–4 23,85 (n03): camera khỏe bị bỏ hay để dành nhiều nhất
  12,4–18,3 % số bộ, 27,1–29,2 bộ/s → 0–0,42 % (chỉ cổng 1, camera nhanh), 23,85–23,90 bộ/s (tắt: 21,6–23,9 bộ/s); độ lệch
  bộ trung vị 17,7–27,7 → 17,1–28,7 ms, p95 33,7–39,0 → 31,0–46,0 ms (tắt: 15,4–27,5 / 28,2–39,9).
  480p, bốn camera m04: 0–0,21 % → 0–0,21 % (để dành, không lần bỏ nào), 23,85 bộ/s cả hai.
  3 × 23,85 (n03) + một camera đều 15 khung/s: camera 15 khung/s bị bỏ 36,4–37,1 %, 23,8–23,9 bộ/s → 0 %, 15,0 bộ/s
  (bằng tắt chờ); độ lệch trung vị 30–36 ms, p95 46 ms (tắt: 19–37 / 38–52 ms).
  Nhịp Markov 31,4/48,3 ms độc lập từng camera (TỔNG HỢP, pha trôi, khắc nghiệt hơn nhịp thật): bỏ 1,2–2,1 %, bỏ + để dành
  2,7–2,9 % → bỏ 0 %, để dành 2,1–2,5 % (pha trôi qua mép nhóm thật thì (c) ghép lại), 95,7–96,3 % bộ đủ.
  Cổng 1 hỏng 36 % khung theo đợt 1 s (nguồn báo khung hỏng): cổng 1 bị bỏ 16,1–18,7 % số bộ ở cả hai bản; camera khỏe
  bị bỏ hay để dành 0–2,1 % → 0–0,21 %; khung mới chờ lâu nhất 29,6–55,3 → 16,4–37,6 ms (nhờ (b')); 23,85 bộ/s (tắt:
  18,5–20,0).
  Cổng 2 treo 0,3 s: như nhau (23,85 bộ/s, chỉ cổng 2 bị bỏ, khung mới chờ lâu nhất 28,7–44,3 → 28,7–47,8 ms).
  Sau hai sửa của vòng kiểm tra tối 24/09 (mốc `due_reference` ở (b), lần tới chụp cùng khóa ở (b')), cùng sáu kịch bản
  cho ĐÚNG các số trên. Kịch bản thêm, 720p khác nhịp như trên mà cổng 4 (23,85) hỏng 36 % khung theo đợt 1 s: bộ bỏ cổng
  4 / khung hỏng của nó 580 / 481 → 513 / 481 (6 hạt × 20 s), 23,90–24,75 → 23,85–24,30 bộ/s; phần dư ≈ 7 % chưa phân
  tích hết (dồn ở 2 / 6 hạt; pha cổng 4 so với nhóm trôi qua cả vùng ≈ P/2, nơi ghép nhóm tự nó mơ hồ). Lưới đều, cùng
  tỉ lệ hỏng, 4 hạt × 3 pha: 1169 → 982 bộ bỏ cho 981 khung hỏng. Camera nhanh (cổng 1) hỏng: như nhau.
  Chỗ còn kém tắt chờ: khi camera khác nhịp, độ lệch bộ lớn hơn vài ms (mỗi camera chỉ chọn trong khung chưa dùng, và bộ
  được phát ngay khi mọi camera có khung mới — quy tắc cũ chặn thêm cho tới khi khung gần mốc nhất của mọi camera đều
  mới). Sàn 60 ms và các hệ số 1,5, P/2, 2,5, P/3, 1,15 là lựa chọn thiết kế, CHƯA đo trên phần cứng; số đo lại trên
  bàn thử sau bản này: CHƯA CÓ.
  **Lịch sử (để đọc số cũ).** Bản đầu (sáng 24/09): L cố định, (b) = "mọi camera đang chờ im quá L". Người kiểm tra và mô
  phỏng tìm ra ba lỗi: (1) camera KHỎE chạy dưới 1/`max_wait_s` (dưới 16,7 fps với 60 ms) im quá 60 ms giữa hai khung
  bình thường nên bị bỏ luân phiên; (2) camera vừa lỡ một khung đã "im quá L" dù khung kế chỉ còn 2 ms nữa; (3) mỗi camera
  chỉ chọn trong khung chưa dùng, nên camera vào sau (mở lần lượt, hay quay lại sau khi mất) ở pha không may bị ghép khung
  chu kỳ k với chu kỳ k+1 của camera kia mãi mãi (độ lệch trung vị ≈ 40 ms thay vì ≈ 6 ms). Bản thứ hai (24/09): L theo
  camera nhanh nhất, (b) dự đoán khung đúng lượt kèm điều kiện "nhóm sau", chu kỳ TRUNG BÌNH trên `arrivals` (bản ước
  lượng "một lưới" trước đó ra ≈ 24–33 ms thay vì 41,9 trên nhịp 31/48 ms và bỏ camera khỏe 3–17 % số bộ khi phát lại
  m04), (c) trên trung vị 5 bộ: phát lại m04 100 % bộ đủ; nhịp Markov pha trôi bỏ 0,2–2,7 % — và lỗi 720p ở trên. Số
  `lagging_per_port`, `sets_partial_wait`, `partial_wait_ms`, `sets_regrouped` của phiên bật chờ chạy trước bản thứ ba
  (w01–w05 ngày 24/09 trong runs/rig_bench/20260924_wait, m01/m02 trong runs/may_moi_20260924_may_ban) là của bản thứ hai;
  `wait_limit_ms` của chúng là ngưỡng chung theo camera nhanh nhất, còn từ bản thứ ba là ngưỡng RIÊNG lớn nhất trong các
  camera tươi của bộ (`FrameSet.wait_limit_s`; từng camera ở `FrameSet.wait_limits_s`, nhịp từng camera ở `period_ms`
  của `camera_stats`).
  Các camera bị bỏ vì chờ nằm ở `FrameSet.lagging`, KHÁC `missing` (không có khung nào trong `stale_after_s`, hoặc không
  mở được) và khác `deferred` (có khung mới nhưng để bộ sau). Khi bật, khung "mới" = CHƯA vào bộ nào VÀ còn tươi
  (≤ `stale_after_s`): nếu chọn cả khung đã dùng, lúc camera chậm quay lại khung của nó gần khung nhanh đã dùng hơn và
  bộ bị chặn tiếp; nếu tính cả khung cũ, camera quay lại sau khi "missing" mang theo khung trước đợt im trong vòng đệm,
  "đã chờ" bị đo từ khung cũ hàng trăm ms và (a) bỏ ngay một camera khỏe. Độ lệch và mốc chỉ tính trên các camera có
  trong bộ. Vì đổi cả cách chọn khung, số đo cũ (trước 24/09) chỉ so được với phiên chạy tắt chờ.
- **Đồng hồ:** mọi stamp dùng `RIG_CLOCK = time.perf_counter` (QPC, phân giải 100 ns trên Windows). KHÔNG dùng
  `time.monotonic`: trên Python 3.12 của Windows nó là GetTickCount64, bước 15,6 ms — các số đo độ lệch vài chục ms
  sẽ bị làm tròn thô (lỗi của bản đầu, phát hiện ngày 23/09). Stamp là thời điểm `read()` trả khung về Python, đã gồm
  chờ và giải mã, **không phải** thời điểm phơi sáng; độ lệch đo được là độ lệch lúc đến, không phải lúc chụp.
- **Khoảng không có khung tốt** (T10, thêm 02/10/2026; `MultiCameraManager.camera_stats`): `gap_closed_max_ms` =
  khoảng dài nhất giữa hai khung tốt liên tiếp (nghĩa của `gap_max_ms` trước T10), `gap_end_ms` = khoảng hở còn mở tới
  cuối phiên (camera ngừng hẳn trước khi hết phiên, hay chưa có khung tốt nào), `gap_max_ms` = số lớn hơn (N-C2). Khoảng
  đi qua lần đặt lại số đếm (bench: hết phần làm nóng) tính đủ cả phần trước đó, nên có thể dài hơn cửa sổ đo. Chỉ
  kiểm bằng đồng hồ giả, camera giả và phát lại bản ghi; chưa đo lại trên bàn thử thật.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from itertools import islice
import threading
import time
from typing import Callable

import numpy as np

from .sources import Frame, FrameReadError, UsbCameraSource

RIG_CLOCK = time.perf_counter
STALE_AFTER_S = 0.5       # camera không có khung mới lâu hơn thế thì bị loại khỏi bộ ảnh và báo "cũ"
LIVE_WINDOW = 3000        # số trực tiếp (giao diện, chuỗi theo giây) chỉ tính trên chừng ấy mẫu cuối
WAIT_PERIODS = 1.5        # ngưỡng chờ RIÊNG từng camera = chừng ấy chu kỳ khung của CHÍNH nó (sàn max_wait_s; đầu module)
STALL_PERIODS = 2.5       # camera không có lần tới nào (tốt hay hỏng) quá chừng ấy chu kỳ của nó: "treo", thôi chờ ở mọi bộ
CADENCE_FRAMES = 25       # chu kỳ khung đo trên chừng ấy khoảng cách giữa các lần khung tới gần nhất (tốt + cắt/xé)
SEED_SPAN = 1.3           # chu kỳ khung: hạt giống = trung bình các khoảng ≤ chừng ấy × phân vị 25 % (xem frame_interval_s)
WIDEN_SPAN = 1.75         # một bước nới: kéo nhóm khoảng dài (48–52 ms) của nhịp 31/48 ms vào nhóm "một khoảng"
SINGLE_SPAN = 1.6         # "một khoảng" = ≤ chừng ấy × chu kỳ (khoảng gộp ≥ 76 ms của nhịp 31/48, hay 2P của nhịp đều, ở ngoài)
OUTAGE_PERIODS = 4        # khoảng dài hơn chừng ấy chu kỳ là đợt im, không dùng để ước lượng chu kỳ
REGROUP_GAIN = 1 / 3      # chỉ ghép lại pha khi độ lệch bộ giảm hơn chừng ấy chu kỳ (rung stamp không làm đảo qua lại)
SAME_CADENCE = 1.15       # "cùng nhịp" với camera chậm nhất: chu kỳ × chừng ấy ≥ chu kỳ lớn nhất (pacing_ports, (c))
REGROUP_SETS = 5          # (c) quyết trên trung vị độ lệch từng camera qua chừng ấy bộ ứng viên đủ, cùng thành phần


def clock_info() -> dict:
    info = time.get_clock_info("perf_counter")
    return {"name": "perf_counter", "implementation": info.implementation, "resolution_s": info.resolution,
            "monotonic": info.monotonic}


def tail(values, n: int | None) -> np.ndarray:
    """n phần tử cuối của một deque/list (tất cả nếu n None), dạng mảng float."""
    k = len(values)
    if n is None or n >= k:
        return np.fromiter(values, float, k)
    return np.fromiter((values[i] for i in range(k - n, k)), float, n)


def dist(values: np.ndarray, scale: float = 1.0, nd: int = 1) -> dict:
    """Trung vị / p95 / min / max / n (một lần sắp xếp trong numpy, không giữ GIL lâu như sorted())."""
    if values.size == 0:
        return {"median": None, "p95": None, "min": None, "max": None, "n": 0}
    med, p95 = np.percentile(values, [50, 95])
    r = lambda x: round(float(x) * scale, nd)
    return {"median": r(med), "p95": r(p95), "min": r(values.min()), "max": r(values.max()), "n": int(values.size)}


def pacing_ports(periods: dict[int, float | None]) -> list[int] | None:
    """Camera "định nhịp": cùng nhịp với camera CHẬM nhất (chu kỳ × SAME_CADENCE ≥ chu kỳ lớn nhất). None khi có camera
    chưa rõ chu kỳ. Khi quy tắc chờ xét mỗi camera theo nhịp của chính nó, camera khỏe chậm nhất không bị bỏ nên nó định
    nhịp cả chuỗi: mỗi bộ nó có đúng một khung mới, camera nhanh hơn có 1–2 khung mới và khung dư không vào bộ nào."""
    if not periods or any(iv is None for iv in periods.values()):
        return None
    slowest = max(periods.values())
    return sorted(p for p, iv in periods.items() if iv * SAME_CADENCE >= slowest)


def fit_width(width: int, height: int, max_width: int) -> tuple[int, int]:
    """Cỡ hiển thị giữ tỉ lệ ảnh: bề rộng ≤ max_width (camera 4:3 không bị ép thành 16:9)."""
    w = min(max_width, width)
    return w, max(1, round(w * height / width))


@dataclass
class CameraSpec:
    port: int                                  # cổng hub (danh tính bền)
    index: int                                 # index OpenCV lúc mở (có thể đổi sau khởi động lại)
    instance_id: str | None = None
    name: str = ""                             # vai trò khi đã gá (trước/sau/trái/phải); rỗng khi chưa có gá

    @property
    def source_id(self) -> str:
        return f"cam_p{self.port}"


def resolve_ports(ports: list[int] | None = None) -> list[CameraSpec]:
    """Cổng hub → index OpenCV qua PnP + DirectShow (Windows, cần pygrabber). `ports=None` lấy mọi camera thấy được.

    Một SỐ cổng có camera ở hai hub khác nhau (`camera_bench._port_of` chỉ đọc số cổng): ví dụ camera trên cao cắm vào
    cổng gốc 2 của máy — KICH_BAN_NGHIEM_THU mục 3.4 bước 4 bảo cắm nó vào cổng gốc riêng, và cổng gốc của laptop thường
    mang số 1–4 — khi camera xe ở cổng 2 của hub. Trước 02/10/2026 (T11) hàm chọn đại một camera theo thứ tự index
    DirectShow, nên `calib_app --port 2` có thể hiệu chuẩn nhầm camera trên cao và ghi đè cam_p2.json. Nay
    (`_rows_on_the_camera_hub`, sửa sau review 02/10/2026):
    - hỏi nhiều cổng mà mọi cổng hỏi KHÔNG trùng số đều ở cùng một hub H (`rig.bench --ports 1 2 3 4`, ô Cổng của dock
      camera, `ports=None` khi ngoài bốn camera xe chỉ có camera trùng số): cổng trùng số lấy camera của nó trên H — danh
      tính camera là cổng của hub camera xe (docs/usb_topology.md);
    - còn lại thì từ chối CẢ lời gọi (ValueError), `ports=None` cũng vậy chứ không bỏ riêng cổng đó: hỏi MỘT cổng
      (`calib_app --port 2`, `roi_app`), mọi cổng hỏi đều trùng số, các cổng không trùng ở nhiều hub (ví dụ `ports=None`
      khi webcam gắn sẵn của laptop cũng có số cổng) hay ở hub không rõ, hoặc H không có camera ở cổng trùng. Lời báo
      nêu cách gỡ cho mọi công cụ.
    Cách chọn giả định các camera hỏi CÙNG LÚC nằm trên một hub, như bàn thử hiện nay; camera xe chia ra nhiều hub mà
    trùng số cổng thì số cổng không phân biệt được chúng: mở theo index (`rig.bench --index …`). Webcam gắn sẵn mang số
    cổng gốc trùng một cổng hub thì chặn lời gọi một cổng số đó (CHƯA gặp: sơ đồ USB của hai máy bàn đã đo chỉ có bốn
    camera xe; laptop chưa đo). Khi mỗi số cổng chỉ ở một hub (bốn camera xe trên một hub), kết quả như trước T11."""
    from . import camera_bench as cb

    pnp = cb.pnp_cameras()
    mapping = cb.join_index_to_port(cb.dshow_device_paths(), pnp)
    by_port: dict[int, list[dict]] = {}
    for m in mapping:
        if m["hub_port"] is not None:
            by_port.setdefault(m["hub_port"], []).append(m)
    wanted = sorted(by_port) if ports is None else list(ports)
    missing = [p for p in wanted if p not in by_port]
    if missing:
        raise ValueError(f"không thấy camera ở cổng {missing}; đang thấy cổng {sorted(by_port)}")
    rows = _rows_on_the_camera_hub(wanted, by_port)
    # như trước: nhiều thiết bị DirectShow ở CÙNG cổng của cùng hub (một camera nhiều giao diện) → lấy cái sau cùng
    chosen = {p: rows[p][-1] for p in wanted}
    return [CameraSpec(port=p, index=chosen[p]["index"], instance_id=chosen[p]["instance_id"]) for p in wanted]


def _rows_on_the_camera_hub(wanted: list[int], by_port: dict[int, list[dict]]) -> dict[int, list[dict]]:
    """Thiết bị DirectShow của từng cổng hỏi. Cổng có camera ở nhiều hub chỉ giữ các thiết bị trên hub H chung của mọi
    cổng hỏi không trùng số; không có H chắc chắn (xem `resolve_ports`) thì ValueError kèm lý do và cách gỡ."""
    unknown = ("", "None")                         # PnP không đọc được hub: không dùng làm mốc
    hubs = {p: sorted({str(m["hub"]) for m in by_port[p]}) for p in wanted}
    rows = {p: by_port[p] for p in wanted}
    anchors = sorted({hubs[p][0] for p in wanted if len(hubs[p]) == 1})
    hub = anchors[0] if len(anchors) == 1 and anchors[0] not in unknown else None
    for p in wanted:
        if len(hubs[p]) == 1:
            continue
        if hub is not None and hub in hubs[p]:
            rows[p] = [m for m in by_port[p] if str(m["hub"]) == hub]
            continue
        if not anchors:
            why = "không cổng nào khác trong lần mở này chỉ ở một hub để biết hub của camera xe"
        elif len(anchors) > 1:
            why = f"các cổng còn lại ở nhiều hub ({', '.join(h or '?' for h in anchors)})"
        elif hub is None:
            why = "không rõ hub của các cổng còn lại"
        else:
            why = f"hub {hub} của các cổng còn lại không có camera ở cổng {p}"
        raise ValueError(
            f"cổng {p}: {len(hubs[p])} hub cùng có camera ở cổng số {p} ({', '.join(h or '?' for h in hubs[p])}); {why}. "
            f"Cách gỡ: cắm camera không qua hub (camera trên cao) vào cổng của máy có số khác {p}, hay rút nó ra (webcam "
            "gắn sẵn của laptop: tắt trong Device Manager); camera không qua hub mở theo index OpenCV (calib_app --index N, "
            "tra N bằng camera_bench list); camera xe mở cùng các cổng khác của hub (ví dụ --ports 1 2 3 4) hay theo "
            "index (rig.bench --index …)")
    return rows


@dataclass
class CameraStats:
    port: int
    index: int
    frames: int = 0
    duplicates: int = 0
    truncated: int = 0                 # khung bị cắt cụt trên đường USB (đáy do bộ giải mã tô), đã loại
    torn: int = 0                      # khung có dải xé giữa ảnh (đáy nguyên), đã loại
    read_failures: int = 0
    open_error: str | None = None
    last_error: str | None = None
    last_stamp: float | None = None
    gap_max_s: float = 0.0             # khoảng dài nhất giữa hai khung tốt liên tiếp (khoảng ĐÃ ĐÓNG)
    # đầu cửa sổ đo, lúc đặt lại số đếm gần nhất; mốc của khoảng hở cuối khi camera chưa có khung tốt nào (T10)
    since: float | None = None
    recent: deque = field(default_factory=lambda: deque(maxlen=240))   # stamp các khung gần đây để tính FPS cửa sổ

    def fps(self, now: float, window_s: float = 2.0, recent: list[float] | None = None) -> float:
        stamps = [t for t in (self.recent if recent is None else recent) if now - t <= window_s]
        if len(stamps) < 2:
            return 0.0
        return (len(stamps) - 1) / max(1e-6, stamps[-1] - stamps[0])

    def age_s(self, now: float) -> float | None:
        return None if self.last_stamp is None else now - self.last_stamp


class CameraWorker(threading.Thread):
    """Một luồng cho một camera: mở nguồn, đọc liên tục, đẩy khung vào vòng đệm. Lỗi được đếm, không làm chết luồng."""

    def __init__(self, spec: CameraSpec, open_source: Callable[[CameraSpec], object], ring: int, clock=RIG_CLOCK):
        super().__init__(daemon=True, name=spec.source_id)
        self.spec, self.open_source, self.clock = spec, open_source, clock
        self.ring: deque[tuple[int, Frame]] = deque(maxlen=ring)
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.stats = CameraStats(port=spec.port, index=spec.index)
        # thời điểm tới của mọi khung MỚI của camera — khung tốt VÀ khung cắt cụt/xé (camera đã gửi một khung, nó chỉ hỏng
        # trên đường USB) — để đo nhịp camera (`frame_interval_s`) cả khi phần lớn khung hỏng. Không ghi "khung cũ"
        # (driver trả lại bộ đệm trước) hay lần đọc hỏng: đó không phải một khung mới.
        self.arrivals: deque[float] = deque(maxlen=CADENCE_FRAMES + 1)
        self.source = None
        self.seq = 0
        self.opened = threading.Event()

    def run(self) -> None:
        try:
            self.source = self.open_source(self.spec)
        except Exception as exc:  # noqa: BLE001 - lỗi mở phải hiện ra, không làm chết cả hệ
            self.stats.open_error = f"{type(exc).__name__}: {exc}"
            self.opened.set()
            return
        self.opened.set()
        try:
            while not self.stop_event.is_set():
                try:
                    frame = self.source.read()
                except FrameReadError as exc:
                    # UsbCameraSource gắn thời điểm đọc vào lỗi (`exc.t`, từ 24/09). Nguồn không gắn (nguồn giả, nguồn khác)
                    # thì lấy đồng hồ ngay khi lỗi tới, tức trễ hơn bằng thời gian nguồn kiểm khung: khoảng trước khung
                    # hỏng dài ra và khoảng sau ngắn lại đúng bằng nhau, nên chu kỳ TRUNG BÌNH không đổi.
                    t_err = getattr(exc, "t", None)
                    t_err = self.clock() if t_err is None else t_err
                    with self.lock:
                        self._count_error(str(exc), t_err)
                    continue
                except Exception as exc:  # noqa: BLE001
                    with self.lock:
                        self.stats.last_error = f"{type(exc).__name__}: {exc}"
                        self.stats.read_failures += 1
                    time.sleep(0.05)
                    continue
                with self.lock:
                    self._accept(frame)
        finally:
            try:
                self.source.close()
            except Exception:  # noqa: BLE001
                pass

    def _accept(self, frame: Frame) -> None:
        """Nhận một khung TỐT (gọi trong `self.lock`, như `_count_error`): khoảng cách tới khung tốt trước, vòng đệm, số
        đếm, stamp gần nhất, cửa sổ FPS, lần tới. Tách khỏi `run()` (T10, 02/10/2026) để test nạp khung qua đúng logic
        này mà không cần luồng hay nguồn."""
        t = frame.meta.stamp.t
        if self.stats.last_stamp is not None:
            self.stats.gap_max_s = max(self.stats.gap_max_s, t - self.stats.last_stamp)
        self.seq += 1
        self.ring.append((self.seq, frame))
        self.stats.frames += 1
        self.stats.last_stamp = t
        self.stats.recent.append(t)
        self.arrivals.append(t)

    def _count_error(self, message: str, t: float | None = None) -> None:
        """Đếm một lần đọc hỏng (gọi trong `self.lock`). Khung cắt cụt/xé là một khung MỚI đã tới ở `t`: ghi vào
        `arrivals` để nhịp camera vẫn đo đúng khi nhiều khung hỏng."""
        if "previous frame" in message:
            self.stats.duplicates += 1
        elif "truncated frame" in message:
            self.stats.truncated += 1
            if t is not None:
                self.arrivals.append(t)
        elif "torn frame" in message:
            self.stats.torn += 1
            if t is not None:
                self.arrivals.append(t)
        else:
            self.stats.read_failures += 1
            self.stats.last_error = message

    def snapshot(self) -> list[tuple[int, Frame]]:
        with self.lock:
            return list(self.ring)

    def snapshot_with_arrival(self) -> tuple[list[tuple[int, Frame]], float | None]:
        """Vòng đệm VÀ lần khung tới gần nhất (tốt hoặc cắt/xé), chụp trong CÙNG một lần giữ khóa — cho quy tắc chờ.

        Đọc lần tới riêng, sau ảnh chụp vòng đệm (bản trước, sửa 24/09): khung TỐT tới giữa hai lần đọc có trong
        `arrivals` mà không có trong ảnh chụp, và (b') của `MultiCameraManager.worth_waiting` tưởng khung đúng lượt đã
        tới mà hỏng → bỏ một camera khỏe. Tái hiện tất định bằng đồng hồ giả, và bằng luồng thật khi ép
        sys.setswitchinterval ≤ 100 µs (người kiểm tra, 24/09); tần suất trên phần cứng CHƯA ĐO."""
        with self.lock:
            return list(self.ring), (self.arrivals[-1] if self.arrivals else None)

    def last_arrival(self) -> float | None:
        """Lần khung tới gần nhất (khung tốt HOẶC khung cắt/xé), None khi chưa có lần nào. Quy tắc chờ KHÔNG dùng hàm
        này (đọc sau ảnh chụp vòng đệm là sai, xem `snapshot_with_arrival`)."""
        with self.lock:
            return self.arrivals[-1] if self.arrivals else None

    def frame_interval_s(self, n: int = CADENCE_FRAMES) -> float | None:
        """Chu kỳ khung TRUNG BÌNH của camera, đo từ n + 1 lần khung tới gần nhất (`arrivals`: khung tốt và khung
        cắt/xé). None khi chưa có 3 lần.

        Nhịp thật KHÔNG đều: ở phơi sáng tự động khoảng cách xen kẽ ≈ 31 / 48 ms, không bao giờ hai khoảng ngắn liền
        nhau, trung bình 41,9 ms (GIAI_DOAN_1_CAMERA.md mục 4.1). Bản trước coi khung nằm trên MỘT lưới chu kỳ (gốc =
        phân vị 25 %, g / round(g / gốc), trung vị): gốc rơi vào cụm 31 ms, khoảng 48 ms bị chia đôi, chu kỳ ra ≈ 24–34 ms
        (có lúc nhảy lên ≈ 47 ms), và quy tắc (b) bỏ camera KHỎE: phát lại m04 chỉ 43–78 % bộ đủ bốn camera (người kiểm
        tra, tái hiện 24/09). Cách tính bây giờ:
        (1) b = trung bình các khoảng ≤ SEED_SPAN × phân vị 25 %; (2) một bước nới: b = trung bình các khoảng
        ≤ WIDEN_SPAN × b (cụm 31 ms rung xuống 26 ms vẫn kéo cụm 48–52 ms vào); (3) lặp b = trung bình các khoảng
        ≤ SINGLE_SPAN × b tới khi đứng (khoảng gộp hai khung ≥ 76 ms của nhịp 31/48, hay 2P của nhịp đều, bị đẩy ra);
        (4) P = Σg / Σk trên các khoảng có k = max(1, round(g / b)) ≤ OUTAGE_PERIODS (đợt im dài hơn không tính), lặp ba
        lần — khoảng gộp vì khung không tới (driver bỏ hẳn, hay chỉ có khung tốt khi nguồn không báo khung hỏng) được
        tính đúng số khung. Các hệ số là lựa chọn thiết kế, kiểm bằng mô phỏng đồng hồ giả và chuỗi khoảng cách đo được
        (m04), CHƯA đo trực tiếp trên bàn thử."""
        with self.lock:                                # luồng camera ghi `arrivals` đồng thời
            arrivals = self.arrivals
            if len(arrivals) < 3:
                return None
            stamps = list(islice(reversed(arrivals), n + 1))
        gaps = [a - b for a, b in zip(stamps, stamps[1:])]          # stamps mới → cũ: a − b > 0
        base = sorted(gaps)[(len(gaps) - 1) // 4]
        if base <= 0:
            return None

        def mean_upto(cap: float) -> float:                         # luôn khác rỗng: cap ≥ base, mà base là một khoảng
            sel = [g for g in gaps if g <= cap]
            return sum(sel) / len(sel)

        b = mean_upto(WIDEN_SPAN * mean_upto(SEED_SPAN * base))
        for _ in range(8):
            nb = mean_upto(SINGLE_SPAN * b)
            if nb == b:
                break
            b = nb
        for _ in range(3):
            ks = [(g, max(1, round(g / b))) for g in gaps]
            ks = [(g, k) for g, k in ks if k <= OUTAGE_PERIODS]
            b = sum(g for g, _ in ks) / sum(k for _, k in ks)
        return b

    def reset_stats(self) -> None:
        """Đặt lại số đếm (đầu cửa sổ đo). Giữ `last_stamp`: khoảng đi qua lúc đặt lại vẫn tính đủ, như trước T10 — cả
        khoảng hở cuối `gap_end_ms` của camera ngừng trước lúc đặt lại (xem `MultiCameraManager.camera_stats`)."""
        with self.lock:
            s = self.stats
            s.frames, s.duplicates, s.truncated, s.torn, s.read_failures, s.gap_max_s = 0, 0, 0, 0, 0, 0.0
            s.since = self.clock()


@dataclass
class FrameSet:
    frames: dict[int, Frame]              # cổng → khung (chỉ các camera CÓ trong bộ)
    seqs: dict[int, int]
    anchor_t: float                       # mốc: khung mới nhất sớm nhất trong số camera có trong bộ (bật chờ, camera
    #                                       khác nhịp: chỉ trong số camera định nhịp, xem `build_set`)
    skew_s: float                         # stamp lớn nhất − nhỏ nhất trong bộ
    missing: list[int]                    # cổng bị loại vì không có khung hoặc khung quá cũ (> stale_after_s)
    t_built: float
    lagging: list[int] = field(default_factory=list)   # cổng còn khung tươi nhưng chưa có khung mới, bị bỏ sau khi chờ
    waited_s: float | None = None         # bộ thiếu camera chậm: khung mới cũ nhất đã chờ bao lâu lúc phát bộ
    # bật chờ: ngưỡng RIÊNG từng camera tươi lúc phát bộ, L_p = max(max_wait_s, 1,5 × chu kỳ của chính camera p) (xem
    # `MultiCameraManager.wait_limits_s`), và ngưỡng lớn nhất trong số đó = lâu nhất một khung mới có thể bị giữ cho bộ này
    wait_limits_s: dict[int, float] = field(default_factory=dict)
    wait_limit_s: float | None = None
    # bật chờ: cổng CÓ khung mới nhưng khung đó thuộc chu kỳ sau so với các camera còn lại → để dành cho bộ sau (sửa lệch
    # pha, xem đầu module). Khác `lagging`: camera không chậm; AI và giao diện vẫn dùng kết quả gần nhất của nó.
    deferred: list[int] = field(default_factory=list)

    @property
    def t_min(self) -> float:
        return min(f.meta.stamp.t for f in self.frames.values())

    @property
    def t_max(self) -> float:
        return max(f.meta.stamp.t for f in self.frames.values())


def build_set(rings: dict[int, list[tuple[int, Frame]]], now: float, stale_after_s: float = STALE_AFTER_S,
              anchor_ports=None) -> FrameSet | None:
    """Ghép một bộ ảnh từ vòng đệm của từng camera (hàm thuần, để test). Mốc = khung mới nhất sớm nhất trong các camera
    tươi; `anchor_ports` (chỉ quy tắc chờ dùng, khi các camera khác nhịp): chỉ lấy mốc trong các cổng này — camera "định
    nhịp", xem `pacing_ports` — các camera khác chọn khung gần mốc đó nhất. None, hay không cổng nào trong đó tươi: mọi
    camera tươi, như quy tắc cũ."""
    fresh = {port: ring for port, ring in rings.items() if ring and now - ring[-1][1].meta.stamp.t <= stale_after_s}
    missing = sorted(p for p in rings if p not in fresh)
    if not fresh:
        return None
    anchor_from = [ring for p, ring in fresh.items() if anchor_ports is None or p in anchor_ports] or list(fresh.values())
    anchor = min(ring[-1][1].meta.stamp.t for ring in anchor_from)
    frames, seqs = {}, {}
    for port, ring in fresh.items():
        seq, frame = min(ring, key=lambda item: abs(item[1].meta.stamp.t - anchor))
        frames[port], seqs[port] = frame, seq
    stamps = [f.meta.stamp.t for f in frames.values()]
    return FrameSet(frames=frames, seqs=seqs, anchor_t=anchor, skew_s=max(stamps) - min(stamps), missing=missing, t_built=now)


class MultiCameraManager:
    """Mở nhiều camera, mỗi cái một luồng; `latest_set()` trả bộ ảnh đồng bộ mới nhất."""

    def __init__(self, specs: list[CameraSpec], *, width: int = 1280, height: int = 720, fps: float = 30.0,
                 fourcc: str = "MJPG", exposure: float | None = None, ring: int = 3,
                 open_source: Callable[[CameraSpec], object] | None = None, clock=RIG_CLOCK,
                 stale_after_s: float = STALE_AFTER_S):
        if ring < 1:
            raise ValueError("ring must be >= 1")
        self.specs, self.clock, self.stale_after_s = specs, clock, stale_after_s
        self.mode = {"width": width, "height": height, "fps": fps, "fourcc": fourcc, "exposure": exposure}
        if open_source is None:
            def open_source(spec: CameraSpec):
                return UsbCameraSource(spec.index, width=width, height=height, fps=fps, fourcc=fourcc,
                                       exposure=exposure, source_id=spec.source_id, clock=clock)
        self.workers = {s.port: CameraWorker(s, open_source, ring, clock) for s in specs}
        self._lock = threading.Lock()
        self._last_seqs: dict[int, int] | None = None
        self._blocked_key: tuple | None = None
        # stamp các bộ ứng viên ĐỦ (không camera đang chờ) gần nhất, cùng thành phần, cho quy tắc (c) `out_of_phase`
        self._phase_hist: deque[dict[int, float]] = deque(maxlen=REGROUP_SETS)
        self.skews: deque[float] = deque(maxlen=200_000)
        self.waits: deque[float] = deque(maxlen=200_000)    # FrameSet.waited_s của các bộ thiếu camera chậm đã phát
        self.wait_limits: deque[float] = deque(maxlen=200_000)   # FrameSet.wait_limit_s của mọi bộ đã phát khi bật chờ
        self.reset_stats()

    def reset_stats(self) -> None:
        with self._lock:
            self.sets_built = 0
            self.sets_rejected_skew = 0
            self.sets_partial = 0
            # bộ ứng viên bị chặn vì có camera chưa có khung mới (đếm mỗi bộ một lần). Khi bật chờ: mỗi trạng thái "khung
            # mới nhất của từng camera" bị giữ lại được đếm một lần; một phần sau đó được phát thành bộ thiếu camera chậm.
            self.sets_blocked_not_new = 0
            self.sets_partial_wait = 0            # bộ đã phát thiếu camera chậm sau khi chờ (max_wait_s)
            self.lagging_per_port = {port: 0 for port in self.workers}  # số bộ đã phát mà cổng này bị bỏ vì chậm
            self.sets_regrouped = 0               # bộ đã phát sau khi để dành camera lệch pha cho bộ sau (FrameSet.deferred)
            self.frames_skipped = {port: 0 for port in self.workers}   # khung không bao giờ vào bộ nào
            self.skews.clear()
            self.waits.clear()
            self.wait_limits.clear()
        for worker in self.workers.values():
            worker.reset_stats()

    def start(self, open_timeout_s: float = 10.0, sequential: bool = True) -> None:
        """Mở từng camera lần lượt (DirectShow không thích mở song song), rồi để các luồng tự đọc."""
        for worker in self.workers.values():
            worker.start()
            if sequential:
                worker.opened.wait(open_timeout_s)

    def request_stop(self) -> None:
        for worker in self.workers.values():
            worker.stop_event.set()

    def stop(self, join_timeout_s: float = 3.0) -> list[str]:
        """Dừng mọi luồng camera trong một hạn chung; trả tên các luồng chưa dừng."""
        self.request_stop()
        deadline = time.perf_counter() + join_timeout_s
        for worker in self.workers.values():
            if worker.is_alive():
                worker.join(max(0.0, deadline - time.perf_counter()))
        return [w.name for w in self.workers.values() if w.is_alive()]

    def rings(self) -> dict[int, list[tuple[int, Frame]]]:
        return {port: (w.snapshot() if w.stats.open_error is None else []) for port, w in self.workers.items()}

    def _snapshot(self) -> tuple[dict[int, list[tuple[int, Frame]]], dict[int, float | None]]:
        """Vòng đệm và lần tới gần nhất của từng camera, mỗi camera chụp dưới CÙNG một khóa (`snapshot_with_arrival`)."""
        rings, arrivals = {}, {}
        for port, w in self.workers.items():
            rings[port], arrivals[port] = w.snapshot_with_arrival() if w.stats.open_error is None else ([], None)
        return rings, arrivals

    def latest_set(self, max_skew_s: float | None = None, require_new: bool = True,
                   max_wait_s: float | None = None) -> FrameSet | None:
        """Bộ ảnh mới nhất. `require_new`: chỉ trả khi mọi camera trong bộ đều có khung khác bộ trước (kể cả bộ bị bỏ),
        để không suy luận lại khung cũ. Bộ lệch hơn `max_skew_s` bị bỏ (đếm vào `sets_rejected_skew`).

        `max_wait_s` (None hoặc ≤ 0 = tắt, đúng quy tắc cũ): SÀN của ngưỡng chờ. Mỗi camera tươi chưa có khung mới được
        xét theo nhịp của CHÍNH nó: ngưỡng riêng L_p = max(max_wait_s, 1,5 × chu kỳ khung của camera p) (`wait_limits_s`;
        camera chưa rõ chu kỳ dùng chu kỳ của camera nhanh nhất đã rõ), và nó còn đáng chờ theo `worth_waiting`: (a) khung
        mới cũ nhất đang chờ chưa chờ quá L_p, (b) khung đúng lượt của nó chưa trễ quá P_p/2, (b') khung đúng lượt chưa tới
        mà hỏng, (b'') nó chưa treo quá 2,5 × P_p. Khi không camera nào đang chờ còn đáng chờ, bộ được phát không có chúng
        (`FrameSet.lagging`, đếm ở `sets_partial_wait` và `lagging_per_port`). Ngưỡng từng camera tươi của bộ ghi ở
        `FrameSet.wait_limits_s`, ngưỡng lớn nhất trong số đó ở `FrameSet.wait_limit_s` — xem đầu module. Vòng đệm và lần
        tới gần nhất của mỗi camera được chụp cùng một lần giữ khóa (`CameraWorker.snapshot_with_arrival`)."""
        rings, arrivals = self._snapshot()
        fs = build_set(rings, self.clock(), self.stale_after_s)
        if fs is None:
            return None
        with self._lock:
            last = self._last_seqs
            if require_new and last is not None:
                if max_wait_s is not None and max_wait_s > 0:
                    fs = self._new_frames_set(rings, fs, last, max_wait_s, arrivals)
                    if fs is None:
                        return None
                else:
                    same = [last.get(port) == seq for port, seq in fs.seqs.items()]
                    if all(same):
                        return None                     # đúng bộ trước: không camera nào có khung mới, không đếm
                    if any(same):                        # vài camera có khung mới, vài camera chưa: bộ bị chặn
                        self._count_blocked(tuple(sorted(fs.seqs.items())))
                        return None
            if last is not None:
                for port, seq in fs.seqs.items():
                    prev = last.get(port)
                    if prev is not None and seq > prev + 1:
                        self.frames_skipped[port] = self.frames_skipped.get(port, 0) + seq - prev - 1
            # camera chậm hay để dành (lagging/deferred) vẫn giữ seq đã dùng lần cuối (để khung đã dùng của nó không bị coi
            # là mới, còn khung để dành vẫn mới); camera "missing" bị xóa seq như quy tắc cũ — khung trước đợt im của nó bị
            # loại ở `_new_frames_set` bằng ngưỡng tuổi stale_after_s. Khi tắt chờ, lagging/deferred luôn rỗng: kết quả
            # đúng bằng dict(fs.seqs) (số đo cũ so được).
            kept = set(fs.lagging) | set(fs.deferred)
            seqs = {} if last is None else {p: s for p, s in last.items() if p in kept}
            seqs.update(fs.seqs)
            self._last_seqs = seqs
            self.skews.append(fs.skew_s)
            if max_skew_s is not None and fs.skew_s > max_skew_s:
                self.sets_rejected_skew += 1
                return None
            self.sets_built += 1
            if fs.wait_limit_s is not None:
                self.wait_limits.append(fs.wait_limit_s)
            if fs.deferred:
                self.sets_regrouped += 1
            if fs.missing:
                self.sets_partial += 1
            if fs.lagging:
                self.sets_partial_wait += 1
                for port in fs.lagging:
                    self.lagging_per_port[port] = self.lagging_per_port.get(port, 0) + 1
                if fs.waited_s is not None:
                    self.waits.append(fs.waited_s)
        return fs

    def _count_blocked(self, key: tuple) -> None:
        if key != self._blocked_key:
            self._blocked_key = key
            self.sets_blocked_not_new += 1

    def frame_periods(self, ports) -> dict[int, float | None]:
        """Chu kỳ khung đo được của từng cổng (None: chưa đủ 3 lần khung tới)."""
        return {p: self.workers[p].frame_interval_s() for p in ports}

    @staticmethod
    def wait_limits_s(max_wait_s: float, periods: dict[int, float | None]) -> dict[int, float]:
        """Ngưỡng chờ RIÊNG từng camera: L_p = max(max_wait_s, WAIT_PERIODS × chu kỳ khung của CHÍNH camera p).

        Camera chưa rõ chu kỳ (mới mở, < 3 lần tới) dùng ngưỡng dự phòng max(max_wait_s, WAIT_PERIODS × chu kỳ của camera
        nhanh nhất đã rõ) — đúng ngưỡng chung của bản trước, nghiêng về bỏ sớm hơn là giữ lâu; không camera nào rõ thì
        chỉ còn sàn max_wait_s. Bản trước dùng MỘT ngưỡng chung theo camera nhanh nhất cho mọi camera: đo 24/09 ở 720p,
        cổng 1 29,3 khung/s (chu kỳ 34 ms) còn cổng 2–4 23,85 khung/s (41,9 ms), và camera 24 khung/s khỏe bị bỏ ở 263 /
        855 bộ (xem đầu module)."""
        known = [iv for iv in periods.values() if iv is not None]
        fallback = max(max_wait_s, WAIT_PERIODS * min(known)) if known else max_wait_s
        return {p: fallback if iv is None else max(max_wait_s, WAIT_PERIODS * iv) for p, iv in periods.items()}

    @staticmethod
    def worth_waiting(t_last: float, t_old: float, now: float, period: float | None, limit: float,
                      t_arrival: float | None = None, t_ref: float | None = None) -> bool:
        """Camera chưa có khung mới còn đáng chờ không — xét theo nhịp của CHÍNH nó (`period`, `limit` = L_p của nó).

        (a) Khung mới cũ nhất t_old (của MỌI camera đã có khung mới) đã chờ quá L_p thì không chờ camera này nữa. (b) Chu
        kỳ chưa rõ: đáng chờ khi nó im chưa quá L_p. Đã rõ chu kỳ P: khung "đúng lượt" của nó là khung dự đoán
        slot = t_last + m·P gần mốc `t_ref` nhất (m ≥ 1, vì khung t_last đã dùng); đáng chờ khi khung đó chưa trễ quá nửa
        chu kỳ P. `t_ref` = khung mới cũ nhất của các camera đã có khung mới CÙNG NHỊP với camera này (xem
        `due_reference`); None: t_old. Với m = 1 đây đúng là "chưa có khung tốt mới trong 1,5 × chu kỳ của chính nó kể từ
        khung tốt cuối". Camera vừa lỡ MỘT khung vẫn được chờ nếu khung kế của nó sắp tới; camera treo bị bỏ khi lỡ khung
        đúng lượt quá P/2, rồi mỗi nhóm sau chỉ còn chờ nó tới hạn khung dự đoán kế + P/2 (khung tốt đầu tiên sau đợt treo
        vì thế vào đúng nhóm của nó). (b') `t_arrival` = lần tới gần nhất của camera, gồm khung cắt/xé, chụp CÙNG khóa với
        vòng đệm (`CameraWorker.snapshot_with_arrival`): nếu sau khung tốt cuối đã có một khung HỎNG tới và nó chính là
        khung đúng lượt (slot − t_arrival < P/2), khung đúng lượt đã hỏng — không chờ nữa, khỏi đợi tới slot + P/2 (đợt
        khung hỏng của cổng 1, đo 23/09: mỗi khung hỏng bớt tới P/2 ≈ 21 ms chờ). (b'') không có lần tới nào (tốt hay
        hỏng) trong STALL_PERIODS × P: treo, không chờ.

        Vì sao mốc là `t_ref`, không phải t_old (sửa 24/09, mô phỏng đồng hồ giả, CHƯA đo trên phần cứng): khi các camera
        khác nhịp, t_old thường là khung dư CHƯA dùng của camera nhanh (29,3 khung/s), tới sớm hơn nhóm của camera 24
        khung/s. Camera 24 khung/s vừa mất MỘT khung (hỏng, bị (b') bỏ ngay) bị so với đúng lượt nó VỪA lỡ ở bộ kế, nên
        bị bỏ thêm một bộ dù khung tốt kế của nó đúng hạn, rồi bị ghép trễ một chu kỳ mãi ((c) không ghép lại vì lợi
        < P/3). Cổng 1 29,3 + cổng 2–4 23,85 khung/s, cổng 4 hỏng 36 % khung theo đợt 1 s: trên lưới đều (4 hạt × 3 pha ×
        20 s) 1169 bộ bỏ cổng 4 cho 981 khung hỏng với t_old → 982 với `t_ref`; trên khoảng cách khung thật (6 hạt × 20 s)
        580 → 513 cho 481 (người kiểm tra tìm ra, tái hiện lại 24/09). Không camera nào đã có khung mới cùng nhịp (ví dụ
        camera 15 khung/s duy nhất giữa các camera 24 khung/s) thì vẫn dùng t_old như trước; mọi camera cùng nhịp thì
        t_ref = t_old, kết quả như trước. Vì t_ref ≥ t_old, mốc này chỉ làm chờ lâu hơn hoặc bằng, và (a) vẫn chặn trên
        bằng t_old thật. Còn lại (đã biết): camera cùng nhịp lệch pha ≈ P/2 so với nhóm — ghép nhóm tự nó mơ hồ — một
        khung hỏng vẫn có thể làm nó thiếu ở hai bộ.

        KHÔNG còn điều kiện "khung dự đoán tới sau t_old quá một chu kỳ của camera nhanh nhất thì thuộc nhóm sau" của bản
        trước: khi các camera khỏe có nhịp khác nhau (29,3 và 23,85 khung/s), khung đúng lượt của camera 24 khung/s thường
        tới sau khung của camera 29 khung/s hơn 34 ms, và điều kiện đó bỏ nó đi dù nó đúng nhịp (đo 24/09). Bây giờ camera
        nhanh hơn chờ camera khỏe chậm hơn; khung dư của nó không vào bộ nào (`frames_skipped`)."""
        if now - t_old > limit:
            return False
        if period is None:
            return now - t_last <= limit
        t_seen = t_last if t_arrival is None else max(t_last, t_arrival)
        if now - t_seen > STALL_PERIODS * period:
            return False                                # treo: không khung nào (tốt hay hỏng) trong 2,5 chu kỳ của nó
        ref = t_old if t_ref is None else t_ref
        slot = t_last + max(1, round((ref - t_last) / period)) * period
        if t_arrival is not None and t_arrival > t_last + 0.5 * period and slot - t_arrival < 0.5 * period:
            return False                                # (b') khung đúng lượt đã tới nhưng hỏng
        return now <= slot + 0.5 * period

    @staticmethod
    def due_reference(port: int, periods: dict[int, float | None], oldest_new: dict[int, float]) -> float | None:
        """Mốc để đoán khung "đúng lượt" của camera `port` đang chờ (tham số `t_ref` của `worth_waiting`): khung mới cũ
        nhất trong các camera ĐÃ có khung mới (`oldest_new` = {cổng: stamp khung mới cũ nhất của nó}) cùng nhịp với nó
        (chu kỳ lớn / nhỏ ≤ SAME_CADENCE, như `pacing_ports`). None — dùng t_old như trước — khi `port` chưa rõ chu kỳ
        hoặc không camera nào đã có khung mới cùng nhịp với nó."""
        P = periods.get(port)
        if P is None:
            return None
        same = [t for q, t in oldest_new.items()
                if periods.get(q) is not None and max(P, periods[q]) <= SAME_CADENCE * min(P, periods[q])]
        return min(same) if same else None

    @staticmethod
    def out_of_phase(fs: FrameSet, periods: dict[int, float | None],
                     history: list[dict[int, float]] | None = None) -> list[int]:
        """Cổng nên để dành cho bộ sau vì bộ `fs` ghép khung của hai chu kỳ khác nhau ("khóa lệch pha").

        Chỉ xét các camera "định nhịp" của bộ: camera cùng nhịp với camera CHẬM nhất trong bộ (chu kỳ ×
        SAME_CADENCE ≥ chu kỳ chậm nhất). Mọi camera trong bộ phải đã rõ chu kỳ. Độ lệch pha của từng camera định nhịp =
        trung vị, qua các bộ trong `history` ({cổng: stamp}, gồm cả bộ `fs`), của stamp camera đó trừ stamp trung bình
        của các camera định nhịp trong bộ; không có `history` thì chỉ dùng bộ `fs` (như bản đầu). Sắp theo độ lệch đó,
        tìm khe lớn nhất g: cụm cũ (trước khe) và cụm mới (sau khe). Nếu phát cụm cũ bây giờ và để cụm mới ghép với khung
        KẾ TIẾP của cụm cũ (tới sau ≈ một chu kỳ P, P = chu kỳ nhỏ nhất trong các camera định nhịp), độ lệch bộ sau
        ≈ P − g, thay vì độ lệch hiện tại S (trải của các độ lệch). Chỉ làm khi có ≥ 2 camera định nhịp,
        S − (P − g) > REGROUP_GAIN × P, và trong CHÍNH bộ `fs` mọi khung của cụm mới tới sau mọi khung của cụm cũ.
        Khi mọi camera cùng nhịp (trường hợp thường gặp) thì mọi camera đều là camera định nhịp, như bản trước.

        Vì sao chỉ xét camera định nhịp (sửa 24/09, trước đó xét cả bộ và chỉ đòi cụm cũ cùng nhịp với camera NHANH
        nhất, SAME_CADENCE = 1,25): từ khi mỗi camera được xét theo nhịp của chính nó (xem `worth_waiting`), camera khỏe
        chậm hơn không bị bỏ nữa mà định nhịp cả chuỗi; mỗi bộ nó có đúng một khung mới, nên chỉ giữa các camera này mới
        có "khóa lệch pha" bền. Camera nhanh hơn có 1–2 khung mới mỗi bộ, pha của nó so với nhóm trôi liên tục và
        `build_set` tự chọn lại khung gần mốc nhất; đưa nó vào (c) chỉ để dành oan. Mô phỏng 24/09 (đồng hồ giả, KHÔNG
        đo trên phần cứng): cổng 1 29,3 khung/s + cổng 2–4 23,85 khung/s (khoảng cách thật m02/n03; tỉ số chu kỳ
        1,19–1,40, lọt ngưỡng 1,25 cũ) → cổng 2–4 bị để dành 2–3,8 % số bộ; ba camera 24 khung/s + một camera 15 khung/s →
        camera 15 khung/s bị để dành 9–16 %; hai camera 24 + hai camera 15 khung/s mà cổng 15 khung/s thứ hai tới sau cổng
        kia 50–61 ms → nếu (c) chỉ chạy khi CẢ bộ cùng nhịp thì hai camera 15 khung/s khóa lệch pha mãi, bộ lệch > 60 ms bị
        bỏ (37 / 75 bộ trong test_two_slower_cameras_locked_out_of_phase_are_regrouped_among_themselves). Tỉ số chu kỳ
        ước lượng giữa các camera cùng nhịp: ≤ 1,04 trên khoảng cách thật (m04, m05, n03, n06, q05; có và không rung
        3 ms), ≤ 1,11 trên nhịp Markov 31/48 ms tổng hợp; giữa 29,3 và 23,85 khung/s thật: ≥ 1,19. Nên SAME_CADENCE = 1,15.

        Vì sao cần trung vị: nhịp thật xen kẽ ≈ 31/48 ms, nên stamp của hai camera cùng chu kỳ lệch nhau dao động ±8 ms
        — cỡ ngưỡng P/3 ≈ 14 ms. Quyết trên từng bộ thì (c) tách liên tục những bộ vốn đúng nhóm (phát lại nhịp m04, P
        đúng, pha 0/8/16/24 ms: 165 lần tách trong ≈ 24 s, chỉ 76 % bộ đủ bốn camera; pha 0/11/22/33: 47 lần, 92 % —
        người kiểm tra, tái hiện 24/09). Trung vị qua 5 bộ, cùng phép phát lại: 0 lần tách, 100 % bộ đủ."""
        per = {p: periods.get(p) for p in fs.frames}
        pace = pacing_ports(per)                        # None: có camera chưa rõ nhịp, không đoán được khung kế của nó
        if pace is None or len(pace) < 2:
            return []
        period = min(per[p] for p in pace)
        cur = {p: fs.frames[p].meta.stamp.t for p in pace}
        hist = [{p: h[p] for p in pace} for h in history] if history else [cur]
        offs = {p: float(np.median([h[p] - sum(h.values()) / len(h) for h in hist])) for p in cur}
        order = sorted(cur, key=lambda p: (offs[p], cur[p]))
        ts = [offs[p] for p in order]
        k = max(range(1, len(ts)), key=lambda i: ts[i] - ts[i - 1])
        gap, spread = ts[k] - ts[k - 1], ts[-1] - ts[0]
        if spread - (period - gap) <= REGROUP_GAIN * period:
            return []
        if min(cur[p] for p in order[k:]) <= max(cur[p] for p in order[:k]):
            return []                                   # bộ này rung ngược thứ tự hai cụm: chưa tách
        return sorted(order[k:])

    def _new_frames_set(self, rings: dict[int, list[tuple[int, Frame]]], fs: FrameSet, last: dict[int, int],
                        max_wait_s: float, arrivals: dict[int, float | None]) -> FrameSet | None:
        """Quy tắc chờ có giới hạn (gọi trong `self._lock`; khóa từng camera chỉ được giữ ngắn bên trong, không ai giữ
        khóa camera rồi xin khóa này). `fs` là bộ ứng viên đủ camera tươi, chỉ dùng để biết camera nào tươi và camera nào
        "missing"; bộ trả về chỉ gồm khung CHƯA vào bộ nào VÀ còn tươi (≤ stale_after_s). `arrivals` = lần tới gần nhất
        của từng camera, chụp cùng khóa với `rings` (`_snapshot`); chu kỳ khung (`frame_periods`) đọc sau đó cũng không
        sao — một lần tới thêm chỉ làm ước lượng chu kỳ chính xác hơn."""
        now = fs.t_built
        fresh = sorted(fs.frames)
        # Khung mới = chưa vào bộ nào VÀ còn tươi. Camera từng "missing" bị xóa seq khỏi _last_seqs (hoặc chưa từng có seq
        # vì đã im từ trước bộ đầu); lúc nó quay lại, vòng đệm còn khung trước đợt im, luôn cũ hơn stale_after_s. Tính
        # chúng là khung đang chờ thì `waited` đo từ khung cũ hàng trăm ms, (a) bắn ngay và bỏ một camera khỏe.
        new = {p: [item for item in rings[p]
                   if (last.get(p) is None or item[0] > last[p]) and now - item[1].meta.stamp.t <= self.stale_after_s]
               for p in fresh}
        ready = [p for p in fresh if new[p]]
        waiting = [p for p in fresh if not new[p]]
        if not ready:
            return None                                 # không camera nào có khung mới: không đếm, như quy tắc cũ
        periods = self.frame_periods(fresh)
        limits = self.wait_limits_s(max_wait_s, periods)
        oldest_new = {p: new[p][0][1].meta.stamp.t for p in ready}
        t_old = min(oldest_new.values())                            # khung mới cũ nhất đang chờ
        waited = now - t_old
        if waiting:
            # phát bộ thiếu khi KHÔNG camera nào đang chờ còn đáng chờ theo nhịp của chính nó (xem `worth_waiting`); khung
            # đúng lượt đoán theo camera cùng nhịp đã có khung mới (`due_reference`), không theo khung dư của camera nhanh
            expected = [p for p in waiting
                        if self.worth_waiting(rings[p][-1][1].meta.stamp.t, t_old, now, periods[p], limits[p],
                                              arrivals.get(p), self.due_reference(p, periods, oldest_new))]
            if expected:
                self._count_blocked(("wait",) + tuple((p, rings[p][-1][0]) for p in fresh))
                return None                             # còn trong hạn chờ
        # Camera khác nhịp: mốc lấy trong các camera định nhịp (chậm nhất, mỗi bộ đúng một khung mới); camera nhanh hơn
        # chọn khung mới gần mốc đó nhất. Lấy mốc trong mọi camera thì camera nhanh có hai khung mới hay chọn khung CŨ
        # (gần khung mới nhất sớm nhất của các camera nhanh khác) và bộ lệch tới hơn một chu kỳ của nó (mô phỏng 24/09:
        # ba camera 24 khung/s + một camera 15 khung/s, bộ lệch > 60 ms bị bỏ 11–41 lần / 20 s ở 3 trong 4 hạt).
        pace = pacing_ports({p: periods[p] for p in ready})
        anchor_ports = pace if pace is not None and len(pace) < len(ready) else None
        out = build_set({p: new[p] for p in ready}, now, self.stale_after_s, anchor_ports=anchor_ports)
        # (c) chỉ khi không camera nào đang chờ: khóa lệch pha là trạng thái ổn định của bộ ĐỦ; bộ phát vì hết hạn chờ đã
        # xáo nhóm, để dành thêm ở đó làm mất khung cũ còn chưa dùng của chính camera được để dành (mô phỏng 24/09).
        # Quyết trên REGROUP_SETS bộ ứng viên đủ liên tiếp cùng thành phần (xem `out_of_phase`). Bộ phát vì hết hạn chờ
        # KHÔNG xóa lịch sử: bộ đủ và bộ thiếu xen kẽ nhau thì (c) không bao giờ gom đủ bộ (người kiểm tra thử, 24/09).
        deferred = []
        if not waiting:
            cur = {p: f.meta.stamp.t for p, f in out.frames.items()}
            if self._phase_hist and set(self._phase_hist[-1]) != set(cur):
                self._phase_hist.clear()                # đổi thành phần bộ (camera mất / quay lại): đo lại từ đầu
            self._phase_hist.append(cur)
            if len(self._phase_hist) == REGROUP_SETS:
                deferred = self.out_of_phase(out, periods, list(self._phase_hist))
                if deferred:
                    self._phase_hist.clear()            # nhóm đã đổi: độ lệch cũ không còn đúng
        if deferred:                                    # khung mới của các cổng này để nguyên (vẫn "mới") cho bộ sau
            # cụm cũ giữ ĐÚNG khung đã chọn: ghép lại từ cả vòng đệm thì mốc đổi và camera có hai khung mới nhảy sang khung
            # mới hơn, khung cũ của nó bị bỏ qua (mô phỏng 24/09)
            out = build_set({p: [(out.seqs[p], out.frames[p])] for p in out.frames if p not in deferred}, now,
                            self.stale_after_s, anchor_ports=anchor_ports)
        out.missing, out.lagging, out.deferred = list(fs.missing), waiting, deferred
        out.waited_s = waited if waiting else None
        out.wait_limits_s = limits
        out.wait_limit_s = max(limits.values())
        return out

    def latest_frames(self) -> dict[int, Frame]:
        """Khung mới nhất của từng camera, không đồng bộ (cho hiển thị khi tắt AI)."""
        out = {}
        for port, ring in self.rings().items():
            if ring:
                out[port] = ring[-1][1]
        return out

    def camera_stats(self, t_end: float | None = None) -> list[dict]:
        """Số từng camera (rẻ: không đụng tới thống kê bộ ảnh). Dùng được 25 lần/giây từ giao diện.

        Khoảng không có khung tốt của từng camera (T10, 02/10/2026; ms). Chỉ xét khoảng ĐÓNG sau, hay còn mở lúc, lần
        đặt lại số đếm gần nhất, nhưng mỗi khoảng tính ĐỦ từ khung tốt trước nó, kể cả phần trước lúc đặt lại
        (`reset_stats` giữ `last_stamp`, như `gap_max_ms` trước T10):
        - `gap_closed_max_ms`: khoảng dài nhất giữa hai khung tốt liên tiếp — đúng nghĩa của `gap_max_ms` trước T10;
        - `gap_end_ms`: khoảng hở còn MỞ ở cuối phiên, từ khung tốt cuối (có thể trước lần đặt lại) tới `t_end`; chỉ
          camera chưa có khung tốt nào mới tính từ lần đặt lại số đếm (`CameraStats.since`). `t_end` None = bây giờ;
          muộn hơn bây giờ thì lấy bây giờ; không âm;
        - `gap_max_ms` = max(hai số trên), đại lượng của N-C2: camera ngừng hẳn trước khi hết phiên, hay không có khung
          tốt nào (kể cả camera không mở được), báo cả khoảng đó thay vì khoảng đã đóng cuối cùng hay 0.
        Vì tính đủ nên hai số có thể LỚN HƠN cả cửa sổ đo (`duration_s` của .rig.json), thêm tới cỡ phần làm nóng của
        `rig.bench`: camera ngừng trong lúc làm nóng báo `frames` 0 và `gap_end_ms` từ khung tốt cuối của nó (sửa
        docstring sau review 02/10/2026; bản trước ghi "tính từ lần đặt lại số đếm", sai với mã).
        Tệp .rig.json ghi trước T10 không có gap_end_ms và gap_max_ms của chúng = gap_closed_max_ms bây giờ. Khi phát
        lại bản ghi, `Rig` truyền `t_end` = cuối bản ghi (`ReplaySession.end_t`): hết bản ghi không phải camera ngừng."""
        now = self.clock()
        end = now if t_end is None else min(now, t_end)
        cams = []
        for port, w in self.workers.items():
            with w.lock:                               # vòng đệm stamp bị luồng camera ghi đồng thời
                s = w.stats
                recent = list(s.recent)
                start = s.last_stamp if s.last_stamp is not None else s.since
                gap_end = None if start is None else max(0.0, end - start)
                gap = s.gap_max_s if gap_end is None else max(s.gap_max_s, gap_end)
                row = {"port": port, "index": s.index, "frames": s.frames, "duplicates": s.duplicates,
                       "truncated": s.truncated, "torn": s.torn, "read_failures": s.read_failures,
                       "gap_max_ms": round(1000 * gap, 1), "gap_closed_max_ms": round(1000 * s.gap_max_s, 1),
                       "gap_end_ms": None if gap_end is None else round(1000 * gap_end, 1),
                       "open_error": s.open_error, "last_error": s.last_error}
                age = s.age_s(now)
            period = w.frame_interval_s()              # tự lấy khóa camera: gọi NGOÀI khối trên (Lock không vào lại được)
            row.update({"fps_last2s": round(s.fps(now, recent=recent), 2),
                        # chu kỳ khung đo từ 26 lần tới gần nhất (khung tốt + cắt/xé): nhịp mà quy tắc chờ xét camera này
                        "period_ms": None if period is None else round(1000 * period, 1),
                        "age_ms": None if age is None else round(1000 * age, 1),
                        "stale": age is None or age > self.stale_after_s})
            cams.append(row)
        return cams

    def stats(self, window: int | None = LIVE_WINDOW, t_end: float | None = None) -> dict:
        """Số camera + bộ ảnh. `window`: độ lệch tính trên chừng ấy bộ cuối (None = cả phiên, dùng cho tổng kết).
        `t_end`: cuối phiên cho khoảng hở cuối của từng camera (xem `camera_stats`; None = bây giờ)."""
        with self._lock:
            skews = tail(self.skews, window)
            waits = tail(self.waits, window)
            limits = tail(self.wait_limits, window)
            counts = {"sets_built": self.sets_built, "sets_rejected_skew": self.sets_rejected_skew,
                      "sets_partial": self.sets_partial, "sets_blocked_not_new": self.sets_blocked_not_new,
                      "sets_partial_wait": self.sets_partial_wait, "lagging_per_port": dict(self.lagging_per_port),
                      "sets_regrouped": self.sets_regrouped,
                      "frames_skipped": dict(self.frames_skipped)}
        return {"cameras": self.camera_stats(t_end), **counts, "skew_ms": dist(skews, 1000.0),
                "partial_wait_ms": dist(waits, 1000.0), "wait_limit_ms": dist(limits, 1000.0),
                "skew_window": "cả phiên" if window is None else f"{window} bộ cuối"}
