"""Request-local storage and deterministic processing evidence; no public schema."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

from PIL import Image

PROJECT = Path(__file__).resolve().parents[2]
ACTIVE = ContextVar("intake_request", default=None)


@dataclass
class Settings:
    root: Path = field(default_factory=lambda: PROJECT / ".runtime" / "intake")
    tools: Path = field(default_factory=lambda: PROJECT / ".runtime" / "tools")
    retention_seconds: int = 3600
    max_image_bytes: int = 10 * 1024 * 1024
    max_pixels: int = 20_000_000
    max_audio_bytes: int = 30 * 1024 * 1024
    max_video_bytes: int = 50 * 1024 * 1024
    sdk_timeout_ms: int = 120_000
    # Gemini remains the default for the existing entrypoint and its tests.
    text_provider: str = "gemini"
    transcription_provider: str = "gemini"
    nvidia_http_factory: object = None  # Explicit offline-test dependency only.
    nvidia_asr_factory: object = None


@dataclass
class RequestState:
    settings: Settings
    token: str
    raw: Path
    safe: Path
    client_factory: object = None
    client: object = None
    processed: dict = field(default_factory=dict)
    provider_calls: int = 0
    provider_trace: list = field(default_factory=list)
    provider_failed: bool = False


class StorageBusy(RuntimeError):
    pass


@contextmanager
def storage_lease(settings):
    """Process-safe admission for all workers sharing the same private root."""
    settings.root.mkdir(parents=True, exist_ok=True)
    handle = (settings.root / ".processing.lock").open("a+b")
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise StorageBusy("Private storage is processing another request") from None
    try:
        yield
    finally:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def state():
    result = ACTIVE.get()
    if result is None:
        raise RuntimeError("Media processing requires an isolated request context")
    return result


def confined(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("Media path outside controlled storage")
    # A symlink/junction to another request/root must not be accepted.
    cursor = path
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError("Linked media paths are not accepted")
        cursor = cursor.parent
    return path


def cleanup(settings):
    """Run under the exclusive storage lease; never remove the active request."""
    receipts = settings.root / "receipts"
    now = time.time()
    active = ACTIVE.get()
    for category in ("raw", "safe"):
        parent = settings.root / category
        if not parent.is_dir():
            continue
        for directory in parent.iterdir():
            name = directory.name
            if (len(name) != 32 or any(c not in "0123456789abcdef" for c in name)
                    or directory.is_symlink() or not directory.is_dir()
                    or active is not None and active.token == name):
                continue
            if now - directory.stat().st_mtime >= settings.retention_seconds:
                shutil.rmtree(confined(directory, parent))
    for receipt in receipts.glob("*.json") if receipts.is_dir() else []:
        if receipt.is_symlink() or now - receipt.stat().st_mtime < settings.retention_seconds:
            continue
        token = receipt.stem
        if len(token) != 32 or any(c not in "0123456789abcdef" for c in token):
            continue
        target = confined(settings.root / "safe" / token, settings.root / "safe")
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        receipt.unlink(missing_ok=True)


@contextmanager
def request_context(settings, client_factory=None):
    settings.root = settings.root.resolve()
    with storage_lease(settings):
        with _request_context(settings, client_factory) as request:
            yield request


@contextmanager
def _request_context(settings, client_factory):
    cleanup(settings)
    token = uuid.uuid4().hex
    raw = settings.root / "raw" / token
    safe = settings.root / "safe" / token
    raw.mkdir(parents=True)
    safe.mkdir(parents=True)
    request = RequestState(settings, token, raw, safe, client_factory)
    marker = ACTIVE.set(request)
    try:
        yield request
    finally:
        if request.client is not None and hasattr(request.client, "close"):
            try:
                request.client.close()
            except Exception:
                pass  # Cleanup must continue even if the provider close fails.
        # Both targets are generated under a checked request root, never caller paths.
        raw_target = confined(raw, settings.root / "raw")
        shutil.rmtree(raw_target)
        receipts = settings.root / "receipts"
        receipts.mkdir(exist_ok=True)
        record = {
            "request_token": token, "completed_at": time.time(),
            "inference_mode": ("TEST_DOUBLE" if client_factory or any(t.get("inference_mode")=="TEST_DOUBLE" for t in request.provider_trace) else "REAL_PROVIDER") if request.provider_calls else "NOT_CALLED",
            "provider_call_attempts": request.provider_calls,
            "provider_trace": request.provider_trace,
            "processed_images": request.processed,
            "limits": "Evidence of face-processing execution, not complete PII removal",
        }
        (receipts / (token + ".json")).write_text(json.dumps(record, indent=2), encoding="utf-8")
        ACTIVE.reset(marker)


class ProviderFailure(RuntimeError):
    """Safe provider failure retaining only retry status, never provider text."""

    def __init__(self, error):
        self.code = getattr(error, "code", None)
        super().__init__("Provider request failed" + (f" (HTTP {self.code})" if isinstance(self.code, int) else ""))


class SafeModels:
    def __init__(self, models):
        self.models = models

    def generate_content(self, *args, **kwargs):
        state().provider_calls += 1
        try:
            return self.models.generate_content(*args, **kwargs)
        except Exception as error:
            raise ProviderFailure(error) from None


class SafeClient:
    def __init__(self, client):
        self.client = client
        self.models = SafeModels(client.models)

    def close(self):
        if hasattr(self.client, "close"):
            self.client.close()


def get_client():
    request = state()
    if request.client is None:
        if request.client_factory is not None:
            request.client = SafeClient(request.client_factory())
        else:
            if os.environ.get("INTAKE_ALLOW_PAID_CALLS") != "1":
                raise RuntimeError("Real provider calls are disabled pending explicit approval")
            key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            if not key:
                raise RuntimeError("Gemini credential not configured")
            from google import genai
            from google.genai import types
            request.client = SafeClient(genai.Client(api_key=key, http_options=types.HttpOptions(
                timeout=request.settings.sdk_timeout_ms,
                retry_options=types.HttpRetryOptions(attempts=1),
            )))
    return request.client


class ClientProxy:
    @property
    def models(self):
        return get_client().models


def work_path(name):
    return confined(state().raw / name, state().raw)


def safe_image_path(source):
    request = state()
    # No caller-supplied filename becomes a stored name.
    return request.safe / ("image_" + uuid.uuid4().hex + ".png")


def face_model_path():
    path = state().settings.tools / "yunet.onnx"
    if not path.is_file():
        raise ValueError("YuNet face model is unavailable")
    if state().client_factory is None:
        manifest = json.loads((PROJECT / "intake-agent/assets.lock.json").read_text(encoding="utf-8"))
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["yunet"]["sha256"]:
            raise ValueError("YuNet model checksum mismatch")
    return path


def checked_image_mime(path):
    request = state()
    path = confined(path, request.safe)
    if str(path) not in request.processed:
        raise ValueError("Image has no face-processing evidence")
    with Image.open(path) as image:
        return Image.MIME[image.format]


def record_processed(source, output, count):
    request = state()
    output = confined(output, request.safe)
    with Image.open(output) as image:
        image.verify()
    with Image.open(output) as image:
        image.load()
    request.processed[str(output)] = {
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "detector": "YuNet", "detector_completed": True,
        "faces_detected": int(count), "write_and_decode_verified": True,
        "model_sha256": hashlib.sha256(face_model_path().read_bytes()).hexdigest(),
    }


def run_media_command(command, **kwargs):
    request = state()
    name = command[0]
    executable = shutil.which(name)
    if not executable:
        executable_path = request.settings.tools / (name + (".exe" if os.name == "nt" else ""))
        if executable_path.is_file():
            executable = str(executable_path)
    if not executable:
        raise ValueError(f"{name} is unavailable; run the local asset setup")
    return subprocess.run([executable, *command[1:]], timeout=90, **kwargs)
