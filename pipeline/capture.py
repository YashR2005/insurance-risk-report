"""
Stage 1 - Capture.

Turns raw field inputs (typed notes, voice, photos) into one structured
Observation object that the rest of the pipeline consumes.

In the skeleton we load a pre-made JSON observation (typed notes only).
Where voice / photo would plug in is marked with TODO so the path is obvious.
"""

import json
import re
from dataclasses import dataclass, field, asdict


@dataclass
class Finding:
    text: str                 # what the inspector observed
    area: str = ""            # optional hazard area tag, e.g. "egress", "storage"


@dataclass
class Observation:
    site_name: str
    inspection_date: str
    inspector: str
    jurisdiction: str         # e.g. "SG"
    findings: list[Finding] = field(default_factory=list)

    def as_dict(self):
        return asdict(self)


def load_observation(path: str) -> Observation:
    with open(path) as f:
        raw = json.load(f)
    findings = [Finding(**x) for x in raw.pop("findings", [])]
    return Observation(findings=findings, **raw)


# ---- the other two input modes -------------------------------------------
# Heavy/optional dependencies are imported inside the functions so the core
# pipeline keeps running with zero install; a missing backend gives a clear hint.
def _split_findings(text: str, area: str = "") -> list[Finding]:
    """One finding per sentence-ish line. Keeps capture deterministic and simple."""
    import re
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", text) if p.strip()]
    return [Finding(text=p, area=area) for p in parts]


def from_voice(audio_path: str, area: str = "") -> list[Finding]:
    """Transcribe an audio note with Whisper, then split into findings."""
    try:
        import whisper
    except ImportError as e:
        raise RuntimeError(
            "Voice capture needs Whisper: pip install openai-whisper (and ffmpeg)."
        ) from e
    from . import config
    try:
        model = whisper.load_model(config.get("WHISPER_MODEL"))
        text = model.transcribe(audio_path).get("text", "").strip()
    except FileNotFoundError as e:
        # Whisper shells out to ffmpeg; a missing binary surfaces here, not at import.
        raise RuntimeError(
            "Voice capture needs the ffmpeg binary on PATH (e.g. brew install ffmpeg)."
        ) from e
    return _split_findings(text, area=area)


def from_photo(image_path: str, area: str = "") -> list[Finding]:
    """OCR an inspection photo (Tesseract) into one or more findings.

    Falls back with a clear message if the OCR backend isn't installed. A vision
    model could be swapped in here without changing the return type.
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError as e:
        raise RuntimeError(
            "Photo capture needs OCR: pip install pytesseract pillow (and the tesseract binary)."
        ) from e
    try:
        text = pytesseract.image_to_string(Image.open(image_path)).strip()
    except pytesseract.TesseractNotFoundError as e:
        # Library is installed but the OCR engine binary is not on PATH.
        raise RuntimeError(
            "Photo capture needs the tesseract binary on PATH (e.g. brew install tesseract)."
        ) from e
    if not text:
        return [Finding(text=f"Photo {image_path}: no legible text extracted.", area=area)]
    return _split_findings(text, area=area)


def observation_from_inputs(
    site_name: str, inspection_date: str, inspector: str, jurisdiction: str,
    notes: list[str] | None = None,
    audio_paths: list[str] | None = None,
    image_paths: list[str] | None = None,
) -> Observation:
    """Assemble one Observation from mixed inputs (typed notes, voice, photos).

    Near-duplicate findings (e.g. a voice note restating a typed line) are collapsed.
    """
    findings: list[Finding] = []
    for n in notes or []:
        findings.extend(_split_findings(n))
    for a in audio_paths or []:
        findings.extend(from_voice(a))
    for img in image_paths or []:
        findings.extend(from_photo(img))
    return Observation(
        site_name=site_name, inspection_date=inspection_date,
        inspector=inspector, jurisdiction=jurisdiction, findings=_dedupe_findings(findings),
    )


_DEDUPE_THRESHOLD = 0.7


def _content_tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}


def _dedupe_findings(findings: list[Finding], threshold: float = _DEDUPE_THRESHOLD) -> list[Finding]:
    """Drop near-duplicate findings using the overlap coefficient
    |A∩B| / min(|A|,|B|); when two overlap, keep the longer (more detailed) one.
    Catches voice-vs-typed restatements that aren't exact string matches."""
    kept: list[Finding] = []
    kept_tokens: list[set[str]] = []
    for f in findings:
        ft = _content_tokens(f.text)
        if not ft:
            continue
        dup_index = None
        for i, kt in enumerate(kept_tokens):
            overlap = len(ft & kt) / min(len(ft), len(kt))
            if overlap >= threshold:
                dup_index = i
                break
        if dup_index is None:
            kept.append(f)
            kept_tokens.append(ft)
        elif len(ft) > len(kept_tokens[dup_index]):   # keep the more detailed version
            kept[dup_index] = f
            kept_tokens[dup_index] = ft
    return kept
