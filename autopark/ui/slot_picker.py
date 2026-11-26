"""Nút "Tìm ô đỗ" của cửa sổ chính (thêm 26/11/2026): tìm ô trống, vẽ lên sa bàn, bấm một ô để đặt làm đích.

Bản đồ để tìm là bản đồ LiDAR MÔ PHỎNG của sa bàn đang mở (`slot_finder.sim_map`): LiDAR ảo quét các vật cản của sa
bàn. Ở cửa sổ bàn thử LiDAR (`ui.lidar_app`), vật cản LiDAR thật đã được đưa vào sa bàn thành hộp, nên chúng cũng có
trong bản đồ này. Việc tìm chạy ở luồng nền (vài giây) và cửa sổ vẫn dùng được trong lúc đó.

Bấm một ô: đích đặt vào giữa ô theo kiểu đỗ đầu tiên (vuông góc: lùi vào; song song: song song). Bấm lại chính ô đó
để đổi kiểu đỗ (lùi vào ↔ tiến vào). Giới hạn thao tác nới theo cỡ sa bàn (`slot_finder.wide_limits`), nên ô xa hơn
0,7 m vẫn chọn được. Sau đó bấm "Tính thao tác" như thường.

Đổi xe hoặc mở kịch bản khác thì các ô cũ bị bỏ, phải tìm lại. Vật cản đổi sau lần tìm (dời hộp, vật cản LiDAR thật
cập nhật) thì ô vẫn hiện, nhưng lúc bấm chọn, xe đặt trong ô được kiểm lại với vật cản hiện tại; bị chặn thì không nhận.
"""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import copy
import math
from typing import TYPE_CHECKING

from autopark.geometry.footprint import check_pose
from autopark.planning import slot_finder as sf
from autopark.ui.items import SlotCandidateItem

if TYPE_CHECKING:
    from autopark.ui.main_window import MainWindow

MODE_LABEL = {"reverse_in": "lùi vào", "head_in": "tiến vào", "parallel": "song song"}


def scene_signature(session) -> tuple:
    """Biên sa bàn và kích thước xe: đổi một trong hai thì mọi ô cũ sai. Vật cản không có ở đây (vật cản LiDAR thật đổi
    liên tục); lúc bấm chọn, ô được kiểm lại với vật cản hiện tại."""
    sc, cfg = session.scenario, session.cfg
    return (repr(sc.bounds.to_dict()),
            (cfg.wheelbase, cfg.width, cfg.front_overhang, cfg.rear_overhang, cfg.max_steer))


def search(scenario, cfg, resolution: float = 0.02) -> list[sf.SlotCandidate]:
    """Chạy ở luồng nền: bản đồ LiDAR mô phỏng của sa bàn rồi tìm ô, xếp theo khoảng cách tới điểm xuất phát."""
    states, grid = sf.sim_map(scenario, resolution=resolution)
    return sf.find_slots(states, grid, cfg, vehicle_pose=scenario.start)


class SlotPicker:
    """Trạng thái tìm và chọn ô của một cửa sổ chính. Cửa sổ gọi `poll()` mỗi nhịp và `drop()` khi dựng lại cảnh."""

    def __init__(self, window: "MainWindow"):
        self.window = window
        self.candidates: list[sf.SlotCandidate] = []
        self.items: list[SlotCandidateItem] = []
        self.signature: tuple | None = None
        self.chosen: int | None = None
        self.mode_index = 0
        self._executor: ThreadPoolExecutor | None = None
        self._future: Future | None = None
        self._future_signature: tuple | None = None

    # ------------------------------------------------------------------ tìm
    @property
    def busy(self) -> bool:
        return self._future is not None

    def start(self) -> bool:
        """Bắt đầu tìm ô ở luồng nền. Trả False nếu đang tìm hoặc phiên không ở trạng thái chỉnh."""
        from autopark.application.session import EDITABLE_STATES

        session = self.window.session
        if self.busy or session.state not in EDITABLE_STATES:
            return False
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="slot_finder")
        self._future_signature = scene_signature(session)
        self._future = self._executor.submit(search, copy.deepcopy(session.scenario), session.cfg)
        self.window.statusBar().showMessage("Đang tìm ô đỗ trên bản đồ LiDAR mô phỏng của sa bàn…")
        return True

    def poll(self) -> bool:
        """Nhận kết quả nếu luồng nền đã xong. Trả True khi vừa nhận (thành công hay lỗi)."""
        future = self._future
        if future is None or not future.done():
            return False
        self._future = None
        try:
            cands = future.result()
        except Exception as exc:  # lỗi thuật toán phải hiện ra, không im lặng
            self.window.statusBar().showMessage(f"Lỗi tìm ô đỗ: {exc!r}", 8000)
            return True
        if self._future_signature != scene_signature(self.window.session):
            self.window.statusBar().showMessage("Sa bàn đã đổi trong lúc tìm. Bấm Tìm ô đỗ lại.", 6000)
            return True
        self.show(cands, self._future_signature)
        return True

    def wait(self, timeout: float | None = None) -> bool:
        """Chờ luồng nền xong rồi nhận kết quả (cho test và khi cần kết quả ngay)."""
        if self._future is None:
            return False
        self._future.result(timeout)
        return self.poll()

    # ------------------------------------------------------------------ vẽ, chọn
    def show(self, cands: list[sf.SlotCandidate], signature: tuple) -> None:
        self.drop()
        self.candidates = list(cands)
        self.signature = signature
        cfg = self.window.session.cfg
        for i, cand in enumerate(self.candidates):
            sl = cand.slot
            wall = "end" if cand.kind == sf.PERPENDICULAR else cand.kerb_side
            item = SlotCandidateItem(i, sl.cx, sl.cy, sl.yaw, sl.length, sl.width, unsure=cand.boundary_unknown,
                                     wall=wall, tooltip=self.describe(i, cfg), on_pick=self.pick)
            self.window.scene.addItem(item)
            self.items.append(item)
        if self.candidates:
            unsure = sum(c.boundary_unknown for c in self.candidates)
            note = f" ({unsure} ô thành chưa thấy rõ, nét đứt cam)" if unsure else ""
            self.window.statusBar().showMessage(
                f"Tìm được {len(self.candidates)} ô đỗ{note}. Bấm một ô để đặt làm đích; bấm lại để đổi kiểu đỗ.",
                15000)
        else:
            self.window.statusBar().showMessage("Không tìm thấy ô đỗ nào trên sa bàn này.", 8000)
        self.refresh()

    def describe(self, index: int, cfg=None) -> str:
        cand = self.candidates[index]
        extra = cand.slack_width_m if cand.kind == sf.PERPENDICULAR else cand.slack_length_m
        text = f"Ô {index + 1}: {sf.KIND_LABEL[cand.kind]}, khe dư {extra * 100:.0f} cm"
        if cand.distance_m is not None:
            text += f", cách xe {cand.distance_m:.2f} m"
        if cand.boundary_unknown:
            text += ". Thành chưa thấy rõ (vùng LiDAR chưa quét tới)"
        return text + ". Kiểu đỗ: " + ", ".join(MODE_LABEL.get(m.value, m.value) for m in cand.modes)

    def pick(self, index: int) -> bool:
        """Đặt đích vào ô `index`. Bấm lại cùng ô thì đổi sang kiểu đỗ kế tiếp."""
        from autopark.application.session import EDITABLE_STATES, SessionError

        window, session = self.window, self.window.session
        if session.state not in EDITABLE_STATES or not 0 <= index < len(self.candidates):
            return False
        if self.signature != scene_signature(session):
            self.drop()
            window.statusBar().showMessage("Sa bàn hoặc xe đã đổi sau lần tìm. Bấm Tìm ô đỗ lại.", 6000)
            window._refresh_mode_widgets()
            return False
        cand = self.candidates[index]
        self.mode_index = (self.mode_index + 1) % len(cand.modes) if index == self.chosen else 0
        mode = cand.modes[self.mode_index]
        goal = cand.goal_pose(session.cfg, mode, session.scenario.start.yaw)
        hit = check_pose(session.cfg, goal, session.scenario.obstacles, session.scenario.bounds)
        if not hit.ok:
            window.statusBar().showMessage(
                f"Ô {index + 1} giờ không còn trống ({hit.describe()}). Bấm Tìm ô đỗ lại.", 8000)
            return False
        current = session.scenario.maneuver
        limits = sf.wide_limits(session.scenario.bounds, max(6, current.max_cusps if current is not None else 0))
        try:
            session.set_maneuver_limits(limits)
            session.set_goal_pose(goal)
        except SessionError as exc:
            window.statusBar().showMessage(str(exc), 5000)
            return False
        self.chosen = index
        for item in self.items:
            item.set_chosen(item.index == index)
        window.scene.clearSelection()
        window._refresh_all()
        window._sync_path_items()
        distance = session.scenario.start.distance_to(goal)
        window.statusBar().showMessage(
            f"Đích: ô {index + 1} ({sf.KIND_LABEL[cand.kind]}, {MODE_LABEL.get(mode.value, mode.value)}), cách xe "
            f"{distance:.2f} m, hướng {math.degrees(goal.yaw):.0f}°. Bấm Tính thao tác."
            + (" Bấm lại ô để đổi kiểu đỗ." if len(cand.modes) > 1 else ""), 15000)
        return True

    def drop(self) -> None:
        """Bỏ các ô đang vẽ (cảnh dựng lại hay sa bàn đổi). Không hủy lần tìm đang chạy."""
        scene = self.window.scene
        for item in self.items:
            if item.scene() is scene:
                scene.removeItem(item)
        self.items = []
        self.candidates = []
        self.signature = None
        self.chosen = None
        self.mode_index = 0

    def forget_items(self) -> None:
        """Cảnh vừa bị `scene.clear()` (các item đã bị xóa cùng cảnh): chỉ quên danh sách."""
        self.items = []
        self.candidates = []
        self.signature = None
        self.chosen = None
        self.mode_index = 0

    def refresh(self) -> None:
        """Hiện ô khi đang chỉnh; lúc chạy chỉ giữ ô đang chọn. Cập nhật nút."""
        from autopark.application.session import EDITABLE_STATES

        editable = self.window.session.state in EDITABLE_STATES
        if self.items and self.signature != scene_signature(self.window.session):
            self.drop()                         # vật cản hay xe đổi: ô cũ không còn đúng
        for item in self.items:
            item.setVisible(editable or item.chosen)     # bấm khi đang chạy: pick() từ chối
        button = getattr(self.window, "find_slots_action", None)
        if button is not None:
            button.setVisible(editable)
            button.setEnabled(editable and not self.busy)
            button.setText("Đang tìm ô…" if self.busy else "Tìm ô đỗ")

    def close(self) -> None:
        if self._future is not None:
            self._future.cancel()
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None
