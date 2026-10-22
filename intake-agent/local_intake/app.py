"""Native Intake routes with local-only reliability and privacy corrections."""

from pathlib import Path
from threading import Lock
from typing import Optional
import os
import json
import shutil

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from . import pipeline
from .runtime import Settings, StorageBusy, confined, request_context


class RequeteSignalement(BaseModel):
    texte: Optional[str] = None
    chemin_image: Optional[str] = None
    chemin_audio: Optional[str] = None
    chemin_video: Optional[str] = None


class BodyLimit:
    """Bound the multipart stream before the framework spools uploaded files."""

    def __init__(self, app, maximum=92 * 1024 * 1024):
        self.app, self.maximum = app, maximum

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        total = 0

        async def limited_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > self.maximum:
                raise HTTPException(413, "Envoi trop volumineux.")
            return message

        await self.app(scope, limited_receive, send)


def create_app(settings=None, model_client_factory=None, *, preparation_only=False):
    settings = settings or Settings()
    admission = Lock()  # One full pipeline at a time, including timed-out callers.
    service = FastAPI(
        title="API Signalement Municipal",
        description=("Préparation du texte et des médias. Les décisions visuelles appartiennent à Vision."
                     if preparation_only else "Analyse de textes, images, audios et vidéos. Évalue la pertinence municipale, la cohérence et le niveau de confirmation apporté par chaque média."),
        version="5.0.0" if preparation_only else "4.0.0",
    )
    service.add_middleware(BodyLimit)
    if preparation_only:
        from .preparation import PreparedReport
    response_model = PreparedReport if preparation_only else None

    def process(texte, incoming, server_paths=False, response=None):
        if len(texte or "") > 5000:
            raise HTTPException(413, "Texte trop volumineux (5000 caractères maximum).")
        if not admission.acquire(blocking=False):
            raise HTTPException(503, "Un traitement est déjà en cours.")
        try:
            with request_context(settings, model_client_factory) as request:
                paths = {"image": None, "audio": None, "video": None}
                for kind, source in incoming.items():
                    if source is None:
                        continue
                    if server_paths:
                        try:
                            original = confined(source, settings.root / "inbox")
                            if not original.is_file():
                                raise ValueError("Fichier absent")
                        except (ValueError, OSError):
                            raise HTTPException(400, "Fichier hors du stockage d'entrée autorisé ou absent.") from None
                        stream = original.open("rb")
                    else:
                        stream = source.file
                    try:
                        # Generated name; image decoding chooses its real format below.
                        target = request.raw / (kind + ".bin")
                        maximum = {"image": settings.max_image_bytes,
                                   "audio": settings.max_audio_bytes,
                                   "video": settings.max_video_bytes}[kind]
                        count = 0
                        with target.open("wb") as destination:
                            while chunk := stream.read(64 * 1024):
                                count += len(chunk)
                                if count > maximum:
                                    raise HTTPException(413, "Fichier trop volumineux.")
                                destination.write(chunk)
                        if count == 0:
                            raise HTTPException(400, "Le fichier est vide.")
                    finally:
                        if server_paths:
                            stream.close()
                    if kind == "image":
                        from PIL import Image
                        try:
                            with Image.open(target) as image:
                                if image.width * image.height > settings.max_pixels or getattr(image, "n_frames", 1) != 1:
                                    raise HTTPException(400, "Une image fixe de 20 millions de pixels maximum est requise.")
                        except (OSError, ValueError, Image.DecompressionBombError):
                            raise HTTPException(400, "Image invalide ou dimensions excessives.") from None
                        valid, _, _ = pipeline.verifier_image(str(target))
                        if not valid:
                            raise HTTPException(400, "Image invalide ou format non pris en charge.")
                    paths[kind] = str(target)
                # Explicit opt-in, not credential presence, enables provider calls.
                if model_client_factory is None and not preparation_only:
                    if os.environ.get("INTAKE_ALLOW_PAID_CALLS") != "1":
                        raise HTTPException(503, "Appels Gemini désactivés en attente d'autorisation explicite.")
                    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
                        raise HTTPException(503, "Identifiant Gemini non configuré.")
                if preparation_only:
                    from .preparation import prepare_report
                    prepared=prepare_report(texte, paths)
                    if response is not None:
                        # Service-reported facts, not independent inference verification.
                        response.headers['X-Intake-Provenance']=json.dumps({
                            'text_provider':settings.text_provider,
                            'transcription_provider':settings.transcription_provider,
                            'normalization':'French' if settings.text_provider=='nvidia' else 'preserve-input-language',
                            'language_scope':'source-report',
                            'provider_call_attempts':request.provider_calls,
                            'calls':request.provider_trace},separators=(',',':'),ensure_ascii=True)
                    return prepared
                result = pipeline.traiter_signalement(
                    texte_citoyen=texte, chemin_image=paths["image"],
                    chemin_audio=paths["audio"], chemin_video=paths["video"],
                )
                # Enforce a local invariant without introducing response fields.
                image_paths = result.get("images_traitees", [])
                evidence_ok = isinstance(image_paths, list)
                if paths["image"] and not image_paths:
                    evidence_ok = False
                for path in image_paths if isinstance(image_paths, list) else []:
                    try:
                        safe = confined(path, request.safe)
                        evidence = request.processed.get(str(safe))
                        if not safe.is_file() or not evidence:
                            evidence_ok = False
                    except (ValueError, TypeError):
                        evidence_ok = False
                if not evidence_ok:
                    result["avertissements"].append("Vérification déterministe du traitement des visages indisponible.")
                    result["validation_humaine_requise"] = True
                    if isinstance(result.get("validation_multimodale"), dict):
                        result["validation_multimodale"]["validation_humaine_requise"] = True
                return result
        except HTTPException:
            raise
        except StorageBusy:
            raise HTTPException(503, "Un traitement est déjà en cours.") from None
        except Exception:
            # Never return exception/provider text or credentials to callers.
            raise HTTPException(500, "Le traitement a échoué. Vérifiez les fichiers et les journaux du serveur.") from None
        finally:
            admission.release()

    @service.get("/")
    def accueil():
        return {"message": "API Signalement Municipal opérationnelle", "endpoint": "/signaler", "version": "5.0.0" if preparation_only else "4.0.0"}

    @service.get("/app", response_class=HTMLResponse)
    def page_signalement():
        page = "preparation.html" if preparation_only else "citizen.html"
        return HTMLResponse((Path(__file__).with_name(page)).read_text(encoding="utf-8"))

    @service.post("/signaler", response_model=response_model)
    def endpoint_signaler(req: RequeteSignalement, response: Response):
        if not any(value and value.strip() for value in (req.texte, req.chemin_image, req.chemin_audio, req.chemin_video)):
            raise HTTPException(400, "Fournis au moins un texte, une image, un audio ou une vidéo.")
        return process(req.texte or "", {"image": req.chemin_image, "audio": req.chemin_audio, "video": req.chemin_video}, True, response)

    @service.post("/analyser", response_model=response_model)
    async def analyser_depuis_interface(
        response: Response,
        texte: str = Form(""),
        image: Optional[UploadFile] = File(None),
        audio: Optional[UploadFile] = File(None),
        video: Optional[UploadFile] = File(None),
    ):
        files = {"image": image, "audio": audio, "video": video}
        try:
            if not (texte.strip() or any(f and f.filename for f in files.values())):
                raise HTTPException(400, "Ajoutez une description ou au moins un média.")
            return await run_in_threadpool(process, texte, {k: v for k, v in files.items() if v and v.filename}, False, response)
        finally:
            for file in files.values():
                if file:
                    await file.close()

    return service


app = create_app()
