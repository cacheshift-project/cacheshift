# Target-user interviews (#14, assumption A1)

*Anthony Capraru and Spencer Aldrich · guide written 25 Oct 2026 · notes added below after each conversation*

**Who we are looking for** (see [SPRINT1.md §2](../../../SPRINT1.md#2-target-user)): **the builder**, the person who
builds and runs an AI feature for a small business from code they control (a freelancer or small agency, a solo
developer, or a startup's one technical person). As a secondary group: **a student** who has built on a paid AI API.
An owner is worth talking to only if someone they work with can change the address their app calls. Someone who
only uses ChatGPT or Claude in the browser, or a hosted chatbot they cannot reconfigure, does not qualify.

**What we need to learn (A1):** do they (or their client) watch the AI bill closely enough to want a cache and a
cheaper-model router in front of it, and would they act on a report showing whether that costs answer quality?

**Pass line (SPRINT1.md §7):** three conversations. A1 holds if at least one of the three agrees to try a drift and
cached-answer-quality report on a sample of their own traffic. Saying they would use it is not enough. If none
does by the end of Sprint 2, we change direction.

## Candidates

| # | Who | How we reach them | Status |
|---|---|---|---|
| 1 | Freelancer who builds AI chatbots for small businesses | Upwork or Fiverr profiles offering "AI chatbot" work | Not contacted |
| 2 | Small web/AI agency, or a solo developer or startup's one technical person | Local agencies' sites, BU/Boston startup groups | Not contacted |
| 3 | BU student who has built an app on a paid AI API | Class Slack/Discord, Spark!, hackathon projects | Not contacted |

## Outreach message

> Hi [name], I'm a BU engineering student working on a class project about keeping AI costs down for small
> businesses. I saw that you [build AI chatbots for small businesses / built (app) on (OpenAI/Claude)]. Could
> I ask you a few questions about how you run it? It takes 15 minutes, by phone or video, whenever suits
> you. No sales pitch: we're trying to learn whether the problem we're working on is real. Thanks! [name]

## Questions (15 minutes)

Ask about what they have actually done, not what they would do. Don't describe CacheShift until question 6.

1. **Their setup.** What does the AI feature do, which model or provider does it use, and **roughly how many
   requests does it get a month?** **Who set it up, and could they change the web address it calls?**
2. **The bill.** Who pays it, you or the client? What did it cost last month? How often does anyone look at
   it, and has it ever surprised you?
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
