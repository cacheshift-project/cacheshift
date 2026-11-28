# Sprint 4

**Dates:** 18 Nov to 4 Dec 2026 (dates to confirm)  ·  **Demo:** 4 Dec poster session

## Goal
Make the demo something a visitor understands in a minute, and answer the Sprint 3 next steps with enough questions to tell: re-tuning at scale, uneven repeats, reworded questions, and the report leading with wrong answers.

## Committed stories
| Story | Owner | Acceptance criteria | Done? |
|---|---|---|---|
| Live demo dashboard | Anthony | A page sends a question stream through the real gateway and shows each question's path, wrong answers caused by the cache, and live cost, accuracy and share against the plan. Works offline, with kiosk mode; tests pass | ☐ PR #57 |
| Report leads with wrong answers; "too few to tell" | Anthony | The first card shows wrong answers *caused* by the cache, with a range, and the examples to check. The plan and re-tuning labels say when the range is too wide to call | ☐ PR #58 |
| Re-tuning at scale | Anthony | Protocol committed before the run. The held-out verdict is reported whatever it is | ☐ PR #59: **within ±3** (50.2% [48.6, 52.0]); 16 of 20 random splits within |
| Uneven repeats | Anthony | Protocol committed before the run. Easy topics 3×, with hard and uniform as checks | ☐ PR #59: all within ±3; the router barely tells topic levels apart |
| Reworded questions | Anthony + Spencer | 120 rewordings, hand-checked (≥ 95% keep meaning), lookups at each setting | ☐ PR #59. Hand check open in the shared sheet |
| Difference check (fix for the template finding) | Anthony | Protocol committed before the run. Wrong answers caused at 0.90 on MMLU, top of range below 1% | ☐ PR (final-polish): **0.49% [0.33, 0.66]**, down from 4.12% |
| Safe setting finder | Anthony | One command replays your traffic at each setting and recommends the loosest one under a wrong-answer limit; a card in the report | ☐ PR (final-polish) |

## Demo
<!-- Fill in after 4 Dec: what we showed, what worked live, what we faked. -->
- **Plan:** run the dashboard on ARC at 0.90, then 0.80, to show wrong answers appearing. Then on MMLU at 0.90 to show the template problem, and again with the difference check. The runs-compared table puts them side by side.
- **Backup:** a screen recording of the same run, in case the laptop or wifi fails.

## Retro
- **What worked:**
- **What broke:**
- **What we're changing next sprint:**

## Assumptions tested this sprint
| Assumption | Test | Result | Pivot? |
|---|---|---|---|
| Re-tuning the cutoff on traffic the router has seen brings the share back within ±3 on new questions | Re-tuning at scale: 6,875 MMLU test questions, held-out half | **Holds.** 50.2% [48.6, 52.0]; 16 of 20 random splits within | No |
| Easy questions repeating more push the router off its budget once the cache is on | Uneven repeats: easy topics 3× | **Not seen.** +0.3 [−0.5, +1.1]. The router scores topic levels almost the same, so this test is weak | No |
| 0.90 is a safe match setting | Wrong answers caused by the cache, ARC vs MMLU | **Fails on MMLU.** 4.1% caused, mostly templated questions | Yes: added the difference check (0.49%) and the setting finder |
| The semantic cache catches reworded questions | 120 rewordings | **Holds (pending hand check).** 111 of 120 at 0.90 (97 with the check); exact cache 0 | No |

## LLM chat links used this sprint
- Claude (dashboard, report changes, Sprint 4 experiments, difference check, setting finder): https://claude.ai/code/session_01GioLAAaYAGLNK4RQ84y99o
