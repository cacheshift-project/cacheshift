# Target-user interviews (#14, assumption A1)

*Anthony Capraru and Spencer Aldrich · guide written 25 Oct 2026 · notes added below after each conversation*

**Who we are looking for** (see [SPRINT1.md §2](../../../SPRINT1.md#2-target-user)): a small-business owner, or as a
secondary group a student, whose own app, website or script calls an AI model (OpenAI, Anthropic or similar)
and who pays the per-use bill themselves. Someone who only uses ChatGPT or Claude in the browser does not qualify.

**What we need to learn (A1):** do they watch the AI bill closely enough to want a cache and a cheaper-model
router in front of it, and would they act on a report showing whether that costs answer quality?

**Pass line (from SPRINT1.md §7):** the person agrees to try a drift and cached-answer-quality report on a sample
of their own traffic. Saying they would use it is not enough.

## Candidates

| # | Who | How we reach them | Status |
|---|---|---|---|
| 1 | Local small-business owner with an AI chatbot or assistant on their site or app | | Not contacted |
| 2 | Second owner, or a freelancer who builds AI tools for small businesses | | Not contacted |
| 3 | BU student who has built an app on a paid AI API | | Not contacted |

## Outreach message

> Hi [name], I'm a BU engineering student working on a class project about lowering AI costs for small
> businesses. I saw that [business/app] uses [an AI chatbot / AI feature]. Could I ask you a few questions
> about how you run it? It takes 15 minutes, by phone or video, whenever suits you. No sales pitch: we're
> trying to learn whether the problem we're working on is real. Thanks! [name]

## Questions (15 minutes)

Ask about what they have actually done, not what they would do. Don't describe CacheShift until question 6.

1. **Their setup.** What does your AI feature do, roughly how many requests does it get a week, and which
   model or provider does it use?
2. **The bill.** What did it cost last month? How often do you look at the bill, and has it ever surprised you?
3. **What they've tried.** Have you done anything to bring the cost down, such as a cheaper model, shorter
   prompts or reusing answers? What happened?
4. **Quality.** How do you find out when the AI gives a customer a wrong or bad answer? When did that last happen?
5. **Trade-off.** If a setting cut the bill by a third but made one answer in fifty worse, would you take it?
   How would you decide?
6. **The report.** *(Show the [report mock-up](../Sprint_2/Report_Mockup.html): open the file in a browser, or print it.)* What would you do with this? Would you run it on a week
   of your own requests? *(The pass line: ask for a yes or no and what they'd need from us to do it.)*

End with: "Who else do you know who runs something like this?"

## Notes template (copy one block per conversation)

```
### [Name], [business or project], [date], [interviewer]
- Setup (Q1):
- Bill and how closely watched (Q2):
- Cost-cutting tried (Q3):
- How they catch bad answers (Q4):
- Trade-off answer (Q5):
- Reaction to the report; would they run it on their own traffic (Q6): yes / no / maybe, and conditions
- Referrals:
- What this means for A1:
```

## Notes

*None yet.*
