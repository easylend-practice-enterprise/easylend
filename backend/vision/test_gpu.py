import torch

print("GPU beschikbaar?:", torch.cuda.is_available())
print(
    "Naam van de GPU:",
    torch.cuda.get_device_name(0)
    if torch.cuda.is_available()
    else "Geen GPU gevonden :(",
)
