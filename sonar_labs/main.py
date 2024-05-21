"""FastAPI app creation, logger configuration and main API routes."""

from sonar_labs.di import global_injector
from sonar_labs.launcher import create_app

app = create_app(global_injector)
