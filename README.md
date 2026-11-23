# Omni Mail

Omni Mail is a local inbox for reviewing Gmail. It puts your threads in one
compact list and uses a small model on your Mac to flag mail that might need
your attention. Open a thread to read the conversation. Gmail is where you
reply and manage your mail.

Use **All** to see the synced inbox, **Action** to see what the model flagged,
and **No Action** to see the messages it judged as requiring no action.
Messages with a pending or unavailable decision remain visible in **All**.

## V1 scope and status

- **Mail provider:** Gmail with read-only access. Connect one or more accounts.
- **Local models:** Omni 600M by default, with d1-2B as a second option. Both run on Apple silicon Macs.
- **Optional tuning:** The [Omni Mail Lab](omni-mail-lab/README.md) uses DSPy
  and documents the Codex adapter as its writer option.
- **Try it first:** Sample mode opens with fictional mail and preset decisions.
  It works without Gmail, weights, or a Codex login.

## Try the sample inbox

Use Node.js 22 and Python 3.12 for the V1 setup. From the checkout root:

```sh
npm --prefix web ci
npm --prefix web run build
python3 -m omni_mail serve
```

Open [Omni Mail](http://127.0.0.1:8765). Use the filters or open a thread to see
how the reader works. The server listens on your Mac's loopback address. Use
`--port 8766` if the default port is already in use.

## Set up local inference

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and
create a project environment with the release's pinned dependencies.
The first release is verified on Apple silicon with macOS 26 and Python 3.12.

```sh
uv venv --python 3.12
uv pip sync --python .venv/bin/python requirements.lock
```

Download the model you want to use into the Hugging Face cache. Omni 600M's
weights take about 2.35 GB and d1-2B's take about 3.84 GB. Each command downloads the files for one pinned
checkpoint.

```sh
# Default model
.venv/bin/hf download LiquidAI/d1-omni-600M \
  config.json tokenizer.json tokenizer_config.json model.safetensors LICENSE \
  --revision 02b55d7076f15129e59ab3f94783f32c4b088674

# Optional second model
.venv/bin/hf download LiquidAI/d1-2B \
  config.json tokenizer.json tokenizer_config.json model.safetensors LICENSE \
  --revision 652f920e544ea37f81e4b0ce89b81d4ed0da90b1
```

[Omni 600M model card](https://huggingface.co/LiquidAI/d1-omni-600M) · [d1-2B model card](https://huggingface.co/LiquidAI/d1-2B) · [Hugging Face download guide](https://huggingface.co/docs/huggingface_hub/en/guides/cli#hf-download)

Run the sample messages through the local model before connecting Gmail:

```sh
.venv/bin/python -m omni_mail serve --mode sample-model
```

The **Decision model** picker switches between downloaded models once the
current pass finishes. To start with d1-2B, add `--model d1-2b` to the serve
command. The model works in the background and **All** stays readable while
**Action** and **No Action** fill in. Refresh and model switching reuse saved
decisions for unchanged messages with the exact same profile.

## Connect Gmail

1. Create or select a Google Cloud project. Enable **Gmail API** in that exact
   project. If two projects have similar names, check the project ID or number
   before enabling it.
2. Set up the OAuth consent screen. If the app is in External Testing, add
   each Gmail account you plan to connect as a test user.
3. Create an OAuth client of type **Desktop app**. Download its JSON file and
   save it in a private folder outside the checkout.
4. Run the authorize command and choose the Gmail account in your browser.
   Check that the consent screen requests read-only Gmail access.
   [Google's Gmail setup guide](https://developers.google.com/workspace/gmail/api/quickstart/python)

For one account, run this after local inference works:

```sh
.venv/bin/python -m omni_mail authorize /path/to/your/client_secret.json
.venv/bin/python -m omni_mail serve --mode gmail
```

To combine two accounts, authorize each into a separate private directory.
Choose a different account at each consent screen.

```sh
omni_data="$HOME/Library/Application Support/Omni Mail"
.venv/bin/python -m omni_mail --data-dir "$omni_data/account-1" authorize /path/to/your/client_secret.json
.venv/bin/python -m omni_mail --data-dir "$omni_data/account-2" authorize /path/to/your/client_secret.json
.venv/bin/python -m omni_mail serve --mode gmail --mailbox account-1 --mailbox account-2
```

The inbox shows up to 50 threads per account. Each account has its own token,
mail cache, and decisions. If Google asks you to reconnect, repeat the
authorize command for that account. External Testing can issue refresh
tokens that expire after seven days. [Google's token expiration rules](https://developers.google.com/identity/protocols/oauth2#expiration)

## How the decision works

Omni Mail reads the newest received message still in the inbox for each
thread. It passes the sender, subject, and normalized body to one DSPy
`Predict` call. DSPy defines the inputs, the Action rubric, and the Yes/No
output. `dspy-wsp` runs the model locally and returns the Yes score. DSPy uses
the profile's cutoff to turn that score into a label. The thread reader can
show the full conversation.

An Action can be an owed reply, an outstanding task, or a concrete problem
the email asks you to check. A routine update, receipt, or optional offer
normally falls under No Action. Review both filters while you get to know
the classifier. A small model can miss an action or flag an email that
needs nothing from you.

The defaults use the original weights and a 0.50 cutoff. A classifier version
records the model revision, prompt, encoder, cutoff, and patch digest if one is
used. Changing the profile gives cached mail its own fresh set of decisions. [DSPy backend package](https://pypi.org/project/dspy-wsp/0.2.0/)

## Tune it on your own mail

Start with two labels, **Action** and **No Action**. The most useful first
decision is whether an email needs your attention. A reply you owe and a
payment you need to fix both get **Action**. A receipt you can file gets
**No Action**. With more categories, the 600M model has to learn finer
distinctions from fewer examples per label. Two labels also make it easy to
check the two mistakes that matter here: missed actions and unnecessary alerts.

The [Omni 600M notebook](omni-mail-lab/tune-omni-600m.ipynb) and
[d1-2B notebook](omni-mail-lab/tune-d1-2b.ipynb) walk through a baseline,
ReAnchor, optional WeightSpace, and export to an app profile.
[Omni Mail Lab](omni-mail-lab/README.md) shows how to collect a private Gmail sample. Start with a few fictional messages to learn the workflow, then tune
on your own labeled emails.

For labeling, start with 50–100 emails. Have a capable model suggest labels,
review every label yourself, and explain any corrections. Repeat with a fresh
batch before scaling to around 1,500 emails. At that scale, ask the model to
bring the edge cases back to you for review. [Batch labeling workflow](omni-mail-lab/README.md#label-in-batches)

Use the **Codex adapter** for hosted writer steps in V1. Install the Codex
CLI using the [official OpenAI installation guide](https://developers.openai.com/codex/cli#getting-started).
Sign in with ChatGPT and check the sign-in before opening that part of the
notebook:

```sh
codex login
codex login status
```

Baseline scoring and ReAnchor run locally. The Codex writer is optional.
When you explicitly run it, the adapter can send the selected training
examples to Codex. Review the writer input and budget first. Validation
supplies scores for selecting candidates. Keep the final evaluation
set sealed until the profile is frozen. [Official OpenAI documentation for Codex sign-in](https://learn.chatgpt.com/docs/developer-commands#codex-login)

## Load your profile

The notebook prints the path to your exported profile. Pass it to
`serve` with `--profile`. The profile replaces the settings for its model in
the picker. Use `--profile` twice to supply one profile per model.

```sh
.venv/bin/python -m omni_mail serve --mode sample-model --profile /path/to/profile.json
```

A profile references its optional patch file on disk. Keep it with the
weights it was built on. Omni Mail checks the checkpoint revision, patch file
hashes, and the original tensor hashes before applying an edit.

## Evaluation results

In the local Omni 600M experiment, the selected edit missed 20 actions and
raised 30 false alerts on a 400-email reserved comparison. The previous edit
missed 30 actions and raised 37 false alerts. This compares two tuned profiles
from one inbox dataset. An earlier stock-prompt run had scored those rows.
The app's original-weight profiles are separate from that experiment.

## Repository layout and local data

```text
README.md         Setup, use, and contribution guide
omni_mail/        Gmail sync, local inbox store, and shared classifier
web/              Inbox UI
omni-mail-lab/    Public teaching notebook and synthetic fixtures
licenses/         Notices for styles adapted from Commons
```

Keep real mail, label CSVs, run logs, notebook outputs, and personal profiles
in a private directory outside the checkout. The app defaults to
`~/Library/Application Support/Omni Mail` for Gmail tokens and inbox databases.
The downloaded model lives in the Hugging Face cache. Codex credentials are
managed by the Codex CLI. The public lab folder is for reviewed teaching
source and fictional examples only.

Before the first public commit, use `git status --short --untracked-files=all`
and review `git diff --cached --name-only` and `git diff --cached`. Verify that
the staged files contain no credentials, personal paths, inbox text,
notebook outputs from real mail, or weight files. Ignore rules help with
normal staging. They cannot remove an already tracked file or prevent a
force-add.

## Contributing

Contributions are welcome. If you'd like to extend Omni Mail to another mail
provider, add another writer adapter, or improve the local model setup, open
an issue or a pull request. For bugs, tell us which mode and version you ran,
what you expected, and what happened. Use a made-up message for anything
that needs an email example.

The app code is covered by the [project licence](LICENSE). See the
[Commons notices](licenses/NOTICE.md) for reused design code and each
model card for the separately downloaded weights.
