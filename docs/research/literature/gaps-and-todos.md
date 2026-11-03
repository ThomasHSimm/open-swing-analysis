# Gaps & TODOs — balance/CoP golf trial

Updated after 15 extractions. Three critical gaps cannot be closed by reading more papers;
they are design decisions. The rest are acquisition targets with search terms.

## Critical gaps (NOT fixable by citation)

### G1. Test–retest reliability of swing-CoP — the primary outcome
- No paper establishes reliability of CoP timing/magnitude *during the swing*. Watson flags
  it as the field's biggest gap; Bishop/Shaw cover launch monitors only; Severin validated
  trial-count on ROM/velocity/GRF-magnitude/moments but **explicitly NOT CoP timing**.
- **Hardware decision, not a literature gap** (see D1).
- **Action:** build a same-week retest into the protocol; report SEM and MDC for *your* plate
  and *your* swing-event definitions, using **SEMind** (Severin's recommended method, robust to
  small heterogeneous samples). Run it specifically on the CoP-timing metric — do not assume
  Severin's ~8-trial figure transfers to timing.

### G2. No effect-size / MCID for dynamic CoP timing
- Every effect size in hand is the wrong construct or wrong design: static balance (Li),
  ball flight (Bishop/Shaw/Brennan), cross-sectional skill *differences* (McHugh ES 1–2.6,
  Ball η² up to 0.66). None is a within-subject *training change* in swing CoP timing.
- **Action:** frame as a **feasibility / variability-estimation pilot**, not powered to detect
  a CoP change. Use it to estimate the SD needed to power a later study. Do not assert a target
  effect. Note Yang's sobering prior: a distance-moving manipulation produced no COG change at
  n=10/group — small samples may miss real effects.

### G3. Balance-training → swing-CoP causal link is untested — THE load-bearing gap
- The intervention arm and outcome arm have never been connected:
  - Trains balance, no swing CoP: Li, Yılmaz.
  - Moves swing CoP, not balance training: Faux (cue; immediate=null, 1-yr=n=1), Belotti (acute cue).
- Duration signal cuts against a short trial: Faux is the only direct read and says an immediate
  cue did nothing; only a year worked.
- **This is what the pilot exists to test.** State the chain (balance training → dynamic CoP →
  weight transfer) explicitly as the hypothesis, not background. If the trainability signal is
  null at 4 weeks, that is itself the headline finding.

### G4. (New) No established "correct" CoP pattern to train toward
- Ball: weight-transfer style unrelated to skill; two styles both effective; 4/6 pros "Reverse."
  McHugh: magnitude doesn't discriminate; trunk rotation drives performance.
- **Action:** reconsider whether the outcome should be "movement toward a target pattern" at all.
  Safer candidates: within-style *consistency*/timing quality, or change in unweighting *rate*
  (McHugh's discriminating metric). Decide before pre-registration.

## Open design decision (gates G1)

### D1. Force-measurement hardware
| Option | CoP? | Reliability status | Consequence |
|---|---|---|---|
| TrackMan / GCQuad only | No | Covered (Bishop, Shaw) | Abandons primary outcome — ball flight only |
| Smart2Move dual plate | Vertical only | None in hand | Must self-run reliability session (G1) |
| VALD ForceDecks | Yes (vGRF/CoP) | Published ICC + MDC exists | Can cite reliability |
| Force insoles | Yes (CoP) | Published ICC exists | Can cite; portable, on-course |

Pick the plate first. Loughborough kit? Budget? Need CoP *trajectory* (insoles/plates) vs
vertical force only? Then T1 resolves to a specific paper, or G1 becomes a designed session.

## Acquisition targets (with search terms)

### T0. Smith et al. 2017 — CoP-specific, HIGHEST priority now
- Flagged by Severin as the CoP-specific paper closer to your outcome than anything held.
- Search: `Smith 2017 centre of gravity centre of pressure patterns golf swing`

### T1. Peterson et al. 2016 / 2019 — angular impulse + balance regulation (on-construct)
- Flagged by You 2023 as on-construct for weight-transfer kinetics; not yet in library.
- Search: `Peterson golf swing angular impulse balance regulation force plate 2016 2019`

### T2. Reliability paper matching the chosen plate — get AFTER D1
- ForceDecks: `ForceDecks reliability ICC MDC vertical ground reaction force`
- Insoles: `force insole CoP validity reliability ICC golf` (PMC12787798 surfaced earlier)
- Fallback: `force plate reliability golf swing test-retest`

### T3. Queen et al. 2013 — handicap × weight-transfer timing
- Queen RM, Butler RJ, Dai B, Barnes CL. *J Strength Cond Res* 2013;27(9):2481–2486.
  DOI 10.1519/jsc.0b013e31827f4da6.

### T4. Richards et al. 1985 — historical precedent (background)
- Richards J, Farrell M, Kent J, Kraft R. *Res Q Exerc Sport* 1985;56(4):361–365.
  DOI 10.1080/02701367.1985.10605341.

### T5. Sham-controlled RCT template (control-design model)
- Adolescent golfer LBP prevention RCT. *BMC Sports Sci Med Rehabil* 2025.
  DOI 10.1186/s13102-025-01287-z. Open access. Model for solving the no-control weakness.

### T6. Villarrasa-Sapiña 2022 — ONLY if Mevo+ chosen
- Search: `Villarrasa-Sapina FlightScope Mevo test-retest reliability Sensors 2022`

## What NOT to acquire (layers saturated)
- Further launch-monitor reliability/validity (Bishop, Shaw, Brennan 2023).
- Further motor-learning pedagogy (Barzyk).
- More magnitude-focused GRF reviews (You is already low-value; don't add similar).
- Strength & conditioning / shaft / equipment papers (off-construct).

## Housekeeping
- evidence-register.qmd: 15 papers, McHugh + Ball re-tiered to Core, You demoted to pointer. DONE.
- gaps-and-todos.md: this file, updated with G4. DONE.
- Repo: add the 15 rows to the Completed Extractions table in the prompt doc.
