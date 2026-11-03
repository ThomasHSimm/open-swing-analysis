# Synthesis: the ball-flight measurement layer (Shaw 2023, Barzyk 2024, Brennan 2023)

**Scope note.** These three papers arrived together but none of them is about the trial's primary
construct (centre-of-pressure timing and magnitude in weight transfer). Shaw and Brennan are
launch-monitor reliability/validity studies; Barzyk is a motor-learning pedagogy review. They inform
at most a *secondary* outcome layer (does ball flight change after training) plus protocol confounds.
They contribute **nothing** to powering the primary CoP outcome. This note records what they do
establish so the register does not over-state their relevance.

## 1. What ball-flight metrics can serve as secondary outcomes

Converging across Shaw (TrackMan, within + between session) and Brennan (Mevo+, within session,
validated vs TrackMan):

| Metric | TrackMan (Shaw, between-session) | Mevo+ (Brennan, within-session) | Use as outcome? |
|---|---|---|---|
| CHS | Excellent (ICC 0.99, CV <1%) | Trustworthy (r ≥0.92, CV <2%) | Yes |
| Ball speed | Reliable | Trustworthy (r ≥0.92, CV <5%) | Yes |
| Carry distance | Reliable | Usable (r ~0.88, CV ~7%) | Yes, noisier |
| Total distance | Reliable | (not separately reported) | Yes (TrackMan) |
| Smash factor | Reliable between-session | Usable, but ratio | Caution — see §4 |
| Spin rate | Marginal (6-iron only) | Unusable on Mevo+ | No |
| Launch / attack angle, spin axis | Unreliable by CV | Caution; sig device diffs | No |

**Defensible secondary outcome set: CHS, ball speed, carry, total distance.** These are the only
ball-flight metrics with reliability sufficient to detect a training-period change on either device.

## 2. Device decision hinges on a between-session gap

- TrackMan has between-session reliability evidence (Shaw) → fine for pre/post.
- Mevo+ has only *within-session* evidence (Brennan). For a pre/post design you need between-session
  (test–retest) error, which Brennan does not provide. The between-session Mevo+ source it cites
  (Villarrasa-Sapiña et al., *Sensors* 2022) is not reproduced.
- **Decision rule:** if budget allows TrackMan, the reliability question is settled for the four core
  metrics. If the pilot uses a Mevo+, source Villarrasa-Sapiña 2022 and confirm between-session CV/SEM
  before treating any ball-flight metric as a pre/post outcome. → **TODO.**

## 3. The cross-cutting confound: instruction / cueing

This is the most actionable thing the three papers say jointly, and it cuts across measurement *and*
intervention:

- Brennan: shot intent (they used "maximal distance") changes the variability of strategy metrics. A
  different instruction pre vs post would break reliability.
- Barzyk: attentional-focus instruction (internal vs external) is itself a documented moderator of
  golf-task outcomes — i.e. *how you cue* changes the movement.
- Implication for this trial: a balance-training cue such as "feel the weight move to your lead foot"
  is an *internal* focus instruction. It could shift CoP behaviour independently of any balance
  adaptation. If the cueing differs between groups or across time points, the training effect is
  confounded with an attentional-focus effect.
- **Mitigation:** fix and document the verbal-instruction protocol (warm-up script, per-shot cue,
  feedback given) identically across groups and time points, and report it. Pre-register the cue
  wording.

## 4. Smash factor — avoid as an outcome despite "good reliability"

Brennan's own argument (citing Bishop's ratio-data work): smash factor = ball speed ÷ CHS, so any
change conflates changes in either component. To interpret it you have to inspect CHS and ball speed
separately anyway — at which point the ratio adds little. Reliable ≠ useful. Track CHS and ball speed
directly instead.

## 5. Population read-across is weak

All three skew to skilled/young samples (cat-1; handicaps 6.7–11.8; youth pathway). Shaw and Brennan
both explicitly flag that reliability may differ for higher-handicap players. If the pilot recruits a
different population, the device-error figures above are not guaranteed to hold — measure your own
within-cohort typical error (Shaw's suggested individual-SD approach) rather than importing these CVs.

## 6. What is still missing (gaps these papers do NOT fill)

- **Primary-outcome reliability:** no CoP/GRF measurement reliability here at all. That must come from
  the priority papers (GRF systematic review; Roehampton CoP intervention).
- **Effect-size priors for powering:** none for a balance→CoP→weight-transfer mechanism. The Barzyk f
  values are skill-learning effects and are not transferable.
- **Training duration for balance adaptation:** none. Barzyk's durations are skill-acquisition, not
  strength/balance.
- **Mevo+ between-session reliability:** cited but not in hand (TODO §2).

## Register actions

| Paper | Tier | Rationale |
|---|---|---|
| Brennan 2023 | Evidence — device selection (within-session) | Tells you which Mevo+ metrics to trust |
| Shaw 2023 | Evidence — measurement layer (TrackMan between-session) | Only if TrackMan is the device |
| Barzyk 2024 | Background / methods-watch | Construct mismatch; kept only for the cueing confound |

**Net:** the three give a clean answer to "which ball-flight metrics are trustworthy and on which box"
and a useful confound warning, but they do not advance the core measurement (CoP) or the power
calculation. Do not let three measurement papers inflate the apparent maturity of the evidence base
for the actual hypothesis.
