from dataclasses import dataclass
import re


@dataclass(frozen=True)
class PrivacyFinding:
    kind: str
    value: str

    @property
    def redacted_value(self) -> str:
        return "<redacted>"


NOTION_URL_RE = re.compile(r"https://(?:www\.)?notion\.so/[^\s)>\"]+", re.IGNORECASE)
API_KEY_RE = re.compile(r"\b(?:sk|ntn|secret)[-_][A-Za-z0-9_-]{12,}\b")
ENV_SECRET_RE = re.compile(r"\b(?:NOTION_TOKEN|DEEPSEEK_API_KEY|GITHUB_TOKEN)[ \t]*=[ \t]*[^ \t\r\n]+")
WINDOWS_USER_PATH_RE = re.compile(
    r"\b[A-Za-z]:[\\/]Users[\\/][^<>\s\\/]+[\\/]",
    re.IGNORECASE,
)
WPS_ACCOUNT_PATH_RE = re.compile(
    r"WPS Cloud Files[\\/]\d{5,}[\\/]",
    re.IGNORECASE,
)


def scan_text_for_private_leaks(text: str) -> list[PrivacyFinding]:
    findings: list[PrivacyFinding] = []
    findings.extend(
        PrivacyFinding("notion_url", match.group(0)) for match in NOTION_URL_RE.finditer(text)
    )
    findings.extend(PrivacyFinding("api_key", match.group(0)) for match in API_KEY_RE.finditer(text))
    findings.extend(
        PrivacyFinding("env_secret", match.group(0)) for match in ENV_SECRET_RE.finditer(text)
    )
    findings.extend(
        PrivacyFinding("windows_user_path", match.group(0))
        for match in WINDOWS_USER_PATH_RE.finditer(text)
    )
    findings.extend(
        PrivacyFinding("wps_account_path", match.group(0))
        for match in WPS_ACCOUNT_PATH_RE.finditer(text)
    )
    return findings
