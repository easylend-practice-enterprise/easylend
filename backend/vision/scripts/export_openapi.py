import json

from main import app  # main.py is in the root, so just import app


def export_openapi():
    openapi_schema = app.openapi()
    with open("openapi.json", "w") as f:
        json.dump(openapi_schema, f, indent=2)
    print("✅ Vision API OpenAPI JSON exported!")


if __name__ == "__main__":
    export_openapi()
