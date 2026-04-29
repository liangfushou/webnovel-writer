import { useEffect, useMemo, useState } from 'react'
import Badge from '../components/Badge.jsx'
import { fetchWorkflowStatus } from '../api.js'
import { useDashboardContext } from '../App.jsx'

function toneForDoc(doc) {
    if (doc?.exists && !doc?.error) return 'green'
    if (doc?.required) return 'red'
    return 'amber'
}

function statusText(doc) {
    if (doc?.error) return '读取失败'
    if (doc?.exists) return '已接入'
    if (doc?.required) return '缺失'
    return '可选缺失'
}

function WorkflowDocCard({ doc, active, onSelect }) {
    return (
        <button
            type="button"
            className={`workflow-doc-card ${active ? 'active' : ''}`.trim()}
            onClick={onSelect}
        >
            <div>
                <div className="workflow-doc-title">{doc.title}</div>
                <div className="workflow-doc-path">{doc.path}</div>
            </div>
            <Badge tone={toneForDoc(doc)}>{statusText(doc)}</Badge>
        </button>
    )
}

export default function WorkflowPage() {
    const { refreshToken } = useDashboardContext()
    const [workflow, setWorkflow] = useState(null)
    const [selectedPath, setSelectedPath] = useState('')
    const [error, setError] = useState('')

    useEffect(() => {
        let cancelled = false

        fetchWorkflowStatus()
            .then(payload => {
                if (cancelled) return
                setWorkflow(payload)
                setError('')
                const docs = [...(payload.docs || []), ...(payload.optional_docs || [])]
                setSelectedPath(current => current || docs.find(item => item.exists)?.path || docs[0]?.path || '')
            })
            .catch(exc => {
                if (cancelled) return
                setWorkflow(null)
                setError(exc.message || '写作流程读取失败')
            })

        return () => {
            cancelled = true
        }
    }, [refreshToken])

    const allDocs = useMemo(() => {
        if (!workflow) return []
        return [...(workflow.docs || []), ...(workflow.optional_docs || [])]
    }, [workflow])

    const selectedDoc = allDocs.find(item => item.path === selectedPath) || allDocs[0] || null
    const requiredReady = workflow?.docs?.filter(item => item.exists).length || 0
    const requiredTotal = workflow?.docs?.length || 0

    return (
        <section className="dashboard-page">
            <header className="page-header">
                <h2>写作流程</h2>
                {workflow ? (
                    <Badge tone={workflow.ok ? 'green' : 'red'}>
                        {workflow.ok ? '流程已接入' : '流程缺文件'}
                    </Badge>
                ) : null}
            </header>

            {error ? <div className="notice-card notice-red">{error}</div> : null}

            <div className="stat-grid">
                <article className="card stat-card">
                    <span className="stat-label">必备文件</span>
                    <span className="stat-value">{requiredReady}/{requiredTotal}</span>
                    <span className="stat-sub">写作流程、No 提示词、写后清单、技能物品账本、Codex skill</span>
                </article>
                <article className="card stat-card">
                    <span className="stat-label">Codex Skill</span>
                    <span className="stat-value plain">
                        {allDocs.find(item => item.path === '.codex/skills/no-webnovel-write/SKILL.md')?.exists ? '已安装' : '未安装'}
                    </span>
                    <span className="stat-sub">新会话可直接使用 No Webnovel Write 约束</span>
                </article>
                <article className="card stat-card">
                    <span className="stat-label">状态更新</span>
                    <span className="stat-value plain">
                        {allDocs.find(item => item.path === '.webnovel/post_chapter_update_checklist.md')?.exists ? '有清单' : '缺清单'}
                    </span>
                    <span className="stat-sub">正式提交前检查人物、技能、物品、时间线和伏笔</span>
                </article>
            </div>

            {workflow?.required_missing?.length ? (
                <article className="notice-card notice-red">
                    缺少必备文件：{workflow.required_missing.join('、')}
                </article>
            ) : null}

            <div className="content-grid two-columns workflow-grid">
                <article className="card">
                    <div className="card-header">
                        <div>
                            <div className="section-label">流程文件</div>
                            <div className="card-title">当前项目接入情况</div>
                        </div>
                        <Badge tone="blue">{allDocs.length} 项</Badge>
                    </div>
                    <div className="workflow-doc-list">
                        {allDocs.map(doc => (
                            <WorkflowDocCard
                                key={doc.path}
                                doc={doc}
                                active={selectedDoc?.path === doc.path}
                                onSelect={() => setSelectedPath(doc.path)}
                            />
                        ))}
                    </div>
                </article>

                <article className="card workflow-preview-card">
                    <div className="card-header">
                        <div>
                            <div className="section-label">预览</div>
                            <div className="card-title">{selectedDoc?.title || '未选择文件'}</div>
                        </div>
                        {selectedDoc ? <Badge tone={toneForDoc(selectedDoc)}>{statusText(selectedDoc)}</Badge> : null}
                    </div>
                    {selectedDoc?.exists ? (
                        <pre className="workflow-preview">{selectedDoc.content || '文件为空'}</pre>
                    ) : (
                        <div className="empty-state compact">
                            {selectedDoc ? `${selectedDoc.path} 尚未生成` : '暂无流程文件'}
                        </div>
                    )}
                </article>
            </div>
        </section>
    )
}
