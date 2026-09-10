from datetime import date, timedelta
import re

from job_hunt_agent.domain.models import ApplicationDraft
from job_hunt_agent.domain.statuses import RecruitingStage


CHANNELS = ("内推", "官网", "Boss", "BOSS", "牛客", "猎聘", "拉勾", "脉脉")
LOCATIONS = (
    "北京",
    "上海",
    "深圳",
    "广州",
    "杭州",
    "南京",
    "苏州",
    "成都",
    "武汉",
    "西安",
    "远程",
)
DIRECTIONS = ("AI Agent", "LLM", "RAG", "Agent", "大模型", "后端", "算法", "应用")
URL_PATTERN = re.compile(r"https?://[^\s，。；！？]+", re.IGNORECASE)


def parse_application_text(
    text: str,
    today: date,
    default_season: str | None = None,
) -> ApplicationDraft:
    normalized = normalize_text(text)
    cleaned, job_url = without_job_urls(normalized)
    company, role = company_and_role(cleaned)
    return ApplicationDraft(
        company=company,
        role=role,
        season=default_season,
        direction=first_matching_direction(cleaned),
        location=first_matching_value(cleaned, LOCATIONS),
        channel=first_matching_value(before_next_step(cleaned), CHANNELS),
        jd_url=job_url,
        resume_version=resume_version(cleaned),
        applied_date=applied_date(cleaned, today),
        current_stage=stage(cleaned),
        deadline=deadline(cleaned, today),
        next_step=next_step(cleaned),
    )


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def without_job_urls(text: str) -> tuple[str, str | None]:
    match = URL_PATTERN.search(text)
    job_url = match.group(0) if match else None
    return normalize_text(URL_PATTERN.sub(" ", text)), job_url


def company_and_role(text: str) -> tuple[str, str]:
    head = first_clause(text)
    head = re.sub(
        r"^(今天|昨天|明天)?\s*(我)?\s*(已)?\s*(投了|投递了|投递|申请了|申请|待投|准备投)\s*",
        "",
        head,
        flags=re.IGNORECASE,
    ).strip()
    if " 的 " in head:
        company, role = head.split(" 的 ", 1)
        return clean_company(company), clean_role(role)
    if "的" in head:
        company, role = head.split("的", 1)
        return clean_company(company), clean_role(role)
    for separator in (" - ", "-", "—", "：", ":"):
        if separator in head:
            company, role = head.split(separator, 1)
            return clean_company(company), clean_role(role)
    parts = head.split(" ", 1)
    if len(parts) == 2:
        return clean_company(parts[0]), clean_role(parts[1])
    raise ValueError("Could not parse company and role from application text")


def first_clause(text: str) -> str:
    return re.split(r"[，,。；;]", text, maxsplit=1)[0]


def clean_company(value: str) -> str:
    return value.strip(" 　的-—:：")


def clean_role(value: str) -> str:
    return value.strip(" 　岗位-—:：")


def first_matching_value(text: str, values: tuple[str, ...]) -> str | None:
    lowered = text.lower()
    for value in values:
        if value.lower() in lowered:
            return "BOSS" if value.lower() == "boss" else value
    return None


def before_next_step(text: str) -> str:
    return re.split(r"下一步\s*[:：]", text, maxsplit=1)[0]


def first_matching_direction(text: str) -> str | None:
    for direction in DIRECTIONS:
        if re.search(rf"{re.escape(direction)}\s*方向", text, re.IGNORECASE):
            return direction
    return first_matching_value(text, DIRECTIONS)


def resume_version(text: str) -> str | None:
    match = re.search(r"(?:简历|resume)\s*([vV]\s*\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).replace(" ", "").lower()


def applied_date(text: str, today: date) -> date | None:
    if "待投" in text or "准备投" in text:
        return None
    if "昨天" in text:
        return today - timedelta(days=1)
    if "今天" in text:
        return today
    return today if any(word in text for word in ("投了", "投递", "申请")) else None


def stage(text: str) -> RecruitingStage:
    if "待投" in text or "准备投" in text:
        return RecruitingStage.TO_APPLY
    if "笔试" in text:
        return RecruitingStage.WRITTEN_TEST
    if "面试" in text:
        return RecruitingStage.INTERVIEW
    if "offer" in text.lower():
        return RecruitingStage.OFFER
    return RecruitingStage.APPLIED


def deadline(text: str, today: date) -> date | None:
    match = re.search(r"截止\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?", text)
    if not match:
        match = re.search(r"截止\s*(\d{1,2})[./-](\d{1,2})", text)
    if not match:
        return None
    month = int(match.group(1))
    day = int(match.group(2))
    return date(today.year, month, day)


def next_step(text: str) -> str | None:
    match = re.search(r"下一步\s*[:：]\s*([^，,。；;]+)", text)
    if not match:
        return None
    return match.group(1).strip()
