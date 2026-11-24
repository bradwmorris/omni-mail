# Contributing to Omni Mail

[Back to the Omni Mail walkthrough](README.md)

## Repository layout and local data

```text
README.md         End-to-end walkthrough
docs/             Installation, Gmail, model, and inbox guides
omni_mail/        Gmail sync, local inbox store, and shared classifier
web/              Inbox UI
omni-mail-lab/    Public tuning notebooks and fictional fixtures
licenses/         Notices for styles adapted from Commons
```

Keep real mail, label CSVs, run logs, notebook outputs, and personal profiles
in a private directory outside the checkout. The app defaults to
`~/Library/Application Support/Omni Mail` for Gmail tokens and inbox databases.
The downloaded model lives in the Hugging Face cache. Codex credentials are
managed by the Codex CLI. The public lab folder is for reviewed teaching
source and fictional examples only.

Before committing lab changes, use `git status --short --untracked-files=all`
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
