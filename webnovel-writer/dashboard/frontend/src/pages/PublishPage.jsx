import { useEffect, useMemo, useState } from 'react'
import Badge from '../components/Badge.jsx'
import { fetchChapters, fetchJSON, postJSONBody } from '../api.js'
import { formatChapterLabel } from '../lib/format.js'
import { formatStatus } from '../lib/labels.js'

function chapterNumberFromRemoteTitle(item) {
    const title = String(item?.title || item?.chapter_title || '')
    const match = title.match(/第\s*(\d+)\s*章/)
    return match ? Number(match[1]) : 0
}

function buildRangeSpec(chapters) {
    return [...chapters].sort((left, right) => left - right).join(',')
}

const BOOK_STATUS_LABELS = {
    0: '未发布',
    1: '连载中',
    2: '已完结',
    3: '已下架',
    4: '审核中',
}

function stripHTML(value) {
    return String(value || '').replace(/<[^>]+>/g, '').trim()
}

function formatBookStatus(book) {
    const introTag = String(book?.book_intro?.tag || '').trim()
    if (introTag) return introTag
    const introStatus = String(book?.book_intro?.status || '').trim()
    if (introStatus === 'sign_audit') return '审核中'
    const status = book?.status
    return BOOK_STATUS_LABELS[status] || formatStatus(status)
}

function bookStatusTone(book) {
    const label = formatBookStatus(book)
    if (label.includes('审核')) return 'amber'
    if (label.includes('下架') || label.includes('失败') || label.includes('异常')) return 'red'
    if (label.includes('完结') || label.includes('连载')) return 'green'
    return 'blue'
}

function bookStatusTitle(book) {
    return stripHTML(book?.book_intro?.message)
}

function buildChapterGroups(chapters) {
    const groups = new Map()
    for (const chapter of chapters) {
        const volume = Number(chapter.volume || 0)
        const key = volume > 0 ? `volume-${volume}` : 'unassigned'
        if (!groups.has(key)) {
            groups.set(key, {
                key,
                volume,
                title: chapter.volume_title || (volume > 0 ? `第${volume}卷` : '未分卷章节'),
                range: chapter.volume_range || '',
                chapters: [],
            })
        }
        groups.get(key).chapters.push(chapter)
    }
    return [...groups.values()]
        .map(group => ({
            ...group,
            chapters: group.chapters.sort((left, right) => Number(left.chapter) - Number(right.chapter)),
        }))
        .sort((left, right) => (left.volume || 999999) - (right.volume || 999999))
}

export default function PublishPage() {
    const [status, setStatus] = useState(null)
    const [statusError, setStatusError] = useState('')
    const [setupTask, setSetupTask] = useState(null)
    const [setupRunning, setSetupRunning] = useState(false)
    const [books, setBooks] = useState([])
    const [booksLoading, setBooksLoading] = useState(false)
    const [selectedBook, setSelectedBook] = useState('')
    const [remoteChapters, setRemoteChapters] = useState([])
    const [remoteLoading, setRemoteLoading] = useState(false)
    const [localChapters, setLocalChapters] = useState([])
    const [expandedVolumes, setExpandedVolumes] = useState({})
    const [selectedChapters, setSelectedChapters] = useState(new Set())
    const [publishMode, setPublishMode] = useState('draft')
    const [publishing, setPublishing] = useState(false)
    const [task, setTask] = useState(null)
    const [message, setMessage] = useState(null)
    const [showCreateForm, setShowCreateForm] = useState(false)
    const [newBook, setNewBook] = useState({
        title: '',
        genre: '',
        synopsis: '',
        protagonist1: '',
        protagonist2: '',
    })

    function showMessage(text, tone = 'green') {
        setMessage({ text, tone })
    }

    function refreshStatus() {
        setStatusError('')
        fetchJSON('/api/publish/status')
            .then(setStatus)
            .catch(error => {
                setStatus(null)
                setStatusError(error.message)
            })
    }

    function refreshLocalChapters() {
        fetchChapters()
            .then(setLocalChapters)
            .catch(() => setLocalChapters([]))
    }

    async function refreshBooks() {
        if (!status?.ready) {
            showMessage('发布环境还没就绪，请先按提示完成 Playwright 和番茄登录配置。', 'amber')
            return
        }
        setBooksLoading(true)
        try {
            setBooks(await fetchJSON('/api/publish/books'))
            showMessage('书籍列表已刷新')
        } catch (error) {
            showMessage(`书籍列表读取失败：${error.message}`, 'red')
        } finally {
            setBooksLoading(false)
        }
    }

    async function handleSetupBrowser() {
        const confirmed = window.confirm('将打开本机浏览器用于番茄作家后台登录。你需要在弹出的浏览器里手动完成登录，面板不会自动输入账号密码。确认打开？')
        if (!confirmed) return

        setSetupRunning(true)
        setSetupTask(null)
        try {
            const result = await postJSONBody('/api/publish/setup-browser', {})
            setSetupTask({
                task_id: result.task_id,
                status: 'pending',
                message: '正在打开登录浏览器…',
                logs: ['请在弹出的浏览器中手动登录番茄作家后台。'],
            })
            showMessage('登录浏览器正在打开，请在浏览器中手动完成番茄登录。', 'amber')
        } catch (error) {
            setSetupRunning(false)
            showMessage(`登录浏览器启动失败：${error.message}`, 'red')
        }
    }

    useEffect(() => {
        refreshStatus()
        refreshLocalChapters()
    }, [])

    useEffect(() => {
        if (!selectedBook) {
            setRemoteChapters([])
            setSelectedChapters(new Set())
            return
        }
        setRemoteLoading(true)
        setRemoteChapters([])
        setSelectedChapters(new Set())
        fetchJSON(`/api/publish/books/${encodeURIComponent(selectedBook)}/remote-chapters`)
            .then(payload => setRemoteChapters(Array.isArray(payload) ? payload : []))
            .catch(() => setRemoteChapters([]))
            .finally(() => setRemoteLoading(false))
    }, [selectedBook])

    useEffect(() => {
        if (!task || !['pending', 'running'].includes(task.status)) return undefined
        const timer = window.setInterval(() => {
            fetchJSON(`/api/publish/task/${task.task_id}`)
                .then(nextTask => {
                    setTask(nextTask)
                    if (['success', 'failed'].includes(nextTask.status)) {
                        setPublishing(false)
                    }
                })
                .catch(error => {
                    setPublishing(false)
                    showMessage(`任务状态读取失败：${error.message}`, 'red')
                })
        }, 1500)
        return () => window.clearInterval(timer)
    }, [task?.task_id, task?.status])

    useEffect(() => {
        if (!setupTask || !['pending', 'running'].includes(setupTask.status)) return undefined
        const timer = window.setInterval(() => {
            fetchJSON(`/api/publish/task/${setupTask.task_id}`)
                .then(nextTask => {
                    setSetupTask(nextTask)
                    if (['success', 'failed'].includes(nextTask.status)) {
                        setSetupRunning(false)
                        refreshStatus()
                    }
                })
                .catch(error => {
                    setSetupRunning(false)
                    showMessage(`登录任务状态读取失败：${error.message}`, 'red')
                })
        }, 1500)
        return () => window.clearInterval(timer)
    }, [setupTask?.task_id, setupTask?.status])

    const remoteChapterNumbers = useMemo(() => {
        return new Set(remoteChapters.map(chapterNumberFromRemoteTitle).filter(Boolean))
    }, [remoteChapters])

    const unpublishedChapters = useMemo(() => {
        return localChapters.filter(chapter => !remoteChapterNumbers.has(Number(chapter.chapter)))
    }, [localChapters, remoteChapterNumbers])

    const chapterGroups = useMemo(() => buildChapterGroups(localChapters), [localChapters])

    function selectAll() {
        setSelectedChapters(new Set(localChapters.map(chapter => Number(chapter.chapter)).filter(Boolean)))
    }

    function selectUnpublished() {
        setSelectedChapters(new Set(unpublishedChapters.map(chapter => Number(chapter.chapter)).filter(Boolean)))
    }

    function selectVolume(group, onlyUnpublished = false) {
        setSelectedChapters(current => {
            const next = new Set(current)
            for (const chapter of group.chapters) {
                const number = Number(chapter.chapter)
                if (!number) continue
                if (onlyUnpublished && remoteChapterNumbers.has(number)) continue
                next.add(number)
            }
            return next
        })
    }

    function clearVolume(group) {
        setSelectedChapters(current => {
            const next = new Set(current)
            for (const chapter of group.chapters) {
                next.delete(Number(chapter.chapter))
            }
            return next
        })
    }

    function toggleVolume(groupKey) {
        setExpandedVolumes(current => ({ ...current, [groupKey]: !(current[groupKey] ?? true) }))
    }

    function toggleChapter(chapter) {
        setSelectedChapters(current => {
            const next = new Set(current)
            if (next.has(chapter)) {
                next.delete(chapter)
            } else {
                next.add(chapter)
            }
            return next
        })
    }

    async function handleCreateBook() {
        if (!newBook.title || !newBook.genre || !newBook.synopsis) {
            showMessage('请填写标题、题材和简介。', 'amber')
            return
        }
        const confirmed = window.confirm('将把新书标题、题材、简介和主角名发送到番茄作家后台创建书籍。确认继续？')
        if (!confirmed) return

        try {
            const result = await postJSONBody('/api/publish/books', newBook)
            showMessage(`书籍创建成功：${result.book_id}`)
            setShowCreateForm(false)
            setNewBook({ title: '', genre: '', synopsis: '', protagonist1: '', protagonist2: '' })
            await refreshBooks()
        } catch (error) {
            showMessage(`创建失败：${error.message}`, 'red')
        }
    }

    async function handlePublish() {
        if (!selectedBook) {
            showMessage('请先选择一本书。', 'amber')
            return
        }
        if (!selectedChapters.size) {
            showMessage('请至少选择一章。', 'amber')
            return
        }
        const rangeSpec = buildRangeSpec(selectedChapters)
        const modeText = publishMode === 'publish' ? '直接发布' : '保存为草稿'
        const confirmed = window.confirm(`将把第 ${rangeSpec} 章上传到番茄作家后台，模式：${modeText}。确认继续？`)
        if (!confirmed) return

        setPublishing(true)
        setTask(null)
        try {
            const result = await postJSONBody('/api/publish/chapters', {
                book_id: selectedBook,
                range_spec: rangeSpec,
                publish_mode: publishMode,
            })
            setTask({
                task_id: result.task_id,
                status: 'pending',
                progress: 0,
                total: 0,
                message: '任务已创建',
                logs: [],
            })
            showMessage('发布任务已创建')
        } catch (error) {
            setPublishing(false)
            showMessage(`发布任务创建失败：${error.message}`, 'red')
        }
    }

    const ready = Boolean(status?.ready)
    const playwright = status?.playwright
    const login = status?.login

    return (
        <section className="dashboard-page">
            <header className="page-header">
                <h2>小说发布</h2>
                <Badge tone={ready ? 'green' : 'amber'}>{ready ? '环境就绪' : '需要配置'}</Badge>
                <Badge tone="blue">默认草稿</Badge>
            </header>

            {message ? (
                <div className={`notice-card notice-${message.tone}`}>
                    {message.text}
                </div>
            ) : null}

            <div className="content-grid two-columns">
                <article className="card">
                    <div className="card-header">
                        <div>
                            <div className="section-label">发布状态</div>
                            <div className="card-title">发布环境</div>
                        </div>
                        <div className="header-badges">
                            <button type="button" className="page-btn" onClick={refreshStatus}>刷新状态</button>
                            <button
                                type="button"
                                className="page-btn"
                                onClick={handleSetupBrowser}
                                disabled={setupRunning || playwright?.available === false}
                            >
                                {setupRunning ? '等待登录...' : login?.logged_in ? '重新登录' : '打开登录浏览器'}
                            </button>
                        </div>
                    </div>

                    {statusError ? (
                        <div className="notice-card notice-red">{statusError}</div>
                    ) : (
                        <div className="publish-status-grid">
                            <div>
                                <span className="mini-label">浏览器驱动</span>
                                <Badge tone={playwright?.available ? 'green' : 'red'}>
                                    {playwright?.available ? `可用 ${playwright.version}` : '未安装'}
                                </Badge>
                            </div>
                            <div>
                                <span className="mini-label">番茄登录</span>
                                <Badge tone={login?.logged_in ? 'green' : 'red'}>
                                    {login?.logged_in ? '已登录' : '未登录'}
                                </Badge>
                            </div>
                        </div>
                    )}

                    {!ready && login?.cli_command ? (
                        <div className="command-hint">
                            <div className="mini-label">首次配置命令</div>
                            <code>{login.cli_command}</code>
                            <p>也可以直接点击上方“打开登录浏览器”；登录态会保存在本机。</p>
                        </div>
                    ) : null}

                    {setupTask ? (
                        <div className="task-panel compact-task-panel">
                            <div className="summary-card-header">
                                <strong>登录任务 {setupTask.task_id}</strong>
                                <Badge tone={setupTask.status === 'success' ? 'green' : setupTask.status === 'failed' ? 'red' : 'amber'}>
                                    {formatStatus(setupTask.status)}
                                </Badge>
                            </div>
                            {setupTask.message ? <p>{setupTask.message}</p> : null}
                            {setupTask.logs?.length ? (
                                <pre className="task-log">{setupTask.logs.join('\n')}</pre>
                            ) : null}
                        </div>
                    ) : null}
                </article>

                <article className="card">
                    <div className="card-header">
                        <div>
                            <div className="section-label">书籍管理</div>
                            <div className="card-title">书籍管理</div>
                        </div>
                        <div className="header-badges">
                            <button type="button" className="page-btn" onClick={refreshBooks} disabled={booksLoading || !ready}>
                                {booksLoading ? '读取中...' : '刷新书单'}
                            </button>
                            <button type="button" className="page-btn" onClick={() => setShowCreateForm(value => !value)} disabled={!ready}>
                                {showCreateForm ? '收起' : '创建新书'}
                            </button>
                        </div>
                    </div>

                    {showCreateForm ? (
                        <div className="form-panel">
                            <div className="form-grid">
                                <label className="form-field">
                                    <span>小说标题</span>
                                    <input className="text-input" value={newBook.title} onChange={event => setNewBook(current => ({ ...current, title: event.target.value }))} />
                                </label>
                                <label className="form-field">
                                    <span>题材</span>
                                    <input className="text-input" value={newBook.genre} onChange={event => setNewBook(current => ({ ...current, genre: event.target.value }))} placeholder="如 玄幻 / 都市 / 同人" />
                                </label>
                                <label className="form-field wide">
                                    <span>简介</span>
                                    <textarea className="text-input" rows={4} value={newBook.synopsis} onChange={event => setNewBook(current => ({ ...current, synopsis: event.target.value }))} />
                                </label>
                                <label className="form-field">
                                    <span>主角 1</span>
                                    <input className="text-input" value={newBook.protagonist1} onChange={event => setNewBook(current => ({ ...current, protagonist1: event.target.value }))} />
                                </label>
                                <label className="form-field">
                                    <span>主角 2</span>
                                    <input className="text-input" value={newBook.protagonist2} onChange={event => setNewBook(current => ({ ...current, protagonist2: event.target.value }))} />
                                </label>
                            </div>
                            <button type="button" className="page-btn primary-action" onClick={handleCreateBook}>确认创建</button>
                        </div>
                    ) : null}

                    {books.length ? (
                        <div className="table-wrap">
                            <table className="data-table">
                                <thead>
                                    <tr><th>书名</th><th>书籍编号</th><th>状态</th></tr>
                                </thead>
                                <tbody>
                                    {books.map(book => (
                                        <tr
                                            key={book.book_id}
                                            className={selectedBook === book.book_id ? 'entity-row selected' : 'entity-row'}
                                            onClick={() => setSelectedBook(book.book_id)}
                                        >
                                            <td>{book.book_name || '未命名'}</td>
                                            <td><code>{book.book_id}</code></td>
                                            <td>
                                                <Badge tone={bookStatusTone(book)} title={bookStatusTitle(book)}>
                                                    {formatBookStatus(book)}
                                                </Badge>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    ) : (
                        <div className="empty-state compact">
                            <p>{ready ? '刷新书单后选择番茄书籍。' : '完成发布环境配置后可读取书单。'}</p>
                        </div>
                    )}
                </article>
            </div>

            <article className="card">
                <div className="card-header">
                    <div>
                            <div className="section-label">章节选择</div>
                        <div className="card-title">章节选择</div>
                    </div>
                    <div className="header-badges">
                        <Badge tone="cyan">本地 {localChapters.length}</Badge>
                        <Badge tone="green">可发布 {unpublishedChapters.length}</Badge>
                        {remoteLoading ? <Badge tone="amber">平台章节读取中</Badge> : null}
                    </div>
                </div>

                <div className="filter-group">
                    <button type="button" className="filter-btn" onClick={refreshLocalChapters}>刷新本地</button>
                    <button type="button" className="filter-btn" onClick={selectAll}>全选本地</button>
                    <button type="button" className="filter-btn" onClick={selectUnpublished}>仅未发布</button>
                    <button type="button" className="filter-btn" onClick={() => setSelectedChapters(new Set())}>清空</button>
                </div>

                {localChapters.length ? (
                    <div className="chapter-volume-list">
                        {chapterGroups.map(group => {
                            const isOpen = expandedVolumes[group.key] ?? true
                            const selectedInGroup = group.chapters.filter(chapter => selectedChapters.has(Number(chapter.chapter))).length
                            const unpublishedInGroup = group.chapters.filter(chapter => !remoteChapterNumbers.has(Number(chapter.chapter))).length
                            return (
                                <section key={group.key} className="chapter-volume-block">
                                    <div className="chapter-volume-header">
                                        <button
                                            type="button"
                                            className={`tree-item tree-dir ${isOpen ? 'open' : ''}`.trim()}
                                            onClick={() => toggleVolume(group.key)}
                                        >
                                            <span className="tree-glyph" />
                                            <span className="tree-name">{group.title}</span>
                                        </button>
                                        <div className="header-badges">
                                            {group.range ? <Badge tone="purple">{group.range} 章</Badge> : null}
                                            <Badge tone="cyan">{group.chapters.length} 章</Badge>
                                            <Badge tone="green">已选 {selectedInGroup}</Badge>
                                            <Badge tone="blue">可发 {unpublishedInGroup}</Badge>
                                            <button type="button" className="filter-btn compact-filter" onClick={() => selectVolume(group)}>选本卷</button>
                                            <button type="button" className="filter-btn compact-filter" onClick={() => selectVolume(group, true)}>本卷未发</button>
                                            <button type="button" className="filter-btn compact-filter" onClick={() => clearVolume(group)}>清本卷</button>
                                        </div>
                                    </div>

                                    {isOpen ? (
                                        <div className="table-wrap chapter-volume-table">
                                            <table className="data-table">
                                                <thead>
                                                    <tr><th>选择</th><th>章节</th><th>标题</th><th>字数</th><th>平台状态</th></tr>
                                                </thead>
                                                <tbody>
                                                    {group.chapters.map(chapter => {
                                                        const number = Number(chapter.chapter)
                                                        const isPublished = remoteChapterNumbers.has(number)
                                                        return (
                                                            <tr key={number}>
                                                                <td>
                                                                    <input
                                                                        type="checkbox"
                                                                        checked={selectedChapters.has(number)}
                                                                        onChange={() => toggleChapter(number)}
                                                                    />
                                                                </td>
                                                                <td>{formatChapterLabel(number)}</td>
                                                                <td>{chapter.title || '—'}</td>
                                                                <td>{chapter.word_count ? `${chapter.word_count.toLocaleString('zh-CN')} 字` : '—'}</td>
                                                                <td>
                                                                    <Badge tone={isPublished ? 'green' : 'blue'}>
                                                                        {isPublished ? '已在平台' : '可发布'}
                                                                    </Badge>
                                                                </td>
                                                            </tr>
                                                        )
                                                    })}
                                                </tbody>
                                            </table>
                                        </div>
                                    ) : null}
                                </section>
                            )
                        })}
                    </div>
                ) : (
                    <div className="empty-state">
                        <p>暂无可读取章节，请先提交正式章节。</p>
                    </div>
                )}
            </article>

            <article className="card">
                <div className="card-header">
                    <div>
                        <div className="section-label">发布操作</div>
                        <div className="card-title">发布操作</div>
                    </div>
                    <Badge tone={publishMode === 'publish' ? 'red' : 'green'}>
                        {publishMode === 'publish' ? '直接发布' : '草稿模式'}
                    </Badge>
                </div>

                <div className="action-row">
                    <label className="form-field compact-field">
                        <span>发布模式</span>
                        <select className="text-input" value={publishMode} onChange={event => setPublishMode(event.target.value)}>
                            <option value="draft">保存为草稿</option>
                            <option value="publish">直接发布</option>
                        </select>
                    </label>
                    <button
                        type="button"
                        className="page-btn primary-action"
                        disabled={publishing || !selectedBook || selectedChapters.size === 0}
                        onClick={handlePublish}
                    >
                        {publishing ? '发布中...' : `发布选中章节（${selectedChapters.size}）`}
                    </button>
                </div>

                {task ? (
                    <div className="task-panel">
                        <div className="summary-card-header">
                            <strong>任务 {task.task_id}</strong>
                            <Badge tone={task.status === 'success' ? 'green' : task.status === 'failed' ? 'red' : 'amber'}>
                                {formatStatus(task.status)}
                            </Badge>
                        </div>
                        {task.message ? <p>{task.message}</p> : null}
                        {task.total > 0 ? (
                            <div className="progress-track">
                                <div className="progress-fill" style={{ width: `${Math.round((task.progress / task.total) * 100)}%` }} />
                            </div>
                        ) : null}
                        {task.logs?.length ? (
                            <pre className="task-log">{task.logs.join('\n')}</pre>
                        ) : null}
                    </div>
                ) : null}
            </article>
        </section>
    )
}
