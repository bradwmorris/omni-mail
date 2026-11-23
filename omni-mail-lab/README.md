# Omni Mail Lab

This folder contains the notebooks and fictional examples for tuning either
classifier used in Omni Mail. Start with the
[main README](../README.md) for app and model setup.

## Run a notebook

Install the app environment and the model you want to use, then install
Jupyter and launch it from the checkout.

```sh
uv pip install --python .venv/bin/python notebook
.venv/bin/jupyter notebook
```

- [Tune Omni 600M](tune-omni-600m.ipynb)
- [Tune d1-2B](tune-d1-2b.ipynb)

The default cells use fictional mail and run locally. Enable the Codex writer
cell if you want to try WeightSpace with training examples you choose to share.

## Export a batch from Gmail

After connecting Gmail, create a private output directory and export a batch
of currently inboxed messages between two UTC dates. For a named mailbox,
pass its existing directory with `--data-dir` before `export-mail`.

```sh
lab_data="$HOME/Library/Application Support/Omni Mail Lab"
mkdir -m 700 -p "$lab_data"
.venv/bin/python -m omni_mail export-mail "$lab_data/label-batch.csv" \
  --after 2026-01-01 --before 2026-02-01 --limit 100
```

Choose dates that match your inbox. Fill the `label` column with `yes` for
Action and `no` for No Action. Keep the sender, subject, and body as text. Group
repeated templates by assigning the same `group_id` before you split the data.

## Start with two labels

For each email, ask whether it needs your attention. Use **Action** for a
reply, task, or concrete problem to check. Use **No Action** for a routine
update or a completed request. This gives you one useful inbox filter and
keeps the 600M model focused on a single decision. If you split the same
sample into more categories, each category gets fewer examples and the
model has more distinctions to learn.

## Label in batches

Here’s the approach Bradley used with GPT-6.2 Sol. Give the model your
definitions of **Action** and **No Action** up front.

1. **Label 50–100 emails.** Ask the model to suggest a label for each one.
2. **Review every label yourself.** Call out anything you think it got wrong
   and explain why. Turn those corrections into clearer instructions and
   examples for the next batch.
3. **Run another batch.** Give the model the updated instructions and a fresh
   set of emails. Review those labels and give it another round of feedback.
4. **Scale to around 1,500 emails.** Once the labels are mostly matching your
   judgment, ask the model to flag edge cases and explain what makes them hard
   to call. Go through those cases yourself and decide the final labels.

The labeling model helps you build the dataset. Omni 600M uses the reviewed
labels later, when you measure and tune its decisions.

## Notebook outline

1. **Try the classifier.** Run the same model and DSPy signature the app uses
   on a few fictional messages.
2. **Collect real examples.** Export a small batch from your Gmail inbox to
   a private directory and follow the [batch labeling workflow](#label-in-batches).
3. **Split the data and baseline it.** Keep related threads or repeated
   templates together. Use training for fitting, validation for choosing,
   and a final set for the comparison after the profile is frozen.
4. **Run ReAnchor.** Fit the cutoff on training predictions, then check
   missed actions and false alerts on validation.
5. **Try WeightSpace if you want to edit the weights.** Use the Codex
   adapter as the writer. Start from the accepted cutoff and use the
   original training emails you choose. Preview the writer input and
   budget before running.
6. **Export and verify.** Run the frozen versions on the final set and
   reload the chosen profile in Omni Mail.

## Where your work goes

Use a private directory outside the checkout, such as
`~/Library/Application Support/Omni Mail Lab`, for exported emails, labels,
personal notebooks, profiles, and tuning output. The teaching notebook in
this folder will use fictional messages by default. Review and clear cell
outputs before sharing a notebook that has been run on real mail.

Git stages the reviewed notebook paths and fictional sample CSV. New files in
this folder are ignored until their paths are reviewed and allowed. Keep personal experiments in your private directory
and contribute reusable teaching code or fictional examples here.
