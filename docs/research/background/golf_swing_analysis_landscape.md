# Golf Swing Analysis: State of the Field (2026)

A review for planning a new open-source instructor tool. Covers what professionals use,
what consumer apps do, where the technology fails, and what gap a new tool could fill.

---

## 1. What professionals actually use

### The top tier: hardware-dependent systems

Professional tour players and high-end teaching academies use systems that are fundamentally
different from anything phone-based. These are not realistic targets for a small project but
set the benchmark for what "accurate" means.

**Gears Golf** ([gearssports.com](https://www.gearssports.com/golf-swing-biomechanics/))
Full optical motion capture. Reflective markers, multiple calibrated cameras, lab environment.
Provides sub-millimetre accuracy on joint positions, club path, and face angle. Used by PGA
tour players, club fitters, and equipment manufacturers. Cost: ~$50,000+. Not portable.

**TrackMan** ([trackman.com](https://www.trackman.com/blog/golf/the-ultimate-guide-to-understanding-trackman))
Dual-radar system. Tracks ball flight (speed, spin, launch angle, carry distance) and club
data (path, face angle, attack angle). The gold standard for ball data. Does *not* do body
analysis — it measures what the club and ball do, not why the body caused it. TrackMan has
recently added "AI Motion Analysis" to its coaching software (automated line drawing,
shoulder/hip tracking) but this is still a bolt-on to radar-first data, not pose estimation.
Cost: ~$20,000+.

**High-speed cameras in broadcast**
Competitive golf broadcasts use cameras capable of 6,000 fps. This is how you see the
clubface at impact clearly. Phone cameras at 60–240 fps cannot capture this. Impact happens
in under 5 milliseconds — at 240 fps you get roughly one frame at impact.

**What pros actually care about (from TrackMan data)**
- Club head speed and ball speed (ratio = smash factor, ideally ~1.48 for driver)
- Attack angle (pros hit slightly up with driver, down with irons)
- Club path and face angle relative to path (this determines shot shape)
- Spin rate and axis (determines ball flight curvature)

These are *ball and club* metrics. Body position matters instrumentally — it produces these
outcomes. The link between body mechanics and ball outcome is what instruction is about.

---

## 2. Consumer app landscape

The market has grown substantially since 2022. Most apps now claim "AI" but vary enormously
in what that actually means.

### The main players

**Sportsbox 3D Golf** ([sportsbox.ai](https://www.sportsbox.ai/))
Currently the most technically ambitious consumer app. Claims markerless 3D motion capture
from a *single* phone video, reconstructing the body in 3D that can be viewed from six angles.
Measures turn, bend, side-bend, sway, and lift. Has a specific coach version with student
management, remote lesson tools, and goal-setting. Requires slow-motion video (120fps minimum)
filmed face-on. Price: ~$15/month player, higher for coaches.

*Honest caveat*: "3D from single 2D video" is a hard computer vision problem. The app likely
uses a learned model to infer depth rather than true stereo reconstruction. Accuracy for
occluded joints (e.g. trailing arm at top of backswing) will be estimated, not measured.

**V1 Golf** ([v1golf.com](https://www.golfspan.com/best-golf-swing-analysis-app))
Long-established, widely used by instructors. Primarily a video analysis toolbox: slow-motion,
frame-by-frame, drawing tools, side-by-side comparison with pro swings. Good for instructors
who want to annotate and communicate. AI analysis available in newer versions. Supports iOS
and Android. ~$60/year.

**Onform** ([deepswing.io blog comparison](https://deepswing.io/blog/the-best-golf-swing-analyzer-apps-in-2025))
Designed specifically for coaches, not solo golfers. Multi-angle video, voiceover annotation,
coach-student communication, lesson management. Described as the strongest option for
"teaching pros, indoor bays, academies, and remote coaching workflows". Less AI analysis,
more professional workflow tooling.

**DeepSwing** ([deepswing.io](https://deepswing.io))
On-device AI (runs locally, no cloud upload required). Automatically detects phases (Setup,
Backswing, Top, Downswing, Impact, Finish), gives an overall score, and checks 30 specific
issues including: stance width, spine angle stability, head movement, lead arm structure,
hip rotation, pelvis slide, weight shift, tempo ratio, reverse spine, sway, over-the-top,
hanging back, early release, shaft lean, shoulder tilt, early extension, hand depth, and
chicken wing. iPhone only (2026). Considered the strongest all-round option for solo iPhone
users.

**GolfFix** ([Google Play](https://play.google.com/store/apps/details?id=kr.co.moais.golffix))
Strong Android option. Auto swing detection. Currently records at 60fps with higher fps
planned. AI swing issue detection. ~$10/month.

**SWEE** ([App Store](https://apps.apple.com/us/app/swee-golf-ai-swing-analyzer/id1591618831))
Claims 50+ analysis metrics from address to follow-through. Automatic swing detection from
face-on and down-the-line. Side-by-side comparison with model golfers. Actively updated.

**Sparrow** ([App Store](https://apps.apple.com/us/app/sparrow-golf/id1526670395))
Claims real-time swing detection (auto-detects without pressing record). Club head tracking.
Updated ML models in early 2025.

---

## 3. What these apps do technically

Understanding what's under the hood matters for knowing what's possible.

### Pose estimation
Most apps use a form of 2D human pose estimation — detecting where joints are in each video
frame. MediaPipe (Google, open source) and YOLO-based models are common. A 2025 research study
comparing these for golf specifically found MediaPipe achieved mean OKS (Object Keypoint
Similarity) of 0.636 vs YOLO at 0.604 — both significantly below what motion capture achieves,
and this is on reasonable footage
([Drocárová & Fucsiková, 2025](https://github.com/Strojove-uceni/23206-final-pose-estimation-for-swing-improvement)).
Accuracy is heavily dependent on camera angle and lighting.

### Phase detection
The GolfDB dataset (2019) and SwingNet model established the standard: detect 8 key events
(Address, Toe-Up, Mid-Backswing, Top, Mid-Downswing, Impact, Mid-Follow-Through, Finish)
in a trimmed swing video. SwingNet achieves ~76% accuracy on broadcast-quality footage it
was trained on. Performance on phone video of amateurs is untested and likely worse, particularly
for Address detection which was already noted as problematic
([McNally et al., CVPR 2019](https://arxiv.org/abs/1903.06528)).

### Metrics
A recent paper (CaddieSet, 2025) is the most relevant academic work. With golf expert input,
it defined 15 key swing metrics (shoulder angle, hip rotation, weight shift, head location,
stance ratio etc.) that influence ball outcome, and demonstrated these could predict direction
angle, spin axis, and ball speed from joint data
([arxiv.org/abs/2508.20491](https://arxiv.org/abs/2508.20491)).
This is the best available reference for *which metrics matter* rather than inventing them.

### The "3D from single video" claim
Sportsbox and some others claim full 3D body reconstruction from one phone video. This is
technically possible using learned depth estimation models but carries important caveats:
joints that are occluded (hidden behind the body from the camera angle) are inferred, not
observed. Accuracy for occluded joints is unknown and unlikely to match what the apps imply.

---

## 4. What currently works and what doesn't

### What works reliably

- **Video recording and slow-motion playback**: All apps do this well. Modern phones at
  120–240fps are adequate for most of the swing (not impact).
- **Skeleton overlay and joint angle visualisation**: Works reasonably on good footage with
  clear background, adequate lighting, and camera at the correct height and angle.
- **Side-by-side comparison**: Mature feature in V1 Golf, SWEE, Sportsbox. Useful for
  instructors showing a pupil their swing next to a pro reference.
- **Phase detection on reasonable footage**: Good enough for structured practice sessions
  when the golfer is clearly visible and camera placement is correct.
- **Workflow tools for coaches**: V1 Golf and Onform are genuinely useful for lesson management,
  annotation, and communication.

### What doesn't work reliably

- **Automatic shot boundary detection in continuous multi-shot video**: No app handles this
  well. All current apps analyse individual, pre-trimmed swing clips. Getting the app to watch
  a 30-minute lesson video and automatically segment each shot is not a solved problem.
- **Audio labelling**: No existing app allows verbal shot annotation ("hook left", "fat") linked
  to swings. This is an entirely novel feature that does not exist in the market.
- **Generalised feedback across swing styles**: A former golf instructor reviewing GolfFix
  noted the app flagged a move that modern teachers actually teach, calling its prescriptive
  feedback unreliable without expert validation
  ([App Store review](https://apps.apple.com/us/app/golffix-ai-swing-analyzer-cam/id1586120680)).
  Generic AI feedback can actively mislead.
- **Pose quality on poor footage**: Camera angle wrong, background cluttered, low light, or
  golfer partially out of frame all degrade pose estimation significantly. Apps require
  specific setup (tripod at hip height, face-on or DTL, adequate distance). In a real lesson
  environment this is often not achievable.
- **Impact frame capture**: At 60fps a golf swing is ~25 frames total; at 240fps ~100 frames.
  The impact interval is still often 1–2 frames and frequently blurry. True impact position
  data requires radar or high-speed hardware.
- **Left-handed golfer support**: Noted as a gap in multiple apps.
- **Club tracking**: The club moves faster than the body. Tracking club path from phone video
  is approximate. Dedicated club path analysis still requires radar.

### The fundamental accuracy ceiling

MediaPipe and similar models were not designed for golf-specific pose. A 2023 study found
MediaPipe accuracy drops sharply when camera angle or exercise type differs from training
conditions
([Dill et al., 2023](https://doi.org/10.1515/cdbme-2023-1141)).
A side-on camera angle (standard for instructor filming) causes limb occlusion. The trailing
arm behind the body at the top of the backswing cannot be directly observed from a face-on
or DTL view — it is estimated. Metrics derived from occluded joints should be treated as
approximations.

---

## 5. What a new tool could offer

Based on the above, the gap that does not exist in current tools:

**The instructor session workflow.** Current apps are designed for the solo golfer with a
tripod at a driving range. They do not handle:
- A continuous video of multiple shots filmed by an instructor
- Vocal annotations linked to specific shots ("good", "hook left", "fat")
- Automated comparison between good and bad shots within a session
- Export of session findings in a format useful for post-session review

This is genuinely unoccupied. It is also technically achievable with open-source tools
(MediaPipe, Whisper for speech recognition, standard video processing) without needing
proprietary hardware or cloud ML infrastructure.

**Realistic scope for a first version:**
1. Upload a session video (multiple shots, instructor commentary)
2. Detect shot boundaries (motion-based or manual)
3. Transcribe instructor audio using Whisper; associate label with preceding shot
4. Extract pose and key metrics per shot
5. Table output: shot / label / metrics
6. Simple comparison: metric distributions for "good" vs labelled-problem shots

**What this does not need to do (yet):**
- 3D reconstruction
- Real-time analysis
- Club tracking
- Ball flight data
- Generalised feedback (the instructor provides the labels — the tool compares mechanics)

The last point is the critical difference from all existing apps: **the feedback comes from the
expert, not the AI**. The AI just measures mechanics and groups them by what the expert said.
This sidesteps the "prescriptive feedback that might be wrong" problem entirely.

---

## 6. Key references and links

| Resource | What it's for |
|---|---|
| [GolfDB / SwingNet (McNally et al., 2019)](https://arxiv.org/abs/1903.06528) | Phase detection dataset and baseline model |
| [CaddieSet (Jung et al., 2025)](https://arxiv.org/abs/2508.20491) | 15 expert-validated swing metrics linked to ball outcome |
| [MediaPipe vs YOLO for golf (2025)](https://www.scirp.org/journal/paperinformation?paperid=148105) | Accuracy benchmarks on actual golf video |
| [MediaPipe Golf + ML (Springer, 2025)](https://link.springer.com/chapter/10.1007/978-981-96-6291-3_24) | Phase classification using MediaPipe landmarks |
| [Sportsbox 3D Golf](https://www.sportsbox.ai/) | Most technically advanced consumer app |
| [V1 Golf](https://www.v1golf.com/) | Most established instructor tooling |
| [Onform](https://www.onformsports.com/) | Coach workflow, multi-angle, annotation |
| [DeepSwing](https://deepswing.io/) | Best solo iPhone AI analysis (2026) |
| [Gears Golf (pro hardware)](https://www.gearssports.com/) | Pro-grade motion capture reference |
| [TrackMan](https://www.trackman.com/) | Ball/club radar, industry standard for ball data |

---

*Prepared May 2026. Technology in this space is moving quickly — app capabilities change with
updates every few months.*
