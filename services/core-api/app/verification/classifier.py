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


def classify_page(body: str) -> PageClassification:
    text = re.sub(r"\s+", " ", body or "")
    if any(re.search(pattern, text, re.I) for pattern in CLOSED_PATTERNS):
        return PageClassification("closed", [])
    if re.search(r"type\s*=\s*[\"']password[\"']", text, re.I) and re.search(r"登录|login|验证码", text, re.I):
        return PageClassification("login", [])
    evidence: list[str] = []
    for pattern in APPLY_PATTERNS:
        match = re.search(pattern, text, re.I)
        if match:
            evidence.append(match.group(0))
    if evidence and (any(re.search(p, text, re.I) for p in JOB_DETAIL_PATTERNS) or re.search(r"<form|<button|role=[\"']button", text, re.I)):
        return PageClassification("job_detail", list(dict.fromkeys(evidence)))
    if any(re.search(pattern, text, re.I) for pattern in CAREER_PATTERNS):
        return PageClassification("career_home", list(dict.fromkeys(evidence)))
    if any(re.search(pattern, text, re.I) for pattern in JOB_DETAIL_PATTERNS):
        return PageClassification("job_detail", list(dict.fromkeys(evidence)))
    return PageClassification("unknown", list(dict.fromkeys(evidence)))
