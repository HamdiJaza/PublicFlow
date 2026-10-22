"""Development entrypoint for the approved preparation-only Intake contract."""

from .app import create_app

app = create_app(preparation_only=True)
