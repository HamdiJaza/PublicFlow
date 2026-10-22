"""Separate NVIDIA entrypoint; existing Gemini entrypoints stay available."""
from .app import create_app
from .runtime import Settings

app=create_app(Settings(text_provider='nvidia',transcription_provider='nvidia'),preparation_only=True)
