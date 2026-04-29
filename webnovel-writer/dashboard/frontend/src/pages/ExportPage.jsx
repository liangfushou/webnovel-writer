import { useEffect, useState } from 'react'
import Badge from '../components/Badge.jsx'
import { fetchJSON, postJSONBody } from '../api.js'

const FORMAT_OPTIONS = [
    { key: 'markdown', label: '文稿', desc: '保留章节结构，适合继续编辑' },
    { key: 'txt', label: '纯文本', desc: '适合复制、归档和平台整理' },
    { key: 'epub', label: '电子书', desc: '适合阅读器归档，需要电子书依赖' },
]

const RANGE_ALL = '全部'

function normalizeRangeSpec(value) {
    return String(value || '').trim() === RANGE_ALL ? 'all' : value
}

function formatExportFormat(value) {
    const formatName = String(value || '').toLowerCase()
    if (formatName === 'markdown') return '文稿'
    if (formatName === 'txt') return '纯文本'
    if (formatName === 'epub') return '电子书'
    return value || '—'
}

function formatSize(bytes) {
    const size = Number(bytes || 0)
    if (size < 1024) return `${size} B`
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
    return `${(size / 1024 / 1024).toFixed(2)} MB`
}

function formatExportDate(timestamp) {
    const date = new Date(Number(timestamp || 0) * 1000)
    if (Number.isNaN(date.getTime())) return '—'
    return date.toLocaleString('zh-CN', {
        hour12: false,
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    })
}

export default function ExportPage() {
    const [info, setInfo] = useState(null)
    const [history, setHistory] = useState([])
    const [format, setFormat] = useState('markdown')
    const [range, setRange] = useState(RANGE_ALL)
    const [author, setAuthor] = useState('')
    const [exporting, setExporting] = useState(false)
    const [result, setResult] = useState(null)
    const [activeTab, setActiveTab] = useState('new')

    function refresh() {
        fetchJSON('/api/export/info').then(setInfo).catch(() => setInfo(null))
        fetchJSON('/api/export/files').then(setHistory).catch(() => setHistory([]))
    }

    useEffect(() => {
        refresh()
    }, [])

    async function handleExport() {
        setExporting(true)
        setResult(null)
        try {
            const payload = await postJSONBody('/api/export/do', {
                format,
                range_spec: normalizeRangeSpec(range || RANGE_ALL),
                author,
            })
            setResult(payload)
            fetchJSON('/api/export/files').then(setHistory).catch(() => {})
        } catch (error) {
            setResult({ success: false, error: error.message })
        } finally {
            setExporting(false)
        }
    }

    const currentRange = info?.chapter_min && info?.chapter_max
        ? `${info.chapter_min}-${info.chapter_max}`
        : RANGE_ALL

    return (
        <section className="dashboard-page">
            <header className="page-header">
                <h2>导出小说</h2>
                <Badge tone="blue">{info?.chapter_count || 0} 章</Badge>
                {info?.output_dir ? <Badge tone="cyan" title={info.output_dir}>导出目录</Badge> : null}
            </header>

            <div className="tab-strip">
                <button type="button" className={`tab-btn ${activeTab === 'new' ? 'active' : ''}`.trim()} onClick={() => setActiveTab('new')}>
                    新建导出
                </button>
                <button type="button" className={`tab-btn ${activeTab === 'history' ? 'active' : ''}`.trim()} onClick={() => setActiveTab('history')}>
                    导出历史（{history.length}）
                </button>
                <button type="button" className="tab-btn" onClick={refresh}>刷新</button>
            </div>

            {activeTab === 'new' ? (
                <>
                    <div className="stat-grid">
                        <article className="card stat-card">
                            <span className="stat-label">可导出章节</span>
                            <span className="stat-value">{info?.chapter_count || 0}</span>
                            <span className="stat-sub">范围 {info?.chapter_range || '—'}</span>
                        </article>
                        <article className="card stat-card">
                            <span className="stat-label">封面</span>
                            <span className="stat-value plain">{info?.cover_exists || info?.cover_png_exists ? '已检测' : '无'}</span>
                            <span className="stat-sub">电子书会自动尝试使用</span>
                        </article>
                        <article className="card stat-card">
                            <span className="stat-label">样式</span>
                            <span className="stat-value plain">{info?.style_exists ? '已检测' : '默认'}</span>
                            <span className="stat-sub">style.css 可覆盖电子书样式</span>
                        </article>
                    </div>

                    <article className="card">
                        <div className="card-header">
                            <div>
                                <div className="section-label">输出格式</div>
                                <div className="card-title">输出格式</div>
                            </div>
                        </div>
                        <div className="choice-grid">
                            {FORMAT_OPTIONS.map(option => (
                                <button
                                    key={option.key}
                                    type="button"
                                    className={`choice-card ${format === option.key ? 'selected' : ''}`.trim()}
                                    onClick={() => setFormat(option.key)}
                                >
                                    <strong>{option.label}</strong>
                                    <span>{option.desc}</span>
                                </button>
                            ))}
                        </div>
                    </article>

                    <article className="card">
                        <div className="card-header">
                            <div>
                                <div className="section-label">导出范围</div>
                                <div className="card-title">导出范围</div>
                            </div>
                        </div>
                        <div className="filter-group">
                            <button type="button" className={`filter-btn ${range === RANGE_ALL ? 'active' : ''}`.trim()} onClick={() => setRange(RANGE_ALL)}>
                                全部章节
                            </button>
                            <button type="button" className={`filter-btn ${range === currentRange ? 'active' : ''}`.trim()} onClick={() => setRange(currentRange)}>
                                当前进度
                            </button>
                        </div>
                        <div className="form-grid">
                            <label className="form-field">
                                <span>自定义范围</span>
                                <input className="text-input" value={range} onChange={event => setRange(event.target.value)} placeholder="全部 / 1-10 / 1,3,5" />
                            </label>
                            {format === 'epub' ? (
                                <label className="form-field">
                                    <span>作者名</span>
                                    <input className="text-input" value={author} onChange={event => setAuthor(event.target.value)} placeholder="电子书元数据，可留空" />
                                </label>
                            ) : null}
                        </div>
                    </article>

                    <article className="card">
                        <div className="action-row">
                            <button type="button" className="page-btn primary-action" onClick={handleExport} disabled={exporting || !info?.chapter_count}>
                                {exporting ? '导出中...' : '开始导出'}
                            </button>
                            <span className="page-info">文件会写入：{info?.output_dir || '导出目录'}</span>
                        </div>

                        {result ? (
                            <div className={`notice-card ${result.success ? 'notice-green' : 'notice-red'}`}>
                                {result.success ? (
                                    <>
                                        <strong>导出成功：</strong>
                                        {result.filename}，{result.chapter_count} 章，{formatSize(result.file_size)}
                                        <a className="download-link" href={`/api/export/download/${encodeURIComponent(result.filename)}`} target="_blank" rel="noopener noreferrer">
                                            下载文件
                                        </a>
                                    </>
                                ) : (
                                    <>导出失败：{result.error}</>
                                )}
                            </div>
                        ) : null}
                    </article>
                </>
            ) : (
                <article className="card">
                    <div className="card-header">
                        <div>
                            <div className="section-label">导出历史</div>
                            <div className="card-title">导出历史</div>
                        </div>
                    </div>
                    {history.length ? (
                        <div className="table-wrap">
                            <table className="data-table">
                                <thead>
                                    <tr><th>文件</th><th>格式</th><th>大小</th><th>时间</th><th>操作</th></tr>
                                </thead>
                                <tbody>
                                    {history.map(item => (
                                        <tr key={item.filename}>
                                            <td>{item.filename}</td>
                                            <td>{formatExportFormat(item.format)}</td>
                                            <td>{formatSize(item.size)}</td>
                                            <td>{formatExportDate(item.modified)}</td>
                                            <td>
                                                <a className="download-link inline" href={`/api/export/download/${encodeURIComponent(item.filename)}`} target="_blank" rel="noopener noreferrer">
                                                    下载
                                                </a>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    ) : (
                        <div className="empty-state">
                            <p>暂无导出历史。</p>
                        </div>
                    )}
                </article>
            )}
        </section>
    )
}
