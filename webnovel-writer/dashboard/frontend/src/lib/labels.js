const STATUS_LABELS = {
    accepted: '已通过',
    done: '已完成',
    ok: '正常',
    full: '完整',
    rejected: '已拒绝',
    failed: '失败',
    error: '错误',
    skipped: '已跳过',
    missing: '缺失',
    bm25_only: '仅关键词检索',
    pending: '等待中',
    running: '运行中',
    success: '成功',
    unknown: '未知',
}

const HOOK_STRENGTH_LABELS = {
    weak: '弱',
    medium: '中',
    strong: '强',
}

const URGENCY_LABELS = {
    critical: '严重',
    high: '高',
    medium: '中',
    normal: '普通',
    resolved: '已回收',
}

const STRAND_LABELS = {
    quest: '目标线',
    fire: '冲突线',
    constellation: '群像线',
    unknown: '未识别',
}

const CONTRACT_LABELS = {
    MASTER_SETTING: '主设定合同',
    VOLUME_BRIEF: '卷纲合同',
    CHAPTER_BRIEF: '章节合同',
    REVIEW_CONTRACT: '审查合同',
    COMMIT: '提交快照',
}

const COMPONENT_LABELS = {
    embed: '嵌入模型',
    rerank: '重排模型',
    vector_db: '向量库',
    rag_mode: '检索模式',
}

export function formatStatus(value) {
    const text = String(value || '').trim()
    if (!text) return '—'
    return STATUS_LABELS[text.toLowerCase()] || text
}

export function formatHookStrength(value) {
    const text = String(value || '').trim().toLowerCase()
    return HOOK_STRENGTH_LABELS[text] || (text ? value : '无钩子')
}

export function formatUrgency(value) {
    const text = String(value || '').trim().toLowerCase()
    return URGENCY_LABELS[text] || value || '普通'
}

export function formatStrand(value) {
    const text = String(value || '').trim().toLowerCase()
    return STRAND_LABELS[text] || value || '未识别'
}

export function formatContractType(value) {
    return CONTRACT_LABELS[value] || value || '未知合同'
}

export function formatComponentName(value) {
    return COMPONENT_LABELS[value] || value || '未知组件'
}

export function formatProjectionName(value) {
    const text = String(value || '')
    const labels = {
        state: '状态投影',
        index: '索引投影',
        summary: '摘要投影',
        memory: '记忆投影',
        vector: '向量投影',
    }
    return labels[text] || text
}
