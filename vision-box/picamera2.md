# Gebruik van `picamera2` binnen een `uv`-omgeving op Raspberry Pi

Bij gebruik van `uv` voor Python dependency management op een Raspberry Pi is er een compatibiliteitsvereiste voor `picamera2`.

`picamera2` kan niet via `pip`, `uv`, of een standaard `pyproject.toml` dependency worden geïnstalleerd. De library is nauw geïntegreerd met het onderliggende Linux-systeem en communiceert rechtstreeks met `libcamera`. Installatie verloopt via het systeem package management (`apt`).

Standaard creëert `uv` een geïsoleerde virtuele omgeving (`.venv`) zonder toegang tot systeempackages. Hierdoor zal code die `picamera2` importeert falen met:

```python
ModuleNotFoundError: No module named 'picamera2'
```

## Vereiste configuratie

Om `picamera2` beschikbaar te maken binnen een `uv`-omgeving, moet de virtual environment worden aangemaakt met toegang tot systeempackages.

1. Installer `picamera2` op systeemniveau:

```bash
sudo apt update
sudo apt install python3-picamera2
```

1. Maak de `uv` virtual environment aan met toegang tot systeempackages:

```bash
uv venv --system-site-packages
```

1. Synchroniseer vervolgens de projectdependencies:

```bash
uv sync
```

## Resultaat

De Python-omgeving blijft geïsoleerd voor projectafhankelijke packages (zoals Flask of GPIO Zero), terwijl systeemgebonden dependencies zoals `picamera2` beschikbaar blijven via de onderliggende Python-installatie. Hierdoor blijft compatibiliteit met de Raspberry Pi camera stack behouden.
