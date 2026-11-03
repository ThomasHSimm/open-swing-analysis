#!/usr/bin/env python3
"""Build the original PyPI benchmark notebooks from reviewable cell sources."""

from pathlib import Path
import nbformat as nbf


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ROOT / "notebooks" / "benchmarks"
NOTEBOOKS.mkdir(parents=True, exist_ok=True)


def md(text: str):
    return nbf.v4.new_markdown_cell(text.strip())


def code(text: str):
    return nbf.v4.new_code_cell(text.strip())


def write(name: str, title: str, cells: list):
    nb = nbf.v4.new_notebook()
    nb["metadata"] = {
        "kernelspec": {"display_name": title, "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3"},
    }
    nb["cells"] = cells
    nbf.write(nb, NOTEBOOKS / name)


write(
    "01_swing_analyzer.ipynb",
    "swing-analyzer benchmark",
    [
        md("""
# `swing-analyzer` 0.1.2 benchmark

Executed against the golftracker project's `00001.mov` and `00002.mov` samples. This notebook uses the published wheel and its public Python functions; it does not implement another pose estimator. The sample clips are down-the-line, so face-on rotation metrics are deliberately treated as unreliable.

Status: package import and pose analysis work. The package's native `avc1` writer fails on this Linux host and the package does not check `VideoWriter.isOpened()`. The failure is probed below, followed by a runtime-only `mp4v` codec fallback; site-packages are not modified.
"""),
        code("""
from pathlib import Path
import ast, inspect, json, platform, sys, traceback
import importlib.metadata as md
import cv2, matplotlib.pyplot as plt, numpy as np, pandas as pd
from IPython.display import display, Markdown, Video

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "pyproject.toml").exists())
SAMPLES = ROOT / "data" / "raw" / "golftracker_samples"
OUT = ROOT / "outputs" / "swing_analyzer"
OUT.mkdir(parents=True, exist_ok=True)

from swing_analyzer import analyze
import swing_analyzer.compare as compare_mod

versions = pd.DataFrame({"value": {
    "Python": platform.python_version(),
    "swing-analyzer": md.version("swing-analyzer"),
    "MediaPipe": md.version("mediapipe"),
    "OpenCV": cv2.__version__,
    "NumPy": np.__version__,
    "SciPy": md.version("scipy"),
}})
display(versions)
print("import path:", inspect.getfile(analyze))
print("Requires-Python:", md.metadata("swing-analyzer").get("Requires-Python"))
print("Declared requirements:", md.requires("swing-analyzer"))
"""),
        md("""
## Installed source structure and algorithms

Important source locations in 0.1.2:

- `analyze.py`: `analyze_video` (line 183), `detect_phases` (431), `summarize_metrics` (609), retiming/framing/report helpers.
- `core.py`: drawing geometry and `PoseTracker`, which wraps legacy `mediapipe.solutions.pose.Pose` with complexity 1, detection confidence 0.5, tracking confidence 0.5.
- `compare.py`: runs the analyzer twice, phase-warps videos, and diffs only the summary dictionaries.
- `full.py`: coaching-style fault rules and two-view reporting.

The analyzer retains only selected derived frame fields—not all 33 landmarks and not landmark visibility. Metrics use raw landmark positions; the skeleton drawing is EMA-smoothed (`POSE_EMA=0.5`), the wrist tracer uses an EMA (`0.6`) plus a five-point moving-average polyline, and phase detection smooths wrist height with a three-frame box filter.
"""),
        code("""
package_dir = Path(inspect.getfile(analyze)).parent
rows = []
for path in sorted(package_dir.glob("*.py")):
    tree = ast.parse(path.read_text())
    defs = [f"{n.name}:{n.lineno}" for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
    rows.append({"file": path.name, "lines": len(path.read_text().splitlines()), "top-level definitions": ", ".join(defs)})
display(pd.DataFrame(rows))
"""),
        md("""
## Native output-codec failure, then documented fallback

`VIDEO_FOURCC` is hard-coded to `avc1`. OpenCV can read the input but this host has no usable H.264 encoder. The package writes no file and raises no exception because it never checks whether the writer opened.
"""),
        code("""
probe_path = OUT / "codec_probe.mp4"
probe = cv2.VideoWriter(str(probe_path), cv2.VideoWriter_fourcc(*analyze.VIDEO_FOURCC), 30, (432, 768))
native_codec_opened = probe.isOpened()
probe.release()
if probe_path.exists():
    probe_path.unlink()
print({"package_codec": analyze.VIDEO_FOURCC, "VideoWriter.isOpened": native_codec_opened})

# Runtime-only fallback; the installed package remains untouched.
analyze.OUTPUT_DIR = str(OUT)
compare_mod.OUTPUT_DIR = str(OUT)
analyze.VIDEO_FOURCC = "mp4v"
video_a = SAMPLES / "00001.mov"
out_path, frames_data, fps = analyze.analyze_video(str(video_a), view_type="dtl")
phases = analyze.detect_phases(frames_data, fps)
summary = analyze.summarize_metrics(frames_data, phases)
flags = analyze.flag_issues(summary, view_type="dtl")
print("annotated output:", out_path, Path(out_path).exists(), Path(out_path).stat().st_size)
print("frames / tracked frames / fps:", len(frames_data), sum("wrist_x" in x for x in frames_data), fps)
display(pd.Series(phases, name="frame").to_frame())
display(pd.Series(summary, name="value").to_frame())
print(*flags, sep="\\n")
"""),
        md("""
## What the events actually mean

- **Address** is the first frame with a detected pose, not a learned or biomechanical address detector.
- **Top** is the first prominent minimum of smoothed wrist `y` (hands high), with a threshold/plateau fallback.
- **Impact** is the first prominent wrist-`y` maximum after top (hands low), with velocity/return-height fallbacks. There is no ball contact observation.
- **Release** is fixed at about 0.12 seconds after estimated impact.
- **Finish** is the last tracked frame, not a finish-pose detector.

Thus frame numbers are reproducible heuristic events, not ground-truth impact labels. The swing-plane overlay is a fixed line through the address hands at a default 54° shaft angle; it is not a detected shaft or club path.
"""),
        code("""
scalar_rows = [{k: v for k, v in row.items() if not isinstance(v, tuple)} for row in frames_data]
frame_df = pd.DataFrame(scalar_rows)
frame_df.to_csv(OUT / "00001_frame_metrics.csv", index=False)

fig, axes = plt.subplots(2, 2, figsize=(12, 8))
axes[0,0].plot(frame_df.wrist_x, frame_df.wrist_y)
axes[0,0].invert_yaxis(); axes[0,0].set(title="Wrist-mid 2D trajectory", xlabel="normalized x", ylabel="normalized y")
axes[0,1].plot(frame_df.frame, frame_df.wrist_y, label="wrist y")
axes[1,0].plot(frame_df.frame, frame_df.spine_angle, label="spine angle")
axes[1,1].plot(frame_df.frame, frame_df.wrist_x.notna().astype(int)); axes[1,1].set_ylim(-0.05, 1.05)
axes[1,1].set(title="Pose available (confidence is not retained)", xlabel="frame", ylabel="available")
for ax in (axes[0,1], axes[1,0]):
    for label, frame in phases.items():
        ax.axvline(frame, alpha=.25, label=label.replace("_frame", ""))
axes[0,1].invert_yaxis(); axes[0,1].set(title="Wrist height and heuristic events", xlabel="frame")
axes[1,0].set(title="Derived spine-angle trace", xlabel="frame", ylabel="degrees")
axes[0,1].legend(fontsize=7, ncol=2)
fig.tight_layout(); fig.savefig(OUT / "00001_diagnostics.png", dpi=140)
plt.show()
"""),
        code("""
cap = cv2.VideoCapture(str(out_path))
key_names = ["address_frame", "top_of_backswing_frame", "impact_frame", "finish_frame"]
fig, axes = plt.subplots(1, 4, figsize=(16, 5))
for ax, name in zip(axes, key_names):
    idx = phases[name]
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ok, frame = cap.read()
    if ok:
        ax.imshow(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    ax.set_title(f"{name.replace('_frame','').replace('_',' ')}\\nframe {idx}")
    ax.axis("off")
cap.release(); fig.tight_layout(); fig.savefig(OUT / "00001_key_frames.png", dpi=140)
plt.show()
"""),
        md("""
## Genuine measurements versus instructional heuristics
"""),
        code("""
classification = pd.DataFrame([
    ("wrist/head/joint normalized coordinates", "MediaPipe-derived measurement", "2D image coordinates; selected points only"),
    ("spine and projected shoulder/hip line angles", "derived geometry", "projection-sensitive; not 3D rotation"),
    ("head sway / head vertical / ankle change", "derived geometry", "normalized image displacement"),
    ("top and impact frames", "signal heuristic", "wrist-height peaks/fallbacks; no club or ball evidence"),
    ("address and finish frames", "clip-boundary heuristic", "first and last tracked frames"),
    ("swing-plane line", "instructional proxy", "hands anchor plus default/manual shaft angle"),
    ("TARGETS and flags", "coaching heuristic", "hard-coded generic ranges, not validated personal norms"),
], columns=["output", "type", "interpretation"])
display(classification)
"""),
        md("""
## Package comparison mode

This executes the package's own `compare()` path on two supplied DTL clips with baked framing disabled to avoid a second pose pass. It still re-analyzes both clips, writes annotated videos, phase-warps a side-by-side video, and writes a summary-difference report. Any exception is printed with its traceback.
"""),
        code("""
comparison = None
try:
    comparison = compare_mod.compare(
        str(SAMPLES / "00001.mov"), str(SAMPLES / "00002.mov"),
        label_a="Sample 00001", label_b="Sample 00002", view_type="dtl",
        bake_framing=False,
    )
    display(pd.DataFrame({"00001": comparison["summary_a"], "00002": comparison["summary_b"]}))
    print({k: (v, Path(v).exists()) for k, v in comparison.items() if k in {"out_a", "out_b", "side_by_side", "report"}})
except Exception:
    traceback.print_exc()
"""),
        md("""
## Assessment

Strengths: recent packaging; simple callable API; automatic body pose; transparent phase heuristics; usable selected frame-level traces; annotations; basic two-swing synchronization and metric differencing.

Weaknesses for this project: no club, shaft, clubhead, ball, raw 33-landmark export, visibility/confidence export, robust event model, calibrated 3D biomechanics, collection-level consistency model, or anomaly/outcome workflow. Address/finish are clip boundaries, impact is inferred from hands, coaching thresholds are unvalidated generic rules, and the output writer can fail silently.
"""),
        code("""
print("EXECUTED_OK: swing-analyzer notebook reached the final cell")
"""),
    ],
)


write(
    "02_golftracker.ipynb",
    "golftracker benchmark",
    [
        md("""
# `golftracker` 2.0 benchmark

This notebook reviews the published 2.0 wheel, the installed site-packages source, the project's supplied video/JSON/pickle trio, and a real MediaPipe run. `golftracker` is a frame-level data capture concept, but the published wheel is not reproducibly installable as declared.

Observed native install blockers:

1. `mediapipe==0.8.10` has no matching distribution on this Python 3.9/Linux index.
2. Current pip rejects the malformed `tune_line_det = scripts.tune_line_det` entry point (no callable suffix).
3. The wheel omits the `scripts` package targeted by every CLI wrapper.

For library evaluation only, the unmodified wheel contents were installed with MediaPipe 0.10.14 (same legacy `mp.solutions` API), protobuf 4.25.9, OpenCV contrib 4.11, and NumPy 1.26.4. This override is not claimed to satisfy the package metadata.
"""),
        code("""
from pathlib import Path
from collections import Counter
import ast, inspect, json, os, platform, subprocess, sys
import importlib.metadata as md
import cv2, matplotlib.pyplot as plt, numpy as np, pandas as pd
from IPython.display import display

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "pyproject.toml").exists())
SAMPLES = ROOT / "data" / "raw" / "golftracker_samples"
OUT = ROOT / "outputs" / "golftracker"
OUT.mkdir(parents=True, exist_ok=True)

import golftracker
from golftracker import (club_head_detector, club_head_params, golf_swing_factory,
                         golf_swing_repository, gt_const, media_pipe_operation,
                         video_utils)

versions = pd.DataFrame({"value": {
    "Python": platform.python_version(), "golftracker": md.version("golftracker"),
    "declared MediaPipe": "0.8.10 (unavailable)", "tested MediaPipe": md.version("mediapipe"),
    "declared protobuf": "3.20.0", "tested protobuf": md.version("protobuf"),
    "OpenCV": cv2.__version__, "NumPy": np.__version__, "pandas": pd.__version__,
    "scikit-learn": md.version("scikit-learn"),
}})
display(versions)
print("import path:", inspect.getfile(golftracker))
print("declared requirements:", md.requires("golftracker"))
"""),
        md("""
## Installed source structure and processing architecture

The wheel's importable `golftracker/` package is present, but `scripts/` is absent. Data flow in the intended repository workflow is:

`video -> all frames in RAM -> MediaPipe landmarks -> optional sklearn pose classifier -> pickle -> GUI pose/club labels -> straight-line club interpolation -> JSON -> golftrainer`

Key implementation details:

- `media_pipe_operation.run`: creates and destroys a MediaPipe `Pose` object **inside every frame iteration**. Despite `static_image_mode=False`, temporal tracker state is discarded. It enables segmentation but discards the mask.
- `pose_model.PoseModel`: classifies each 132-value landmark row with a supplied sklearn model and accepts maximum class probability above 0.7. No temporal smoothing/state machine is used.
- `club_head_detector.ClubHeadDetector`: copies manual labels and linearly interpolates missing frames between adjacent labels. It is not an OpenCV tracker.
- Canny/Hough modules exist, but are tuning experiments and are not connected to `ClubHeadDetector.run`.
- The JSON/pickle model retains 33 `(x,y,z,visibility)` pose landmarks per frame, pose labels, and one club-head `(x,y,source)` per frame. There is no ball field or shaft endpoints.
"""),
        code("""
package_dir = Path(inspect.getfile(golftracker)).parent
rows=[]
for path in sorted(package_dir.glob("*.py")):
    tree=ast.parse(path.read_text())
    defs=[f"{n.name}:{n.lineno}" for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))]
    rows.append((path.name,len(path.read_text().splitlines()),", ".join(defs)))
display(pd.DataFrame(rows,columns=["file","lines","definitions"]))
"""),
        md("""
## Published CLI failure

The wrapper exists because pip partially generated it, but importing its target fails because the wheel contains no `scripts` package.
"""),
        code("""
cli = ROOT / "envs" / "golftracker" / "bin" / "create_swing_db"
probe = subprocess.run([str(cli), "--help"], text=True, capture_output=True)
print("return code:", probe.returncode)
print(probe.stdout)
print(probe.stderr)
"""),
        md("""
## Automatic MediaPipe path

During preparation, the complete 136-frame `00001.mov` was run through `video_utils.split_video_to_frames(..., scale=50)` and `golf_swing_factory.create_from_video` with no pose model and no club labels. All 136 frames received landmarks in 10.96 seconds. The package-generated JSON is checked below. It naturally contains only MediaPipe output: every golf pose remains `Unknown` and every club point remains invalid.

The implementation emits two MediaPipe model-initialization warnings per frame because it reopens the model every iteration; this is a substantial performance/design defect.
"""),
        code("""
auto_path = OUT / "00001_auto_50pct.json"
auto = json.loads(auto_path.read_text())
auto_rows = auto["mp_result"]
print({
    "file": str(auto_path.relative_to(ROOT)), "frames": auto["num_frames"],
    "landmark_success": sum(bool(x) for x in auto_rows),
    "landmark_failures": sum(not bool(x) for x in auto_rows),
    "pose_values": sorted(set(auto["pose_result"]["poses"])),
    "valid_club_points": sum(x is not None for x in auto["club_head_result"]["norm_points"]),
    "top_level_keys": list(auto),
})

# Execute the actual automatic detector on a short slice in this notebook too.
frames, short_spec = video_utils.split_video_to_frames(str(SAMPLES / "00001.mov"), scale=50, rotate=0)
short_landmarks = media_pipe_operation.run(frames[:8])
print("live 8-frame MediaPipe success:", sum(bool(x) for x in short_landmarks), "/", len(short_landmarks))
"""),
        md("""
## Supplied pre-labelled pickle: body, phases and club path

The project's own `00001.pkl` loads successfully when its matching video is searchable. This is the strongest artifact in the three-package set for the eventual project's raw-data requirement: frame-level pose coordinates, visibility, coarse phase classes, and labelled/interpolated club-head coordinates are internally available.
"""),
        code("""
gs = golf_swing_repository.reconstitute(str(SAMPLES / "00001.pkl"), [str(SAMPLES)])
print(gs.video_spec)
print(gs.pose_result)
print(gs.club_head_result)

raw = gs.mp_result.serialize()
cols = gt_const.mp_landmark_row_header()
pose_df = pd.DataFrame([row if row else [np.nan]*len(cols) for row in raw], columns=cols)
pose_df.insert(0, "frame", np.arange(len(pose_df)))
pose_df.insert(1, "timestamp", pose_df.frame / gs.video_spec.fps)
pose_df["phase"] = [p.name for p in gs.pose_result.poses]
pose_df["club_head_x"] = [p[0] if p else np.nan for p in gs.club_head_result.norm_points]
pose_df["club_head_y"] = [p[1] if p else np.nan for p in gs.club_head_result.norm_points]
pose_df["club_source"] = gs.club_head_result.algos
pose_df.to_csv(OUT / "00001_frame_data.csv", index=False)
display(pose_df.head())
display(pd.DataFrame({"phase": Counter(pose_df.phase), "club source": Counter(pose_df.club_source)}).fillna(0).astype(int))
"""),
        code("""
pose_df["wrist_x"] = pose_df[["left_wrist_x","right_wrist_x"]].mean(axis=1)
pose_df["wrist_y"] = pose_df[["left_wrist_y","right_wrist_y"]].mean(axis=1)
pose_df["hip_x"] = pose_df[["left_hip_x","right_hip_x"]].mean(axis=1)
pose_df["hip_y"] = pose_df[["left_hip_y","right_hip_y"]].mean(axis=1)
pose_df["shoulder_x"] = pose_df[["left_shoulder_x","right_shoulder_x"]].mean(axis=1)
pose_df["shoulder_y"] = pose_df[["left_shoulder_y","right_shoulder_y"]].mean(axis=1)
pose_df["mean_visibility"] = pose_df[[c for c in cols if c.endswith("_v")]].mean(axis=1)

fig, axes = plt.subplots(2,2,figsize=(12,9))
for x,y,label in [("wrist_x","wrist_y","wrist mid"),("hip_x","hip_y","hip centre"),("shoulder_x","shoulder_y","shoulder centre"),("club_head_x","club_head_y","club head")]:
    axes[0,0].plot(pose_df[x],pose_df[y],label=label)
axes[0,0].invert_yaxis(); axes[0,0].legend(); axes[0,0].set_title("Normalized trajectories")
axes[0,1].plot(pose_df.frame,pose_df.wrist_y,label="wrist y"); axes[0,1].plot(pose_df.frame,pose_df.club_head_y,label="club y")
axes[0,1].invert_yaxis(); axes[0,1].legend(); axes[0,1].set_title("Body/club height by frame")
axes[1,0].plot(pose_df.frame,pose_df.mean_visibility); axes[1,0].set_ylim(0,1.05); axes[1,0].set_title("Mean MediaPipe visibility")
phase_codes=pd.Categorical(pose_df.phase,categories=["RhStart","RhTop","RhFinish","Unknown"]).codes
axes[1,1].step(pose_df.frame,phase_codes,where="mid"); axes[1,1].set_yticks(range(4),["RhStart","RhTop","RhFinish","Unknown"]); axes[1,1].set_title("Stored pose class per frame")
for ax in axes.flat: ax.set_xlabel("frame" if ax is not axes[0,0] else "normalized x")
fig.tight_layout(); fig.savefig(OUT/"00001_trajectories.png",dpi=140)
plt.show()
"""),
        md("""
## Club tracking: what really happens

The supplied club points are 24 manual `Label` positions plus 72 `LinearFit` positions and 40 `Invalid` positions. Interpolation is straight in image space and only fills gaps bracketed by labels. It has no motion model, confidence, optical flow, appearance model, automatic initialization, or correction audit beyond the `algo` string.

The package draws a line from MediaPipe's right thumb to the club-head point. That drawn segment is not a detected shaft. The current schema has no ball coordinate. Earlier documentation mentions OpenCV trackers and ball/heel/toe/grip concepts, but those are not implemented in the published 2.0 data model reviewed here.
"""),
        code("""
params = club_head_params.ClubHeadParams()
params.club_head_points_dict = {0:(0.20,0.80), 10:(0.40,0.30)}
demo = club_head_detector.ClubHeadDetector(params).run(gs)
display(pd.DataFrame({"frame":range(11),"point":demo.norm_points[:11],"source":demo.algos[:11]}))
"""),
        code("""
cap = cv2.VideoCapture(str(SAMPLES/"00001.mov"))
key_indices = {
    "start": gs.pose_result.get_first_start_pose_frame_idx(),
    "top": next(i for i,p in enumerate(gs.pose_result.poses) if p.name=="RhTop"),
    "finish": gs.pose_result.get_last_finish_pose_frame_idx(),
}
fig,axes=plt.subplots(1,3,figsize=(12,6))
for ax,(name,idx) in zip(axes,key_indices.items()):
    cap.set(cv2.CAP_PROP_POS_FRAMES,idx); ok,frame=cap.read()
    if ok:
        gs.draw_frame(idx,frame)
        ax.imshow(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
    ax.set_title(f"stored {name} class, frame {idx}"); ax.axis("off")
cap.release(); fig.tight_layout(); fig.savefig(OUT/"00001_labelled_key_frames.png",dpi=140)
plt.show()
"""),
        md("""
## Export and compatibility findings

`GolfSwing.to_json` in 2.0 emits a raw `mp_result` list and no top-level `version`. `golftrainer` 1.0.2 expects `version` plus `mp_result={landmarks,norm_points}`. Therefore the currently published producer and consumer do not interoperate directly. Only supplied `00001.json` has the consumer's required schema; samples 00002–00004 omit `version`.

Strengths: best continuous raw-data retention here; 33 landmarks with `z` and visibility; pickle/JSON concepts; manual provenance for club points; useful geometry/path utilities.

Weaknesses: broken wheel/CLIs and unreproducible pin; all frames held in RAM; model recreated per frame; unsafe/version-fragile pickle; tiny, opaque pose model with no temporal logic; manual phases/club labelling; straight-line club interpolation; no ball/shaft; producer-consumer schema drift.
"""),
        code("""
print("EXECUTED_OK: golftracker notebook reached the final cell")
"""),
    ],
)


write(
    "03_golftrainer.ipynb",
    "golftrainer benchmark",
    [
        md("""
# `golftrainer` 1.0.2 benchmark

The published package is much smaller than its description suggests. The wheel contains only dataclasses, a JSON factory, and coordinate-to-DataFrame conversion. It contains **no analysis metrics, phase detector, geometry module, plots, scoring, thresholds, or coaching interpretations**. Repository-only modules must not be mistaken for installed 1.0.2 functionality.
"""),
        code("""
from pathlib import Path
from collections import Counter
import inspect, json, platform, subprocess
import importlib.metadata as md
import matplotlib.pyplot as plt, numpy as np, pandas as pd
from IPython.display import display

ROOT=next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "pyproject.toml").exists())
SAMPLES=ROOT/"data"/"raw"/"golftracker_samples"
OUT=ROOT/"outputs"/"golftrainer"; OUT.mkdir(parents=True,exist_ok=True)

import golftrainer
from golftrainer import factory, golf_data

display(pd.DataFrame({"value":{
    "Python":platform.python_version(), "golftrainer":md.version("golftrainer"),
    "pandas":pd.__version__, "NumPy":np.__version__,
    "MediaPipe":"not a dependency", "OpenCV":"not a dependency",
}}))
print("import path:",inspect.getfile(golftrainer))
print("requirements:",md.requires("golftrainer"))
"""),
        md("""
## Installed source and CLI

The wheel contains `__init__.py`, `__version__.py`, `factory.py`, and `golf_data.py`. The advertised `golf_trainer` wrapper targets an omitted `scripts.golf_trainer`, so it fails. Public `GolfData` methods only name columns and return normalized, screen-origin, or Cartesian-origin DataFrames.
"""),
        code("""
package_dir=Path(inspect.getfile(golftrainer)).parent
rows=[]
for p in sorted(package_dir.glob("*.py")):
    rows.append({"file":p.name,"lines":len(p.read_text().splitlines()),"functions/classes":[n for n,v in inspect.getmembers(__import__(f"golftrainer.{p.stem}",fromlist=[p.stem])) if inspect.isfunction(v) or inspect.isclass(v)]})
display(pd.DataFrame(rows))
print("GolfData methods:",[n for n,v in inspect.getmembers(golf_data.GolfData,inspect.isfunction) if not n.startswith("__")])

cli=ROOT/"envs"/"golftrainer"/"bin"/"golf_trainer"
probe=subprocess.run([str(cli),"--help"],text=True,capture_output=True)
print("CLI return code:",probe.returncode); print(probe.stderr)
"""),
        md("""
## Expected JSON schema and real compatibility

The factory requires these exact fields:

- `version`
- `video_spec`: height, width, num_frames, fps, scale, rotate
- `video_input`: fname, size
- `num_frames`
- `pose_result`: poses, handed
- `club_head_result`: norm_points, algos
- `mp_result`: landmarks, norm_points

Only supplied `00001.json` satisfies it. The other supplied exports and a fresh `golftracker` 2.0 export fail at `version` before their deeper `mp_result` incompatibility is reached.
"""),
        code("""
def shape_tree(obj):
    if isinstance(obj,dict): return {k:shape_tree(v) for k,v in obj.items()}
    if isinstance(obj,list): return f"list[{len(obj)}]" + (f" of {shape_tree(obj[0])}" if obj else "")
    return type(obj).__name__

payload=json.loads((SAMPLES/"00001.json").read_text())
display(shape_tree(payload))
gd=factory.create_golf_data(str(SAMPLES/"00001.json"))
print(gd)

failures=[]
for name in ["00002.json","00003.json","00004.json"]:
    try: factory.create_golf_data(str(SAMPLES/name))
    except Exception as exc: failures.append((name,type(exc).__name__,str(exc)))
display(pd.DataFrame(failures,columns=["input","error","message"]))
"""),
        md("""
## Outputs actually generated by 1.0.2

`mp_data_frame()` returns 132 columns: all 33 MediaPipe landmarks times `(x,y,z,visibility)`. `norm_data_frame()` keeps pose `(x,y)` and appends club-head `(x,y)`, replacing missing club points with `(0,0)`. `screen_data_frame()` scales normalized points to top-left-origin pixels; `cart_data_frame()` also flips `y` to bottom-left origin.

There are no packaged formulas for tempo, angles, swing phases, key positions, or coaching scores. Stored pose labels and `club_source` values are inputs passed through from golftracker, not golftrainer-derived features.
"""),
        code("""
mp=gd.mp_data_frame(); norm=gd.norm_data_frame(); screen=gd.screen_data_frame(); cart=gd.cart_data_frame()
print("mp",mp.shape,"norm",norm.shape,"screen",screen.shape,"cart",cart.shape)
display(norm.head())
display(pd.DataFrame({"pose":Counter(gd.pose_result.poses),"club source":Counter(gd.club_head_result.algos)}).fillna(0).astype(int))
norm.assign(frame=np.arange(len(norm)),timestamp=np.arange(len(norm))/gd.video_spec.fps).to_csv(OUT/"00001_golftrainer_table.csv",index=False)
"""),
        md("""
## Independent diagnostics from package-exposed coordinates

The plots below are our diagnostics over `GolfData` tables, not metrics claimed by golftrainer. They demonstrate that its useful reusable component is coordinate/schema access. No new pose estimator is run.
"""),
        code("""
df=norm.copy(); df["frame"]=np.arange(len(df)); df["timestamp"]=df.frame/gd.video_spec.fps
for part in ["wrist","hip","shoulder"]:
    df[f"{part}_x"]=df[[f"left_{part}_x",f"right_{part}_x"]].mean(axis=1)
    df[f"{part}_y"]=df[[f"left_{part}_y",f"right_{part}_y"]].mean(axis=1)

def joint_angle(ax,ay,bx,by,cx,cy):
    a=np.column_stack([ax-bx,ay-by]); c=np.column_stack([cx-bx,cy-by])
    den=np.linalg.norm(a,axis=1)*np.linalg.norm(c,axis=1)
    cosine=np.divide((a*c).sum(axis=1),den,out=np.full(len(den),np.nan),where=den!=0)
    return np.degrees(np.arccos(np.clip(cosine,-1,1)))

df["left_elbow_angle_diag"]=joint_angle(df.left_shoulder_x,df.left_shoulder_y,df.left_elbow_x,df.left_elbow_y,df.left_wrist_x,df.left_wrist_y)
fig,axes=plt.subplots(2,2,figsize=(12,9))
for part in ["wrist","hip","shoulder"]: axes[0,0].plot(df[f"{part}_x"],df[f"{part}_y"],label=part)
axes[0,0].plot(df.club_head_x.replace(0,np.nan),df.club_head_y.replace(0,np.nan),label="club head")
axes[0,0].invert_yaxis(); axes[0,0].legend(); axes[0,0].set_title("Trajectories exposed by GolfData")
axes[0,1].plot(df.frame,df.wrist_y,label="wrist y"); axes[0,1].plot(df.frame,df.club_head_y.replace(0,np.nan),label="club y"); axes[0,1].invert_yaxis(); axes[0,1].legend()
axes[1,0].plot(df.frame,df.left_elbow_angle_diag); axes[1,0].set_title("Our 2D elbow-angle diagnostic (not package output)")
phase_codes=pd.Categorical(gd.pose_result.poses,categories=["RhStart","RhTop","RhFinish","Unknown"]).codes
axes[1,1].step(df.frame,phase_codes,where="mid"); axes[1,1].set_yticks(range(4),["RhStart","RhTop","RhFinish","Unknown"]); axes[1,1].set_title("Input pose labels (not derived here)")
fig.tight_layout(); fig.savefig(OUT/"00001_golftrainer_diagnostics.png",dpi=140)
plt.show()
"""),
        md("""
## Reuse assessment

The installed feature calculations can be reused independently because there effectively are no calculations beyond table conversion. The dataclass/factory idea is useful, and the raw coordinates are valuable, but the schema needs versioning, validation, nullable values instead of `(0,0)`, timestamps/frame IDs, compatibility tests with the producer, and actual analysis modules.

Repository source after the PyPI release contains experimental `geom.py`, `plot_utils.py`, and `swing_analysis.py`, including club-direction threshold phase segmentation and a nearest-return impact heuristic. Those files are not in wheel 1.0.2 and should not be credited as installed functionality; the phase code is also fragile and includes indexing/phase-range defects.
"""),
        code("""
print("EXECUTED_OK: golftrainer notebook reached the final cell")
"""),
    ],
)


write(
    "10_pypi_package_comparison.ipynb",
    "package comparison",
    [
        md("""
# Package comparison and decision record

Comparison of the exact PyPI releases tested on 2026-11-03: `swing-analyzer` 0.1.2, `golftracker` 2.0, and `golftrainer` 1.0.2. “Yes” means observed in installed code or successful execution—not merely claimed by project documentation.
"""),
        code("""
from pathlib import Path
import json, platform
import matplotlib.pyplot as plt, numpy as np, pandas as pd
from IPython.display import display
ROOT=next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "pyproject.toml").exists())
"""),
        code("""
rows = [
("Role","turnkey body-pose analyzer","video-to-frame-data producer","JSON-to-DataFrame adapter"),
("Pose model","MediaPipe Pose complexity 1","MediaPipe Pose complexity 1","none; consumes coordinates"),
("Landmarks retained","selected derived fields only","33 x/y/z/visibility per frame","33 x/y/z/visibility from input"),
("2D / 3D","2D image geometry; MediaPipe z discarded","normalized x/y plus relative MediaPipe z","passes x/y/z/visibility; tables mainly x/y"),
("Clubhead tracking","No","Manual points + straight-line interpolation","passes input clubhead points"),
("Shaft tracking","No; fixed 54°/manual-angle proxy","No; draws thumb-to-clubhead segment","No"),
("Ball tracking","No","No in v2 schema","No"),
("Swing events","Automatic wrist-height heuristics","sklearn pose classes or manual labels","passes stored labels; no detector"),
("Address / finish semantics","first / last tracked frame","classified/labelled Start / Finish","input labels"),
("Impact semantics","hands-low heuristic","not represented as a pose class","none"),
("Full frame trajectory","selected fields internally returned","Yes: all pose + club fields","Yes when valid producer JSON loads"),
("Visibility/confidence","not retained","MediaPipe visibility retained","visibility exposed in mp DataFrame"),
("Smoothing","3-frame phase; pose/tracer visual EMA/MA","optional path MA/spline utilities; not pipeline","none in wheel"),
("Angles / geometry","spine, line turns, arm and proxy checks","geometry utility module; no analysis report","none in wheel"),
("Tempo","top-to-impact and backswing ratio heuristics","No","No"),
("Automatic operation","Mostly, body only","MediaPipe yes; phases/club usually manual","yes only after compatible JSON exists"),
("Manual labelling","None required","GUI phase and club labels central to usable samples","none; relies on upstream labels"),
("Multi-swing comparison","summary diff + phase-warped video","No","No"),
("Structured export","Markdown; frame dict only via Python return","pickle + JSON (schema inconsistent)","DataFrames; no writer"),
("Annotated video","Yes, but codec can fail silently","draw methods; CLI missing","No"),
("Reusable Python API","Yes, simple functions","Importable library; broken workflow CLIs","small importable factory/dataclasses"),
("CLI","Working","broken: invalid entry point and omitted scripts","broken: omitted scripts"),
("Dependency status","Python 3.9-3.12; MP 0.10.14","MP 0.8.10 unavailable; protobuf 3.20 pin","minimal pandas/numpy"),
("Packaging/code quality","moderate; monolithic and unchecked writer","poor wheel/schema/per-frame model lifecycle","poor wheel completeness/schema validation"),
("Licence verified","MIT file in wheel","MIT file in wheel and source repo","MIT file in wheel and source repo"),
("Maintenance evidence","PyPI 2026-08-10","PyPI 2023-11-25; repo commit 2024-11-10","PyPI 2024-01-06; repo commit 2024-02-12"),
("Usefulness here","best executable reference and event baseline","best raw-data/club-label data model concept","useful only as a schema/table cautionary example"),
]
comparison=pd.DataFrame(rows,columns=["Feature","swing-analyzer","golftracker","golftrainer"])
pd.set_option("display.max_colwidth",120)
display(comparison)
comparison.to_csv(ROOT/"outputs"/"package_comparison.csv",index=False)
"""),
        md("""
## Strongest implementation by area
"""),
        code("""
winners=pd.DataFrame([
("Pose extraction","golftracker","Retains every MediaPipe landmark, z and visibility; swing-analyzer discards most raw data."),
("Phase detection","swing-analyzer","Only automatic temporal event heuristic that ran without an external model/manual labels; still not ground truth."),
("Club tracking","golftracker","Only package with club-head coordinates, but they are chiefly manual plus linear interpolation."),
("Trajectory storage","golftracker","Frame-aligned body, pose and club fields in pickle/JSON."),
("Geometry","swing-analyzer","Most integrated derived geometry and explicit camera-view suppression."),
("Visualization","swing-analyzer","Annotated video, key overlays, reports and synced comparison, subject to codec workaround."),
("Comparison","swing-analyzer","Only package with a two-swing path; it compares a small summary rather than distributions/consistency."),
],columns=["Area","Strongest","Why"])
display(winners)
"""),
        md("""
## Fit to the eventual project

None meets the central requirement. `golftracker` comes closest to the desired row model (`frame`, `timestamp`, all body landmarks, `club_head_x/y`, `phase`) but is manually labelled, packaging-broken, and lacks shaft/ball/robust events. `swing-analyzer` is the strongest currently executable implementation and a useful transparent baseline, but it retains too little raw data and observes no club. `golftrainer` 1.0.2 does not actually analyse.

For personal consistency, anomalous-swing detection, outcome linkage, and population/multi-session comparison, all three lack a dataset/session layer, stable schemas, quality flags, feature tables, alignment uncertainty, and statistical modelling.
"""),
        md("""
## Recommended direction (design only)

- **Reuse concept directly:** golftracker's frame-aligned raw landmark + club provenance model; swing-analyzer's explicit phase trace and camera-view caveats.
- **Adapt:** swing-analyzer's event baseline, smoothing separation, diagnostics, and compare visualization; golftracker's manual correction workflow as an audit tool.
- **Replace:** pose lifecycle, dependency/environment management, club interpolation, phase classifier, JSON schema/versioning, codec handling, and all coaching thresholds.
- **Ignore:** claims of automatic ball/shaft tracking in old documentation, unintegrated Canny/Hough experiments, and golftrainer-as-analysis in the published wheel.

The proposed V0.1 architecture is documented in `docs/research/benchmarks/package-review.md`; it is intentionally not implemented here.
"""),
        code("""
print("EXECUTED_OK: comparison notebook reached the final cell on",platform.python_version())
"""),
    ],
)

print("Built:")
for path in sorted(NOTEBOOKS.glob("*.ipynb")):
    print(path.relative_to(ROOT))
