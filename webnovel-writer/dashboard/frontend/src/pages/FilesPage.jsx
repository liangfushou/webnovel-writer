import { startTransition, useEffect, useMemo, useState } from 'react'
import { useDashboardContext } from '../App.jsx'
import Badge from '../components/Badge.jsx'
import { fetchFileContent, fetchFilesTree, writeClipboard } from '../api.js'
import { findFirstFilePath, hasFilePath } from '../lib/files.js'

function countTreeItems(items) {
    return (items || []).reduce(
        (count, item) => count + (item.type === 'file' ? 1 : countTreeItems(item.children)),
        0,
    )
}

function flattenFiles(items) {
    if (!Array.isArray(items)) return []

    return items.flatMap(item => {
        if (item?.type === 'file') return [item]
        if (item?.type === 'dir') return flattenFiles(item.children)
        return []
    })
}

function stripMarkdownFrame(text) {
    const lines = String(text || '').split(/\r?\n/)

    if (lines[0]?.trim() === '---') {
        const endIndex = lines.findIndex((line, index) => index > 0 && line.trim() === '---')
        if (endIndex > 0) lines.splice(0, endIndex + 1)
    }

    while (lines.length && !lines[0].trim()) lines.shift()
    if (/^#{1,6}\s+/.test(lines[0]?.trim() || '')) {
        lines.shift()
    }
    while (lines.length && !lines[0].trim()) lines.shift()

    return lines.join('\n').trim()
}

function getSelectedPreviewText() {
    const selection = window.getSelection?.()
    const selectedText = selection?.toString() || ''
    return selectedText.trim() ? selectedText : ''
}

async function copyTextToClipboard(text) {
    if (navigator.clipboard?.writeText && window.isSecureContext) {
        try {
            await navigator.clipboard.writeText(text)
            return
        } catch {
            // 内嵌浏览器有时暴露 Clipboard API 但拒绝写入，继续走 textarea 兜底。
        }
    }

    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.setAttribute('readonly', '')
    textarea.style.position = 'fixed'
    textarea.style.left = '-9999px'
    textarea.style.top = '0'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.focus()
    textarea.select()
    textarea.setSelectionRange(0, textarea.value.length)
    const copied = document.execCommand('copy')
    document.body.removeChild(textarea)
    if (!copied) {
        await writeClipboard(text)
    }
}

function TreeNodes({ items, expanded, selectedPath, onToggle, onSelect, depth = 0 }) {
    if (!Array.isArray(items) || !items.length) return null

    return items.map(item => {
        const key = item.path || `${depth}-${item.name}`
        if (item.type === 'dir') {
            const isOpen = expanded[key] ?? depth < 1
            return (
                <li key={key}>
                    <button
                        type="button"
                        className={`tree-item tree-dir ${isOpen ? 'open' : ''}`.trim()}
                        aria-expanded={isOpen}
                        onClick={() => onToggle(key, isOpen)}
                    >
                        <span className="folder-caret">{isOpen ? '-' : '+'}</span>
                        <span className="tree-glyph" />
                        <span className="tree-name">{item.name}</span>
                    </button>
                    {isOpen ? (
                        <ul className="tree-children">
                            <TreeNodes
                                items={item.children}
                                expanded={expanded}
                                selectedPath={selectedPath}
                                onToggle={onToggle}
                                onSelect={onSelect}
                                depth={depth + 1}
                            />
                        </ul>
                    ) : null}
                </li>
            )
        }

        return (
            <li key={key}>
                <button
                    type="button"
                    className={`tree-item tree-file ${selectedPath === item.path ? 'active' : ''}`.trim()}
                    onClick={() => onSelect(item.path)}
                >
                    <span className="tree-glyph file" />
                    <span className="tree-name">{item.name}</span>
                </button>
            </li>
        )
    })
}

export default function FilesPage() {
    const { refreshToken } = useDashboardContext()
    const [tree, setTree] = useState({})
    const [expanded, setExpanded] = useState({})
    const [selectedPath, setSelectedPath] = useState(null)
    const [content, setContent] = useState('')
    const [loadingContent, setLoadingContent] = useState(false)
    const [copyState, setCopyState] = useState('idle')
    const [copyMode, setCopyMode] = useState('full')

    useEffect(() => {
        let cancelled = false
        fetchFilesTree()
            .then(payload => {
                if (!cancelled) {
                    setTree(payload)
                    const initialPath = findFirstFilePath(payload)
                    setSelectedPath(current => {
                        if (current && hasFilePath(payload, current)) return current
                        return initialPath
                    })
                }
            })
            .catch(() => {
                if (!cancelled) {
                    setTree({})
                    setSelectedPath(null)
                }
            })

        return () => {
            cancelled = true
        }
    }, [refreshToken])

    useEffect(() => {
        if (!selectedPath) return undefined

        let cancelled = false
        setCopyState('idle')
        setLoadingContent(true)
        fetchFileContent(selectedPath)
            .then(payload => {
                if (!cancelled) {
                    setContent(payload.content || '')
                }
            })
            .catch(() => {
                if (!cancelled) {
                    setContent('[读取失败]')
                }
            })
            .finally(() => {
                if (!cancelled) {
                    setLoadingContent(false)
                }
            })

        return () => {
            cancelled = true
        }
    }, [selectedPath])

    useEffect(() => {
        if (copyState === 'idle') return undefined

        const timer = window.setTimeout(() => {
            setCopyState('idle')
        }, 1800)

        return () => window.clearTimeout(timer)
    }, [copyState])

    const totalFiles = useMemo(() => {
        return Object.values(tree).reduce((count, items) => count + countTreeItems(items), 0)
    }, [tree])
    const outlineMarkdownFiles = useMemo(() => {
        return flattenFiles(tree['大纲'])
            .filter(item => item?.path?.toLowerCase().endsWith('.md'))
            .sort((a, b) => a.name.localeCompare(b.name, 'zh-Hans-CN', { numeric: true }))
    }, [tree])
    const lineCount = content ? content.split(/\r?\n/).length : 0
    const canCopy = Boolean(selectedPath && !loadingContent && content)

    function toggleExpanded(key, isOpen) {
        startTransition(() => {
            setExpanded(current => ({ ...current, [key]: !isOpen }))
        })
    }

    async function handleCopyContent() {
        if (!canCopy) return

        try {
            const copyText = copyMode === 'selection'
                ? getSelectedPreviewText()
                : copyMode === 'body'
                    ? stripMarkdownFrame(content)
                    : content
            if (!copyText.trim()) throw new Error('empty copy content')
            await copyTextToClipboard(copyText)
            setCopyState('copied')
        } catch {
            setCopyState('failed')
        }
    }

    return (
        <section className="dashboard-page files-page">
            <header className="page-header">
                <h2>文档浏览</h2>
                <Badge tone="blue">{totalFiles} 个文件</Badge>
            </header>

            <div className="content-grid files-layout">
                <article className="card files-tree-card">
                    <div className="card-header">
                        <div>
                            <div className="section-label">目录树</div>
                            <div className="card-title">目录树</div>
                        </div>
                        <Badge tone="cyan">正文 / 大纲 / 设定集</Badge>
                    </div>

                    <div className="folder-group-list">
                        {outlineMarkdownFiles.length ? (() => {
                            const sectionKey = '__outline_shortcuts'
                            const isOpen = expanded[sectionKey] ?? true
                            return (
                            <section className="folder-block outline-shortcuts">
                                <button
                                    type="button"
                                    className="folder-title folder-title-btn"
                                    aria-expanded={isOpen}
                                    onClick={() => toggleExpanded(sectionKey, isOpen)}
                                >
                                    <span className="folder-title-main">
                                        <span className="folder-caret">{isOpen ? '-' : '+'}</span>
                                        <span>大纲 MD 直达</span>
                                    </span>
                                    <Badge tone="amber">{outlineMarkdownFiles.length}</Badge>
                                </button>
                                {isOpen ? (
                                    <div className="outline-shortcut-list">
                                        {outlineMarkdownFiles.map(item => (
                                            <button
                                                key={item.path}
                                                type="button"
                                                title={item.path}
                                                className={`outline-shortcut ${selectedPath === item.path ? 'active' : ''}`.trim()}
                                                onClick={() => setSelectedPath(item.path)}
                                            >
                                                {item.name}
                                            </button>
                                        ))}
                                    </div>
                                ) : null}
                            </section>
                            )
                        })() : null}

                        {Object.entries(tree).map(([folder, items]) => {
                            const sectionKey = `__folder_${folder}`
                            const isOpen = expanded[sectionKey] ?? true
                            return (
                                <section key={folder} className="folder-block">
                                    <button
                                        type="button"
                                        className="folder-title folder-title-btn"
                                        aria-expanded={isOpen}
                                        onClick={() => toggleExpanded(sectionKey, isOpen)}
                                    >
                                        <span className="folder-title-main">
                                            <span className="folder-caret">{isOpen ? '-' : '+'}</span>
                                            <span>{folder}</span>
                                        </span>
                                        <Badge tone="purple">{countTreeItems(items)}</Badge>
                                    </button>
                                    {isOpen ? (
                                        <ul className="file-tree">
                                            <TreeNodes
                                                items={items}
                                                expanded={expanded}
                                                selectedPath={selectedPath}
                                                onToggle={toggleExpanded}
                                                onSelect={setSelectedPath}
                                            />
                                        </ul>
                                    ) : null}
                                </section>
                            )
                        })}
                    </div>
                </article>

                <article className="card files-preview-card">
                    <div className="card-header">
                        <div>
                            <div className="section-label">内容预览</div>
                            <div className="card-title">内容预览</div>
                        </div>
                        {selectedPath ? (
                            <div className="header-actions">
                                <div className="header-badges">
                                    <Badge tone="amber">{lineCount} 行</Badge>
                                    <Badge tone="green">{content.length} 字符</Badge>
                                </div>
                                <label className="copy-mode-field">
                                    <span>复制范围</span>
                                    <select className="text-input" value={copyMode} onChange={event => setCopyMode(event.target.value)}>
                                        <option value="full">全文</option>
                                        <option value="selection">选中文本</option>
                                        <option value="body">纯正文</option>
                                    </select>
                                </label>
                                <button
                                    type="button"
                                    className={`copy-btn ${copyState}`.trim()}
                                    disabled={!canCopy}
                                    onClick={handleCopyContent}
                                >
                                    {copyState === 'copied' ? '已复制' : copyState === 'failed' ? '复制失败' : '复制内容'}
                                </button>
                            </div>
                        ) : null}
                    </div>

                    {selectedPath ? (
                        <div className="files-preview-body">
                            <div className="selected-path">{selectedPath}</div>
                            <pre className={`file-preview ${loadingContent ? 'loading' : ''}`.trim()}>
                                {loadingContent ? '读取中…' : content}
                            </pre>
                        </div>
                    ) : (
                        <div className="empty-state files-preview-empty">
                            <p>选择左侧文件以预览内容</p>
                        </div>
                    )}
                </article>
            </div>
        </section>
    )
}
