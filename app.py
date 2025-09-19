# https://binkhoale1812-edsummariser.hf.space/

# Minimal orchestrator that exposes the FastAPI app and registers routes
from helpers import app  # FastAPI instance

# Import route modules for side-effect registration
import routes.auth as _routes_auth
import routes.projects as _routes_projects
import routes.files as _routes_files
import routes.reports as _routes_report
import routes.chats as _routes_chat
import routes.health as _routes_health

# Local dev
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)


