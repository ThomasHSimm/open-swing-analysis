# Severin et al. (2021) — Required Number of Trials for Biomechanical Analysis of a Golf Swing

> **Triage note:** Not on the priority-5 list as named, but this is the primary source behind the "natural variability / standard outcomes" intent of priority #2, and the single most directly useful methods input for the pilot's data-collection protocol. A reliability/methods paper, not an intervention or proficiency study. **Keep — it underpins your trial-count decision.** Key limitation for your use: validated on ROM/velocity/GRF-magnitude/moments, NOT CoP-timing (your primary outcome).

## Citation
Severin AC, Barnes SG, Tackett SA, Barnes CL, Mannen EM. The required number of trials for biomechanical analysis of a golf swing. *Sports Biomechanics.* 2021;20(2):238–246. (NIH author manuscript, PMC.)

## DOI
10.1080/14763141.2018.1554085 (PMCID available)

## Study type
Methodological / reliability study. Compares three statistical methods for determining the minimum number of swing trials needed for stable biomechanical estimates. Single-session, no intervention, no proficiency contrast.

## Population
10 recreational male golfers, ≥10 yr experience, right-handed, injury-free (prior 6 mo), no orthopaedic surgery. Height 1.77±0.01 m, mass 82.6±5.8 kg, age 39.0±17.4 yr, self-reported handicap 7.8±4.7. Skill level not controlled (acknowledged limitation).

## Intervention
**N/A** — reliability analysis. "Conditions" = two clubs (6-iron, driver), own clubs, 15 max-effort shots each at a 1×1 m target 4 m away; 30–60 s rest between shots, 5 min between clubs.

## Comparator
The three reliability methods compared against each other: sequential averaging (SD25, ±0.25 SD bandwidth), ICC(3,1), and SEMind (individual-SD-based modified standard error of measurement, per Gore et al. 2016).

## Duration
**Single session.** No training period.

## Outcome measures
Equipment: 10-camera Vicon @ 100 Hz, AMTI force plates @ 1000 Hz, 39-marker Plug-in-Gait full body. Kinematic filter 2 Hz, kinetic 4 Hz low-pass Butterworth. Time-normalised to 100 points from backswing initiation to peak trunk rotation at end of follow-through.
Biomechanical variables (the "DV" whose stability was assessed): 3D trunk and hip **ROM**; 3D trunk and hip **angular velocity**; **GRF** both feet (magnitude, N/BW); 3D **hip joint moments** (inverse dynamics).
*No CoP location or CoP-timing variables analysed.*

## Key findings
**Required trials vary by method and variable (range 4–12):**

| Variable | SD25 (conservative) | ICC(3,1) | SEMind (least conservative) |
|---|---|---|---|
| ROM | ~10.5 | 7 | 6.5 |
| Angular velocity | ~10.5 | 6 | 7.3 |
| GRF (magnitude) | ~10.5 | 7 | 6.5 |
| Joint moments | ~10.2 | 7 | 5.5 |

- ICC(3,1) all >0.750 ("good stability"): ROM 0.901, velocity 0.945, GRF 0.844, moments 0.858.
- **Recommendation: 7–8 trials sufficient** for most golf-swing biomechanics; **use SEMind**.
- No fatigue across 15 trials (swing-time first vs last n.s.: 6-iron p=0.379, driver p=0.698).

## Statistical approach
SPSS + Excel. SD25 sequential averaging (James et al. 2007). ICC(3,1) per Portney & Watkins bands (<0.5 poor, 0.5–0.75 moderate, >0.75 good); trial number at highest ICC = required N. SEMind from individual SD × ICC(3,1) over all 15 trials (Gore et al. 2016). Paired t-test on swing time (fatigue check).

## Relevance to trial design
- **Trials to collect — the headline:** adopt **~8 swings per golfer per condition** as a defensible default, citing this paper. More rigorous than the best-of-5 protocols in your cross-sectional sources (Yang best-2-of-5; McHugh best-3-of-5).
- **Method to verify stability:** use **SEMind**, not ICC, especially for a small heterogeneous pilot sample (see statistical caveat).
- **CRITICAL GAP for your study:** the 7–8 figure is validated on ROM/velocity/GRF-magnitude/moments. Your primary outcome is **CoP timing**, which was not tested. The paper's own central thesis — trial count is variable-specific — means you should NOT assume 8 stabilises a CoP-timing estimate. Run your own SEMind analysis on your CoP-timing metric during piloting and report it; this both follows the paper's recommended method and closes the gap.
- **Appropriate outcome measures:** confirms standard kinematic/kinetic vocabulary (3D trunk/hip ROM & velocity, per-foot GRF, hip moments) and a clean event-normalisation scheme (backswing init → end of follow-through, 100 points).
- **Expected effect sizes / confounders:** N/A (reliability study). But supplies a reusable fatigue check (swing-time first vs last) worth replicating in your protocol.

## Limitations noted by authors
n=10; recreational golfers only with uncontrolled skill level; single session. Authors note ICC is inflated by between-subject heterogeneity, so their ICC-based counts may understate within-subject trial needs; results "may be more conservative than a study on only elite golfers." They call for future work on how skill level affects required trial count.

## Quality assessment
**Medium–high for its narrow purpose.** Peer-reviewed, proper dual-plate + Vicon setup, three methods compared, fatigue controlled, sensible event normalisation. Limits: small n, recreational-only, single session, and — decisively for your application — no CoP-timing variable tested. Strong methods backbone; not a substitute for your own variable-specific reliability check.

## Direct quotes worth keeping
Prefer paraphrase. One citable design takeaway:
- The authors conclude that seven or eight trials "will suffice for most research projects" and recommend the SEMind method.

## Contradiction flag
**No contradiction — a methods enabler with one important boundary condition.**
1. **Statistical subtlety (use it):** ICC measures *relative* consistency and is inflated by sample heterogeneity (Weir 2005), so the low ICC-based trial counts here partly reflect a skill-heterogeneous sample, not genuine within-subject stability. For your small, heterogeneous pilot this is the reason to prefer SEMind (individual-SD-based) and to be wary of any ICC-derived "few trials needed" reassurance.
2. **Boundary condition (do not over-extend):** the 7–8 recommendation does not automatically apply to CoP-timing. Event-detection-based timing metrics can be noisier than ROM/velocity magnitudes; treat 8 as a hypothesis to verify, not a settled value, for your specific outcome.
3. **Synergy with Ball (2002):** thin per-golfer sampling + style heterogeneity is how small pilots produce type I/II errors. Collecting ~8 stable trials and verifying per-subject stability with SEMind directly mitigates the per-golfer-estimate instability that compounds that risk.
4. **Pointer:** for CoP specifically, follow up Smith et al. 2017 (ref. in this paper) — "Comparison of centre of gravity and centre of pressure patterns in the golf swing" — which is CoP-specific and closer to your outcome than this trial-count study.
