/**
 * Organization Management for Admin Panel
 *
 * Handles organization CRUD operations, member management, and organization admin management
 */

// Global state
let currentOrgId = null;
let allOrganizations = [];
let allUsers = [];

/**
 * Initialize organization management when tab is switched
 */
function initOrganizations() {
    loadOrganizations();
    loadAllUsers();
}

/**
 * Load all organizations
 */
async function loadOrganizations() {
    try {
        const data = await Auth.apiCall('/api/organizations');
        allOrganizations = data.organizations || [];
        renderOrganizationList();
    } catch (error) {
        logger.error('조직 목록 로드 실패:', error);
        showOrgError('조직 목록을 불러오는데 실패했습니다');
    }
}

/**
 * Load all users for member selection
 */
async function loadAllUsers() {
    try {
        const data = await Auth.apiCall('/api/auth/admin/users');
        allUsers = data.users || [];
    } catch (error) {
        logger.error('사용자 목록 로드 실패:', error);
        allUsers = [];
    }
}

/**
 * Render organization list
 */
function renderOrganizationList() {
    const container = document.getElementById('orgListContainer');

    if (!allOrganizations || allOrganizations.length === 0) {
        container.innerHTML = `
            <div style="text-align: center; padding: 40px; color: #666;">
                <p>생성된 조직이 없습니다</p>
                <p style="font-size: 14px; margin-top: 10px;">➕ 새 조직 버튼을 클릭하여 조직을 생성하세요</p>
            </div>
        `;
        return;
    }

    const html = `
        <div style="display: grid; gap: 12px; margin-top: 15px;">
            ${allOrganizations.map(org => `
                <div class="org-item ${currentOrgId === org.id ? 'active' : ''}"
                     onclick="selectOrganization('${org.id}')"
                     style="padding: 15px; border: 2px solid ${currentOrgId === org.id ? '#667eea' : '#e5e7eb'};
                            border-radius: 8px; cursor: pointer; transition: all 0.2s;
                            background: ${currentOrgId === org.id ? '#f0f4ff' : 'white'};">
                    <div style="display: flex; justify-content: space-between; align-items: start;">
                        <div style="flex: 1;">
                            <div style="font-weight: 600; font-size: 16px; margin-bottom: 5px;">
                                ${org.name}
                            </div>
                            <div style="font-size: 13px; color: #666; margin-bottom: 8px;">
                                ${org.description || '설명 없음'}
                            </div>
                            <div style="font-size: 12px; color: #666;">
                                <span>👥 ${org.member_count || 0}명</span>
                                <span style="margin-left: 10px;">📅 ${new Date(org.created_at).toLocaleDateString()}</span>
                            </div>
                        </div>
                        <div>
                            <span class="status-badge ${org.is_active === 'true' ? 'status-active' : 'status-inactive'}">
                                ${org.is_active === 'true' ? '활성' : '비활성'}
                            </span>
                        </div>
                    </div>
                </div>
            `).join('')}
        </div>
    `;

    container.innerHTML = html;
}

/**
 * Select organization and load details
 */
async function selectOrganization(orgId) {
    currentOrgId = orgId;
    renderOrganizationList();
    await loadOrganizationDetails(orgId);
}

/**
 * Load organization details
 */
async function loadOrganizationDetails(orgId) {
    try {
        const data = await Auth.apiCall(`/api/organizations/${orgId}`);
        const org = data.organization;

        // Show details panel
        document.getElementById('orgDetailsPanel').style.display = 'block';

        // Populate organization info
        document.getElementById('currentOrgName').textContent = org.name;
        document.getElementById('orgDetailName').value = org.name;
        document.getElementById('orgDetailDesc').value = org.description || '';
        document.getElementById('orgDetailActive').checked = org.is_active === 'true';

        // Update stats
        const stats = org.stats || {};
        document.getElementById('orgMemberCount').textContent = stats.member_count || 0;
        document.getElementById('orgAdminCount').textContent = stats.admin_count || 0;
        document.getElementById('orgGroupCount').textContent = stats.group_count || 0;

        // Hide delete button for default organization
        const deleteBtn = document.getElementById('deleteOrgBtn');
        if (deleteBtn) {
            if (orgId === 'default') {
                deleteBtn.style.display = 'none';
            } else {
                deleteBtn.style.display = 'inline-flex';
            }
        }

        // Load members
        await loadOrgMembers(orgId);

        // Load groups
        await loadOrgGroups(orgId);

    } catch (error) {
        logger.error('조직 상세 정보 로드 실패:', error);
        showOrgError('조직 정보를 불러오는데 실패했습니다');
    }
}

/**
 * Load organization members
 */
async function loadOrgMembers(orgId) {
    try {
        const data = await Auth.apiCall(`/api/organizations/${orgId}/members`);
        const members = data.members || [];

        renderMembersList(members);
        renderOrgAdminsList(members);

    } catch (error) {
        logger.error('멤버 목록 로드 실패:', error);
    }
}

/**
 * Render members list
 */
function renderMembersList(members) {
    const container = document.getElementById('orgMembersList');

    if (!members || members.length === 0) {
        container.innerHTML = '<div style="color: #666; font-size: 13px;">멤버가 없습니다</div>';
        return;
    }

    const html = members.map(member => `
        <div style="display: flex; justify-content: space-between; align-items: center;
                    padding: 12px; background: white; border-radius: 6px; margin-bottom: 8px;
                    border: 1px solid #e5e7eb;">
            <div>
                <div style="font-weight: 500; margin-bottom: 3px;">
                    ${member.username}
                    ${member.is_org_admin ? '<span class="badge-org-admin">조직 관리자</span>' : ''}
                </div>
                <div style="font-size: 12px; color: #666;">${member.email}</div>
            </div>
            <div style="display: flex; gap: 8px;">
                ${!member.is_org_admin ? `
                    <button onclick="promoteToOrgAdmin('${currentOrgId}', '${member.user_id}')"
                            class="btn-small btn-primary"
                            title="조직 관리자로 승격">
                        ⬆️ 승격
                    </button>
                ` : `
                    <button onclick="demoteFromOrgAdmin('${currentOrgId}', '${member.user_id}')"
                            class="btn-small btn-secondary"
                            title="조직 관리자에서 해제">
                        ⬇️ 해제
                    </button>
                `}
                <button onclick="removeMember('${currentOrgId}', '${member.user_id}')"
                        class="btn-small btn-danger"
                        title="조직에서 제거">
                    ❌ 제거
                </button>
            </div>
        </div>
    `).join('');

    container.innerHTML = html;
}

/**
 * Render organization admins list
 */
function renderOrgAdminsList(members) {
    const container = document.getElementById('orgAdminsList');
    const admins = members.filter(m => m.is_org_admin);

    if (!admins || admins.length === 0) {
        container.innerHTML = '<div style="color: #666; font-size: 13px;">조직 관리자는 멤버 목록에서 승격할 수 있습니다</div>';
        return;
    }

    const html = admins.map(admin => `
        <div style="display: flex; justify-content: space-between; align-items: center;
                    padding: 10px; background: white; border-radius: 6px; margin-bottom: 6px;
                    border: 1px solid #fbbf24;">
            <div>
                <div style="font-weight: 500;">👑 ${admin.username}</div>
                <div style="font-size: 11px; color: #666;">${admin.email}</div>
            </div>
        </div>
    `).join('');

    container.innerHTML = html;
}

/**
 * Show create organization modal
 */
function showCreateOrgModal() {
    document.getElementById('orgModalTitle').textContent = '새 조직 생성';
    document.getElementById('orgNameInput').value = '';
    document.getElementById('orgDescInput').value = '';
    document.getElementById('orgModalError').style.display = 'none';
    document.getElementById('createOrgModal').style.display = 'flex';
}

/**
 * Close organization modal
 */
function closeOrgModal() {
    document.getElementById('createOrgModal').style.display = 'none';
}

/**
 * Save organization (create new)
 */
async function saveOrganization() {
    const name = document.getElementById('orgNameInput').value.trim();
    const description = document.getElementById('orgDescInput').value.trim();

    if (!name) {
        showOrgModalError('조직 이름을 입력하세요');
        return;
    }

    try {
        const data = await Auth.apiCall('/api/organizations', {
            method: 'POST',
            body: JSON.stringify({ name, description })
        });

        if (data.success) {
            closeOrgModal();
            await loadOrganizations();
            showOrgSuccess('조직이 생성되었습니다');
        }
    } catch (error) {
        logger.error('조직 생성 실패:', error);
        showOrgModalError(error.message || '조직 생성에 실패했습니다');
    }
}

/**
 * Save organization changes
 */
async function saveOrgChanges() {
    if (!currentOrgId) return;

    const name = document.getElementById('orgDetailName').value.trim();
    const description = document.getElementById('orgDetailDesc').value.trim();
    const is_active = document.getElementById('orgDetailActive').checked;

    if (!name) {
        showOrgError('조직 이름을 입력하세요');
        return;
    }

    try {
        const data = await Auth.apiCall(`/api/organizations/${currentOrgId}`, {
            method: 'PUT',
            body: JSON.stringify({ name, description, is_active })
        });

        if (data.success) {
            await loadOrganizations();
            await loadOrganizationDetails(currentOrgId);
            showOrgSuccess('조직 정보가 업데이트되었습니다');
        }
    } catch (error) {
        logger.error('조직 업데이트 실패:', error);
        showOrgError(error.message || '조직 정보 업데이트에 실패했습니다');
    }
}

/**
 * Delete organization
 */
async function deleteOrganization() {
    if (!currentOrgId) return;

    // Prevent deletion of default organization
    if (currentOrgId === 'default') {
        showOrgError('기본 조직은 삭제할 수 없습니다. 기본 조직은 시스템에 필수적입니다.');
        return;
    }

    const org = allOrganizations.find(o => o.id === currentOrgId);
    if (!org) return;

    if (!confirm(`정말로 "${org.name}" 조직을 삭제하시겠습니까?\n\n⚠️ 주의: 이 작업은 되돌릴 수 없습니다.`)) {
        return;
    }

    try {
        const data = await Auth.apiCall(`/api/organizations/${currentOrgId}`, {
            method: 'DELETE'
        });

        if (data.success) {
            currentOrgId = null;
            document.getElementById('orgDetailsPanel').style.display = 'none';
            await loadOrganizations();
            showOrgSuccess('조직이 삭제되었습니다');
        }
    } catch (error) {
        logger.error('조직 삭제 실패:', error);
        showOrgError(error.message || '조직 삭제에 실패했습니다');
    }
}

/**
 * Show add member modal
 */
async function showAddMemberModal() {
    if (!currentOrgId) return;

    try {
        // Get current members
        const membersData = await Auth.apiCall(`/api/organizations/${currentOrgId}/members`);
        const currentMemberIds = (membersData.members || []).map(m => m.user_id);

        // Filter available users (not already members)
        const availableUsers = allUsers.filter(user => !currentMemberIds.includes(user.user_id));

        // Populate select
        const select = document.getElementById('memberUserIdSelect');
        select.innerHTML = '<option value="">사용자를 선택하세요</option>';

        if (availableUsers.length === 0) {
            select.innerHTML = '<option value="">추가 가능한 사용자가 없습니다</option>';
            select.disabled = true;
        } else {
            select.disabled = false;
            availableUsers.forEach(user => {
                const option = document.createElement('option');
                option.value = user.user_id;
                option.textContent = `${user.username} (${user.email})`;
                select.appendChild(option);
            });
        }

        document.getElementById('addMemberError').style.display = 'none';
        document.getElementById('addMemberModal').style.display = 'flex';

    } catch (error) {
        logger.error('멤버 추가 모달 로드 실패:', error);
        showOrgError('사용자 목록을 불러오는데 실패했습니다');
    }
}

/**
 * Close add member modal
 */
function closeAddMemberModal() {
    document.getElementById('addMemberModal').style.display = 'none';
}

/**
 * Add member to organization
 */
async function addMemberToOrg() {
    if (!currentOrgId) return;

    const userId = document.getElementById('memberUserIdSelect').value;

    if (!userId) {
        showAddMemberError('사용자를 선택하세요');
        return;
    }

    try {
        const data = await Auth.apiCall(`/api/organizations/${currentOrgId}/members`, {
            method: 'POST',
            body: JSON.stringify({ user_id: userId })
        });

        if (data.success) {
            closeAddMemberModal();
            await loadOrgMembers(currentOrgId);
            await loadOrganizationDetails(currentOrgId);
            // Display the message from API (handles both add and transfer cases)
            showOrgSuccess(data.message || '멤버가 추가되었습니다');
        }
    } catch (error) {
        logger.error('멤버 추가 실패:', error);
        showAddMemberError(error.message || '멤버 추가에 실패했습니다');
    }
}

/**
 * Remove member from organization
 */
async function removeMember(orgId, userId) {
    const user = allUsers.find(u => u.user_id === userId);
    const username = user ? user.username : userId;
    const currentUser = Auth.getUser();
    const isSelf = currentUser && currentUser.user_id === userId;

    // 자기 자신을 제거하는 경우
    if (isSelf) {
        if (!confirm(`정말로 이 조직을 나가시겠습니까?\n\n기본 조직으로 이동됩니다.`)) {
            return;
        }
    } else {
        if (!confirm(`정말로 "${username}" 사용자를 조직에서 제거하시겠습니까?\n\n해당 사용자는 기본 조직으로 이동됩니다.`)) {
            return;
        }
    }

    try {
        const data = await Auth.apiCall(`/api/organizations/${orgId}/members/${userId}`, {
            method: 'DELETE'
        });

        if (data.success) {
            // Display message from API
            showOrgSuccess(data.message || '멤버가 제거되었습니다');

            // If removing self, reload page to update UI
            if (isSelf) {
                setTimeout(() => {
                    window.location.reload();
                }, 1500);
            } else {
                await loadOrgMembers(orgId);
                await loadOrganizationDetails(orgId);
            }
        }
    } catch (error) {
        logger.error('멤버 제거 실패:', error);
        showOrgError(error.message || '멤버 제거에 실패했습니다');
    }
}

/**
 * Promote user to organization admin
 */
async function promoteToOrgAdmin(orgId, userId) {
    const user = allUsers.find(u => u.user_id === userId);
    const username = user ? user.username : userId;

    if (!confirm(`"${username}" 사용자를 조직 관리자로 승격하시겠습니까?`)) {
        return;
    }

    try {
        const data = await Auth.apiCall(`/api/organizations/${orgId}/admins/${userId}`, {
            method: 'POST'
        });

        if (data.success) {
            await loadOrgMembers(orgId);
            showOrgSuccess('조직 관리자로 승격되었습니다');
        }
    } catch (error) {
        logger.error('조직 관리자 승격 실패:', error);
        showOrgError(error.message || '조직 관리자 승격에 실패했습니다');
    }
}

/**
 * Demote user from organization admin
 */
async function demoteFromOrgAdmin(orgId, userId) {
    const user = allUsers.find(u => u.user_id === userId);
    const username = user ? user.username : userId;

    if (!confirm(`"${username}" 사용자를 조직 관리자에서 해제하시겠습니까?`)) {
        return;
    }

    try {
        const data = await Auth.apiCall(`/api/organizations/${orgId}/admins/${userId}`, {
            method: 'DELETE'
        });

        if (data.success) {
            await loadOrgMembers(orgId);
            showOrgSuccess('조직 관리자에서 해제되었습니다');
        }
    } catch (error) {
        logger.error('조직 관리자 해제 실패:', error);
        showOrgError(error.message || '조직 관리자 해제에 실패했습니다');
    }
}

/**
 * Show error message in modal
 */
function showOrgModalError(message) {
    const errorEl = document.getElementById('orgModalError');
    errorEl.textContent = message;
    errorEl.style.display = 'block';
}

/**
 * Show error message in add member modal
 */
function showAddMemberError(message) {
    const errorEl = document.getElementById('addMemberError');
    errorEl.textContent = message;
    errorEl.style.display = 'block';
}

/**
 * Show success message (using existing notification system)
 */
function showOrgSuccess(message) {
    // Try to use existing notification system if available
    if (typeof showNotification === 'function') {
        showNotification(message, 'success');
    } else {
        alert(message);
    }
}

/**
 * Show error message (using existing notification system)
 */
function showOrgError(message) {
    // Try to use existing notification system if available
    if (typeof showNotification === 'function') {
        showNotification(message, 'error');
    } else {
        alert(message);
    }
}

// ============================================================================
// Group Management Functions
// ============================================================================

/**
 * Load groups for current organization
 */
async function loadOrgGroups(orgId) {
    try {
        const data = await Auth.apiCall(`/api/organizations/${orgId}/groups`);
        const groups = data.groups || [];
        const rootGroupIds = data.root_group_ids || []; // 최상위 그룹 ID 목록

        const container = document.getElementById('orgGroupsList');

        if (groups.length === 0) {
            container.innerHTML = '<div style="text-align: center; padding: 20px; color: #666;">그룹이 없습니다</div>';
            return;
        }

        // Build hierarchical tree structure
        const groupMap = {};
        const rootGroups = [];
        const rootGroupIdSet = new Set(rootGroupIds); // O(1) lookup을 위한 Set

        // Create map of all groups
        groups.forEach(group => {
            groupMap[group.id] = { ...group, children: [] };
        });

        // Build parent-child relationships
        // Only groups explicitly assigned as root (in rootGroupIds) are treated as root
        groups.forEach(group => {
            if (rootGroupIdSet.has(group.id)) {
                // 이 그룹은 조직에 최상위로 명시적으로 할당됨
                rootGroups.push(groupMap[group.id]);
            } else if (group.parent_id && groupMap[group.parent_id]) {
                // 부모가 있고 같은 조직에 속하면 자식으로 추가
                groupMap[group.parent_id].children.push(groupMap[group.id]);
            } else {
                // 부모가 없거나 부모가 이 조직에 없으면 최상위로 표시
                rootGroups.push(groupMap[group.id]);
            }
        });

        // Render hierarchical tree
        function renderGroupTree(group, level = 0) {
            const indent = level * 24; // 24px per level
            const html = `
                <div style="padding: 12px; padding-left: ${12 + indent}px; border-bottom: 1px solid #e5e7eb; display: flex; justify-content: space-between; align-items: center;">
                    <div style="flex: 1;">
                        <div style="font-weight: 600; margin-bottom: 4px;">
                            ${level > 0 ? '<span style="color: #9ca3af;">└─</span> ' : ''}${group.icon || '📁'} ${group.name}
                            ${group.org_count > 1 ? `<span style="font-size: 11px; color: #0ea5e9; margin-left: 8px;">🔗 ${group.org_count}개 조직 공유</span>` : ''}
                        </div>
                        <div style="font-size: 13px; color: #666;">
                            문서: ${group.document_count || 0}개
                            ${group.description ? ` • ${group.description}` : ''}
                        </div>
                    </div>
                    <button onclick="removeGroupFromOrg('${group.id}')" class="btn-small btn-danger" style="margin-left: 10px;">
                        ❌ 제거
                    </button>
                </div>
            `;

            let childrenHtml = '';
            if (group.children && group.children.length > 0) {
                // Sort children by name
                group.children.sort((a, b) => a.name.localeCompare(b.name));
                childrenHtml = group.children.map(child => renderGroupTree(child, level + 1)).join('');
            }

            return html + childrenHtml;
        }

        // Sort root groups by name
        rootGroups.sort((a, b) => a.name.localeCompare(b.name));

        // Render all root groups and their children
        container.innerHTML = rootGroups.map(group => renderGroupTree(group)).join('');

    } catch (error) {
        logger.error('그룹 목록 로드 실패:', error);
        document.getElementById('orgGroupsList').innerHTML =
            '<div style="text-align: center; padding: 20px; color: #dc2626;">그룹 목록을 불러올 수 없습니다</div>';
    }
}

/**
 * Show assign group modal
 */
async function showAssignGroupModal() {
    if (!currentOrgId) return;

    try {
        // Get current organization info
        const currentOrg = allOrganizations.find(o => o.id === currentOrgId);
        if (!currentOrg) return;

        // Display target organization
        document.getElementById('targetOrgDisplay').textContent = currentOrg.name;

        // Get all groups from all organizations
        const allGroupsData = await Auth.apiCall('/api/groups');
        const allGroups = allGroupsData.groups || [];

        // Get groups already assigned to current organization
        const currentOrgGroupsData = await Auth.apiCall(`/api/organizations/${currentOrgId}/groups`);
        const currentOrgGroups = currentOrgGroupsData.groups || [];
        const currentOrgGroupIds = new Set(currentOrgGroups.map(g => g.id));

        // Filter out groups that are already assigned to current organization
        const availableGroups = allGroups.filter(g => !currentOrgGroupIds.has(g.id));

        const select = document.getElementById('assignGroupSelect');
        select.innerHTML = '<option value="">그룹을 선택하세요</option>';

        if (availableGroups.length === 0) {
            select.innerHTML = '<option value="">할당 가능한 그룹이 없습니다</option>';
            select.disabled = true;
        } else {
            select.disabled = false;

            // Sort groups by name
            availableGroups.sort((a, b) => a.name.localeCompare(b.name));

            // Add all groups to select (no grouping by organization)
            availableGroups.forEach(group => {
                const option = document.createElement('option');
                option.value = group.id;
                option.textContent = `${group.icon || '📁'} ${group.name}`;
                option.dataset.groupName = group.name;
                select.appendChild(option);
            });
        }

        // Add change listener to show info
        select.onchange = function() {
            const selectedOption = select.options[select.selectedIndex];
            const infoDiv = document.getElementById('assignGroupInfo');
            const infoP = infoDiv.querySelector('p');

            if (selectedOption.value) {
                const groupName = selectedOption.dataset.groupName;
                infoP.textContent = `"${groupName}" 그룹을 "${currentOrg.name}" 조직에 추가합니다. 다른 조직에서도 계속 사용 가능합니다.`;
                infoDiv.style.display = 'block';
            } else {
                infoDiv.style.display = 'none';
            }
        };

        document.getElementById('assignGroupError').style.display = 'none';
        document.getElementById('assignGroupModal').style.display = 'flex';

    } catch (error) {
        logger.error('그룹 할당 모달 로드 실패:', error);
        showOrgError('그룹 목록을 불러오는데 실패했습니다');
    }
}

/**
 * Close assign group modal
 */
function closeAssignGroupModal() {
    document.getElementById('assignGroupModal').style.display = 'none';
    document.getElementById('assignGroupSelect').value = '';
    document.getElementById('assignGroupInfo').style.display = 'none';
}

/**
 * Confirm and assign group to organization
 */
async function confirmAssignGroup() {
    if (!currentOrgId) return;

    const select = document.getElementById('assignGroupSelect');
    const groupId = select.value;

    if (!groupId) {
        document.getElementById('assignGroupError').textContent = '그룹을 선택해주세요';
        document.getElementById('assignGroupError').style.display = 'block';
        return;
    }

    const selectedOption = select.options[select.selectedIndex];
    const groupName = selectedOption.dataset.groupName;
    const fromOrg = selectedOption.dataset.orgName;

    const currentOrg = allOrganizations.find(o => o.id === currentOrgId);
    const toOrgName = currentOrg ? currentOrg.name : currentOrgId;

    if (!confirm(`"${groupName}" 그룹을 "${toOrgName}" 조직에 추가하시겠습니까?\n\n✅ 기존 조직 관계는 유지됩니다 (중복 할당)`)) {
        return;
    }

    try {
        const data = await Auth.apiCall(`/api/organizations/${currentOrgId}/groups/${groupId}`, {
            method: 'POST'
        });

        if (data.success) {
            closeAssignGroupModal();
            await loadOrgGroups(currentOrgId);
            await loadOrganizationDetails(currentOrgId);
            showOrgSuccess(data.message || '그룹이 추가되었습니다');
        }
    } catch (error) {
        logger.error('그룹 추가 실패:', error);
        document.getElementById('assignGroupError').textContent = error.message || '그룹 추가에 실패했습니다';
        document.getElementById('assignGroupError').style.display = 'block';
    }
}

/**
 * Remove group from organization
 */
async function removeGroupFromOrg(groupId) {
    if (!currentOrgId) return;

    try {
        // Get group info
        const allGroupsData = await Auth.apiCall('/api/groups');
        const group = (allGroupsData.groups || []).find(g => g.id === groupId);

        if (!group) {
            showOrgError('그룹을 찾을 수 없습니다');
            return;
        }

        const currentOrg = allOrganizations.find(o => o.id === currentOrgId);
        const orgName = currentOrg ? currentOrg.name : currentOrgId;

        if (!confirm(`"${group.name}" 그룹을 "${orgName}" 조직에서 제거하시겠습니까?\n\n⚠️ 이 조직의 사용자는 더 이상 이 그룹의 문서에 접근할 수 없습니다.\n✅ 다른 조직에서는 계속 사용 가능합니다.`)) {
            return;
        }

        const data = await Auth.apiCall(`/api/organizations/${currentOrgId}/groups/${groupId}`, {
            method: 'DELETE'
        });

        if (data.success) {
            await loadOrgGroups(currentOrgId);
            await loadOrganizationDetails(currentOrgId);
            showOrgSuccess(data.message || '그룹이 제거되었습니다');
        }
    } catch (error) {
        logger.error('그룹 제거 실패:', error);
        showOrgError(error.message || '그룹 제거에 실패했습니다');
    }
}

// Initialize when organizations tab is activated
document.addEventListener('DOMContentLoaded', () => {
    // Hook into tab switching to initialize organizations when tab is selected
    const originalSwitchTab = window.switchTab;
    window.switchTab = function(tabName) {
        if (originalSwitchTab) {
            originalSwitchTab(tabName);
        }
        if (tabName === 'organizations') {
            initOrganizations();
        }
    };
});
