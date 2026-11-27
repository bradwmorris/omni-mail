# Inside the d1-2B WeightSpace experiment

The writer was the model proposing weight edits. These source excerpts show how the original experiment told the writer what to improve and which examples it could inspect.

## Writer instructions

When resuming a search, the runner built this prompt. It kept the Yes cutoff at 0.50 and counted each missed action twice and each false alert once. The only editable tensor was `model.language_model.layers.23.feed_forward.w2.weight`.

```python
def _compact_search_prompt(self, feedback, *, retry):
    best = []
    for path in (self.run_dir / "validation").glob("pass-*/score.json"):
        item = read_json(path)
        metrics = item["metrics"]
        best.append((metrics["penalty"], metrics["missed"], item["pass"]))
    best.sort()
    instruction = "The previous hosted request timed out. Take one immediate next step." if retry else "Continue from disk."
    return (
        f"{instruction} d1-2B Needs Action. YES cutoff 0.50; penalty = 2*misses + false alerts. "
        f"{RUBRIC} Only edit {TENSOR}. Locally read notes.md and PRACTICE/replay.npz or training.jsonl as needed. "
        "Original training only; group-preserving five-fold replay for fitting. Refit on all training. "
        "Use load_original(name), load(name), save_edit(name,w). Test a new effective BF16 patch with "
        '{"type":"decide","model":"edited","validation":true} in a forward block. '
        "The response must contain a short reason followed by one fenced Python or forward block. "
        "If your current patch has not been scored and is promising, send the forward block now. "
        f"Budget: {self.budget.status()} "
        f"Best archived (penalty, misses, pass): {best[:5]}. "
        f"Latest feedback: {feedback[-(550 if retry else 1200):]}"
    )
```

When handing off a saved preflight test, the runner explicitly asked the writer to explain which error motivated its next edit.

```python
def _handoff(self, kernel_restarted):
    tested = self.run_dir / "preflight-tested.json"
    if tested.is_file():
        result = read_json(tested)["result"]
        return (f"Use the saved test result to revise the installed patch by saving a changed tensor {TENSOR}. "
                "Explain which observed error motivates the revision. Respond with one Python block. "
                f"Last test: {json.dumps(result)}")
```

## Training data supplied to the writer

The original runner wrote one JSON object per training email to `training.jsonl`. This is the code that assembled those rows.

```python
with (staged / "training.jsonl").open("w") as handle:
    for row in training:
        key = row["id"]
        print(json.dumps({"id": key, "input": experiment.fields[key], "label": row["needs_action"],
                          "group": experiment.groups[key], "fold": folds[key],
                          "stock_p_yes": stock[key]["p_yes"]}), file=handle)
```

Here is one example using an email and reviewed label from the [fictional notebook CSV](../omni-mail-lab/examples/sample-labels.csv). The fold and model score below are illustrative.

```json
{
  "id": "sample-01",
  "input": {
    "sender": "workshop@example.invalid",
    "subject": "Please confirm your seat",
    "body": "Could you reply by Friday to confirm your place in the workshop?"
  },
  "label": "yes",
  "group": "group-01",
  "fold": 0,
  "stock_p_yes": 0.32
}
```

At the 0.50 cutoff, a Yes score of 0.32 would mark this email No Action. The reviewed label is Yes because the recipient is asked to confirm a seat. The writer could see that mismatch from the email, label and score. The row contained no written explanation from the reviewer. The writer proposed an edit and the runner tested whether it reduced validation penalty without adding misses.
