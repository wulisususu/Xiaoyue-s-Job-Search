from __future__ import annotations

import base64
import datetime as dt
import json
import re
import urllib.parse
import urllib.request
import zlib
from collections.abc import Callable

TD_PAD_ID = "DTkRMUVhoUWJXZEhJ"
TD_REF = f"https://docs.qq.com/smartsheet/{TD_PAD_ID}"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
SHEETS: tuple[tuple[str, str, int], ...] = (("tTNjGc", "27届内推汇总", 200), ("tvVDZj", "实习提前批每日更新", 2000))
CITY_LIST = ("北京", "上海", "广州", "深圳", "成都", "杭州", "武汉", "南京", "重庆", "西安", "苏州", "天津", "长沙", "郑州", "青岛", "东莞", "佛山", "宁波", "无锡", "厦门", "福州", "济南", "合肥", "昆明", "大连", "哈尔滨", "沈阳", "长春", "石家庄", "太原", "南昌", "贵阳", "南宁", "海口", "兰州", "银川", "西宁", "呼和浩特", "乌鲁木齐", "拉萨")
Fetcher = Callable[[str, int], str]


def _default_fetcher(sheet_id: str, rows: int) -> str:
    params = {"u": "", "noEscape": "1", "enableSmartsheetSplit": "1", "supportOptimizedVer": "4", "chunkCellSize": "15000", "normal": "1", "outformat": "1", "wb": "1", "nowb": "0", "callback": "x", "xsrf": "", "id": TD_PAD_ID, "subId": sheet_id, "startrow": "0", "endrow": str(rows)}
    url = "https://docs.qq.com/dop-api/opendoc?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": TD_REF, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=40) as resp:
        return resp.read().decode("utf-8", "ignore")


def decode_opendoc_jsonp(text: str) -> str:
    match = re.match(r"^[^(]*\((.*)\)\s*;?\s*$", text, re.S)
    if not match:
        raise ValueError("invalid Tencent opendoc JSONP")
    data = json.loads(match.group(1))
    t = data.get("clientVars", {}).get("collab_client_vars", {}).get("initialAttributedText", {}).get("text", [None])[0]
    if not isinstance(t, dict) or not t.get("smartsheet"):
        raise ValueError("missing smartsheet payload")
    b64 = str(t["smartsheet"]).replace("\n", "").replace("\r", "").replace(" ", "")
    raw = base64.b64decode(b64 + "=" * (-len(b64) % 4))
    return zlib.decompress(raw).decode("utf-8", "ignore")


def _field_value(value: object, meta: dict) -> str:
    if not isinstance(value, dict): return ""
    field_type = meta.get("type")
    if field_type == 1:
        arr = value.get("k1") or []
        if isinstance(arr, list): return "".join(str(x.get("k2") or x.get("k1") or "") for x in arr if isinstance(x, dict))
        return str(arr)
    if field_type == 4:
        ts = value.get("k4")
        if ts is None: return ""
        try:
            n = int(ts); stamp = n / 1000 if n > 100_000_000_000 else n
            return dt.datetime.fromtimestamp(stamp).strftime("%Y-%m-%d")
        except (TypeError, ValueError, OSError): return ""
    if field_type == 8:
        url_value = value.get("k8") or value.get("k1")
        if isinstance(url_value, str): return url_value
        if isinstance(url_value, list): return " ".join(str(x.get("k2")) for x in url_value if isinstance(x, dict) and x.get("k2"))
        return ""
    if field_type in (9, 17):
        ids = value.get("k9") or value.get("k17") or []
        if isinstance(ids, list): return "/".join(str(meta.get("options", {}).get(i, i)) for i in ids)
        return str(ids)
    for candidate in value.values():
        if isinstance(candidate, list) and candidate:
            texts = [str(x.get("k2")) for x in candidate if isinstance(x, dict) and x.get("k2")]
            if texts: return "/".join(texts)
    return ""


def parse_sheet(json_text: str) -> list[dict[str, str]]:
    rows = json.loads(json_text)
    if not rows or not isinstance(rows[0], list) or len(rows[0]) < 2: return []
    meta_root, data_root = rows[0][0], rows[0][1]
    definitions = meta_root.get("c", {}).get("k3", {}).get("k3", {})
    field_meta: dict[str, dict] = {}
    for field_id, definition in definitions.items():
        if not isinstance(definition, dict): continue
        options: dict[str, str] = {}
        option_def = definition.get("k17") or definition.get("k9") or {}
        option_rows = option_def.get("k3") if isinstance(option_def, dict) else None
        if isinstance(option_rows, list):
            for option in option_rows:
                if isinstance(option, dict) and option.get("k1") and option.get("k2"): options[str(option["k1"])] = str(option["k2"])
        field_meta[str(field_id)] = {"name": str(definition.get("k30") or field_id), "type": definition.get("k31"), "options": options}
    records = data_root.get("c", {}).get("k2", {}).get("k1", {})
    out: list[dict[str, str]] = []
    for node in records.values():
        fields = node.get("k1") if isinstance(node, dict) else node
        if not isinstance(fields, dict): continue
        record: dict[str, str] = {}
        for field_id, field_value in fields.items():
            meta = field_meta.get(str(field_id))
            if meta: record[meta["name"]] = _field_value(field_value, meta)
        out.append(record)
    return out


def _map_industry(text: str) -> str:
    if not text: return "综合"
    rules = ((r"互联网|软件|游戏|AI|大模型|电商|科技", "互联网科技"), (r"银行|金融|证券|基金|保险|信托", "银行金融"), (r"能源|电力|燃气|核能", "能源电力"), (r"通信|5G|电信", "通信运营商"), (r"汽车|驾驶", "汽车制造"), (r"医药|医疗|生物|制药", "医药医疗"), (r"快消|零售|食品|饮料|家电", "快消零售"), (r"装备|机械|制造|机器人|半导体|芯片|硬件", "装备重工"), (r"建筑|地产|市政|工程", "建筑地产"), (r"石油|石化|化工", "石油化工"), (r"航天|航空|军工|国防", "航天军工"), (r"物流|运输|交通|邮政", "交通物流"), (r"农业|农林|畜牧|食品", "农业食品"))
    for pattern, value in rules:
        if re.search(pattern, text, re.I): return value
    return "综合"


def _extract_location(text: str) -> str:
    if not text: return ""
    if re.search(r"多地|全国|不限地点|工作地不限", text): return "多地"
    found = [city for city in CITY_LIST if city in text]
    return "/".join(found[:4])


def _is_expired(text: str, today: dt.date) -> bool:
    if not text: return False
    value = re.sub(r"\s+", " ", text).strip()
    if re.search(r"招满即止|招聘中|长期|不限|持续", value): return False
    if re.search(r"已结束|已截止|过期|截止$", value): return True
    match = re.search(r"(\d{4})[年/\-.\s]\s*(\d{1,2})[月/\-.\s]\s*(\d{1,2})日?", value)
    if match:
        try: return dt.date(*(int(part) for part in match.groups())) < today
        except ValueError: return False
    short = re.search(r"(\d{1,2})月(\d{1,2})日", value) or re.search(r"^(\d{1,2})[/\-.](\d{1,2})$", value)
    if short:
        try: return dt.date(today.year, int(short.group(1)), int(short.group(2))) < today
        except ValueError: return False
    return False


def to_job_row(record: dict[str, str], today: dt.date | None = None) -> dict[str, str] | None:
    resolved_today = today or dt.date.today()
    company = (record.get("公司名称") or "").strip(); position = (record.get("招聘岗位") or "").strip()[:600]
    if not company and not position: return None
    deadline = (record.get("招聘截止日期") or "").strip()
    if _is_expired(deadline, resolved_today): return None
    location_text = (record.get("工作地点") or "") + " " + (record.get("行业") or "")
    location = _extract_location(location_text) or _extract_location(record.get("工作地点") or "")
    raw_url = (record.get("投递链接or推文") or record.get("投递链接") or "").strip()
    match = re.match(r"^(https?://[^\s]+)", raw_url); clean_url = match.group(1) if match else ""
    industry = _map_industry(record.get("行业") or ""); batch = (record.get("批次") or "").strip(); title = position or batch or "校招信息"
    return {"c": company, "p": title, "l": location, "e": "", "w": f"批次:{batch}" if batch else "", "d": deadline, "s": "腾讯文档校招雷达", "t": "互联网" if industry == "互联网科技" else "其他", "ind": industry, "u": clean_url}


def fetch_tencent_payload(fetcher: Fetcher | None = None, today: dt.date | None = None) -> dict:
    resolved_fetcher = fetcher or _default_fetcher; resolved_today = today or dt.date.today(); jobs: list[dict[str, str]] = []; seen: set[str] = set()
    for sheet_id, _name, limit in SHEETS:
        jsonp = resolved_fetcher(sheet_id, limit)
        for record in parse_sheet(decode_opendoc_jsonp(jsonp)):
            row = to_job_row(record, resolved_today)
            if row is None: continue
            key = f"{row['c']}|{row['p']}|{row['l']}"
            if key in seen: continue
            seen.add(key); jobs.append(row)
    return {"updated": resolved_today.isoformat(), "count": len(jobs), "jobs": jobs}
