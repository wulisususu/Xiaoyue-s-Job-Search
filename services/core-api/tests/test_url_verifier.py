from app.verification.ats import detect_ats
from app.verification.verifier import HttpResponse, verify_url


def test_detects_known_ats_from_domain_or_page_markers():
    assert detect_ats('https://app.mokahr.com/campus-recruitment/acme/1', '') == 'moka'
    assert detect_ats('https://jobs.example.com', '<script src="/assets/beisen-recruit.js"></script>') == 'beisen'
    assert detect_ats('https://foo.hotjob.cn/wt/foo/web/index', '') == 'hotjob'
    assert detect_ats('https://jobs.feishu.cn/something', '') == 'feishu'


def test_active_job_detail_with_apply_button_is_verified_apply():
    response = HttpResponse(
        status_code=200,
        final_url='https://app.mokahr.com/campus-recruitment/acme/123',
        body='<html><h1>视觉设计师</h1><p>职位详情</p><button>立即申请</button></html>',
        redirect_chain=['https://old.example.com/job/123', 'https://app.mokahr.com/campus-recruitment/acme/123'],
    )
    result = verify_url('https://old.example.com/job/123', transport=lambda url: response)
    assert result.health == 'VERIFIED_APPLY'
    assert result.ats == 'moka'
    assert result.page_type == 'job_detail'
    assert result.final_url == response.final_url
    assert '立即申请' in result.apply_evidence


def test_dead_and_blocked_links_are_not_verified():
    dead = verify_url('https://example.com/dead', transport=lambda url: HttpResponse(404, url, 'not found', [url]))
    blocked = verify_url('https://example.com/blocked', transport=lambda url: HttpResponse(403, url, 'forbidden', [url]))
    assert dead.health == 'BROKEN'
    assert blocked.health == 'ACCESS_BLOCKED'
    assert dead.page_type == 'unknown'


def test_closed_job_is_stale_even_when_http_200():
    response = HttpResponse(200, 'https://example.com/job/1', '<h1>职位已下线</h1><p>招聘已结束</p>', ['https://example.com/job/1'])
    result = verify_url('https://example.com/job/1', transport=lambda url: response)
    assert result.health == 'STALE'
    assert result.page_type == 'closed'


def test_login_page_and_career_home_are_classified_without_promotion():
    login = verify_url(
        'https://example.com/login',
        transport=lambda url: HttpResponse(200, url, '<form><input type="password"><button>登录</button></form>', [url]),
    )
    career = verify_url(
        'https://example.com/campus',
        transport=lambda url: HttpResponse(200, url, '<h1>校园招聘</h1><a href="/jobs">招聘职位</a>', [url]),
    )
    assert login.health == 'LOGIN_REQUIRED'
    assert login.page_type == 'login'
    assert career.health == 'HEALTHY'
    assert career.page_type == 'career_home'
