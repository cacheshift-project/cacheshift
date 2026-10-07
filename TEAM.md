# TEAM.md — how we work together

*CacheShift · EC601 Fall 2026 · Agreed on ____ by Spencer Aldrich and Anthony Capraru. Items marked **[confirm]** are proposals until we both approve this file.*

## Members

| Name | GitHub | Email |
|---|---|---|
| Spencer Aldrich | @spaldrich13 | spenceraldrich132@gmail.com |
| Anthony Capraru | @capraruanthony | anthonycapraru@gmail.com |

**Communication channel:** ____ (link: ____) **[confirm]**. This is the only channel for project talk. Decisions made anywhere else get written here or in the relevant issue.

## Roles

Each of us owns one half of the project end to end and reviews every pull request the other opens. Full detail and the two handoff formats: [`docs/Team_Roles.md`](docs/Team_Roles.md).

| | Owns |
|---|---|
| **Anthony** | The **gateway**: server, cache, router connection, replay and live modes, request log |
| **Spencer** | The **measurement**: test set, experiments, drift and wrong-answer metrics, statistics |
| **Both** | User conversations, sprint reports, demos, poster, and reviewing each other's code |

**Sprint lead** (rotates; plans the sprint, runs the meetings, submits the sprint deliverables, breaks ties):

| Sprint 1 | Sprint 2 | Sprint 3 | Sprint 4 | Sprint 5 |
|---|---|---|---|---|
| ____ **[confirm]** | the other person | alternate | alternate | alternate |

## Cadence **[confirm]**

- **Weekly meeting:** right after class, 20–30 minutes: board review, blockers, next week's tasks.
- **Mid-week check-in:** one short message in our channel each Thursday: done, doing, blocked.
- **Reply time:** within 24 hours on weekdays, within 48 hours on weekends.
- **The board is the truth:** move your cards before each meeting, so either of us can see who is doing what without asking.

## Decisions **[confirm]**

1. **Your half, your call.** The owner of a piece decides how to build it, after hearing the other person out.
2. **Shared things need both of us:** the two handoff formats, project scope, and anything we submit for a grade.
3. **If we still disagree,** the sprint lead decides.
4. **Write it down.** Every decision goes in the relevant issue or pull request, with one line on why.

## Silence **[confirm]**

If one of us goes quiet:

1. **After 2 days** with no reply: a direct message ("Are you OK? Here's what's blocked").
2. **After 3 days:** a call or text. Urgent tasks can be picked up by the other person so the sprint keeps moving; say so in the issue.
3. **At the next meeting:** talk about it and adjust the plan.
4. **The professor** only hears about it if none of the above works and a deadline is at risk.

Planned absences (exams, travel, interviews) are posted in the channel in advance.

## How we write code

- Nobody pushes to `main`. One branch per story → pull request → the other person reviews → merge. `main` is protected on GitHub, so tests must pass and one approval is required.
- Setup is reproducible: `pip install -r requirements.txt`, and API keys only in `.env` (copy `.env.example`, never commit it).
- Details and project rules: [`CONTRIBUTING.md`](CONTRIBUTING.md).

## AI use

We each use an LLM (Spencer: Claude; Anthony: ChatGPT). As the course requires, chat links for anything we submit go in the repo, and each sprint plan is reviewed by both models (see `docs/sprints/Sprint_1/AI_Review_Log.md`). We are responsible for everything we commit, whoever or whatever drafted it.
