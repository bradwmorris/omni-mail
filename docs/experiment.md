# Omni Mail experiment

[Back to Omni Mail](../README.md)

We tested whether small decision models could spot email that needed a reply
or another concrete step. We started with several categories, but a model
could pick the right topic and still miss the action. We switched to one
decision per email. The local models use a DSPy program to ask the question
and return a Yes score. A cutoff converts that score to **Action** or
**No Action**.

## Why we start with d1-2B

With the final shared prompt, stock d1-2B missed 11 of 47 actions. Stock
Omni 600M missed 26, and its selected patch missed 22. That is why we
start with d1-2B for local triage. Omni 600M offers a smaller model for
trying the same tuning workflow.
[Matched results](../README.md#results-on-400-emails)

## How we built the dataset

A small batch of recent arrivals showed why accuracy alone could be
misleading. Marking all 48 emails **No Action** would get 45 correct and
miss all three actions. We sought out more genuine action emails so we
could measure misses. After review, the dataset had **137 Action labels
out of 1,000**.

| Split | Emails | Action |
| --- | ---: | ---: |
| Training | 300 | 42 |
| Validation | 300 | 48 |
| Reserved comparison | 400 | 47 |

We grouped related threads and repeated templates so they stayed in one
split. The reserved comparison set combined 300 filtered recent arrivals
with 3 actions and 100 targeted examples with 44 actions. The 13.7% action
rate describes the full dataset from this personal inbox.

### How Sol helped with labels

Bradley used GPT-6.2 Sol to suggest a label and a short reason for each
email in a small batch. He reviewed the suggestions and turned recurring
disagreements into rules for the next batch. A routine sign-in notice is
usually **No Action**. A warning that asks you to recover access is
**Action**. As the dataset grew, he reviewed edge cases and applied
corrections to similar examples before freezing the labels.
[Batch labeling workflow](../omni-mail-lab/README.md#label-in-batches)

## What ReAnchor changed

ReAnchor fits a cutoff while holding the weights fixed. An email with a
Yes score of 0.46 is **No Action** at a 0.50 cutoff and **Action** at 0.43.
Lowering the cutoff can recover some missed actions and may also raise more
false alerts.
[DSPy ReAnchor documentation](https://dspy.ai/current/api/experimental/ReAnchor/)

- **Early d1-2B.** The 0.43 cutoff looked slightly better on 50 training
  emails. On the same 50 validation emails, 0.43 and 0.50 produced
  identical decisions, with two misses and three false alerts. We kept 0.50.
- **Omni 600M.** An early move from 0.50 to 0.40 recovered one action on
  validation without adding a false alert. With the larger dataset and
  shorter instruction, ReAnchor produced no validation gain. We kept 0.50.

## What WeightSpace changed

WeightSpace proposes edits to selected model weights. In the private
searches, we held the cutoff at 0.50 and chose patches on the 300
validation emails. The revised 600M search reused saved training
computations for diagnostics and used full model passes to score candidate
edits on validation.

| Validation comparison | Misses before → after | False alerts before → after | Penalty before → after |
| --- | ---: | ---: | ---: |
| Omni 600M, earlier patch → selected patch | 17 → 10 | 23 → 22 | 57 → 42 |
| d1-2B, stock → patch 20 | 7 → 6 | 31 → 21 | 45 → 33 |

The Omni 600M search scored 24 of 25 planned edits before hosted request
timeouts exhausted its budget. The resumed d1-2B search scored 25 of 25
edits and selected patch 20 on validation.

### Shared prompt comparison

The five runs in the README used the same 400 emails, final frozen
instruction, and 0.50 cutoff. Each 600M result combines 60 earlier pilot
scores with 340 new scores under the same wording. These emails informed
prompt development, so a fresh batch is needed for an independent test.
[Results on 400 emails](../README.md#results-on-400-emails)

The revised prompt reduced JEV's false alerts from 108 to 20 while
misses went from one to two. Under that same revised prompt, WeightSpace
reduced penalty from 82 to 71 for Omni 600M and from 48 to 31 for d1-2B.
Holding the prompt fixed makes the stock-to-patch bars a comparison of
the weight edits.

### Earlier short prompt

Here is what changed when we reran the same five configurations with the
final shared prompt. Penalty is twice the misses plus the false alerts.

| Model | Earlier short prompt | Final shared prompt |
| --- | ---: | ---: |
| Omni 600M, stock | 102 | 82 |
| Omni 600M, WeightSpace | 70 | 71 |
| d1-2B, stock | 63 | 48 |
| d1-2B, WeightSpace (patch 20) | 37 | 31 |
| JEV 1.14, stock via OpenRouter | 110 | 24 |

Earlier patches on those same 400 emails used the short prompt:

| Earlier patch | Correct / 400 | Missed / 47 | False alerts / 353 | Penalty |
| --- | ---: | ---: | ---: | ---: |
| Omni 600M, earlier patch | 333 | 30 | 37 | 97 |
| d1-2B, patch 1 | 372 | 8 | 20 | 36 |

Patch 20 was selected on validation and scored on the same 400 after
patch 1. The public comparison uses patch 20.

The app and teaching notebooks use the instructions in their
[model profiles](../omni_mail/profiles.py). The notebooks run the same
type of stock-to-profile comparison on fictional or user-supplied mail,
with their own group split and a smaller optional WeightSpace search.
[Run the teaching workflow](../omni-mail-lab/README.md)

GEPA optimization instructions coming soon.
