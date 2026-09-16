from datetime import date, timedelta

from app.verification.rediscovery import extract_rediscovery_candidates
from app.verification.scheduler import next_verification_interval


def test_extracts_ranked_same_domain_and_ats_candidates_without_duplicates():
    html = '''
      <a href="/campus">校园招聘</a>
      <a href="https://corp.example.com/campus">校园招聘重复</a>
      <a href="https://app.mokahr.com/campus-recruitment/acme/123">立即申请</a>
      <a href="https://news.example.org/article">新闻</a>
    '''
    candidates = extract_rediscovery_candidates('https://corp.example.com/old-job', html)
    assert [c.url for c in candidates] == [
        'https://app.mokahr.com/campus-recruitment/acme/123',
        'https://corp.example.com/campus',
    ]
    assert candidates[0].source_kind == 'ats_link'
    assert candidates[0].score > candidates[1].score


def test_scheduler_prioritizes_verified_and_near_deadline_jobs():
    assert next_verification_interval('VERIFIED_OPEN', '招满即止', date(2026, 9, 16)) == timedelta(hours=6)
    assert next_verification_interval('DISCOVERED_URL_UNVERIFIED', '2026-09-18', date(2026, 9, 16)) == timedelta(hours=6)
    assert next_verification_interval('DISCOVERED_URL_UNVERIFIED', '2026-12-31', date(2026, 9, 16)) == timedelta(hours=12)
    assert next_verification_interval('REDISCOVERY_REQUIRED', '', date(2026, 9, 16)) == timedelta(hours=24)
    assert next_verification_interval('DISCOVERED_NO_URL', '', date(2026, 9, 16)) == timedelta(days=3)
