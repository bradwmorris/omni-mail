# Omni Mail Lab

Use the same local classifier as the app to answer one question about each
email. Does it require **Action**, or is it **No Action**? The notebooks show
how to measure the original model, adjust its decision cutoff, and optionally
use WeightSpace to edit a small part of its weights.

For the inbox, Gmail setup, or hosted JEV, start with the [app guide](../README.md).
Use the d1-2B notebook to improve your local inbox decisions. The Omni 600M
notebook is a smaller starting point for learning the same tuning workflow.

These are teaching notebooks. They use the app's model profiles, split
your data by group, and default to a small fictional fixture with WeightSpace
disabled. The private case study used a fixed 300/300/400 split, longer
WeightSpace searches, and a shared benchmark prompt across models. The
[experiment guide](../docs/experiment.md) reports those aggregate results.

## 1. Run a notebook on fictional email

Follow [app setup](../docs/install.md#build-the-app) to create the Python environment,
then [download your model](../docs/models.md#set-up-local-inference). From the
Omni Mail checkout, install and start Jupyter in that environment.
[Jupyter Notebook installation](https://jupyter.org/install#jupyter-notebook)

```sh
uv pip install --python .venv/bin/python notebook
.venv/bin/jupyter notebook
```

Open [Tune Omni 600M](tune-omni-600m.ipynb) or
[Tune d1-2B](tune-d1-2b.ipynb) in the `omni-mail-lab` folder. Run the cells
in order with the bundled [fictional CSV](examples/sample-labels.csv).
The default run measures the stock model, tests a fitted cutoff, and
exports and evaluates the selected profile locally. You can do all of that without a Gmail account or a Codex login.

## 2. Prepare your own examples

Follow [Gmail setup](../docs/gmail.md#connect-gmail) to authorize a read-only account.
Then export one message per matching inbox thread. The example limits
the export to 100 messages. The date range includes the first date and excludes the last date, in UTC.
Choose dates that match your inbox and a fresh filename for every export.

```sh
lab_data="$HOME/Library/Application Support/Omni Mail Lab"
mkdir -m 700 -p "$lab_data"
.venv/bin/python -m omni_mail export-mail "$lab_data/label-batch.csv" \
  --after 2026-01-01 --before 2026-02-01 --limit 100
```

For a named mailbox, put `--data-dir "/path/to/account-1"` before
`export-mail`. The CSV has six columns:

| Column | What it means |
| --- | --- |
| `id` | A unique message ID. Remove duplicates if you combine exports. |
| `group_id` | Which messages should stay together when split. The export starts with the Gmail thread ID. Give related threads and near-duplicate templates a shared group ID. |
| `sender`, `subject`, `body` | The three inputs to the decision. |
| `label` | Your reviewed decision. Enter `yes` for Action or `no` for No Action. |

When the labels are ready, set `mail_csv` in your notebook to the path of your
private CSV. The notebook needs at least nine distinct groups and enough
examples of both labels to put Action and No Action in each split. It
allocates about 60%, 20%, and 20% of groups to training, validation, and
the final comparison, so row counts can vary.

### Start with two labels

Use **Action** for a reply you owe, a concrete task, or a problem you need to
check. Use **No Action** for a routine update, a completed request, or an
optional offer. This gives you one useful inbox filter. With the same amount
of data, extra categories leave the small model fewer examples per label.

### Label in batches

Bradley used GPT-6.2 Sol to infer who owed the next step from the sender,
subject, and body. The useful part was discussing why its first guesses
were wrong. That turned personal judgment into rules it could apply to
new emails. Use email text you're comfortable sharing with your labeling
model.

1. Give the model your definitions and ask it to label **50–100 emails**.
   Ask for a short reason and a flag when the next step is unclear.
2. Review every label yourself. Explain why each mistake was wrong and turn
   recurring cases into rules. A routine sign-in alert can be **No Action**.
   A message that requires you to recover access is **Action**.
3. Repeat with a fresh batch. Check whether the updated rules match your
   judgment and refine them again.
4. Scale after the labels are consistent. Ask the model to present edge
   cases with the email, proposed label, and reason. Decide those yourself
   and apply each correction to similar examples before freezing the CSV.

Our final run used **1,000 emails**, including **137 Action labels
(13.7%)**. We deliberately collected additional action emails after a
small test batch turned out to have very few. Choose the size based on
having enough Action examples in each split to measure misses.
[See our split and label counts](../docs/experiment.md#how-we-built-the-dataset)

## 3. Understand what each notebook does

| Step | What you’ll see |
| --- | --- |
| Load the model and try one email | The app's DSPy signature passes sender, subject, and body to the selected model. You can see the decision and, when available, its Yes score. |
| Load and split your labels | Training examples are for error review and tuning. Validation decides whether a change is worth keeping. Related messages stay together, and the final split is reserved until export. |
| Run the stock baseline | The notebook times the training pass and shows missed actions and false alerts. A missed action costs two points and a false alert costs one. Change that tradeoff only if your inbox calls for it. |
| Run ReAnchor | ReAnchor picks a Yes-score cutoff using the training examples and keeps the weights fixed. The notebook accepts it only if validation penalty drops and missed actions stay flat or fall. |
| Optionally run WeightSpace | The Codex writer proposes edits to specific tensors at a fixed cutoff. WeightSpace searches using training examples. The notebook checks the resulting patch on local validation with the same acceptance rule. |
| Freeze and evaluate | Save the chosen profile, then compare the stock model and the reloaded profile on the same reserved examples. If a patch was accepted and the cutoff changed, the notebook also reports the cutoff-only result. |

The bundled fixture is small. Its numbers show that the workflow runs. Use
your own reserved emails to estimate how well the model works for your inbox.
Report missed actions and false alerts alongside totals.

ReAnchor is worth trying when missed actions score close to the current
cutoff. It can bring those emails into **Action** without touching the
weights. Keep the original cutoff if the fitted one gives the same
decisions on validation or adds too many false alerts. In our early
d1-2B run, changing 0.50 to 0.43 made no difference on validation.
[See the ReAnchor comparisons](../docs/experiment.md#what-reanchor-changed)

## 4. Enable the optional WeightSpace step

WeightSpace uses **Codex as the writer**. Install the
[Codex CLI](https://developers.openai.com/codex/cli#getting-started) and sign
in before enabling that cell. [WeightSpace package](https://pypi.org/project/dspy-wsp/0.2.0/)

```sh
codex login
codex login status
```

- Run the preview cell first. It shows the local training rows eligible
  for the writer, the tensors that can be edited, and the search budget.
- When you set `use_codex = True`, the writer can receive training email
  inputs and labels, model or tensor information, and feedback from the
  search. Validation and final email text remain local in this workflow.
- Leave `writer_model` blank to use the CLI default or supply a model ID
  available to your account. Start with the fictional fixture and a small
  `max_passes` budget. Set both in the preview cell before enabling the run.
- When a patch passes validation, the export includes a `selected-patch`
  folder with a manifest and tensor edits for that checkpoint. Keep it
  with the profile. If the edit fails validation, the notebook keeps the
  best cutoff-only profile from the earlier steps.

## 5. Load a profile in Omni Mail

The notebook prints the path to `profile.json`. Start with fictional mail
to confirm the profile loads in the app. For Omni 600M, use:

```sh
.venv/bin/python -m omni_mail serve --mode sample-model \
  --model omni-600m --profile "/path/to/run/profile.json"
```

Use `--model d1-2b` for the d1-2B profile or `--port 8766` if another
instance is using the default port. Click **Process remaining** or select
rows and click **Process selected** to try it. Once you're happy with it,
add the same `--profile` option to your Gmail launch command and choose
the matching `--model`. The profile replaces that model's stock entry for
the session. You can repeat `--profile` to load one for each local model. A patch is tied to
its original model checkpoint, and the profile references the patch's
saved path. Keep the run folder in place.

## Keep private data outside the repo

Use a private directory such as `~/Library/Application Support/Omni Mail Lab`
for exported emails, labels, runs, and profiles. If you open a checked-in
notebook against real mail, Jupyter can save displayed outputs back into that
notebook. Use a private copy for personal experiments and inspect notebook
outputs before sharing. Open that copy by starting Jupyter from your private
folder with `/path/to/omni-mail/.venv/bin/jupyter notebook`. In the first cell,
set `project = Path("/path/to/omni-mail")` to import the shared classifier.

The public lab contains the reusable notebooks and fictional fixtures.
Most new files inside the lab folder are ignored by Git. Keep your data
outside the checkout and review staged files before sharing changes.
