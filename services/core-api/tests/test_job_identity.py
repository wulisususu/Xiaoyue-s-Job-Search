from app.jobs.identity import (
    company_alias_candidates,
    job_fingerprint,
    normalize_company_name,
    normalize_job_url,
)


def test_normalize_company_name_removes_legal_suffix_and_punctuation():
    assert normalize_company_name(' 上海国盛（集团）有限公司 ') == '上海国盛集团'
    assert normalize_company_name('中国核工业集团有限公司') == '中国核工业集团'


def test_company_alias_candidates_keep_full_and_legal_name_variants():
    aliases = company_alias_candidates('上海机场（集团）有限公司')
    assert '上海机场集团有限公司' in aliases
    assert '上海机场集团' in aliases


def test_normalize_job_url_is_conservative_for_unknown_provider():
    url = 'HTTPS://Example.COM/jobs/42?source=abc&utm_x=1#/apply'
    assert normalize_job_url(url) == 'https://example.com/jobs/42?source=abc&utm_x=1#/apply'


def test_normalize_job_url_removes_tracking_only_for_known_company_provider():
    url = 'https://jobs.example.com/42?utm_source=x&job=7&ref=abc'
    assert normalize_job_url(url, provider='company') == 'https://jobs.example.com/42?job=7'


def test_job_fingerprint_is_stable_across_whitespace():
    left = job_fingerprint('company-1', ' 视觉设计岗 ', '上海 / 南京', '27届秋招')
    right = job_fingerprint('company-1', '视觉设计岗', '上海/南京', '27届秋招')
    assert left == right
