"""Classifier settings shared by the app and local notebooks."""

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path

OMNI_INSTRUCTIONS = (
    "Answer YES if the latest message leaves the recipient a reply or concrete step to take, "
    "or reports a specific problem with their account, order, service, or project that needs "
    "attention. Answer NO for optional offers, routine updates, completed requests, someone "
    "else’s next step, and automated run-failure notices."
)
D1_INSTRUCTIONS = (
    "Decide from the sender, subject, and body whether this email needs the recipient's attention. "
    "Say yes for an outstanding reply or step the recipient owes, or a concrete problem to "
    "check involving an account, order, service, or project that the email indicates is theirs "
    "or their team's. A failed payment, blocked deployment, impending loss of access, or "
    "account security warning can qualify even if it can wait. An optional purchase, sales "
    "follow-up, routine update, completed request, or a conversation where someone else owes "
    "the next step is no."
)
QUESTION = "From the email alone, does this require action?"
PATCH_FILES = ("manifest.json", "edit.npz")


@dataclass(frozen=True)
class Profile:
    key: str
    label: str
    repo: str
    revision: str
    encoder: str
    instructions: str
    cutoff: float = 0.5
    question: str = QUESTION
    patch: Path | None = None
    patch_hashes: tuple[str, ...] = ()

    @property
    def version(self):
        state = (self.repo, self.revision, self.encoder, self.instructions,
                 self.cutoff, self.question, self.patch_hashes)
        return hashlib.sha256(json.dumps(state).encode()).hexdigest()


STOCK = {
    "omni-600m": Profile("omni-600m", "Omni 600M", "LiquidAI/d1-omni-600M",
                         "02b55d7076f15129e59ab3f94783f32c4b088674", "omni-v2", OMNI_INSTRUCTIONS),
    "d1-2b": Profile("d1-2b", "d1-2B", "LiquidAI/d1-2B",
                     "652f920e544ea37f81e4b0ce89b81d4ed0da90b1", "d1-2b-v1", D1_INSTRUCTIONS),
}


def read_patch_hashes(directory):
    return tuple(hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in PATCH_FILES)


def load_profile(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    default = STOCK[data["model"]]
    if data["revision"] != default.revision or data.get("encoder", default.encoder) != default.encoder:
        raise ValueError("The profile targets an unsupported checkpoint or encoder.")
    instructions = data["instructions"]
    question = data.get("question", QUESTION)
    cutoff = data.get("cutoff", 0.5)
    if (not isinstance(instructions, str) or not instructions.strip()
            or not isinstance(question, str) or not question.strip()
            or type(cutoff) not in (float, int) or not 0 <= cutoff <= 1):
        raise ValueError("The profile needs instructions, a question, and a cutoff between 0 and 1.")
    patch = None
    hashes = ()
    if data.get("patch"):
        patch = (path.parent / data["patch"]["directory"]).resolve()
        hashes = tuple(data["patch"]["sha256"][name] for name in PATCH_FILES)
        if read_patch_hashes(patch) != hashes:
            raise ValueError("The patch files do not match the profile hashes.")
    label = default.label + (" · local patch" if patch else " · local profile")
    return replace(default, label=label, instructions=instructions, question=question,
                   cutoff=cutoff, patch=patch, patch_hashes=hashes)


def save_profile(path, profile):
    data = {
        "model": profile.key, "revision": profile.revision, "encoder": profile.encoder,
        "instructions": profile.instructions, "question": profile.question, "cutoff": profile.cutoff,
    }
    if profile.patch:
        data["patch"] = {"directory": str(profile.patch.resolve()),
                         "sha256": dict(zip(PATCH_FILES, read_patch_hashes(profile.patch)))}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
