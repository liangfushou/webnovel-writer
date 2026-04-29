export function findFirstFilePath(tree) {
    for (const items of Object.values(tree || {})) {
        const path = walkFirstFile(items)
        if (path) return path
    }
    return null
}

function walkFirstFile(items) {
    if (!Array.isArray(items)) return null
    for (const item of items) {
        if (item?.type === 'file' && item?.path) return item.path
        if (item?.type === 'dir' && Array.isArray(item.children)) {
            const nested = walkFirstFile(item.children)
            if (nested) return nested
        }
    }
    return null
}

export function hasFilePath(tree, targetPath) {
    if (!targetPath) return false
    for (const items of Object.values(tree || {})) {
        if (walkHasFile(items, targetPath)) return true
    }
    return false
}

function walkHasFile(items, targetPath) {
    if (!Array.isArray(items)) return false
    for (const item of items) {
        if (item?.type === 'file' && item?.path === targetPath) return true
        if (item?.type === 'dir' && walkHasFile(item.children, targetPath)) return true
    }
    return false
}
