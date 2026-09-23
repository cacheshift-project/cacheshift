# How we work

## Every change goes through a pull request

1. Start from an up-to-date `main`: `git checkout main && git pull`
2. Make a branch named for the work: `git checkout -b cache-threshold-sweep`
3. Commit small, clear steps.
4. Push the branch and open a pull request on GitHub.
5. Tests must pass, and the other teammate reviews and approves before merging.

`main` is protected: nobody pushes to it directly.

## Rules from our proposal (these apply to every change)

- **Correct answers are never decided by an AI.** They come only from the benchmarks' human-written answer keys.
- **One change per experiment.** If two settings change at once, we can't tell which one caused the result.
- **A margin of error on every number** (95% confidence intervals; five seeds for anything random).
- **Cost, energy and quality in separate columns**, never combined into one score.
- **Tuning and test sets are fixed in advance**, with all rewordings of a question kept on the same side.
- **Every claim is limited** to the models, versions and data we actually used.

## Secrets

API keys go in `.env` only. If a key is ever committed by mistake, revoke it at the provider immediately; deleting the commit is not enough.

## Writing

Everything we submit is in our own words. When an LLM helps, note it in the sprint's LLM log with a chat link.
