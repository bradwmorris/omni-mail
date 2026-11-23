"""Small shared helpers for the public notebooks."""

import csv
import json
import re
import subprocess
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory

import dspy

from .classifier import INPUTS
from .profiles import read_patch_hashes


def load_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    required = {"id", "group_id", "label", *INPUTS}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("Use the CSV columns id, group_id, sender, subject, body, label.")
    for row in rows:
        row["label"] = row["label"].strip().casefold()
        if row["label"] not in {"yes", "no"} or not row["id"] or not row["group_id"]:
            raise ValueError("Each row needs an ID, a group, and a reviewed yes or no label.")
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Message IDs must be unique.")
    return rows


def split_rows(rows, seed=42):
    groups = defaultdict(list)
    for row in rows:
        groups[row["group_id"]].append(row)
    keys = sorted(groups)
    if len(keys) < 9:
        raise ValueError("Use at least nine distinct email groups for this walkthrough.")
    rng = Random(seed)
    train_end = int(len(keys) * 0.6)
    validation_end = int(len(keys) * 0.8)
    for _ in range(100):
        rng.shuffle(keys)
        splits = tuple([row for key in segment for row in groups[key]] for segment in
                       (keys[:train_end], keys[train_end:validation_end], keys[validation_end:]))
        if all({row["label"] for row in split} == {"yes", "no"} for split in splits):
            return splits
    raise ValueError("Could not put both labels in each split. Collect more groups with actions.")


def examples_for(model, rows):
    examples = []
    for row in rows:
        fields = {key: row[key] for key in INPUTS}
        if model.profile.key == "omni-600m":
            fields = model.backend.fit_inputs(fields, model.profile.instructions)
        examples.append(dspy.Example(**fields, label=row["label"]).with_inputs(*INPUTS))
    return examples


def predict(program, examples):
    return [program(**example.inputs()).needs_action.value for example in examples]


def score(examples, decisions):
    missed = sum(example.label == "yes" and not yes for example, yes in zip(examples, decisions, strict=True))
    alerts = sum(example.label == "no" and yes for example, yes in zip(examples, decisions, strict=True))
    return {"count": len(examples), "missed": missed, "false_alerts": alerts, "penalty": 2 * missed + alerts}


def action_credit(example, prediction, trace=None):
    correct = prediction.needs_action.value == (example.label == "yes")
    return float(correct) * (1.0 if example.label == "yes" else 0.5)


class CodexWriter:
    """Use a signed-in Codex CLI for writer replies in an empty directory."""

    def __init__(self, model):
        self.model = model

    def __call__(self, *, messages):
        with TemporaryDirectory(prefix="omni-writer-") as directory:
            reply = Path(directory) / "reply.txt"
            settings = {
                "forced_login_method": "chatgpt", "approval_policy": "never",
                "web_search": "disabled", "project_doc_max_bytes": 0,
                "memories.use_memories": False, "memories.generate_memories": False,
                "skills.include_instructions": False, "skills.bundled.enabled": False,
                "include_environment_context": False, "include_apps_instructions": False,
                **{f"features.{item}": False for item in (
                    "shell_tool", "unified_exec", "apply_patch_freeform", "multi_agent",
                    "apps", "plugins", "remote_plugin", "code_mode", "js_repl",
                    "browser_use", "computer_use", "tool_search",
                )},
            }
            command = [
                "codex", "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
                "--skip-git-repo-check", "--sandbox", "read-only", "--cd", directory,
                "--output-last-message", str(reply),
            ]
            if self.model:
                command.extend(("--model", self.model))
            for key, value in settings.items():
                command.extend(("-c", f"{key}={json.dumps(value)}"))
            result = subprocess.run(
                [*command, "-"], input=json.dumps(messages), text=True,
                capture_output=True, timeout=420, check=False, cwd=directory,
            )
            if result.returncode or not reply.is_file():
                raise RuntimeError("Codex writer failed. Check `codex login status` and the chosen writer model.")
            answer = reply.read_text(encoding="utf-8").strip()
            if not answer:
                raise RuntimeError("Codex writer returned an empty reply.")
            return [answer]


def tune_weights(model, program, train, validation, run_dir, writer_model, max_passes, cutoff):
    from dspy_wsp import WeightSpace

    names = (("head.scorer.0.weight", "head.scorer.0.bias", "head.scorer.3.weight")
             if model.profile.key == "omni-600m" else ("model.language_model.layers.23.feed_forward.w2.weight",))
    pattern = "|".join(map(re.escape, names))
    optimizer = WeightSpace(
        metric=action_credit, writer_lm=CodexWriter(writer_model), backend=model.backend,
        run_dir=run_dir, max_passes=max_passes, max_turns=max_passes * 3,
        holdout=0, seed=42, protected=(rf"^(?!(?:{pattern})$).*$",),
        sandbox="auto", simulate_head=True,
        task_description="Edit the decision weights to reduce missed actions and false alerts. Keep the cutoff fixed.",
    )
    baseline = score(validation, predict(program, validation))
    compiled = optimizer.compile(program, trainset=train)
    candidate = score(validation, predict(compiled, validation))
    print("Validation baseline:", baseline, "patch:", candidate)
    patch = compiled.wsp_patch
    if not patch.names or candidate["penalty"] >= baseline["penalty"] or candidate["missed"] > baseline["missed"]:
        return None
    path = patch.save(run_dir / "selected-patch")
    return replace(model.profile, cutoff=cutoff, patch=path, patch_hashes=read_patch_hashes(path))
