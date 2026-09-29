"""Đọc/ghi ảnh chịu được đường dẫn có dấu (29/09/2026): repo nằm ở D:\\gấp\\..., nơi cv2.imread/imwrite hỏng lặng lẽ.

Test đặt mọi tệp dưới một thư mục tên tiếng Việt trong tmp_path, vì tmp_path mặc định (%TEMP%) chỉ có ký tự ASCII nên
không bắt được lỗi này."""
import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from autopark.image_io import imread, imwrite  # noqa: E402


@pytest.fixture
def folder(tmp_path):
    path = tmp_path / "thư mục gấp"
    path.mkdir()
    return path


@pytest.mark.parametrize("name", ["anh.png", "anh.jpg"])
def test_round_trip_on_a_vietnamese_path(folder, name):
    image = np.zeros((48, 64, 3), np.uint8)
    image[10:30, 5:40] = (0, 128, 255)
    assert imwrite(folder / name, image) is True
    back = imread(folder / name)
    assert back is not None and back.shape == image.shape
    if name.endswith(".png"):
        assert np.array_equal(back, image)
    gray = imread(str(folder / name), cv2.IMREAD_GRAYSCALE)     # nhận cả chuỗi
    assert gray.shape == (48, 64)


def test_unchanged_keeps_16_bit_and_single_channel(folder):
    image = (np.arange(12, dtype=np.uint16).reshape(3, 4) * 1000)
    assert imwrite(folder / "sau.png", image)
    assert np.array_equal(imread(folder / "sau.png", cv2.IMREAD_UNCHANGED), image)


def test_failures_match_cv2(folder):
    assert imread(folder / "khong_co.png") is None
    (folder / "rong.png").write_bytes(b"")
    assert imread(folder / "rong.png") is None
    (folder / "hong.png").write_bytes(b"khong phai png")
    assert imread(folder / "hong.png") is None
    image = np.zeros((4, 4, 3), np.uint8)
    assert imwrite(folder / "khong_co_thu_muc" / "a.png", image) is False


@pytest.mark.parametrize("name, image", [("khong_duoi", np.zeros((4, 4, 3), np.uint8)),
                                         ("rong.png", np.zeros((0, 0, 3), np.uint8))])
def test_imwrite_raises_where_cv2_raises(tmp_path, folder, name, image):
    with pytest.raises(cv2.error):
        cv2.imwrite(str(tmp_path / name), image)          # đường dẫn ASCII: hành vi gốc của cv2
    with pytest.raises(cv2.error):
        imwrite(folder / name, image)


def test_callers_write_on_a_vietnamese_path(folder):
    from autopark.lidar.bench import render_placement
    from autopark.lidar.occupancy import OccupancyCounts, write_outputs
    from autopark.lidar.recording import read_recording
    from autopark.perception.costmap import GridSpec
    from tests.test_lidar_bench_map import room_scan, write_room_recording

    png = render_placement(read_recording(write_room_recording(folder / "p01")), folder / "p01.png", 1.0, 0.0)
    assert imread(png).shape == (700, 700, 3)

    counts = OccupancyCounts(GridSpec(-2.5, 2.5, -2.5, 2.5, 0.1))
    for i in range(5):
        counts.add_scan(room_scan(0.1 * i))
    write_outputs(counts, counts.states(), folder / "ban_do", source="thử", source_id="c1", t=0.0)
    assert imread(folder / "ban_do" / "map.png") is not None


def test_load_roi_on_a_vietnamese_path(folder):
    pytest.importorskip("torch")                  # perception.roi nhập perception.dataset (cần torch)
    from autopark.perception.roi import load_roi

    roi = np.zeros((6, 8), np.uint8)
    roi[2:4, 2:6] = 255
    assert imwrite(folder / "roi_FV.png", roi)
    assert np.array_equal(load_roi(folder / "roi_FV.png", (6, 8)), roi)
