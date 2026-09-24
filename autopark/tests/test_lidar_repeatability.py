"""Độ lặp lại khoảng cách LiDAR (`lidar/repeatability.py`) trên bản ghi tổng hợp có nhiễu biết trước, và tái lập số
đã công bố trên bản ghi thật p07/k01 nếu có sẵn trong `runs/` (git-ignored; thiếu thì bỏ qua). Không mở thiết bị nào."""
import hashlib
import json
import math
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from autopark.domain.sensors import LidarScan, SourceStamp  # noqa: E402
from autopark.lidar import repeatability as rep  # noqa: E402
from autopark.lidar.recording import ScanRecorder, read_recording  # noqa: E402

RUNS = Path(__file__).resolve().parents[1] / "runs" / "lidar_bench"


def wrap(a):
    return (np.asarray(a, np.float64) + math.pi) % (2 * math.pi) - math.pi


def room_range(angles, shape: str, size: float) -> np.ndarray:
    """Range from a sensor at the centre of a circular room (radius `size`) or a square room (half side `size`)."""
    if shape == "circle":
        return np.full(len(angles), size)
    return size / np.maximum(np.abs(np.cos(angles)), np.abs(np.sin(angles)))


def make_recording(path, *, revolutions=80, beams=512, sigma=0.002, shape="circle", size=1.5, jitter=True,
                   nan_fraction=0.0, nan_sector_deg=None, flicker=None, bias=None, offsets_deg=None, quality=None,
                   seed=1, period=0.1, t_start=2.3, quantise=True):
    """Writes a recording the way `bench record` does. Angles decrease like the C1 (after the driver's sign flip);
    each revolution starts at a random angle offset (`jitter`) or at the same angle. Ranges are quantised to 1/4 mm
    unless `quantise=False`. `flicker=(lo_deg, hi_deg, p)`: inside that sector a beam returns only with probability p
    (flickering edge). `bias(i) -> metres` adds a per-revolution offset (motor spin-up), `offsets_deg[i]` a fixed angle
    offset, `quality(i, angles) -> uint8 array` custom qualities. Returns the list of per-revolution validity masks."""
    rng = np.random.default_rng(seed)
    masks = []
    with ScanRecorder(path, {"source_id": "c1_gia"}) as recorder:
        for i in range(revolutions):
            if offsets_deg is not None:
                offset = math.radians(offsets_deg[i])
            else:
                offset = rng.uniform(0, 2 * math.pi / beams) if jitter else 0.0
            angles = wrap(offset - 2 * math.pi * np.arange(beams) / beams)
            ranges = room_range(angles, shape, size) + rng.normal(0.0, sigma, beams) + (bias(i) if bias else 0.0)
            if quantise:
                ranges = np.round(ranges * 4000.0) / 4000.0
            valid = rng.random(beams) >= nan_fraction
            if nan_sector_deg is not None:
                lo, hi = (math.radians(v) for v in nan_sector_deg)
                valid &= ~((angles >= lo) & (angles <= hi))
            if flicker is not None:
                lo, hi = (math.radians(v) for v in flicker[:2])
                valid &= ~((angles >= lo) & (angles <= hi)) | (rng.random(beams) < flicker[2])
            ranges[~valid] = np.nan
            masks.append(valid)
            q = np.where(valid, 20, 0).astype(np.uint8) if quality is None else quality(i, angles)
            scan = LidarScan(SourceStamp("c1_gia", t_start + i * period, True, "lidar"), tuple(angles.tolist()),
                             tuple(ranges.tolist()))
            recorder.add(scan, quality=q, t_first=t_start + i * period - 0.09)
    return masks


def analyze(path, **config):
    return rep.analyze_repeatability(read_recording(path), rep.RepeatabilityConfig(**config))


# ---- ghép theo góc -------------------------------------------------------------------------------------------------
def test_nearest_by_angle_goes_round_the_zero_seam():
    reference = np.radians([0.05, 90.0, 180.0, 270.0, 359.9])
    index, offset = rep.nearest_by_angle(reference, np.radians([-0.02, 179.0, 90.3]))
    assert index.tolist() == [0, 2, 1]                                # −0.02° lies 0.07° from 0.05°, 0.08° from 359.9°
    assert np.degrees(offset) == pytest.approx([0.07, 1.0, 0.3], abs=1e-9)


def test_pairs_must_be_within_the_angle_tolerance(tmp_path):
    offsets = [0.3 * (i % 2) for i in range(20)]                     # consecutive revolutions 0.3° apart
    make_recording(tmp_path / "xen_ke", revolutions=20, jitter=False, offsets_deg=offsets)
    result, _, _ = analyze(tmp_path / "xen_ke", skip_s=0.0, tolerances_deg=(0.2, 0.4))
    tight, loose = result["consecutive"]
    assert tight["pairs"] == 0 and tight["abs_diff_mm"]["median"] is None
    assert loose["pairs"] == 19 * 512


def test_only_directly_consecutive_revolutions_are_paired(tmp_path):
    make_recording(tmp_path / "le", revolutions=6, jitter=False)
    recording, config = read_recording(tmp_path / "le"), rep.RepeatabilityConfig(skip_s=0.0)
    assert len(rep.consecutive_differences(recording, np.array([0, 2, 4]), 0.1, config)) == 0
    assert len(rep.consecutive_differences(recording, np.array([0, 1, 3, 4]), 0.1, config)) == 2 * 512


# ---- nhiễu biết trước ----------------------------------------------------------------------------------------------
def test_consecutive_differences_recover_known_noise(tmp_path):
    make_recording(tmp_path / "tron", sigma=0.002)
    result, _, first_abs = analyze(tmp_path / "tron", skip_s=0.0, tolerances_deg=(0.2,))
    row = result["consecutive"][0]
    # |N(0, 2σ²)| has median 0.6745·√2·σ = 1.91 mm and p90 1.645·√2·σ = 4.65 mm
    assert row["abs_diff_mm"]["median"] == pytest.approx(0.6745 * math.sqrt(2) * 2.0, rel=0.08)
    assert row["abs_diff_mm"]["p90"] == pytest.approx(1.645 * math.sqrt(2) * 2.0, rel=0.08)
    assert abs(row["signed_mean_mm"]) < 0.1 and len(first_abs) == row["pairs"] > 0.5 * 79 * 512
    assert result["range_step_mm"] == 0.25 and result["revolutions_used"] == 80


def test_range_step_is_reported_only_for_quarter_millimetre_data(tmp_path):
    # `range_step_mm` là bằng chứng "trung vị đi theo bậc 0,25 mm" ở GIAI_DOAN_1_LIDAR.md mục 3c
    make_recording(tmp_path / "luong_tu", revolutions=5, nan_fraction=0.2)      # NaN (không phản hồi) phải được bỏ qua
    make_recording(tmp_path / "lien_tuc", revolutions=5, quantise=False)
    assert rep.observed_range_step_mm(read_recording(tmp_path / "luong_tu")) == 0.25
    assert rep.observed_range_step_mm(read_recording(tmp_path / "lien_tuc")) is None
    result, _, _ = analyze(tmp_path / "lien_tuc", skip_s=0.0)
    assert result["range_step_mm"] is None


def test_angle_bins_remove_the_slope_of_an_oblique_wall(tmp_path):
    make_recording(tmp_path / "vuong", sigma=0.002, shape="square", size=2.5)
    result, bins, _ = analyze(tmp_path / "vuong", skip_s=0.0, bin_deg=1.0)
    stats = result["angle_bins"]
    assert stats["bins_used"] == 360
    assert stats["std_detrended_mm"]["median"] == pytest.approx(2.0, rel=0.1)
    assert stats["mad_sigma_mm"]["median"] == pytest.approx(2.0, rel=0.15)
    # without the line fit, the wall's slope inside a 1° bin is counted as noise
    assert stats["std_raw_mm"]["median"] > 1.5 * stats["std_detrended_mm"]["median"]
    corner = np.abs(np.abs(bins.centre_deg) - 45.0) < 1.0                 # steepest slope next to the corners
    assert np.nanmin(bins.std_raw_m[corner]) > 3 * 0.002


def test_no_return_beams_are_ignored_not_counted_as_zero(tmp_path):
    masks = make_recording(tmp_path / "thieu", revolutions=40, jitter=False, nan_fraction=0.3,
                           nan_sector_deg=(30.0, 60.0))
    result, bins, _ = analyze(tmp_path / "thieu", skip_s=0.0, tolerances_deg=(0.1,))
    expected_pairs = sum(int((masks[i] & masks[i - 1]).sum()) for i in range(1, 40))
    assert result["consecutive"][0]["pairs"] == expected_pairs
    assert result["consecutive"][0]["abs_diff_mm"]["median"] == pytest.approx(1.91, rel=0.1)
    in_sector = (bins.centre_deg > 31.0) & (bins.centre_deg < 59.0)
    assert in_sector.any() and not bins.used[in_sector].any() and (bins.samples[in_sector] == 0).all()
    reached = ~in_sector & (bins.beams > 0)             # fixed 0.70° beam spacing leaves some 0.5° bins empty
    assert bins.used[reached].mean() > 0.95
    assert result["angle_bins"]["std_detrended_mm"]["median"] == pytest.approx(2.0, rel=0.15)
    json.dumps(result, allow_nan=False)                                    # no NaN leaks into the JSON


# ---- quy tắc nhận ô góc (thêm sau rà soát, muộn tối 24/09/2026): số theo ô ở mục 3c phụ thuộc hai quy tắc này ------
def test_bins_where_most_beams_return_nothing_are_not_used(tmp_path):
    # 20…50°: only ~30 % of beams return (flickering edge); every bin there still has ≥ 10 samples
    make_recording(tmp_path / "chap_chon", revolutions=150, flicker=(20.0, 50.0, 0.3))
    result, bins, _ = analyze(tmp_path / "chap_chon", skip_s=0.0, tolerances_deg=(0.1,))
    inside = (bins.centre_deg > 20.5) & (bins.centre_deg < 49.5)
    assert inside.sum() == 58 and (bins.samples[inside] >= 10).all()
    assert (bins.samples[inside] < 0.5 * bins.beams[inside]).all() and not bins.used[inside].any()
    assert bins.used[~inside & (bins.beams > 0)].mean() > 0.98
    assert result["angle_bins"]["bins_used"] == int(bins.used.sum()) <= 720 - 58
    relaxed, relaxed_bins, _ = analyze(tmp_path / "chap_chon", skip_s=0.0, tolerances_deg=(0.1,),
                                       min_bin_return_fraction=0.1)
    assert relaxed_bins.used[inside].all()
    assert relaxed["angle_bins"]["bins_used"] > result["angle_bins"]["bins_used"]


def test_bins_need_at_least_min_bin_samples(tmp_path):
    # no jitter, 0.70° beam spacing: each hit 0.5° bin gets exactly one sample per revolution, all returning
    for revolutions, expected in ((9, 0), (10, 512)):
        make_recording(tmp_path / f"it_{revolutions}", revolutions=revolutions, jitter=False)
        result, bins, _ = analyze(tmp_path / f"it_{revolutions}", skip_s=0.0, tolerances_deg=(0.1,))
        assert set(bins.samples[bins.beams > 0].tolist()) == {revolutions}
        assert result["angle_bins"]["bins_used"] == expected
    loose, _, _ = analyze(tmp_path / "it_9", skip_s=0.0, tolerances_deg=(0.1,), min_bin_samples=9)
    assert loose["angle_bins"]["bins_used"] == 512


def test_range_window_and_quality_filter(tmp_path):
    def quality(i, angles):
        return np.where(angles > 0, 5, 20).astype(np.uint8)              # left half: weak returns

    make_recording(tmp_path / "loc", revolutions=30, jitter=False, quality=quality)
    all_beams, _, _ = analyze(tmp_path / "loc", skip_s=0.0, tolerances_deg=(0.1,))
    strong, _, _ = analyze(tmp_path / "loc", skip_s=0.0, tolerances_deg=(0.1,), min_quality=10)
    assert strong["consecutive"][0]["pairs"] == pytest.approx(all_beams["consecutive"][0]["pairs"] / 2, rel=0.02)
    outside, _, _ = analyze(tmp_path / "loc", skip_s=0.0, tolerances_deg=(0.1,), range_min_m=1.6)   # room is 1.5 m
    assert outside["consecutive"][0]["pairs"] == 0 and outside["angle_bins"]["bins_used"] == 0


def test_warm_up_skip_drops_the_spin_up_revolutions(tmp_path):
    # first 10 revolutions (1 s): ranges drift by up to +30 mm, like beams of a motor still spinning up
    make_recording(tmp_path / "khoi_dong", revolutions=60, bias=lambda i: 0.003 * (10 - i) if i < 10 else 0.0)
    kept, _, _ = analyze(tmp_path / "khoi_dong", skip_s=1.5)
    everything, _, _ = analyze(tmp_path / "khoi_dong", skip_s=0.0)
    assert kept["revolutions_used"] == 45 and everything["revolutions_used"] == 60
    assert kept["used_from_s"] == pytest.approx(1.5) and everything["used_from_s"] == 0.0
    assert kept["angle_bins"]["std_detrended_mm"]["median"] == pytest.approx(2.0, rel=0.15)
    assert everything["angle_bins"]["std_detrended_mm"]["median"] > 2 * kept["angle_bins"]["std_detrended_mm"]["median"]
    assert everything["consecutive"][0]["abs_diff_mm"]["p90"] > kept["consecutive"][0]["abs_diff_mm"]["p90"] + 0.3


def test_config_is_validated():
    with pytest.raises(ValueError):
        rep.RepeatabilityConfig(bin_deg=0.7)                               # 360 / 0.7 is not whole
    with pytest.raises(ValueError):
        rep.RepeatabilityConfig(range_min_m=4.0, range_max_m=0.2)
    with pytest.raises(ValueError):
        rep.RepeatabilityConfig(tolerances_deg=())


# ---- dòng lệnh -----------------------------------------------------------------------------------------------------
def test_cli_writes_json_and_png_into_a_non_ascii_directory(tmp_path, capsys):
    make_recording(tmp_path / "a", revolutions=45)
    make_recording(tmp_path / "b", revolutions=45, shape="square", size=2.0, seed=2)
    out = tmp_path / "độ lặp lại"
    code = rep.main([str(tmp_path / "a.npz"), str(tmp_path / "b.npz"), "--out", str(out), "--skip", "1",
                     "--tol", "0.1", "--tol", "0.3"])
    assert code == 0
    summary = json.loads((out / "repeatability_summary.json").read_text(encoding="utf-8"),
                         parse_constant=lambda name: pytest.fail(f"{name} in JSON"))
    assert [r["file"] for r in summary["recordings"]] == ["a.npz", "b.npz"]
    assert summary["config"]["tolerances_deg"] == [0.1, 0.3] and summary["config"]["skip_s"] == 1.0
    assert len(summary["code_sha256"]) == 64 and "--skip 1" in summary["command"]
    for stem in ("a", "b"):
        single = json.loads((out / f"{stem}.repeatability.json").read_text(encoding="utf-8"))
        assert single["revolutions_used"] == 35
        image = cv2.imdecode(np.fromfile(out / f"{stem}.repeatability.png", np.uint8), cv2.IMREAD_COLOR)
        assert image is not None and image.shape == (520, 1100, 3)
    printed = capsys.readouterr().out
    assert "a.npz: 35 vòng" in printed and "lệch góc < 0.3°" in printed


def test_cli_rejects_bad_options_and_missing_files_without_a_traceback(tmp_path, capsys):
    make_recording(tmp_path / "a", revolutions=5)
    for argv in ([str(tmp_path / "a.npz"), "--out", str(tmp_path / "o"), "--bin", "0.7"],
                 [str(tmp_path / "khong_co.npz"), "--out", str(tmp_path / "o")]):
        with pytest.raises(SystemExit) as info:
            rep.main(argv)
        assert info.value.code == 2
    err = capsys.readouterr().err
    assert "bin_deg must divide 360" in err and "không có bản ghi" in err and "Traceback" not in err


# ---- hai bản ghi trùng tên tệp, hash mã (thêm sau rà soát, muộn tối 24/09/2026) -----------------------------------
def test_cli_keeps_both_outputs_when_two_recordings_share_a_name(tmp_path, capsys):
    # như `lidar/part_0000.npz` của hai phiên bàn thử: trước đây tệp ra của bản ghi sau đè tệp của bản ghi trước
    for session in ("s1", "s2"):
        (tmp_path / session / "lidar").mkdir(parents=True)
    make_recording(tmp_path / "s1" / "lidar" / "part_0000", revolutions=45)
    make_recording(tmp_path / "s2" / "lidar" / "part_0000", revolutions=25, sigma=0.004, seed=2)
    out = tmp_path / "out"
    assert rep.main([str(tmp_path / "s1/lidar/part_0000.npz"), str(tmp_path / "s2/lidar/part_0000.npz"),
                     "--out", str(out), "--skip", "1"]) == 0
    summary = json.loads((out / "repeatability_summary.json").read_text(encoding="utf-8"))
    records = summary["recordings"]
    assert [r["file"] for r in records] == ["part_0000.npz", "part_0000.npz"]              # tên tệp giữ như cũ
    assert records[0]["path"].endswith("s1/lidar/part_0000.npz")
    assert records[1]["path"].endswith("s2/lidar/part_0000.npz")
    names = [r["outputs"]["json"] for r in records]
    assert names == ["s1__lidar__part_0000.repeatability.json", "s2__lidar__part_0000.repeatability.json"]
    singles = [json.loads((out / name).read_text(encoding="utf-8")) for name in names]
    assert [s["revolutions_used"] for s in singles] == [35, 15]
    medians = [s["consecutive"][0]["abs_diff_mm"]["median"] for s in singles]
    assert medians[1] > 1.5 * medians[0]                                  # σ 4 mm so với 2 mm: đúng số của từng bản ghi
    assert sorted(p.name for p in out.glob("*.repeatability.png")) == [
        "s1__lidar__part_0000.repeatability.png", "s2__lidar__part_0000.repeatability.png"]
    assert len(list(out.glob("*.repeatability.json"))) == 2
    printed = capsys.readouterr().out
    assert "s1/lidar/part_0000.npz: 35 vòng" in printed and "s2/lidar/part_0000.npz: 15 vòng" in printed


def test_output_stems_only_grow_for_names_that_collide(tmp_path):
    paths = [tmp_path / "r/s1/lidar/part_0000", tmp_path / "r/s2/lidar/part_0000.npz",
             tmp_path / "r/s1/lidar/part_0001"]
    assert rep.output_stems(paths) == ["s1__lidar__part_0000", "s2__lidar__part_0000", "part_0001"]
    assert rep.output_stems([tmp_path / "a", tmp_path / "b.npz"]) == ["a", "b"]           # không trùng: như trước
    assert rep.output_stems([tmp_path / "x/p", tmp_path / "y/p"]) == ["x__p", "y__p"]
    with pytest.raises(ValueError):
        rep.output_stems([tmp_path / "a.npz", tmp_path / "a"])


def test_cli_rejects_the_same_recording_given_twice(tmp_path, capsys):
    make_recording(tmp_path / "a", revolutions=5)
    with pytest.raises(SystemExit) as info:
        rep.main([str(tmp_path / "a.npz"), str(tmp_path / "a"), "--out", str(tmp_path / "o")])
    assert info.value.code == 2 and not (tmp_path / "o").exists()
    err = capsys.readouterr().err
    assert "một bản ghi được nêu hai lần" in err and "Traceback" not in err


def test_code_sha256_ignores_line_endings(tmp_path):
    # Git for Windows (core.autocrlf=true) có thể checkout cùng mã thành LF hoặc CRLF: hash phải như nhau
    lf = "a = 1\nb = 'độ lặp lại'\n".encode("utf-8")
    (tmp_path / "lf.py").write_bytes(lf)
    (tmp_path / "crlf.py").write_bytes(lf.replace(b"\n", b"\r\n"))
    expected = hashlib.sha256(lf).hexdigest()
    assert rep.code_sha256(tmp_path / "lf.py") == expected
    assert rep.code_sha256(tmp_path / "crlf.py") == expected
    assert rep.code_sha256() == hashlib.sha256(Path(rep.__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


# ---- tái lập số đã công bố (GIAI_DOAN_1_LIDAR.md mục 3b/3c) trên bản ghi thật --------------------------------------
@pytest.mark.parametrize("name, medians, per_bin", [
    ("20260922/p07_nen_phong", (1.0, 1.25), (286, 1.56, 44.8)),            # per_bin: số ô, trung vị, p90 (mm)
    ("20260924_kiem/k01_kiem_suc_khoe", (1.25, 1.5), (429, 1.39, 3.43))])
def test_published_repeatability_numbers_are_reproduced(name, medians, per_bin):
    path = RUNS / f"{name}.npz"
    if not path.exists():
        pytest.skip(f"bản ghi {name}.npz không có trong runs/ (git-ignored)")
    result, _, _ = rep.analyze_repeatability(read_recording(path))       # defaults = the published method
    got = [row["abs_diff_mm"]["median"] for row in result["consecutive"]]
    assert got == pytest.approx(list(medians), abs=0.01)                   # quarter-millimetre steps
    assert all(4.0 <= row["abs_diff_mm"]["p90"] <= 8.0 for row in result["consecutive"])
    bins_used, median_mm, p90_mm = per_bin                                # GIAI_DOAN_1_LIDAR.md mục 3c, cột theo ô
    assert result["angle_bins"]["bins_used"] == bins_used
    assert result["angle_bins"]["std_detrended_mm"]["median"] == pytest.approx(median_mm, abs=0.01)
    assert result["angle_bins"]["std_detrended_mm"]["p90"] == pytest.approx(p90_mm, abs=0.05)
