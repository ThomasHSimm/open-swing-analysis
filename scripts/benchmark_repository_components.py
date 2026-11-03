#!/usr/bin/env python3
"""Execute reproducible component probes for the GitHub benchmark projects.

The third-party repositories are deliberately kept outside this repository at
``/tmp/golf-benchmark-repos``.  This script imports their code without
modifying it and writes only derived evidence under ``outputs/``.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPOS = Path("/tmp/golf-benchmark-repos")
SAMPLE = ROOT / "data" / "raw" / "golftracker_samples" / "00001.mov"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Upstream notebook functions return NumPy scalar indices.  Preserve their
    # values while making the derived evidence portable JSON.
    path.write_text(
        json.dumps(
            value,
            indent=2,
            default=lambda item: item.item() if hasattr(item, "item") else str(item),
        )
        + "\n"
    )


def run_greggjuri() -> None:
    import cv2
    import numpy as np
    import pandas as pd
    import scipy

    repo = REPOS / "greggjuri-golf-swing-analyzer"
    sys.path.insert(0, str(repo))
    from src.detection import ClubDetector, ClubTracker
    from src.pose import PoseDetector
    from src.video import KeyPositionDetector, VideoLoader

    out = ROOT / "outputs" / "greggjuri"
    out.mkdir(parents=True, exist_ok=True)

    loader = VideoLoader(str(SAMPLE))
    metadata = loader.get_metadata()
    event_detector = KeyPositionDetector(loader)
    started = time.perf_counter()
    positions = event_detector.detect_positions(downsample_factor=4)
    event_seconds = time.perf_counter() - started

    frame_indices = list(range(0, metadata.frame_count, 4))
    frames = [loader.get_frame_at(i) for i in frame_indices]
    frames = [f for f in frames if f is not None]
    motion = event_detector._calculate_motion_magnitude(frames)
    pd.DataFrame(
        {"transition_from_frame": frame_indices[: len(motion)], "motion_sum": motion}
    ).to_csv(out / "00001_motion.csv", index=False)

    detector = ClubDetector(min_line_length=40)
    tracker = ClubTracker(smoothing_window=3, max_gap_frames=5)
    club_rows = []
    errors: dict[str, int] = {}
    started = time.perf_counter()
    for frame_number in range(metadata.frame_count):
        frame = loader.get_frame_at(frame_number)
        try:
            raw = detector.detect(frame)
            tracked = tracker.update(raw)
            line = tracked.shaft_line
            head = tracked.club_head_center
            club_rows.append(
                {
                    "frame": frame_number,
                    "timestamp": frame_number / metadata.fps,
                    "shaft_detected": tracked.shaft_detected,
                    "shaft_x1": line[0] if line else np.nan,
                    "shaft_y1": line[1] if line else np.nan,
                    "shaft_x2": line[2] if line else np.nan,
                    "shaft_y2": line[3] if line else np.nan,
                    "shaft_angle": tracked.shaft_angle,
                    "club_head_detected": tracked.club_head_detected,
                    "club_head_x": head[0] if head else np.nan,
                    "club_head_y": head[1] if head else np.nan,
                    "confidence": tracked.confidence,
                }
            )
        except Exception as exc:  # preserve upstream behavior as evidence
            key = f"{type(exc).__name__}: {exc}"
            errors[key] = errors.get(key, 0) + 1
            club_rows.append(
                {
                    "frame": frame_number,
                    "timestamp": frame_number / metadata.fps,
                    "shaft_detected": False,
                    "club_head_detected": False,
                    "error": key,
                }
            )
    club_seconds = time.perf_counter() - started
    loader.release()
    club_df = pd.DataFrame(club_rows)
    club_df.to_csv(out / "00001_club_tracking.csv", index=False)

    labelled = pd.read_csv(ROOT / "outputs" / "golftracker" / "00001_frame_data.csv")
    labelled = labelled[labelled["club_source"] == "Label"].copy()
    labelled["truth_x_px"] = labelled["club_head_x"] * metadata.width
    labelled["truth_y_px"] = labelled["club_head_y"] * metadata.height
    matched = labelled[["frame", "truth_x_px", "truth_y_px"]].merge(
        club_df, on="frame", how="left"
    )
    matched["club_head_error_px"] = np.hypot(
        matched["club_head_x"] - matched["truth_x_px"],
        matched["club_head_y"] - matched["truth_y_px"],
    )
    endpoint_1_error = np.hypot(
        matched["shaft_x1"] - matched["truth_x_px"],
        matched["shaft_y1"] - matched["truth_y_px"],
    )
    endpoint_2_error = np.hypot(
        matched["shaft_x2"] - matched["truth_x_px"],
        matched["shaft_y2"] - matched["truth_y_px"],
    )
    matched["nearest_shaft_endpoint_error_px"] = np.minimum(
        endpoint_1_error, endpoint_2_error
    )
    matched.to_csv(out / "00001_manual_label_comparison.csv", index=False)

    try:
        PoseDetector()
        pose_probe = "initialized"
    except Exception as exc:
        pose_probe = f"{type(exc).__name__}: {exc}"

    summary = {
        "python": platform.python_version(),
        "opencv": cv2.__version__,
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "sample": str(SAMPLE.relative_to(ROOT)),
        "frames": metadata.frame_count,
        "fps": metadata.fps,
        "event_positions": positions,
        "event_runtime_seconds": event_seconds,
        "club_runtime_seconds": club_seconds,
        "shaft_detected_frames": int(club_df["shaft_detected"].fillna(False).sum()),
        "club_head_detected_frames": int(
            club_df["club_head_detected"].fillna(False).sum()
        ),
        "club_errors": errors,
        "manual_label_frames": len(matched),
        "club_head_available_on_manual_labels": int(
            matched["club_head_error_px"].notna().sum()
        ),
        "median_club_head_error_px": float(matched["club_head_error_px"].median()),
        "club_head_within_50px_rate": float(
            (matched["club_head_error_px"] <= 50).fillna(False).mean()
        ),
        "median_nearest_shaft_endpoint_error_px": float(
            matched["nearest_shaft_endpoint_error_px"].median()
        ),
        "shaft_endpoint_within_50px_rate": float(
            (matched["nearest_shaft_endpoint_error_px"] <= 50).fillna(False).mean()
        ),
        "pose_probe": pose_probe,
        "tracker_algorithm": "causal moving average plus last-value gap hold; no Kalman filter",
    }
    _write_json(out / "00001_summary.json", summary)
    print(json.dumps(summary, indent=2))


def _load_golfposepro_functions() -> dict:
    import cv2
    import matplotlib
    import mediapipe as mp
    import numpy as np
    from scipy.ndimage import uniform_filter1d

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    notebook = json.loads(
        (REPOS / "golfposepro" / "final_golf_swing.ipynb").read_text()
    )
    namespace = {
        "cv2": cv2,
        "mp": mp,
        "np": np,
        "uniform_filter1d": uniform_filter1d,
        "plt": plt,
    }
    # These are the upstream notebook's unmodified extraction and phase cells.
    for cell_index in (13, 18):
        source = "".join(notebook["cells"][cell_index]["source"])
        exec(
            compile(source, f"final_golf_swing.ipynb:cell-{cell_index}", "exec"),
            namespace,
        )
    return namespace


def run_golfposepro() -> None:
    import cv2
    import matplotlib.pyplot as plt
    import mediapipe as mp
    import numpy as np
    import pandas as pd

    functions = _load_golfposepro_functions()
    extract = functions["extract_pose_features_debug"]
    detect = functions["detect_swing_phases"]
    out = ROOT / "outputs" / "golfposepro"
    out.mkdir(parents=True, exist_ok=True)
    summaries = {}

    for sample_name in ("00001.mov", "00002.mov"):
        sample_path = SAMPLE.parent / sample_name
        started = time.perf_counter()
        frame_data = extract(str(sample_path))
        extraction_seconds = time.perf_counter() - started
        phase_ranges, swing_start, swing_end, raw, smoothed = detect(frame_data)
        plt.close("all")

        phase_labels = []
        for frame_number in range(len(frame_data)):
            labels = [
                name
                for name, (start, end) in phase_ranges.items()
                if start <= frame_number <= end
            ]
            phase_labels.append("|".join(labels))

        df = pd.DataFrame(frame_data)
        df["timestamp"] = df["frame_idx"] / float(
            cv2.VideoCapture(str(sample_path)).get(cv2.CAP_PROP_FPS)
        )
        df["smoothed_wrist_y"] = smoothed
        df["phase"] = phase_labels
        df.to_csv(out / f"{sample_path.stem}_wrist_phases.csv", index=False)

        duration = max(1, swing_end - swing_start)
        summaries[sample_path.stem] = {
            "frames": len(frame_data),
            "tracked_wrist_frames": int(np.isfinite(raw).sum()),
            "extraction_runtime_seconds": extraction_seconds,
            "swing_start": swing_start,
            "swing_end": swing_end,
            "phase_ranges": {k: list(v) for k, v in phase_ranges.items()},
            "normalized_phase_midpoints": {
                k: (((v[0] + v[1]) / 2) - swing_start) / duration
                for k, v in phase_ranges.items()
            },
        }

    summaries["environment"] = {
        "python": platform.python_version(),
        "opencv": cv2.__version__,
        "mediapipe": mp.__version__,
        "numpy": np.__version__,
        "source_cells": [13, 18],
    }
    _write_json(out / "summary.json", summaries)
    print(
        json.dumps(
            summaries,
            indent=2,
            default=lambda item: item.item() if hasattr(item, "item") else str(item),
        )
    )


def run_mediapipe_backend() -> None:
    import cv2
    import mediapipe as mp
    import pandas as pd

    out = ROOT / "outputs" / "pose_backends"
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(SAMPLE))
    fps = cap.get(cv2.CAP_PROP_FPS)
    rows = []
    latencies = []
    frame_number = 0
    pose = mp.solutions.pose.Pose(
        static_image_mode=False,
        model_complexity=1,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        started = time.perf_counter()
        result = pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        latencies.append(time.perf_counter() - started)
        if result.pose_landmarks:
            for landmark_number, point in enumerate(result.pose_landmarks.landmark):
                rows.append(
                    {
                        "frame": frame_number,
                        "timestamp": frame_number / fps,
                        "landmark": landmark_number,
                        "name": mp.solutions.pose.PoseLandmark(landmark_number).name,
                        "x": point.x,
                        "y": point.y,
                        "z": point.z,
                        "visibility": point.visibility,
                    }
                )
        frame_number += 1
    cap.release()
    pose.close()
    df = pd.DataFrame(rows)
    df.to_csv(out / "00001_mediapipe_landmarks.csv", index=False)
    detected = int(df["frame"].nunique()) if not df.empty else 0
    summary = {
        "backend": "MediaPipe Pose legacy solutions API",
        "mediapipe": mp.__version__,
        "opencv": cv2.__version__,
        "frames": frame_number,
        "detected_frames": detected,
        "landmarks_per_detection": 33,
        "mean_latency_seconds": sum(latencies) / len(latencies),
        "mean_visibility": float(df["visibility"].mean()),
    }
    _write_json(out / "00001_mediapipe_summary.json", summary)
    print(json.dumps(summary, indent=2))


def run_yolo_backend() -> None:
    import cv2
    import pandas as pd
    import torch
    import ultralytics
    from ultralytics import YOLO

    model_path = Path("/tmp/golf-benchmark-models/yolov8n-pose.pt")
    model = YOLO(str(model_path))
    out = ROOT / "outputs" / "pose_backends"
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(SAMPLE))
    fps = cap.get(cv2.CAP_PROP_FPS)
    rows = []
    latencies = []
    frame_number = 0
    names = [
        "nose", "left_eye", "right_eye", "left_ear", "right_ear",
        "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
        "left_wrist", "right_wrist", "left_hip", "right_hip",
        "left_knee", "right_knee", "left_ankle", "right_ankle",
    ]
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        started = time.perf_counter()
        result = model.predict(frame, imgsz=640, device="cpu", verbose=False)[0]
        latencies.append(time.perf_counter() - started)
        if result.keypoints is not None and len(result.keypoints.data):
            # The golf clips contain one primary person; retain the highest-confidence box.
            person = int(result.boxes.conf.argmax()) if len(result.boxes) > 1 else 0
            points = result.keypoints.data[person].cpu().numpy()
            box_conf = float(result.boxes.conf[person])
            for landmark_number, (x, y, confidence) in enumerate(points):
                rows.append(
                    {
                        "frame": frame_number,
                        "timestamp": frame_number / fps,
                        "landmark": landmark_number,
                        "name": names[landmark_number],
                        "x": float(x),
                        "y": float(y),
                        "confidence": float(confidence),
                        "person_box_confidence": box_conf,
                    }
                )
        frame_number += 1
    cap.release()
    df = pd.DataFrame(rows)
    df.to_csv(out / "00001_yolov8_landmarks.csv", index=False)
    detected = int(df["frame"].nunique()) if not df.empty else 0
    summary = {
        "backend": "Ultralytics YOLOv8n-pose, CPU compatibility probe",
        "ultralytics": ultralytics.__version__,
        "torch": torch.__version__,
        "opencv": cv2.__version__,
        "device": "cpu",
        "frames": frame_number,
        "detected_frames": detected,
        "landmarks_per_detection": 17,
        "mean_latency_seconds": sum(latencies) / len(latencies),
        "mean_keypoint_confidence": float(df["confidence"].mean()),
        "mean_person_box_confidence": float(df["person_box_confidence"].mean()),
        "repository_pin_result": (
            "ultralytics 8.0.20 installed, but its package lacked PoseModel and could "
            "not deserialize the official yolov8n-pose.pt; inference used the "
            "documented upgraded version above"
        ),
    }
    _write_json(out / "00001_yolov8_summary.json", summary)
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", choices=("greggjuri", "golfposepro", "mediapipe", "yolo")
    )
    args = parser.parse_args()
    {
        "greggjuri": run_greggjuri,
        "golfposepro": run_golfposepro,
        "mediapipe": run_mediapipe_backend,
        "yolo": run_yolo_backend,
    }[args.mode]()


if __name__ == "__main__":
    main()
