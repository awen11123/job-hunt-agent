import re


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def application_key(company: str, role: str, season: str) -> tuple[str, str, str]:
    return normalize_text(company), normalize_text(role), normalize_text(season)
