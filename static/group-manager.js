/**
 * Group Management Module
 * Handles group CRUD operations, tree rendering, and document filtering
 */

class GroupManager {
    constructor() {
        this.groups = [];
        this.tree = {};
        this.selectedGroupId = null;
        this.onGroupsChanged = null; // Callback for when groups change
    }

    /**
     * Load all groups from server
     */
    async loadGroups() {
        try {
            const response = await fetch('/api/groups');
            if (!response.ok) {
                throw new Error(`Failed to load groups: ${response.statusText}`);
            }

            const data = await response.json();
            this.groups = data.groups || [];
            this.tree = data.tree || {};

            console.log(`Loaded ${this.groups.length} groups`);

            if (this.onGroupsChanged) {
                this.onGroupsChanged(this.groups, this.tree);
            }

            return { groups: this.groups, tree: this.tree };
        } catch (error) {
            console.error('Error loading groups:', error);
            throw error;
        }
    }

    /**
     * Create a new group
     */
    async createGroup({ name, description = '', color = '#3B82F6', icon = '📁', parent_id = null }) {
        try {
            const response = await fetch('/api/groups', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, description, color, icon, parent_id })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to create group');
            }

            const data = await response.json();
            console.log(`Created group: ${data.group_id}`);

            // Reload groups to update tree
            await this.loadGroups();

            return data;
        } catch (error) {
            console.error('Error creating group:', error);
            throw error;
        }
    }

    /**
     * Update group metadata
     */
    async updateGroup(groupId, updates) {
        try {
            const response = await fetch(`/api/groups/${groupId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates)
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to update group');
            }

            const data = await response.json();
            console.log(`Updated group: ${groupId}`);

            // Reload groups to update tree
            await this.loadGroups();

            return data;
        } catch (error) {
            console.error('Error updating group:', error);
            throw error;
        }
    }

    /**
     * Delete a group
     */
    async deleteGroup(groupId, reassignTo = null) {
        try {
            const url = reassignTo
                ? `/api/groups/${groupId}?reassign_to=${reassignTo}`
                : `/api/groups/${groupId}`;

            const response = await fetch(url, {
                method: 'DELETE'
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to delete group');
            }

            const data = await response.json();
            console.log(`Deleted group: ${groupId}, reassigned ${data.reassigned_documents} documents`);

            // Reload groups to update tree
            await this.loadGroups();

            return data;
        } catch (error) {
            console.error('Error deleting group:', error);
            throw error;
        }
    }

    /**
     * Move a group to a new parent
     */
    async moveGroup(groupId, newParentId) {
        try {
            const response = await fetch(`/api/groups/${groupId}/move`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_parent_id: newParentId })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to move group');
            }

            const data = await response.json();
            console.log(`Moved group: ${groupId} to parent ${newParentId}`);

            // Reload groups to update tree
            await this.loadGroups();

            return data;
        } catch (error) {
            console.error('Error moving group:', error);
            throw error;
        }
    }

    /**
     * Assign a document to a group
     */
    async assignDocument(filename, groupId) {
        try {
            const response = await fetch(`/api/documents/${encodeURIComponent(filename)}/group`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ group_id: groupId })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to assign document');
            }

            const data = await response.json();
            console.log(`Assigned document '${filename}' to group ${groupId}`);

            return data;
        } catch (error) {
            console.error('Error assigning document:', error);
            throw error;
        }
    }

    /**
     * Batch assign documents to a group
     */
    async batchAssignDocuments(filenames, groupId) {
        try {
            const response = await fetch(`/api/groups/${groupId}/documents`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filenames })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to batch assign documents');
            }

            const data = await response.json();
            console.log(`Batch assigned ${data.assigned_count}/${data.total_requested} documents to group ${groupId}`);

            return data;
        } catch (error) {
            console.error('Error batch assigning documents:', error);
            throw error;
        }
    }

    /**
     * Get documents in a group
     */
    async getGroupDocuments(groupId) {
        try {
            const response = await fetch(`/api/groups/${groupId}/documents`);

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to get group documents');
            }

            const data = await response.json();
            return data.documents || [];
        } catch (error) {
            console.error('Error getting group documents:', error);
            throw error;
        }
    }

    /**
     * Remove a document from a group (reassign to default)
     */
    async removeDocumentFromGroup(filename, groupId) {
        try {
            const response = await fetch(`/api/groups/${groupId}/documents/${encodeURIComponent(filename)}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to remove document from group');
            }

            const data = await response.json();
            console.log(`Removed document '${filename}' from group ${groupId}`);

            // Reload groups to update counts
            await this.loadGroups();

            return data;
        } catch (error) {
            console.error('Error removing document from group:', error);
            throw error;
        }
    }

    /**
     * Find group by ID
     */
    findGroup(groupId) {
        return this.groups.find(g => g.id === groupId);
    }

    /**
     * Calculate total document count including all descendants
     */
    getTotalDocumentCount(nodeData) {
        const group = this.findGroup(nodeData.id);
        if (!group) return 0;

        // Start with this group's document count (convert string to number)
        let total = parseInt(group.document_count) || 0;

        // Add counts from all children recursively
        if (nodeData.children && nodeData.children.length > 0) {
            for (const child of nodeData.children) {
                total += this.getTotalDocumentCount(child);
            }
        }

        return total;
    }

    /**
     * Render group tree as HTML
     */
    renderTree(container, options = {}) {
        const {
            onSelect = null,
            onEdit = null,
            onDelete = null,
            selectedGroupId = null,
            showDocumentCount = true
        } = options;

        if (!container) return;

        const renderNode = (nodeData, level = 0) => {
            const group = this.findGroup(nodeData.id);
            if (!group) return '';

            const isSelected = selectedGroupId === nodeData.id;
            const hasChildren = nodeData.children && nodeData.children.length > 0;
            const indent = level * 20;

            // Calculate total document count including all descendants
            const totalCount = this.getTotalDocumentCount(nodeData);

            let html = `
                <div class="group-item ${isSelected ? 'selected' : ''}"
                     data-group-id="${group.id}"
                     style="padding-left: ${indent}px">
                    <div class="group-item-content">
                        ${hasChildren ? '<span class="group-toggle">▼</span>' : '<span class="group-toggle-space"></span>'}
                        <span class="group-icon" style="color: ${group.color}">${group.icon}</span>
                        <span class="group-name">${escapeHtml(group.name)}</span>
                        ${showDocumentCount ? `<span class="group-doc-count">(${totalCount})</span>` : ''}
                        <div class="group-actions">
                            ${onEdit ? '<button class="group-edit-btn" title="편집">✏️</button>' : ''}
                            ${onDelete ? '<button class="group-delete-btn" title="삭제">🗑️</button>' : ''}
                        </div>
                    </div>
                </div>
            `;

            // Render children
            if (hasChildren) {
                html += '<div class="group-children">';
                for (const child of nodeData.children) {
                    html += renderNode(child, level + 1);
                }
                html += '</div>';
            }

            return html;
        };

        // Render tree starting from root
        let treeHtml = '';
        if (this.tree.children) {
            for (const rootNode of this.tree.children) {
                treeHtml += renderNode(rootNode, 0);
            }
        }

        container.innerHTML = treeHtml || '<div class="empty-state">그룹이 없습니다</div>';

        // Attach event listeners
        container.querySelectorAll('.group-item-content').forEach(item => {
            const groupId = item.parentElement.dataset.groupId;

            // Click to select
            item.addEventListener('click', (e) => {
                if (e.target.classList.contains('group-edit-btn') ||
                    e.target.classList.contains('group-delete-btn')) {
                    return;
                }

                if (onSelect) {
                    onSelect(groupId);
                }
            });

            // Edit button
            const editBtn = item.querySelector('.group-edit-btn');
            if (editBtn && onEdit) {
                editBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    onEdit(groupId);
                });
            }

            // Delete button
            const deleteBtn = item.querySelector('.group-delete-btn');
            if (deleteBtn && onDelete) {
                deleteBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    onDelete(groupId);
                });
            }
        });

        // Collapse/expand toggle
        container.querySelectorAll('.group-toggle').forEach(toggle => {
            toggle.addEventListener('click', (e) => {
                e.stopPropagation();
                const groupItem = e.target.closest('.group-item');
                const children = groupItem.querySelector('.group-children');
                if (children) {
                    children.classList.toggle('collapsed');
                    e.target.textContent = children.classList.contains('collapsed') ? '▶' : '▼';
                }
            });
        });
    }
}


class GroupFilter {
    constructor(groupManager) {
        this.groupManager = groupManager;
        this.selectedGroupIds = [];
        this.onFilterChanged = null; // Callback when filter changes
    }

    /**
     * Render group filter UI
     */
    renderGroupSelector(container) {
        if (!container) return;

        const renderCheckboxTree = (nodeData, level = 0) => {
            const group = this.groupManager.findGroup(nodeData.id);
            if (!group) return '';

            const isChecked = this.selectedGroupIds.includes(nodeData.id);
            const hasChildren = nodeData.children && nodeData.children.length > 0;
            const indent = level * 20;

            // Calculate total document count including all descendants
            const totalCount = this.groupManager.getTotalDocumentCount(nodeData);

            let html = `
                <div class="filter-group-item" style="padding-left: ${indent}px">
                    <label class="filter-group-label">
                        <input type="checkbox"
                               class="filter-group-checkbox"
                               value="${group.id}"
                               ${isChecked ? 'checked' : ''}>
                        <span class="filter-group-icon" style="color: ${group.color}">${group.icon}</span>
                        <span class="filter-group-name">${escapeHtml(group.name)}</span>
                        <span class="filter-group-count">(${totalCount})</span>
                    </label>
                </div>
            `;

            // Render children
            if (hasChildren) {
                for (const child of nodeData.children) {
                    html += renderCheckboxTree(child, level + 1);
                }
            }

            return html;
        };

        // Render filter tree
        let filterHtml = '<div class="filter-group-header">그룹 선택</div>';

        if (this.groupManager.tree.children) {
            for (const rootNode of this.groupManager.tree.children) {
                filterHtml += renderCheckboxTree(rootNode, 0);
            }
        } else {
            filterHtml += '<div class="empty-state">그룹이 없습니다</div>';
        }

        container.innerHTML = filterHtml;

        // Attach checkbox event listeners
        container.querySelectorAll('.filter-group-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', (e) => {
                const groupId = e.target.value;

                if (e.target.checked) {
                    if (!this.selectedGroupIds.includes(groupId)) {
                        this.selectedGroupIds.push(groupId);
                    }
                } else {
                    this.selectedGroupIds = this.selectedGroupIds.filter(id => id !== groupId);
                }

                if (this.onFilterChanged) {
                    this.onFilterChanged(this.selectedGroupIds);
                }
            });
        });
    }

    /**
     * Get currently selected group IDs
     */
    getSelectedGroups() {
        return [...this.selectedGroupIds];
    }

    /**
     * Clear all selections
     */
    clearSelection() {
        this.selectedGroupIds = [];
        if (this.onFilterChanged) {
            this.onFilterChanged(this.selectedGroupIds);
        }
    }

    /**
     * Select specific groups
     */
    setSelectedGroups(groupIds) {
        this.selectedGroupIds = [...groupIds];
        if (this.onFilterChanged) {
            this.onFilterChanged(this.selectedGroupIds);
        }
    }
}


/**
 * Utility function to escape HTML
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}


/**
 * Initialize group management UI
 */
async function initializeGroupManagement() {
    const groupManager = new GroupManager();
    const groupFilter = new GroupFilter(groupManager);

    try {
        // Load groups on initialization
        await groupManager.loadGroups();
        console.log('Group management initialized');

        return { groupManager, groupFilter };
    } catch (error) {
        console.error('Failed to initialize group management:', error);
        throw error;
    }
}


// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { GroupManager, GroupFilter, initializeGroupManagement };
}
