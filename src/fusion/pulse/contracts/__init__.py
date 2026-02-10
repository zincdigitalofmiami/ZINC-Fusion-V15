# Pulse Contracts Module
# Contains the JSON schema and prompt templates for all 11 specialists

from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"


def get_prompt(domain: str) -> str:
    """Get the prompt template for a domain."""
    filepath = PROMPTS_DIR / f"{domain.lower()}.txt"
    if filepath.exists():
        return filepath.read_text()
    return ""


def get_system_prompt() -> str:
    """Get the shared system prompt."""
    filepath = PROMPTS_DIR / "system.txt"
    if filepath.exists():
        return filepath.read_text()
    return ""


# All 11 specialist domains
DOMAINS = [
    "CRUSH",
    "CHINA",
    "FX",
    "FED",
    "TARIFF",
    "ENERGY",
    "BIOFUEL",
    "PALM",
    "VOLATILITY",
    "SUBSTITUTES",
    "TRUMP_EFFECT",
]
