import base64
import json
import zlib
from datetime import date

from app.sources.tencent_sheet import decode_opendoc_jsonp, fetch_tencent_payload, parse_sheet, to_job_row


def _text(value: str):
    return {'k1': [{'k2': value}]}


def _jsonp(records):
    defs = {
        'f_company': {'k30': '公司名称', 'k31': 1},
        'f_position': {'k30': '招聘岗位', 'k31': 1},
        'f_location': {'k30': '工作地点', 'k31': 1},
        'f_deadline': {'k30': '招聘截止日期', 'k31': 1},
        'f_url': {'k30': '投递链接or推文', 'k31': 8},
        'f_batch': {'k30': '批次', 'k31': 1},
        'f_industry': {'k30': '行业', 'k31': 1},
    }
    raw_records = {}
    for i, record in enumerate(records):
        raw_records[str(i)] = {'k1': {
            'f_company': _text(record['公司名称']),
            'f_position': _text(record['招聘岗位']),
            'f_location': _text(record['工作地点']),
            'f_deadline': _text(record['招聘截止日期']),
            'f_url': {'k8': record['投递链接or推文']},
            'f_batch': _text(record['批次']),
            'f_industry': _text(record['行业']),
        }}
    sheet = [[
        {'c': {'k3': {'k3': defs}}},
        {'c': {'k2': {'k1': raw_records}}},
    ]]
    compressed = zlib.compress(json.dumps(sheet, ensure_ascii=False).encode('utf-8'))
    b64 = base64.b64encode(compressed).decode('ascii')
    return 'x(' + json.dumps({
        'clientVars': {'collab_client_vars': {'initialAttributedText': {'text': [{'smartsheet': b64}]}}}
    }, ensure_ascii=False) + ')'


def test_decode_and_parse_tencent_opendoc_jsonp():
    text = _jsonp([{
        '公司名称': '中国移动',
        '招聘岗位': '视觉设计',
        '工作地点': '南京',
        '招聘截止日期': '招满即止',
        '投递链接or推文': 'https://example.com/apply',
        '批次': '27届秋招',
        '行业': '通信',
    }])
    inflated = decode_opendoc_jsonp(text)
    rows = parse_sheet(inflated)
    assert rows == [{
        '公司名称': '中国移动',
        '招聘岗位': '视觉设计',
        '工作地点': '南京',
        '招聘截止日期': '招满即止',
        '投递链接or推文': 'https://example.com/apply',
        '批次': '27届秋招',
        '行业': '通信',
    }]


def test_to_job_row_keeps_discovery_semantics():
    row = to_job_row({
        '公司名称': '中国移动',
        '招聘岗位': '视觉设计 / 宣传策划',
        '工作地点': '南京、北京',
        '招聘截止日期': '招满即止',
        '投递链接or推文': 'https://example.com/apply tracking-text',
        '批次': '27届秋招',
        '行业': '通信运营商',
    }, today=date(2026, 9, 16))
    assert row == {
        'c': '中国移动',
        'p': '视觉设计 / 宣传策划',
        'l': '北京/南京',
        'e': '',
        'w': '批次:27届秋招',
        'd': '招满即止',
        's': '腾讯文档校招雷达',
        't': '其他',
        'ind': '通信运营商',
        'u': 'https://example.com/apply',
    }


def test_fetch_tencent_payload_merges_and_deduplicates_sheets():
    row = {
        '公司名称': '中国移动',
        '招聘岗位': '视觉设计',
        '工作地点': '南京',
        '招聘截止日期': '招满即止',
        '投递链接or推文': 'https://example.com/apply',
        '批次': '27届秋招',
        '行业': '通信',
    }
    fixtures = {'tTNjGc': _jsonp([row]), 'tvVDZj': _jsonp([row])}

    payload = fetch_tencent_payload(
        fetcher=lambda sheet_id, rows: fixtures[sheet_id],
        today=date(2026, 9, 16),
    )
    assert payload['updated'] == '2026-09-16'
    assert payload['count'] == 1
    assert len(payload['jobs']) == 1
    assert payload['jobs'][0]['c'] == '中国移动'
