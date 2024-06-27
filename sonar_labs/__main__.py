# start a fastapi server with uvicorn

import uvicorn

from sonar_labs.main import app
from sonar_labs.settings.settings import settings

# Set log_config=None to do not use the uvicorn logging configuration, and
# use ours instead. For reference, see below:
# https://github.com/tiangolo/fastapi/discussions/7457#discussioncomment-5141108
uvicorn.run("sonar_labs.main:app", host="0.0.0.0", port=settings().server.port, workers=8, log_config=None)
