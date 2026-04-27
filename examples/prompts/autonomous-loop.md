# Autonomous Loop

How to run as an autonomous agent that iterates until the goal is met.
Based on [autoresearch](https://github.com/karpathy/autoresearch).

## The Loop

```
LOOP:
  1. Read the current state → verify: understand what exists
  2. Propose a change with a hypothesis → verify: hypothesis is testable
  3. Apply the change → verify: change is minimal and correct
  4. Check the result → verify: result is measurable
  5. Compare to the goal:
     - If improved → keep, record what worked
     - If equal or worse → revert, record what didn't work
  6. Repeat
```

## Rules

- **One change at a time.** Don't change multiple things simultaneously.
- **Keep changes small and reversible.** If something breaks, you can undo.
- **Record every attempt.** Including failures — they're useful data.
- **Never stop.** If you run out of ideas, re-read the context for new angles.
- **If something crashes, fix it or skip it.** Don't get stuck.
- **Simplicity wins.** A small improvement from removing code is better than a large improvement from adding complexity.

## When to Call submit_result

Call submit_result when:
- The goal is achieved and verified.
- You've exhausted your approaches and have the best result so far.
- You've hit the iteration or token limit and need to report what you have.

Always include in your result:
- What you tried
- What worked and what didn't
- The final outcome
