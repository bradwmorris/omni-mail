# Decision models

[Back to the Omni Mail walkthrough](../README.md)

## Set up local inference

Start with stock **d1-2B** for local triage. With the shared benchmark
prompt, it missed 11 of 47 actions. Stock Omni 600M missed 26, and its
selected patch missed 22. Check d1-2B on your own mail before relying on
its labels. [Matched results](../README.md#results-on-400-emails)

After [setting up the Python environment](install.md#build-the-app),
run the d1-2B download from the checkout root. Use a second terminal if the
app is running. Hugging Face saves the pinned checkpoint in its cache.

```sh
# d1-2B (recommended for Gmail, about 3.84 GB)
.venv/bin/hf download LiquidAI/d1-2B \
  config.json tokenizer.json tokenizer_config.json model.safetensors LICENSE \
  --revision 652f920e544ea37f81e4b0ce89b81d4ed0da90b1
```

Download Omni 600M separately if you want to use its lab notebook.

```sh
# Omni 600M (optional for the lab, about 2.35 GB)
.venv/bin/hf download LiquidAI/d1-omni-600M \
  config.json tokenizer.json tokenizer_config.json model.safetensors LICENSE \
  --revision 02b55d7076f15129e59ab3f94783f32c4b088674
```

[d1-2B model card](https://huggingface.co/LiquidAI/d1-2B) · [Omni 600M model card](https://huggingface.co/LiquidAI/d1-omni-600M) · [Hugging Face download guide](https://huggingface.co/docs/huggingface_hub/en/guides/cli#hf-download)

Reload the browser after the download and confirm **d1-2B** in the
**Decision model** picker. To test it on fictional mail, run
`.venv/bin/python -m omni_mail serve --mode sample-model --model d1-2b`.

## Use JEV

JEV runs through a provider API and works without downloading local model
weights. In the Gmail or local-model sample inbox, open the **Settings** cog
at the bottom left. Choose **OpenRouter** or **TypeSafe**, enter your provider
API key and click **Save key**. Click **JEV** in the toolbar or select your
saved provider in the decision model picker.

The key is stored in the app's private data directory. Omni Mail saves decisions separately for each provider. Clicking **Process** with JEV selected sends each
chosen message's sender and subject (up to 512 characters each) and up to
12,000 characters of body text to that provider. Provider usage may incur charges. [OpenRouter Jev](https://openrouter.ai/typesafe/jev-1.14) · [TypeSafe setup](https://docs.typesafe.ai/introduction/quickstart)

## How the decision works

For each thread, Omni Mail uses the sender, subject, and normalized body
of the newest received message still in the inbox. For Omni 600M and d1-2B,
a DSPy `Predict` call supplies the instructions and Yes/No question.
`dspy-wsp` runs the model on your Mac, and the profile's cutoff turns the Yes
score into **Action** or **No Action**. Both stock profiles start at 0.50.
JEV uses the d1-2B instruction and a 0.50 cutoff. The matched experiment
used a shared instruction across all models.
[Experiment setup](experiment.md#shared-prompt-comparison)
[Classifier code](../omni_mail/classifier.py)
