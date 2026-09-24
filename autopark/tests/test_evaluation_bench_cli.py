"""`python -m autopark.evaluation.bench --json <thư mục chưa có>/x.json`: thư mục được tạo trước khi chạy ca (25/09/2026).

Trước đó lệnh chạy hết mọi ca rồi mới hỏng ở bước ghi JSON (FileNotFoundError), mất kết quả."""
import json

from autopark.evaluation import bench


def test_json_into_a_missing_folder_is_created_and_written(tmp_path, capsys):
    out = tmp_path / "chưa có" / "lồng" / "ket_qua.json"
    code = bench.main(["--cases", "reverse_long_corridor", "--no-rollout", "--time-limit", "8", "--json", str(out)])
    assert code == 0 and out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert [r["name"] for r in data["results"]] == ["reverse_long_corridor"]


def test_json_path_that_cannot_be_a_folder_fails_before_any_case(tmp_path, monkeypatch, capsys):
    blocker = tmp_path / "la_tep"
    blocker.write_text("x", encoding="utf-8")                  # một TỆP đứng đúng chỗ thư mục cần tạo
    ran = []
    monkeypatch.setattr(bench, "run_case", lambda *a, **k: ran.append(a) or None)
    try:
        bench.main(["--cases", "reverse_long_corridor", "--json", str(blocker / "x.json")])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("phải thoát mã 2")
    assert ran == [] and "--json" in capsys.readouterr().err
