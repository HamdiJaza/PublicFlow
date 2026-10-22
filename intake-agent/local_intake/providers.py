"""Preparation-only dispatch. Delivered Gemini code/configuration is preserved."""

from . import pipeline
from .runtime import state


def clean_text(text):
    provider=state().settings.text_provider
    if provider=='gemini':
        # Retained original provider. Inactive when the NVIDIA entrypoint is used.
        return pipeline.nettoyer_texte(text)
    if provider=='nvidia':
        from .nvidia import clean_text as nvidia_clean
        return nvidia_clean(text)
    return {'language':'unknown','cleaned_text':'','text_quality':'EMPTY','avertissement':'TEXT_PROVIDER_NOT_CONFIGURED'}


def transcribe_audio(path):
    provider=state().settings.transcription_provider
    if provider=='gemini':
        # No automatic Gemini fallback; this branch requires explicit selection.
        return pipeline.transcrire_audio(path)
    if provider=='nvidia':
        from .nvidia import transcribe_audio as nvidia_transcribe
        return nvidia_transcribe(path)
    return {'transcription':'','avertissement':'TRANSCRIPTION_PROVIDER_NOT_CONFIGURED'}
