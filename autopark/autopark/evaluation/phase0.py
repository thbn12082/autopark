"""Sinh bằng chứng giai đoạn 0: các phiên chạy, replay, video mô phỏng."""
import argparse
import copy
import math
from pathlib import Path

from autopark.application.session import Session, SessionState
from autopark.domain.types import Bounds, Obstacle, ParkingGoal, Pose, Scenario
from autopark.geometry.footprint import body_corners
from autopark.simulation.feedback import FeedbackConfig
from autopark.storage.run_store import export_run, replay_run, write_json
from autopark.storage.scenario_store import load_scenario, load_vehicle_config


def render_video(session, directory: Path):
    import cv2
    import numpy as np
    width, height, fps = 960, 680, 20
    video = cv2.VideoWriter(str(directory / "simulation.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not video.isOpened():
        raise RuntimeError("Không mở được bộ ghi MP4")
    sc = Scenario.from_dict(session.run_snapshot["scenario"])
    scale = min((width - 80) / sc.bounds.width, (height - 120) / sc.bounds.height)

    def points(coords):
        return np.array([(int(40 + (x - sc.bounds.xmin) * scale),
                          int(height - 40 - (y - sc.bounds.ymin) * scale)) for x, y in coords], np.int32)

    rows = session.log.rows[::5]  # log 50 Hz -> video 20 FPS, thời gian nhanh gấp 2
    rows += [session.log.rows[-1]] * fps
    try:
        for row in rows:
            frame = np.full((height, width, 3), (32, 29, 24), np.uint8)
            cv2.rectangle(frame, tuple(points([(sc.bounds.xmin, sc.bounds.ymax)])[0]),
                          tuple(points([(sc.bounds.xmax, sc.bounds.ymin)])[0]), (100, 100, 100), 2)
            obstacles = list(sc.obstacles)
            for event in session.run_events:
                if event["kind"] == "obstacle" and event["t"] <= row["t"]:
                    obstacles.append(Obstacle.from_dict(event["obstacle"]))
            for obstacle in obstacles:
                cv2.fillPoly(frame, [points(obstacle.corners())], (80, 100, 150))
            trajectory = session.run_snapshot["trajectory"]["points"]
            for a, b in zip(trajectory, trajectory[1:]):
                color = (150, 210, 70) if b["direction"] > 0 else (40, 150, 240)
                line = points([(a["pose"]["x"], a["pose"]["y"]), (b["pose"]["x"], b["pose"]["y"])])
                cv2.line(frame, tuple(line[0]), tuple(line[1]), color, 2)
            goal = points(body_corners(session.cfg, sc.goal.pose))
            cv2.polylines(frame, [goal], True, (170, 210, 170), 2)
            pose = Pose(row["x"], row["y"], math.radians(row["yaw_deg"]))
            cv2.fillPoly(frame, [points(body_corners(session.cfg, pose))], (215, 195, 110))
            title = f"SIMULATION ONLY | t={row['t']:.2f}s | v={row['speed']:+.3f} m/s | 2x"
            cv2.putText(frame, title, (25, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (235, 235, 235), 1)
            event_text = next((e.code for e in session.safety_events if e.stamp.t <= row["t"]), "TRACKING")
            if row == session.log.rows[-1]:
                event_text = session.state.value
            cv2.putText(frame, event_text, (25, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 190, 240), 1)
            video.write(frame)
        cv2.imwrite(str(directory / "final_frame.png"), frame)
    finally:
        video.release()
    capture = cv2.VideoCapture(str(directory / "simulation.mp4"))
    ok, decoded = capture.read()
    count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    capture.release()
    if not ok or decoded.shape[:2] != (height, width) or count != len(rows):
        raise RuntimeError("Video không đọc lại được hoặc thiếu khung hình")
    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    cfg = load_vehicle_config(root / "configs/vehicle_default.json")
    cases = []
    for name in ("parking", "reverse", "noisy", "obstacle", "data_loss"):
        if name == "parking":
            scenario = load_scenario(root / "scenarios/bai_do_xe.json")
        else:
            reverse = name == "reverse"
            scenario = Scenario(name, Bounds(0, 0, 3, 2), Pose(2 if reverse else 0.5, 1, 0),
                                ParkingGoal(Pose(0.5 if reverse else 2, 1, 0)), seed=42)
        feedback = (FeedbackConfig(delay_s=0.04, position_std_m=0.002,
                                   yaw_std_rad=math.radians(0.2), drop_probability=0.02)
                    if name == "noisy" else FeedbackConfig())
        session = Session(copy.deepcopy(scenario), cfg, feedback_config=feedback)
        plan = session.plan_sync()
        if not plan.ok:
            raise RuntimeError(f"{name}: {plan.message}")
        session.start_run()
        injected = False
        while session.simulating:
            session.advance(0.1)
            if not injected and session.world.time >= 1 and name in ("obstacle", "data_loss"):
                if name == "obstacle":
                    session.inject_obstacle(Obstacle("new", 1.4, 1, 0.1, 0.2))
                else:
                    session.inject_data_loss()
                injected = True
        expected = SessionState.STOPPED if name in ("obstacle", "data_loss") else SessionState.COMPLETED
        if session.state != expected or session.world.collided:
            raise RuntimeError(f"{name}: {session.state}, {session.stop_reason}")
        directory = export_run(session, args.out / name)
        replay = replay_run(directory)
        assert replay.log.rows == session.log.rows
        replay.close()
        frames = render_video(session, directory)
        cases.append({"case": name, "state": session.state.value, "replay": "exact_match",
                      "position_error_m": session.report.position_error,
                      "heading_error_rad": session.report.heading_error,
                      "time_s": session.world.time, "video_frames": frames,
                      "safety_events": [e.code for e in session.safety_events]})
        session.close()
        print(f"{name}: {expected.value}; replay OK; video {frames} frames", flush=True)
    write_json(args.out / "summary.json", cases)


if __name__ == "__main__":
    main()
