Run an autonomous research experiment on the given topic.

1. Read existing code and data to understand the current state.
2. Propose a modification that might improve results.
3. Apply the change.
4. Run the experiment to measure impact.
5. If the result improved, keep the change. If not, revert.
6. Record the result and repeat.

Submit a JSON result with:
- experiments: list of what was tried and the outcome
- best_result: the best metric achieved
- changes_kept: list of changes that improved results
