import json

from app.main import app  # Start from 'app' since you're in the 'api' directory


def export_openapi():
    # Force the schema to generate
    openapi_schema = app.openapi()

    with open("openapi.json", "w") as f:
        json.dump(openapi_schema, f, indent=2)
    print("✅ OpenAPI JSON exported to openapi.json")


if __name__ == "__main__":
    export_openapi()
