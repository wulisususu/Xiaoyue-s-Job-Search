import { ChangeEvent, useEffect, useState } from 'react';
import { createExtractionRun } from '../api/aiClient';
import { getResumes, importResume, type ResumeVersion } from '../api/resumesClient';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function extractionLabel(status: string): string {
  if (status === 'EXTRACTED') return '已提取';
  if (status === 'OCR_REQUIRED') return '需要 OCR';
  if (status === 'FAILED') return '解析失败';
  return '处理中';
}

function extractionClass(status: string): string {
  if (status === 'EXTRACTED') return 'verified';
  if (status === 'OCR_REQUIRED') return 'warning';
  return '';
}

function upsertResume(items: ResumeVersion[], incoming: ResumeVersion): ResumeVersion[] {
  const next = items.filter((item) => item.id !== incoming.id);
  next.push(incoming);
  return next.sort((a, b) => b.version_number - a.version_number);
}

export function ResumesPage() {
  const [resumes, setResumes] = useState<ResumeVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [extractingResumeId, setExtractingResumeId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getResumes()
      .then((items) => {
        if (active) setResumes(items);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : '简历列表加载失败');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  async function handleImport(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setError(null);
    setMessage(null);
    try {
      const imported = await importResume(file);
      setResumes((items) => upsertResume(items, imported));
      setMessage(imported.deduplicated ? '文件内容已存在，已复用原有不可变版本。' : `已创建简历版本 V${imported.version_number}。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '简历导入失败');
    } finally {
      setImporting(false);
      event.target.value = '';
    }
  }

  async function handleAIExtraction(resume: ResumeVersion) {
    setExtractingResumeId(resume.id);
    setError(null);
    setMessage(null);
    try {
      const run = await createExtractionRun(resume.id);
      if (run.status !== 'SUCCEEDED') {
        throw new Error(run.error || 'AI 提取运行失败');
      }
      const total = run.scalar_draft_count + run.collection_draft_count;
      const refreshed = await getResumes();
      setResumes(refreshed);
      setMessage(`AI 解析完成，已生成 ${total} 项资料候选；请前往“我的资料”审核后再进入正式 Profile。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'AI 解析资料失败');
    } finally {
      setExtractingResumeId(null);
    }
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Resume Vault</p>
          <h1>简历库</h1>
          <p>每次导入都按 SHA-256 固化为不可变版本；重复文件只复用，不覆盖历史版本。</p>
        </div>
        <label className={`primary-button resume-import-button${importing ? ' disabled' : ''}`}>
          <span>{importing ? '正在导入…' : '导入简历'}</span>
          <input
            aria-label="导入简历"
            className="visually-hidden"
            type="file"
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            disabled={importing}
            onChange={handleImport}
          />
        </label>
      </header>

      <section className="resume-summary" aria-label="简历库说明">
        <div><strong>{resumes.length}</strong><span>不可变版本</span></div>
        <div><strong>{resumes.reduce((total, item) => total + item.pending_draft_count, 0)}</strong><span>待审核字段</span></div>
        <p>支持 PDF / DOCX，单文件最大 50 MiB。解析结果只生成候选 Draft，不会自动改写“我的资料”。</p>
      </section>

      {message && <p className="resume-message success">{message}</p>}
      {error && <p className="resume-message error">{error}</p>}

      {loading ? (
        <article className="empty-panel"><h2>正在读取简历库</h2><p>从本地 Core API 加载已保存的不可变版本。</p></article>
      ) : resumes.length === 0 ? (
        <article className="empty-panel"><h2>简历库为空</h2><p>导入 PDF 或 DOCX 后，系统会保留文件哈希、版本号和解析状态。</p></article>
      ) : (
        <div className="resume-list">
          {resumes.map((resume) => (
            <article className="resume-card" key={resume.id}>
              <div className="resume-card-main">
                <div className="resume-card-heading">
                  <div>
                    <div className="badge-row">
                      <span className="soft-badge resume-version">V{resume.version_number}</span>
                      <span className={`soft-badge ${extractionClass(resume.extraction_status)}`}>{extractionLabel(resume.extraction_status)}</span>
                      {resume.pending_draft_count > 0 && <span className="soft-badge warning">{resume.pending_draft_count} 项待审核</span>}
                    </div>
                    <h2>{resume.original_filename}</h2>
                  </div>
                  <span className="source-date">{formatDate(resume.created_at)}</span>
                </div>
                <div className="resume-meta">
                  <span>{resume.file_ext.replace('.', '').toUpperCase()}</span>
                  <span>{formatBytes(resume.size_bytes)}</span>
                  <span>SHA-256 {resume.sha256.slice(0, 12)}…</span>
                  {resume.parser_name && <span>解析器 {resume.parser_name}{resume.parser_version ? ` ${resume.parser_version}` : ''}</span>}
                </div>
                {resume.extraction_status === 'OCR_REQUIRED' && (
                  <p className="resume-note warning-note">当前版本没有可用文本层，需要 OCR 后才能继续生成资料候选字段；原始文件仍已安全保存为独立版本。</p>
                )}
                {resume.extraction_status === 'FAILED' && (
                  <p className="resume-note error-note">解析失败{resume.extraction_error ? `：${resume.extraction_error}` : '，请检查文件是否损坏。'}</p>
                )}
                {resume.extraction_status === 'EXTRACTED' && resume.pending_draft_count === 0 && (
                  <p className="resume-note">文本已提取，可调用已配置的 AI Provider 生成资料候选；未经审核不会写入正式 Profile。</p>
                )}
                {resume.extraction_status === 'EXTRACTED' && (
                  <div className="resume-card-actions">
                    <button
                      className="secondary-button"
                      disabled={extractingResumeId !== null}
                      onClick={() => handleAIExtraction(resume)}
                      type="button"
                    >
                      {extractingResumeId === resume.id ? 'AI 解析中…' : 'AI 解析资料'}
                    </button>
                    {resume.pending_draft_count > 0 && <a className="secondary-button" href="/profile">审核候选</a>}
                  </div>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
