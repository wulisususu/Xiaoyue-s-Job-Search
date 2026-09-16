from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True)
class PageClassification:
    page_type: str
    apply_evidence: list[str]


CLOSED_PATTERNS = (r"职位已下线", r"职位不存在", r"岗位不存在", r"职位已关闭", r"招聘已结束", r"已截止", r"岗位已关闭")
APPLY_PATTERNS = (r"立即申请", r"申请职位", r"立即投递", r"投递简历", r"提交申请", r"申请该职位", r"应聘职位")
CAREER_PATTERNS = (r"校园招聘", r"社会招聘", r"招聘职位", r"加入我们", r"招聘官网", r"职位列表")
JOB_DETAIL_PATTERNS = (r"职位详情", r"岗位详情", r"职位描述", r"岗位职责", r"任职要求", r"工作职责")

# SPA shells: a big JS bundle with a mount point and almost no server-rendered
# text. Matching keywords against these bodies would mostly hit JS string
# literals or hidden templates, so they must NOT be classified as evidence.
_SPA_SCRIPT_RE = re.compile(r"<script\b", re.I)
_SPA_MOUNT_RE = re.compile(r"id=[\"'](?:root|app|__next|__nuxt)[\"']", re.I)
_VISIBLE_TEXT_RE = re.compile(r"<(script|style|noscript|template)\b.*?</\1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)

_MIN_VISIBLE_TEXT = 120
_MIN_BODY_FOR_SPA = 2000


def _visible_text(body: str) -> str:
    text = _HTML_COMMENT_RE.sub(" ", body or "")
    text = _VISIBLE_TEXT_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _looks_like_spa_shell(raw_body: str, visible_text: str) -> bool:
    if len(visible_text) >= _MIN_VISIBLE_TEXT:
        return False
    if not raw_body:
        return False
    has_scripts = bool(_SPA_SCRIPT_RE.search(raw_body))
    has_mount = bool(_SPA_MOUNT_RE.search(raw_body))
    return has_mount or (has_scripts and len(raw_body) >= _MIN_BODY_FOR_SPA)


def classify_page(body: str) -> PageClassification:
    raw_body = body or ""
    text = _visible_text(raw_body)
    if any(re.search(pattern, text, re.I) for pattern in CLOSED_PATTERNS):
        return PageClassification("closed", [])
    if re.search(r"type\s*=\s*[\"']password[\"']", raw_body, re.I) and re.search(r"登录|login|验证码", raw_body, re.I):
        return PageClassification("login", [])
    if _looks_like_spa_shell(raw_body, text):
        return PageClassification("spa_shell", [])
    evidence: list[str] = []
    for pattern in APPLY_PATTERNS:
        match = re.search(pattern, text, re.I)
        if match:
            evidence.append(match.group(0))
    if evidence and (any(re.search(p, text, re.I) for p in JOB_DETAIL_PATTERNS) or re.search(r"<form|<button|role=[\"']button", raw_body, re.I)):
        return PageClassification("job_detail", list(dict.fromkeys(evidence)))
    if any(re.search(pattern, text, re.I) for pattern in CAREER_PATTERNS):
        return PageClassification("career_home", list(dict.fromkeys(evidence)))
    if any(re.search(pattern, text, re.I) for pattern in JOB_DETAIL_PATTERNS):
        return PageClassification("job_detail", list(dict.fromkeys(evidence)))
    return PageClassification("unknown", list(dict.fromkeys(evidence)))
