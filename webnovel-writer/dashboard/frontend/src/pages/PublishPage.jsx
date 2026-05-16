import { useCallback, useEffect, useMemo, useState } from 'react'
import { useDashboardContext } from '../App.jsx'
import Badge from '../components/Badge.jsx'
import { fetchChapters, fetchJSON, postJSONBody } from '../api.js'
import { formatChapterLabel } from '../lib/format.js'
import { formatStatus } from '../lib/labels.js'

const SELECTED_BOOK_STORAGE_KEY = 'webnovel.publish.selectedBookId'
const CHAPTER_PAGE_SIZE_STORAGE_KEY = 'webnovel.publish.chapterPageSize'
const CHAPTER_PAGE_SIZE_OPTIONS = [30, 50, 100]

function chapterNumberFromRemoteTitle(item) {
    const directNumber = Number(item?.chapter || item?.chapter_number || item?.chapter_no || item?.chapter_index || 0)
    if (directNumber > 0) return directNumber

    const title = String(
        item?.title
        || item?.chapter_title
        || item?.item_title
        || item?.article_title
        || item?.item_name
        || item?.chapter_name
        || item?.name
        || '',
    )
    const match = title.match(/第\s*(\d+)\s*章/)
    return match ? Number(match[1]) : 0
}

function remoteChapterLabel(item) {
    const source = String(item?.source || '').toLowerCase()
    if (source === 'draft') return '已在草稿'
    if (source === 'published') return '已发布'

    const statusText = String(item?.status_desc || item?.article_status_desc || item?.verify_status_desc || '')
    if (statusText.includes('草稿')) return '已在草稿'
    if (statusText.includes('发布')) return '已发布'
    return '已在平台'
}

function remoteChapterTone(item) {
    return remoteChapterLabel(item) === '已在草稿' ? 'amber' : 'green'
}

function buildRangeSpec(chapters) {
    return [...chapters].sort((left, right) => left - right).join(',')
}

function formatUploadOrder(chapters, maxVisible = 30) {
    const ordered = [...chapters].sort((left, right) => left - right)
    if (!ordered.length) return ''
    const visible = ordered.slice(0, maxVisible).map(number => `第${number}章`).join('、')
    const hiddenCount = ordered.length - maxVisible
    return hiddenCount > 0 ? `${visible} 等 ${ordered.length} 章` : visible
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
    const lifecycle = BOOK_STATUS_LABELS[book?.status] || formatStatus(book?.status)
    const introTag = String(book?.book_intro?.tag || '').trim()
    const introStatus = String(book?.book_intro?.status || '').trim()
    const introLabel = introStatus === 'sign_audit' ? '审核中' : introTag
    if (introLabel && lifecycle && lifecycle !== '未知') return `${lifecycle} · ${introLabel}`
    return introLabel || lifecycle || '未知'
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

function getBookId(book) {
    return String(
        book?.book_id
        || book?.bookId
        || book?.id
        || book?.book_id_str
        || book?.bookID
        || '',
    ).trim()
}

function getBookName(book) {
    return book?.book_name || book?.bookName || book?.name || book?.title || '未命名'
}

function normalizeTitle(value) {
    return String(value || '').replace(/[^\p{Script=Han}a-zA-Z0-9]/gu, '').toLowerCase()
}

function titleBigrams(value) {
    const text = normalizeTitle(value)
    const bigrams = []
    for (let index = 0; index < text.length - 1; index += 1) {
        bigrams.push(text.slice(index, index + 2))
    }
    return bigrams
}

function scoreBookMatch(book, projectTitle) {
    const bookTitle = normalizeTitle(getBookName(book))
    const localTitle = normalizeTitle(projectTitle)
    if (!bookTitle || !localTitle) return 0
    if (bookTitle === localTitle) return 1000
    if (bookTitle.includes(localTitle) || localTitle.includes(bookTitle)) return 500
    return titleBigrams(localTitle).filter(part => bookTitle.includes(part)).length
}

function findBestBookId(books, projectTitle) {
    const scored = books
        .map(book => ({ bookId: getBookId(book), score: scoreBookMatch(book, projectTitle) }))
        .filter(item => item.bookId && item.score > 0)
        .sort((left, right) => right.score - left.score)
    if (!scored.length) return ''
    if (scored[0].score < 2) return ''
    if (scored[1]?.score === scored[0].score) return ''
    return scored[0].bookId
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
    const { projectInfo } = useDashboardContext()
    const [status, setStatus] = useState(null)
    const [statusError, setStatusError] = useState('')
    const [setupTask, setSetupTask] = useState(null)
    const [setupRunning, setSetupRunning] = useState(false)
    const [books, setBooks] = useState([])
    const [booksLoading, setBooksLoading] = useState(false)
    const [booksLoaded, setBooksLoaded] = useState(false)
    const [selectedBook, setSelectedBook] = useState(() => window.localStorage.getItem(SELECTED_BOOK_STORAGE_KEY) || '')
    const [remoteChapters, setRemoteChapters] = useState([])
    const [remoteLoading, setRemoteLoading] = useState(false)
    const [localChapters, setLocalChapters] = useState([])
    const [expandedVolumes, setExpandedVolumes] = useState({})
    const [selectedChapters, setSelectedChapters] = useState(new Set())
    const [chapterPage, setChapterPage] = useState(1)
    const [chapterPageSize, setChapterPageSize] = useState(() => {
        const stored = Number(window.localStorage.getItem(CHAPTER_PAGE_SIZE_STORAGE_KEY) || 30)
        return CHAPTER_PAGE_SIZE_OPTIONS.includes(stored) ? stored : 30
    })
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

    const showMessage = useCallback((text, tone = 'green') => {
        setMessage({ text, tone })
    }, [])

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

    const refreshRemoteChapters = useCallback((bookId = selectedBook, { clearSelection = true, notifyMissing = false } = {}) => {
        if (!bookId) {
            setRemoteChapters([])
            if (clearSelection) setSelectedChapters(new Set())
            if (notifyMissing) showMessage('请先在书籍管理里选择一本番茄书籍。', 'amber')
            return Promise.resolve([])
        }

        setRemoteLoading(true)
        setRemoteChapters([])
        if (clearSelection) setSelectedChapters(new Set())
        return fetchJSON(`/api/publish/books/${encodeURIComponent(bookId)}/remote-chapters`)
            .then(payload => {
                const chapters = Array.isArray(payload) ? payload : []
                setRemoteChapters(chapters)
                showMessage(`平台章节已刷新：${chapters.length} 条`)
                return chapters
            })
            .catch(error => {
                setRemoteChapters([])
                showMessage(`平台章节读取失败：${error.message}`, 'red')
                return []
            })
            .finally(() => setRemoteLoading(false))
    }, [selectedBook, showMessage])

    async function refreshBooks() {
        if (!status?.ready) {
            showMessage('发布环境还没就绪，请先按提示完成 Playwright 和番茄登录配置。', 'amber')
            return
        }
        setBooksLoading(true)
        try {
            setBooks(await fetchJSON('/api/publish/books'))
            setBooksLoaded(true)
            showMessage('书籍列表已刷新')
        } catch (error) {
            setBooksLoaded(true)
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
        if (status?.ready && !booksLoaded && !booksLoading) {
            refreshBooks()
        }
    }, [status?.ready, booksLoaded, booksLoading])

    useEffect(() => {
        if (!booksLoaded) return
        if (!books.length) {
            setSelectedBook('')
            return
        }
        const bookIds = books.map(getBookId).filter(Boolean)
        if (selectedBook && bookIds.includes(selectedBook)) return
        const storedBookId = window.localStorage.getItem(SELECTED_BOOK_STORAGE_KEY) || ''
        if (storedBookId && bookIds.includes(storedBookId)) {
            setSelectedBook(storedBookId)
            return
        }
        const projectTitle = projectInfo?.project_info?.title || projectInfo?.book_title || projectInfo?.title || ''
        setSelectedBook(findBestBookId(books, projectTitle) || (bookIds.length === 1 ? bookIds[0] : ''))
    }, [books, booksLoaded, selectedBook, projectInfo])

    useEffect(() => {
        if (selectedBook) {
            window.localStorage.setItem(SELECTED_BOOK_STORAGE_KEY, selectedBook)
        } else {
            window.localStorage.removeItem(SELECTED_BOOK_STORAGE_KEY)
        }
    }, [selectedBook])

    useEffect(() => {
        if (!booksLoaded) return
        refreshRemoteChapters(selectedBook)
    }, [booksLoaded, selectedBook, refreshRemoteChapters])

    useEffect(() => {
        if (!task || !['pending', 'running'].includes(task.status)) return undefined
        const timer = window.setInterval(() => {
            fetchJSON(`/api/publish/task/${task.task_id}`)
                .then(nextTask => {
                    setTask(nextTask)
                    if (['success', 'failed'].includes(nextTask.status)) {
                        setPublishing(false)
                        if (nextTask.status === 'success') {
                            refreshRemoteChapters(selectedBook, { clearSelection: false })
                        }
                    }
                })
                .catch(error => {
                    setPublishing(false)
                    showMessage(`任务状态读取失败：${error.message}`, 'red')
                })
        }, 1500)
        return () => window.clearInterval(timer)
    }, [task?.task_id, task?.status, selectedBook, refreshRemoteChapters])

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

    const remoteChapterMap = useMemo(() => {
        const map = new Map()
        for (const chapter of remoteChapters) {
            const number = chapterNumberFromRemoteTitle(chapter)
            if (!number) continue

            const current = map.get(number)
            if (!current || remoteChapterLabel(current) === '已在草稿') {
                map.set(number, chapter)
            }
        }
        return map
    }, [remoteChapters])

    const remoteChapterNumbers = useMemo(() => {
        return new Set(remoteChapterMap.keys())
    }, [remoteChapterMap])

    const selectedBookInfo = useMemo(() => {
        return books.find(book => getBookId(book) === selectedBook) || null
    }, [books, selectedBook])

    const selectedUploadOrderText = useMemo(() => {
        return formatUploadOrder(selectedChapters)
    }, [selectedChapters])

    const selectableChapters = useMemo(() => {
        return localChapters.filter(chapter => !remoteChapterNumbers.has(Number(chapter.chapter)))
    }, [localChapters, remoteChapterNumbers])

    const unpublishedChapters = useMemo(() => selectableChapters, [selectableChapters])

    const sortedLocalChapters = useMemo(() => {
        return [...localChapters].sort((left, right) => Number(left.chapter || 0) - Number(right.chapter || 0))
    }, [localChapters])

    const chapterPageCount = useMemo(() => {
        return Math.max(1, Math.ceil(sortedLocalChapters.length / chapterPageSize))
    }, [sortedLocalChapters.length, chapterPageSize])

    const safeChapterPage = Math.min(Math.max(chapterPage, 1), chapterPageCount)
    const chapterPageStart = sortedLocalChapters.length ? (safeChapterPage - 1) * chapterPageSize + 1 : 0
    const chapterPageEnd = Math.min(safeChapterPage * chapterPageSize, sortedLocalChapters.length)

    const pagedLocalChapters = useMemo(() => {
        const start = (safeChapterPage - 1) * chapterPageSize
        return sortedLocalChapters.slice(start, start + chapterPageSize)
    }, [sortedLocalChapters, safeChapterPage, chapterPageSize])

    const allChapterGroups = useMemo(() => buildChapterGroups(sortedLocalChapters), [sortedLocalChapters])
    const allChapterGroupMap = useMemo(() => {
        return new Map(allChapterGroups.map(group => [group.key, group]))
    }, [allChapterGroups])
    const chapterGroups = useMemo(() => buildChapterGroups(pagedLocalChapters), [pagedLocalChapters])

    useEffect(() => {
        setChapterPage(current => Math.min(Math.max(current, 1), chapterPageCount))
    }, [chapterPageCount])

    useEffect(() => {
        setChapterPage(1)
    }, [chapterPageSize, localChapters.length])

    useEffect(() => {
        window.localStorage.setItem(CHAPTER_PAGE_SIZE_STORAGE_KEY, String(chapterPageSize))
    }, [chapterPageSize])

    useEffect(() => {
        setSelectedChapters(current => {
            const next = new Set([...current].filter(chapter => !remoteChapterNumbers.has(Number(chapter))))
            return next.size === current.size ? current : next
        })
    }, [remoteChapterNumbers])

    function selectAll() {
        setSelectedChapters(new Set(selectableChapters.map(chapter => Number(chapter.chapter)).filter(Boolean)))
    }

    function selectUnpublished() {
        setSelectedChapters(new Set(unpublishedChapters.map(chapter => Number(chapter.chapter)).filter(Boolean)))
    }

    function selectVolume(group) {
        const targetGroup = allChapterGroupMap.get(group.key) || group
        setSelectedChapters(current => {
            const next = new Set(current)
            for (const chapter of targetGroup.chapters) {
                const number = Number(chapter.chapter)
                if (!number) continue
                if (remoteChapterNumbers.has(number)) continue
                next.add(number)
            }
            return next
        })
    }

    function clearVolume(group) {
        const targetGroup = allChapterGroupMap.get(group.key) || group
        setSelectedChapters(current => {
            const next = new Set(current)
            for (const chapter of targetGroup.chapters) {
                next.delete(Number(chapter.chapter))
            }
            return next
        })
    }

    function toggleVolume(groupKey) {
        setExpandedVolumes(current => ({ ...current, [groupKey]: !(current[groupKey] ?? true) }))
    }

    function toggleChapter(chapter) {
        if (remoteChapterNumbers.has(Number(chapter))) return

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

    function handleSelectBook(book) {
        const bookId = getBookId(book)
        const bookName = getBookName(book)
        if (!bookId) {
            showMessage('这条书籍数据没有可用 book_id，无法读取平台章节。', 'red')
            return
        }
        setSelectedBook(bookId)
        window.localStorage.setItem(SELECTED_BOOK_STORAGE_KEY, bookId)
        showMessage(`已切换并保存书籍：${bookName}`)
        if (bookId === selectedBook) {
            refreshRemoteChapters(bookId, { clearSelection: false })
        }
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
        const uploadOrderText = formatUploadOrder(selectedChapters, 20)
        const confirmed = window.confirm(`将按以下顺序上传到番茄作家后台：${uploadOrderText}。\n模式：${modeText}。\n确认继续？`)
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
                                    {books.map(book => {
                                        const bookId = getBookId(book)
                                        return (
                                            <tr
                                                key={bookId || getBookName(book)}
                                                className={selectedBook === bookId ? 'entity-row selected' : 'entity-row'}
                                                onClick={() => handleSelectBook(book)}
                                            >
                                                <td>{getBookName(book)}</td>
                                                <td><code>{bookId || 'N/A'}</code></td>
                                                <td>
                                                    <Badge tone={bookStatusTone(book)} title={bookStatusTitle(book)}>
                                                        {formatBookStatus(book)}
                                                    </Badge>
                                                </td>
                                            </tr>
                                        )
                                    })}
                                </tbody>
                            </table>
                        </div>
                    ) : (
                        <div className="empty-state compact">
                            <p>{booksLoading ? '正在读取书单…' : ready ? '刷新书单后选择番茄书籍。' : '完成发布环境配置后可读取书单。'}</p>
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
                    <button type="button" className="filter-btn" onClick={() => refreshRemoteChapters(selectedBook, { clearSelection: false, notifyMissing: true })} disabled={remoteLoading}>
                        {remoteLoading ? '读取平台中...' : '刷新平台章节'}
                    </button>
                    <button type="button" className="filter-btn" onClick={selectAll}>全选可发</button>
                    <button type="button" className="filter-btn" onClick={selectUnpublished}>仅未发布</button>
                    <button type="button" className="filter-btn" onClick={() => setSelectedChapters(new Set())}>清空</button>
                </div>

                <div className="chapter-pagination">
                    <div className="page-info">
                        显示第 {chapterPageStart}-{chapterPageEnd} 条 / 共 {sortedLocalChapters.length} 章
                    </div>
                    <div className="pager-actions">
                        <label className="form-field compact-field page-size-field">
                            <span>每页</span>
                            <select className="text-input" value={chapterPageSize} onChange={event => setChapterPageSize(Number(event.target.value))}>
                                {CHAPTER_PAGE_SIZE_OPTIONS.map(size => (
                                    <option key={size} value={size}>{size} 章</option>
                                ))}
                            </select>
                        </label>
                        <button type="button" className="filter-btn compact-filter" onClick={() => setChapterPage(page => Math.max(1, page - 1))} disabled={chapterPage <= 1}>
                            上一页
                        </button>
                        <span className="page-info">第 {safeChapterPage} / {chapterPageCount} 页</span>
                        <button type="button" className="filter-btn compact-filter" onClick={() => setChapterPage(page => Math.min(chapterPageCount, page + 1))} disabled={chapterPage >= chapterPageCount}>
                            下一页
                        </button>
                    </div>
                </div>

                <div className={`dashboard-hint ${selectedBookInfo ? '' : 'notice-amber'}`.trim()}>
                    <strong>当前绑定书籍：</strong>
                    {selectedBookInfo ? (
                        <>
                            {getBookName(selectedBookInfo)}
                            <span> · </span>
                            <code>{selectedBook}</code>
                            <span> · 状态 {formatBookStatus(selectedBookInfo)}</span>
                            <span> · 平台章节 {remoteChapters.length} 条</span>
                        </>
                    ) : (
                        '未绑定，请先在书籍管理中选择一本番茄书籍。'
                    )}
                </div>

                {localChapters.length ? (
                    <div className="chapter-volume-list">
                        {chapterGroups.map(group => {
                            const isOpen = expandedVolumes[group.key] ?? true
                            const fullGroup = allChapterGroupMap.get(group.key) || group
                            const selectedInGroup = fullGroup.chapters.filter(chapter => selectedChapters.has(Number(chapter.chapter))).length
                            const unpublishedInGroup = fullGroup.chapters.filter(chapter => !remoteChapterNumbers.has(Number(chapter.chapter))).length
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
                                            <button type="button" className="filter-btn compact-filter" onClick={() => selectVolume(group)}>选本卷可发</button>
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
                                                        const remoteChapter = remoteChapterMap.get(number)
                                                        const isPublished = Boolean(remoteChapter)
                                                        return (
                                                            <tr key={number}>
                                                                <td>
                                                                    <input
                                                                        type="checkbox"
                                                                        checked={selectedChapters.has(number)}
                                                                        disabled={isPublished}
                                                                        title={isPublished ? '平台已有该章节，避免重复上传' : ''}
                                                                        onChange={() => toggleChapter(number)}
                                                                    />
                                                                </td>
                                                                <td>{formatChapterLabel(number)}</td>
                                                                <td>{chapter.title || '—'}</td>
                                                                <td>{chapter.word_count ? `${chapter.word_count.toLocaleString('zh-CN')} 字` : '—'}</td>
                                                                <td>
                                                                    <Badge tone={isPublished ? remoteChapterTone(remoteChapter) : 'blue'}>
                                                                        {isPublished ? remoteChapterLabel(remoteChapter) : '可发布'}
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

                {selectedUploadOrderText ? (
                    <div className="dashboard-hint">
                        <strong>实际提交顺序：</strong>
                        <span>{selectedUploadOrderText}</span>
                        <span> · 已按章号升序提交，和勾选先后无关。</span>
                    </div>
                ) : null}

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
                        disabled={publishing || remoteLoading || !selectedBook || selectedChapters.size === 0}
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
