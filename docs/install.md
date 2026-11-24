# Install Omni Mail

[Back to the Omni Mail walkthrough](../README.md)

## How it works

- **Browser interface.** React and TypeScript render the inbox, filters,
  and thread reader. Vite builds those files. The Python app serves them
  at `http://127.0.0.1:8765` on your Mac.
- **Mail sync.** The Python app uses Gmail's read-only API when you click
  **Sync mail**. It saves the synced threads and decisions in SQLite,
  in a separate directory for each Gmail account.
- **Processing.** Click **Process** to run the selected model on the newest
  received inbox message in each chosen thread. With a local model, the
  decision runs on your Mac. With JEV, Omni Mail sends those message inputs
  to the provider you picked. Each model or profile has its own saved
  decisions. [Decision models](models.md#how-the-decision-works)

## Build the app

Use Node.js 22 and Python 3.12. From the checkout root:

```sh
npm --prefix web ci
npm --prefix web run build
```

For Gmail or local inference, install
[uv](https://docs.astral.sh/uv/getting-started/installation/) and create the
Python environment. V1 was verified on Apple silicon with macOS 26.

```sh
uv venv --python 3.12
uv pip sync --python .venv/bin/python requirements.lock
```

## Try the sample inbox

After [building the frontend](#build-the-app), run:

```sh
python3 -m omni_mail serve
```

Open [Omni Mail](http://127.0.0.1:8765). The sample inbox uses fictional mail
and preset decisions. It runs without weights or account setup. If the
default port is busy, pass `--port 8766` and open that port instead.
