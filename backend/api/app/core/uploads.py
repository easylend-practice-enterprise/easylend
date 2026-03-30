from app.core.config import settings

# Centralized directory for all runtime file uploads.
# Configured via the UPLOAD_DIR setting (defaults to the project-root /uploads).
# Must be absolute to work correctly regardless of the process working directory.
UPLOAD_DIR = settings.UPLOAD_DIR.resolve()
