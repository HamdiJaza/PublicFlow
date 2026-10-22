"""Prepare text/media only. No visual interpretation or incident classification.

The delivered notebook extraction is preserved in pipeline.py. This explicitly
versioned contract replaces its semantic outputs in the new development path.
"""

from typing import Literal
import json

from pydantic import BaseModel, ConfigDict, Field

from . import pipeline
from .runtime import confined, safe_image_path, state
from .providers import clean_text, transcribe_audio

SCHEMA_VERSION = "intake-preparation-v1"


class FaceProcessing(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    detector: Literal["YuNet"]
    detector_completed: bool
    faces_detected: int = Field(ge=0)
    write_and_decode_verified: bool
    model_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class PreparedMedia(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str
    source: Literal["image", "video"]
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    face_processing: FaceProcessing


class PreparedReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["intake-preparation-v1"]
    language: str
    cleaned_text: str
    text_quality: Literal["CLEAR", "VAGUE", "EMPTY"]
    transcription_audio: str
    transcription_video: str
    media: list[PreparedMedia]
    preparation_status: Literal["READY", "REVIEW"]
    processing_errors: list[str]
    avertissements: list[str]


def prepare_report(text, paths):
    result = {
        "schema_version": SCHEMA_VERSION,
        "language": "unknown", "cleaned_text": "", "text_quality": "EMPTY",
        "transcription_audio": "", "transcription_video": "",
        "media": [], "preparation_status": "REVIEW",
        "processing_errors": [], "avertissements": [],
    }
    emails = phones = 0

    def mask(value):
        nonlocal emails, phones
        masked, e, p = pipeline.masquer_texte(value)
        emails += e
        phones += p
        return masked

    def error(code):
        # Codes only: never expose exceptions, provider text or filesystem paths.
        result["processing_errors"].append(code)

    def retained(path, media_id, source):
        request = state()
        safe = confined(path, request.safe)
        evidence = request.processed.get(str(safe))
        if not safe.is_file() or not evidence or not evidence.get("detector_completed") or not evidence.get("write_and_decode_verified"):
            raise ValueError("Face-processing evidence missing")
        # Recheck actual bytes, not only an earlier successful write.
        import hashlib
        from PIL import Image
        if hashlib.sha256(safe.read_bytes()).hexdigest() != evidence["sha256"]:
            raise ValueError("Processed bytes changed")
        with Image.open(safe) as image:
            image.verify()
        result["media"].append({"id": media_id, "source": source, "path": str(safe),
                                "sha256": evidence["sha256"],
                                "face_processing": dict(evidence)})

    # Validate/process media before making any optional text-provider requests.
    if paths.get("image"):
        try:
            valid, _, _ = pipeline.verifier_image(paths["image"])
            if not valid:
                raise ValueError("Invalid image")
            output = safe_image_path(paths["image"])
            pipeline.flouter_visages(paths["image"], str(output))
            retained(output, "image_independante", "image")
        except Exception:
            error("IMAGE_PRIVACY_PROCESSING_FAILED")

    video_audio = None
    if paths.get("video"):
        try:
            video = pipeline.extraire_video(paths["video"])
            if video.get("erreur") or not video.get("images"):
                raise ValueError("Video preparation incomplete")
            for index, frame in enumerate(video["images"], 1):
                # Extraction already applies face processing; do not blur twice.
                retained(frame, f"image_video_{index}", "video")
            if len(video["images"]) != 3:
                error("VIDEO_FRAME_EXTRACTION_INCOMPLETE")
            video_audio = video.get("audio")
            # The native extractor can return no audio after an ffmpeg failure.
            # Distinguish that failure from a video that genuinely has no track.
            probe = pipeline._lancer(["ffprobe", "-v", "error", "-show_streams", "-of", "json", paths["video"]])
            if probe.returncode != 0:
                raise ValueError("Video track verification failed")
            streams = json.loads(probe.stdout or b"{}")
            if any(stream.get("codec_type") == "audio" for stream in streams.get("streams", [])) and not video_audio:
                error("VIDEO_AUDIO_EXTRACTION_FAILED")
        except Exception:
            error("VIDEO_PREPARATION_FAILED")

    # Stop external transmission if supplied media failed preparation.
    original = mask((text or "").strip())
    if not result["processing_errors"]:
        for source, field in [(paths.get("audio"), "transcription_audio"),
                              (video_audio, "transcription_video")]:
            if not source:
                continue
            transcription = transcribe_audio(source)
            value = transcription.get("transcription", "")
            result[field] = mask(value) if isinstance(value, str) else ""
            if transcription.get("avertissement") or not result[field].strip():
                error("AUDIO_TRANSCRIPTION_FAILED" if field == "transcription_audio" else "VIDEO_TRANSCRIPTION_FAILED")

        # Include video speech too, without making any claim about its truth.
        text_source = "\n".join(part for part in (original, result["transcription_audio"],
                                                  result["transcription_video"]) if part)
        if text_source and not result["processing_errors"]:
            cleaned = clean_text(text_source)
            result["language"] = cleaned.get("language", "unknown")
            result["cleaned_text"] = mask(cleaned.get("cleaned_text", ""))
            result["text_quality"] = cleaned.get("text_quality", "EMPTY")
            if cleaned.get("avertissement"):
                error("TEXT_CLEANING_FAILED")
            if result["language"] not in {"fr", "en", "ar", "mixed"} or result["text_quality"] != "CLEAR" or not result["cleaned_text"].strip():
                error("TEXT_PREPARATION_INCOMPLETE")
        elif not text_source:
            error("TEXT_REQUIRED_FOR_VISION")

    if emails or phones:
        result["avertissements"].append(f"Données masquées ({emails} email(s), {phones} téléphone(s)).")
    result["processing_errors"] = list(dict.fromkeys(result["processing_errors"]))
    result["preparation_status"] = "REVIEW" if result["processing_errors"] else "READY"
    return PreparedReport.model_validate(result).model_dump()
