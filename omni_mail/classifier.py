"""Run the shared DSPy email decision on either supported local model."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Lock

import dspy
from dspy.experimental import Noul
from dspy_wsp.backends.decision import D1Backend, D1LMBackend
from dspy_wsp.decision.families.d1_lm import encoding as d1_encoding
from dspy_wsp.decision.families.d1_omni import encoding as omni_encoding
from dspy_wsp.decision.schema import Question
from dspy_wsp.patch import Patch
from huggingface_hub.constants import HF_HUB_CACHE

from .profiles import QUESTION, read_patch_hashes

INPUTS = ("sender", "subject", "body")
V2_CONTEXT_OVERHEAD = 139
OMISSION = "\n\n[Middle of email omitted to fit Omni context.]\n\n"


def inbox_request(state, questions):
    fields = state["inputs"]
    question = questions["needs_action"]
    if tuple(fields) != INPUTS or state.get("demos") or question.type != "noul":
        raise ValueError("Expected sender, subject, and body and one YES/NO decision.")
    return fields, replace(question, instructions=state["instructions"])


class InboxD1Backend(D1LMBackend):
    def _encode_request(self, state, questions):
        fields, question = inbox_request(state, questions)
        encoded = super()._encode_request(fields, {"needs_action": question})
        full = d1_encoding.prefix(self.tok, fields) + d1_encoding.suffix(self.tok, question, self.scheme)
        if len(encoded) != 1:
            raise ValueError("Expected one request for the action decision.")
        row, names = encoded[0]
        if names != ["needs_action"] or row.ids != self.tok.encode(full):
            raise ValueError("The native request differs from the complete input.")
        return encoded


class InboxOmniBackend(D1Backend):
    def text_ids(self, text):
        return self.tok.encode(omni_encoding.escape(text))

    def delimiter(self, name):
        return self.tok.token_id(omni_encoding.DELIM[name])

    def _encode_request(self, state, questions):
        fields, question = inbox_request(state, questions)
        state_ids = self.text_ids(omni_encoding.serialize(fields))
        ids = [self.tok.bos_token_id, self.delimiter("state"), *state_ids,
               self.delimiter("q"), *self.text_ids(question.instructions)]
        markers = []
        for option in omni_encoding.render_options(question):
            markers.append(len(ids) + 1)
            ids.extend([self.delimiter("opt"), self.tok.token_id(omni_encoding.MARKER),
                        *self.text_ids(" " + option), self.delimiter("opt_end")])
        ids.append(self.delimiter("decide"))
        if len(ids) > self.max_length:
            raise ValueError(f"Message exceeds the {self.max_length:,}-token context.")
        return [((ids, markers, question), ["needs_action"])]

    def fit_inputs(self, fields, instructions):
        # Match the long-email preparation used for the V2 scores.
        question = Question(type="noul", instructions=instructions)
        overhead = 4 + len(self.text_ids(question.instructions)) + sum(
            3 + len(self.text_ids(" " + option)) for option in omni_encoding.render_options(question)
        )

        overhead = max(overhead, V2_CONTEXT_OVERHEAD)

        def fits():
            return overhead + len(self.text_ids(omni_encoding.serialize(fields))) <= self.max_length

        if fits():
            return fields
        body = fields["body"]

        def shortened(keep):
            head = (4 * keep + 4) // 5
            return body[:head] + OMISSION + body[len(body) - (keep - head):]

        low, high = 0, max(0, len(body) - 1)
        while low < high:
            keep = (low + high + 1) // 2
            fields["body"] = shortened(keep)
            if fits():
                low = keep
            else:
                high = keep - 1
        fields["body"] = shortened(low)
        if not fits():
            raise ValueError("The message headers exceed the Omni context.")
        return fields


class ClassifyEmail(dspy.Signature):
    sender: str = dspy.InputField()
    subject: str = dspy.InputField()
    body: str = dspy.InputField()
    needs_action: Noul = dspy.OutputField(desc=QUESTION)


def decision_program(backend, profile, *, cache=False):
    signature = ClassifyEmail.with_instructions(profile.instructions).with_updated_fields(
        "needs_action", desc=profile.question
    )
    program = dspy.Predict(signature)
    program.set_lm(backend.lm(cache=cache))
    program.fields["needs_action"] = {"threshold": profile.cutoff}
    return program


def checkpoint_path(profile):
    cached = Path(HF_HUB_CACHE) / ("models--" + profile.repo.replace("/", "--"))
    return cached / "snapshots" / profile.revision


class LocalClassifier:
    def __init__(self, profile):
        self.profile = profile
        checkpoint = checkpoint_path(profile)
        if not (checkpoint / "model.safetensors").is_file():
            raise FileNotFoundError(f"Download {profile.label} using the README before selecting it.")
        dspy.configure_cache(enable_disk_cache=False, enable_memory_cache=False)
        backend_type = InboxOmniBackend if profile.key == "omni-600m" else InboxD1Backend
        self.backend = backend_type(str(checkpoint), revision=profile.revision, framework="mlx")
        try:
            if profile.patch:
                if read_patch_hashes(profile.patch) != profile.patch_hashes:
                    raise ValueError("The patch changed after the profile was loaded.")
                patch = Patch.load(profile.patch)
                self.backend.set_weights({
                    name: tensor.float().numpy()
                    for name, tensor in patch.edited_tensors(self.backend.reader).items()
                })
            self.program = decision_program(self.backend, profile)
        except BaseException:
            self.close()
            raise

    def predict(self, sender, subject, body):
        fields = dict(zip(INPUTS, (sender, subject, body)))
        if isinstance(self.backend, InboxOmniBackend):
            fields = self.backend.fit_inputs(fields, self.profile.instructions)
        return self.program(**fields).needs_action

    def __call__(self, sender, subject, body):
        return "yes" if self.predict(sender, subject, body).value else "no"

    def close(self):
        self.backend.close()


class ModelWorker:
    """Both inboxes use one local model on one worker thread."""

    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="omni-model")
        self.lock = Lock()
        self.model = None

    def _load(self, profile):
        if self.model and self.model.profile == profile:
            return
        self._unload()
        self.model = LocalClassifier(profile)

    def for_profile(self, profile):
        with self.lock:
            self.executor.submit(self._load, profile).result()

        def classify(*fields):
            return self.executor.submit(self.model, *fields).result()

        return classify

    def _unload(self):
        if self.model:
            self.model.close()
            self.model = None

    def close(self):
        self.executor.submit(self._unload).result()
        self.executor.shutdown()
