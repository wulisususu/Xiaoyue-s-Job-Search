import json
import sqlite3
import subprocess
import sys
from pathlib import Path


def _write_sources(tmp_path: Path) -> tuple[Path, Path, Path]:
    workfind_db = tmp_path / 'workfind.db'
    con = sqlite3.connect(workfind_db)
    con.executescript('''
        CREATE TABLE provinces (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE companies (id INTEGER PRIMARY KEY, province_id INTEGER, name TEXT NOT NULL, level TEXT);
        CREATE TABLE central_enterprises (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
    ''')
    con.execute("INSERT INTO provinces VALUES (1, '安徽')")
    con.execute("INSERT INTO companies VALUES (1, 1, '安徽省投资集团控股有限公司', '省级')")
    con.commit(); con.close()

    relations = tmp_path / 'relations.json'
    relations.write_text('[]', encoding='utf-8')

    jobs = tmp_path / 'jobs.json'
    jobs.write_text(json.dumps({
        'updated': '2026-09-03', 'count': 1,
        'jobs': [{'c': '安徽省投资集团控股有限公司', 'p': '视觉设计', 'l': '合肥', 'w': '27届秋招', 'd': '招满即止', 'ind': '投资', 'u': ''}]
    }, ensure_ascii=False), encoding='utf-8')
    return workfind_db, relations, jobs


def test_import_job_sources_command_populates_target_database(tmp_path: Path):
    workfind_db, relations, jobs = _write_sources(tmp_path)
    repo_root = Path(__file__).resolve().parents[3]
    data_dir = tmp_path / 'data'
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / 'scripts' / 'import_job_sources.py'),
            '--workfind-db', str(workfind_db),
            '--workfind-relations', str(relations),
            '--xiaozhao-jobs', str(jobs),
            '--data-dir', str(data_dir),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload['workfind']['companies_created'] == 1
    assert payload['xiaozhao']['jobs_created'] == 1

    con = sqlite3.connect(data_dir / 'xiaoyue.db')
    assert con.execute('SELECT count(*) FROM companies').fetchone()[0] == 1
    assert con.execute('SELECT count(*) FROM jobs').fetchone()[0] == 1
    con.close()
