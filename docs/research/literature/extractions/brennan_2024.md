# Brennan et al. (2024) — Physical Characteristics and Golf Clubhead Speed

> **Triage note:** Not one of the 5 priority papers. Study type (associative meta-analysis) does not match the intervention-oriented template — several fields are N/A. Primary value to this project is contextual (which physical tests matter for golf) plus a cautionary balance finding. Consider whether this warrants a full library slot or a shorter context note.

## Citation
Brennan A, Murray A, Mountjoy M, Hellstrom J, Coughlan D, Wells J, Brearley S, Ehlert A, Jarvis P, Turner A, Bishop C. Associations Between Physical Characteristics and Golf Clubhead Speed: A Systematic Review with Meta-Analysis. *Sports Medicine.* 2024;54:1553–1577.

## DOI
10.1007/s40279-024-02004-5 (Open Access, CC BY 4.0)

## Study type
Systematic review with meta-analysis. Pooled studies are cross-sectional / observational associative designs. **Intervention studies were explicitly excluded** per inclusion criteria — so this is an associational, not causal/training, evidence base.

## Population
20 included studies (from 3039 screened; 16 met criteria + 4 from reference/citation checks). Pooled samples by group:

| Group | n |
|---|---|
| Category 1 golfers (handicap ≤5) | 93 |
| Elite youth golfers | 82 |
| NCAA Division I/II | 61 |
| Single/double-digit handicap | 282 |
| European Tour | 31 |
| PGA Tour | 20 |

Skill range: elite to recreational. Mostly male; several studies did not report sex; very few female-only samples. All samples injury-free (inclusion criterion).

## Intervention
**N/A** — no interventions; associative meta-analysis only.

## Comparator
**N/A.**

## Duration
**N/A** — cross-sectional associations. *This paper cannot inform training-period length for your design.*

## Outcome measures
Single dependent variable: **clubhead speed (CHS), driver only** (where multiple clubs reported, driver carried forward). Independent variables grouped into 10 physical characteristics, each correlated with CHS. Effect sizes pooled as Fisher's z-transformed r (zr) under a random-effects model. Note on assessment heterogeneity: each "characteristic" pools multiple distinct tests (e.g. lower body strength = 1RM back squat, IMTP, hack squat, isokinetic dynamometry — which the authors acknowledge do not measure the same thing).

## Key findings
Pooled associations with CHS, ordered by strength (Cohen: <0.2 trivial, 0.2–0.49 small, 0.5–0.79 moderate, ≥0.8 large):

| Characteristic | zr [95% CI] | Magnitude | Sig. | I² | Notes |
|---|---|---|---|---|---|
| Jump impulse | 0.82 [0.63, 1.02] | Large | Yes | 0% | Strongest; clean (no heterogeneity, no small-study bias) |
| Upper body explosive strength | 0.67 [0.53, 0.80] | Moderate | Yes | 0% | |
| Jump peak power | 0.66 [0.53, 0.79] | Moderate | Yes | 0% | Only 1 study's CI crossed zero |
| Jump displacement (height) | 0.53 [0.28, 0.78] | Moderate | Yes | 80% | High heterogeneity; small-study bias flagged (z=2.22, p=0.03), trim-and-fill imputed 0 missing |
| Upper body strength | 0.48 [0.28, 0.68] | Small | Yes | 45% | |
| Lower body strength | 0.47 [0.24, 0.69] | Small | Yes | 51% | Moderate, significant heterogeneity |
| Anthropometry | 0.43 [0.29, 0.58] | Small | Yes | 0% | 6/7 studies pooled multiple measures; directionally-aligned (×−1 applied) — interpret with care |
| Muscle capacity | 0.17 [0.04, 0.31] | Trivial | Yes | 0% | Significant but trivial |
| Flexibility | −0.04 [−0.33, 0.26] | Trivial | **No** | 67.5% | High heterogeneity; authors question assessment ecological validity |
| Balance | −0.06 [−0.46, 0.34] | Trivial | **No** | 13% | Only 2 studies; see flag below |

Headline narrative: explosive force production (impulse, power, upper-body explosive) outperforms maximal strength; jump impulse is the single best CHS correlate; flexibility and balance are not significantly associated.

## Statistical approach
Random-effects model on Fisher's zr; `metafor` v4.4-0 in R v4.2.2. Multiple eligible effect sizes within a study aggregated via Fisher's Z before pooling (independence assumption). Heterogeneity: Q (α<0.10) and I² (Higgins–Thompson bands). Small-study/publication bias: funnel plots + Egger's regression (p<0.05 threshold), trim-and-fill for adjustment where flagged. Cohen thresholds for interpretation.

## Relevance to trial design
- **Appropriate training duration:** No information — associative design.
- **Appropriate outcome measures:** Useful for *physical-test selection* in golf generally — net impulse from force plates is the strongest CHS correlate, and the authors give a practical fallback (inverse dynamics from jump height + body mass when only a jump mat/phone is available). **However, your study's outcome (CoP timing/magnitude during the swing) is not among the characteristics studied here.** "Balance" here = static balance ability (BESS, Biodex), not dynamic weight transfer. Do not treat this paper as validating CoP-based outcome measures.
- **Expected effect sizes:** For balance → CHS, effectively zero (zr=−0.06). Gives no effect-size anchor for a CoP-timing change outcome.
- **Likely confounders surfaced:** body mass (authors argue it inflates CHS via momentum, and complicates jump-height interpretation), skill/handicap level, sex.

## Limitations noted by authors
Heterogeneous assessment protocols within each characteristic (not measuring the same construct); very few female-golfer studies; individual-level analysis rarely reported; questionable ecological validity of several flexibility/balance assessments (e.g. sit-and-reach); reliance on CHS as sole outcome (recommend ball speed, carry, strokes-gained instead). Balance pooled only 2 studies, one with n=5 per sex group.

## Quality assessment
**High** for the meta-analysis itself: Downs & Black scores 7–9/10 across all 20 studies, no internal validity bias detected, methods appropriate. **Caveat:** the balance and flexibility sub-analyses rest on thin, heterogeneous evidence (balance n=2 studies; one drives ~85% of the balance weighting, the other has n=5/group). The authors themselves flag balance/flexibility evidence quality as questionable. So: high-quality synthesis, but the parts most relevant to a balance project are its weakest cells.

## Direct quotes worth keeping
Keep sparing (paraphrase preferred). The authors' balance rationale is worth one verbatim line for context:
- On balance's irrelevance to CHS: "golfers are very rarely off-balance and never take a shot standing on one leg."

## Contradiction flag
**Cuts against a naïve balance rationale, with an important construct caveat.**
- The paper finds balance is the *weakest* CHS correlate (non-significant, near zero) and argues balance training/testing should not be a staple for golfers.
- **Construct mismatch protects your design but demands precise citation:** this paper's "balance" = static balance ability vs CHS. Your study = within-swing CoP timing/magnitude as the outcome, with balance-focused training as the intervention. Different constructs, different outcome. The paper does not measure whether balance training shifts CoP timing.
- **Net risk for your design:** the link from balance ability → CHS/performance has unfavourable evidence here. If your study's framing leans on a performance (CHS) payoff, this is the paper a reviewer will cite against you. Safer framing: weight-transfer / CoP timing as a movement-quality outcome in its own right, explicitly distinguished from the static-balance→CHS question this meta-analysis answers.
