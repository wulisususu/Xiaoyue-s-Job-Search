from __future__ import annotations

from urllib.parse import urlparse


def detect_ats(url: str, body: str) -> str | None:
    host = urlparse(url).netloc.lower()
    text = body.lower()
    if "mokahr.com" in host or "moka，智能化招聘管理系统".lower() in text or "mokahr" in text:
        return "moka"
    if "hotjob.cn" in host or "hotjob" in text:
        return "hotjob"
    if "feishu.cn" in host or "larkoffice.com" in host or "feishu" in text and "招聘" in body:
        return "feishu"
    if "beisen.com" in host or "beisen" in text or "北森" in body and "招聘" in body:
        return "beisen"
    if "51job.com" in host:
        return "51job"
    if "iguopin.com" in host or "国聘" in body:
        return "guopin"
    if "successfactors" in host or "successfactors" in text:
        return "successfactors"
    return None
