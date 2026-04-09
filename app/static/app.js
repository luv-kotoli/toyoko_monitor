const state = {
  areas: [],
  catalog: [],
  searchResults: [],
  monitorTargets: [],
  monitorGroups: [],
  selectedHotelCodes: new Set(),
  selectedRoomTargets: new Set(),
  expandedGroupIds: new Set(),
  monitorSettings: {
    check_interval_minutes: 15,
  },
};

const elements = {
  appStatus: document.querySelector("#app-status"),
  areaSelect: document.querySelector("#area-select"),
  subareaSelect: document.querySelector("#subarea-select"),
  startDate: document.querySelector("#start-date"),
  endDate: document.querySelector("#end-date"),
  peopleInput: document.querySelector("#people-input"),
  roomsInput: document.querySelector("#rooms-input"),
  smokingSelect: document.querySelector("#smoking-select"),
  searchButton: document.querySelector("#search-button"),
  addMonitorButton: document.querySelector("#add-monitor-button"),
  refreshMonitorButton: document.querySelector("#refresh-monitor-button"),
  monitorToolbarNote: document.querySelector("#monitor-toolbar-note"),
  monitorCheckIntervalInput: document.querySelector("#monitor-check-interval-input"),
  saveMonitorIntervalButton: document.querySelector("#save-monitor-interval-button"),
  selectAllHotelsButton: document.querySelector("#select-all-hotels-button"),
  clearSelectedHotelsButton: document.querySelector("#clear-selected-hotels-button"),
  catalogCount: document.querySelector("#catalog-count"),
  catalogSummary: document.querySelector("#catalog-summary"),
  catalogList: document.querySelector("#catalog-list"),
  searchSummary: document.querySelector("#search-summary"),
  resultsList: document.querySelector("#results-list"),
  monitorBody: document.querySelector("#monitor-body"),
};

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  seedDefaultDates();
  initialize();
});

function bindEvents() {
  elements.areaSelect.addEventListener("change", () => {
    populateSubareas(elements.areaSelect.value);
    void loadCatalog();
  });

  elements.subareaSelect.addEventListener("change", () => {
    void loadCatalog();
  });

  elements.searchButton.addEventListener("click", () => {
    void runSearch();
  });

  elements.addMonitorButton.addEventListener("click", () => {
    void addMonitorTargets();
  });

  elements.refreshMonitorButton.addEventListener("click", () => {
    void refreshMonitorTargets();
  });

  elements.saveMonitorIntervalButton.addEventListener("click", () => {
    void saveMonitorSettings();
  });

  elements.selectAllHotelsButton.addEventListener("click", () => {
    state.catalog.forEach((hotel) => state.selectedHotelCodes.add(hotel.hotel_code));
    renderCatalog();
  });

  elements.clearSelectedHotelsButton.addEventListener("click", () => {
    state.selectedHotelCodes.clear();
    renderCatalog();
  });
}

async function initialize() {
  setStatus("加载区域列表中");
  try {
    await loadAreas();
    await loadMonitorSettings();
    await loadMonitorTargets();
    setStatus("可用");
  } catch (error) {
    console.error(error);
    setStatus(`初始化失败: ${error.message}`);
  }

  window.setInterval(() => {
    void loadMonitorTargets();
  }, 60_000);
}

function seedDefaultDates() {
  const now = new Date();
  const start = new Date(now);
  start.setDate(start.getDate() + 1);
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  elements.startDate.value = toInputDate(start);
  elements.endDate.value = toInputDate(end);
}

async function loadAreas() {
  const areas = await api("/api/areas");
  state.areas = areas;
  elements.areaSelect.innerHTML = areas
    .map(
      (area) =>
        `<option value="${escapeHtml(area.key)}">${escapeHtml(area.label)} (${area.hotel_count})</option>`,
    )
    .join("");

  if (areas.length > 0) {
    populateSubareas(areas[0].key);
    await loadCatalog();
  }
}

function populateSubareas(areaKey) {
  const area = state.areas.find((item) => item.key === areaKey);
  const options = [
    `<option value="all">全部 (${area ? area.hotel_count : 0})</option>`,
    ...(area?.subareas || []).map(
      (subarea) =>
        `<option value="${escapeHtml(subarea.key)}">${escapeHtml(subarea.label)} (${subarea.hotel_count})</option>`,
    ),
  ];
  elements.subareaSelect.innerHTML = options.join("");
}

async function loadCatalog() {
  const areaKey = elements.areaSelect.value;
  const subareaKey = elements.subareaSelect.value || "all";
  if (!areaKey) {
    return;
  }

  setStatus("加载日文酒店目录");
  const hotels = await api(
    `/api/hotels?area_key=${encodeURIComponent(areaKey)}&subarea_key=${encodeURIComponent(subareaKey)}`,
  );
  state.catalog = hotels;
  const visibleHotelCodes = new Set(hotels.map((hotel) => hotel.hotel_code));
  state.selectedHotelCodes = new Set(
    [...state.selectedHotelCodes].filter((hotelCode) => visibleHotelCodes.has(hotelCode)),
  );
  renderCatalog();
  setStatus("可用");
}

function renderCatalog() {
  elements.catalogCount.textContent = `${state.catalog.length} 家`;
  elements.catalogSummary.textContent =
    state.selectedHotelCodes.size > 0
      ? `当前勾选 ${state.selectedHotelCodes.size} 家。`
      : "点击酒店卡片即可勾选。";

  if (state.catalog.length === 0) {
    elements.catalogList.innerHTML = '<div class="empty-row">暂无酒店目录</div>';
    return;
  }

  elements.catalogList.innerHTML = state.catalog
    .map((hotel) => {
      const selected = state.selectedHotelCodes.has(hotel.hotel_code);
      return `
        <button
          type="button"
          class="catalog-item ${selected ? "is-selected" : ""}"
          data-hotel-code="${escapeHtml(hotel.hotel_code)}"
        >
          <div class="catalog-name">${escapeHtml(hotel.name)}</div>
          <div class="catalog-meta catalog-meta-primary">
            ${escapeHtml(hotel.subarea_label)} · ${escapeHtml(hotel.city || "都市名なし")}
          </div>
          <div class="catalog-meta catalog-meta-secondary">${escapeHtml(hotel.address || "住所未提供")}</div>
        </button>
      `;
    })
    .join("");

  document.querySelectorAll("[data-hotel-code]").forEach((button) => {
    button.addEventListener("click", () => {
      toggleHotelSelection(button.dataset.hotelCode);
    });
  });
}

function toggleHotelSelection(hotelCode) {
  if (state.selectedHotelCodes.has(hotelCode)) {
    state.selectedHotelCodes.delete(hotelCode);
  } else {
    state.selectedHotelCodes.add(hotelCode);
  }
  renderCatalog();
}

async function runSearch() {
  const hotelCodes = [...state.selectedHotelCodes];
  if (hotelCodes.length === 0) {
    setStatus("请先从酒店目录里选择至少一家酒店");
    return;
  }

  elements.searchButton.disabled = true;
  elements.searchSummary.textContent = `正在查询 ${hotelCodes.length} 家酒店，请稍候。`;
  setStatus("正在查询空房");

  try {
    const results = await api("/api/search", {
      method: "POST",
      body: JSON.stringify({
        ...collectCriteria(),
        hotel_codes: hotelCodes,
      }),
    });
    state.searchResults = results;
    state.selectedRoomTargets.clear();
    renderSearchResults();
    const availableCount = results.filter((item) => item.has_vacancy).length;
    elements.searchSummary.textContent =
      `已查询 ${results.length} 家酒店，其中 ${availableCount} 家当前至少有一个房型可订。`;
    setStatus("查询完成");
  } catch (error) {
    console.error(error);
    elements.searchSummary.textContent = error.message;
    setStatus(`查询失败: ${error.message}`);
  } finally {
    elements.searchButton.disabled = false;
  }
}

function renderSearchResults() {
  if (state.searchResults.length === 0) {
    elements.resultsList.innerHTML = '<div class="empty-row">暂无查询结果</div>';
    syncAddMonitorButton();
    return;
  }

  elements.resultsList.innerHTML = state.searchResults
    .map((hotel) => {
      const roomButtons = hotel.room_types.length
        ? hotel.room_types
            .map((room) => {
              const selectionKey = buildRoomSelectionKey(hotel.hotel_code, room.room_type_id);
              const selected = state.selectedRoomTargets.has(selectionKey);
              const hasVacancy = Math.max(room.general_vacant_room, room.member_vacant_room) > 0;
              return `
                <button
                  type="button"
                  class="room-button ${selected ? "is-selected" : ""} ${hasVacancy ? "is-available" : "is-unavailable"}"
                  data-room-selection="${escapeHtml(selectionKey)}"
                >
                  <span class="room-button-line room-button-title">
                    ${escapeHtml(room.room_type_name)} · ${escapeHtml(room.smoking)}
                  </span>
                  <span class="room-button-line">
                    空房 ${Math.max(room.general_vacant_room, room.member_vacant_room)} 室
                  </span>
                  <span class="room-button-line">
                    ${formatRoomPrice(room.general_price, room.member_price)}
                  </span>
                </button>
              `;
            })
            .join("")
        : '<div class="muted">当前未返回房型数据。</div>';

      return `
        <article class="result-card">
          <div class="result-card-head">
            <div class="hotel-cell">
              <div class="hotel-name">${escapeHtml(hotel.name)}</div>
              <div class="hotel-sub">${escapeHtml(hotel.subarea_label)} · ${escapeHtml(hotel.hotel_code)}</div>
            </div>
            ${renderStatusBadge(hotel)}
          </div>
          <div class="result-card-grid">
            <div>
              <span class="result-label">地址</span>
              <div>${escapeHtml(composeAddress(hotel))}</div>
            </div>
            <div>
              <span class="result-label">可订房数</span>
              <div>${hotel.available_room_count ?? 0}</div>
            </div>
          </div>
          ${hotel.error_message ? `<div class="result-error">${escapeHtml(hotel.error_message)}</div>` : ""}
          <div class="room-button-grid">${roomButtons}</div>
        </article>
      `;
    })
    .join("");

  document.querySelectorAll("[data-room-selection]").forEach((button) => {
    button.addEventListener("click", () => {
      toggleRoomTarget(button.dataset.roomSelection);
    });
  });

  syncAddMonitorButton();
}

function toggleRoomTarget(selectionKey) {
  if (state.selectedRoomTargets.has(selectionKey)) {
    state.selectedRoomTargets.delete(selectionKey);
  } else {
    state.selectedRoomTargets.add(selectionKey);
  }
  renderSearchResults();
}

async function addMonitorTargets() {
  const targets = resolveSelectedMonitorTargets();
  if (targets.length === 0) {
    setStatus("请先在查询结果里选择要监控的房型");
    return;
  }

  const defaultGroupName = buildSuggestedGroupName();
  const groupNameInput = window.prompt("请输入本次监控组名", defaultGroupName);
  if (groupNameInput === null) {
    setStatus("已取消加入监控");
    return;
  }
  const groupName = groupNameInput.trim();
  if (!groupName) {
    setStatus("组名不能为空");
    return;
  }

  elements.addMonitorButton.disabled = true;
  setStatus(`正在加入监控: ${targets.length} 个房型 -> ${groupName}`);

  try {
    const updatedTargets = await api("/api/monitor-targets", {
      method: "POST",
      body: JSON.stringify({
        ...collectCriteria(),
        group_name: groupName,
        targets,
      }),
    });
    state.monitorTargets = updatedTargets;
    state.monitorGroups = buildMonitorGroups(updatedTargets);
    const createdGroup = [...state.monitorGroups]
      .filter((group) => group.name === groupName)
      .sort((left, right) => right.id - left.id)[0];
    if (createdGroup) {
      state.expandedGroupIds.add(String(createdGroup.id));
    }
    state.selectedRoomTargets.clear();
    renderSearchResults();
    renderMonitorTargets();
    setStatus(`已加入监控: ${targets.length} 个房型 -> ${groupName}`);
  } catch (error) {
    console.error(error);
    setStatus(`加入监控失败: ${error.message}`);
  } finally {
    syncAddMonitorButton();
  }
}

function resolveSelectedMonitorTargets() {
  const resultMap = new Map();
  state.searchResults.forEach((hotel) => {
    hotel.room_types.forEach((room) => {
      resultMap.set(buildRoomSelectionKey(hotel.hotel_code, room.room_type_id), {
        hotel_code: hotel.hotel_code,
        room_type_id: room.room_type_id,
        room_type_name: room.room_type_name,
        room_type_smoking: room.smoking,
      });
    });
  });

  return [...state.selectedRoomTargets]
    .map((selectionKey) => resultMap.get(selectionKey))
    .filter(Boolean);
}

async function loadMonitorTargets() {
  try {
    const targets = await api("/api/monitor-targets");
    state.monitorTargets = targets;
    state.monitorGroups = buildMonitorGroups(targets);
    const visibleGroupIds = new Set(state.monitorGroups.map((group) => String(group.id)));
    state.expandedGroupIds = new Set(
      [...state.expandedGroupIds].filter((groupId) => visibleGroupIds.has(groupId)),
    );
    renderMonitorTargets();
  } catch (error) {
    console.error(error);
    setStatus(`加载监控失败: ${error.message}`);
  }
}

async function loadMonitorSettings() {
  const response = await api("/api/settings/monitor");
  state.monitorSettings = response.monitor || { check_interval_minutes: 15 };
  renderMonitorSettings();
}

async function saveMonitorSettings() {
  const checkIntervalMinutes = parseCheckInterval(elements.monitorCheckIntervalInput.value);
  elements.saveMonitorIntervalButton.disabled = true;
  setStatus(`正在保存刷新间隔: ${checkIntervalMinutes} 分钟`);
  try {
    const response = await api("/api/settings/monitor", {
      method: "PUT",
      body: JSON.stringify({
        check_interval_minutes: checkIntervalMinutes,
      }),
    });
    state.monitorSettings = response.monitor || { check_interval_minutes: checkIntervalMinutes };
    renderMonitorSettings();
    setStatus(`刷新间隔已更新为 ${state.monitorSettings.check_interval_minutes} 分钟`);
  } catch (error) {
    console.error(error);
    setStatus(`刷新间隔保存失败: ${error.message}`);
  } finally {
    elements.saveMonitorIntervalButton.disabled = false;
  }
}

function renderMonitorTargets() {
  if (state.monitorGroups.length === 0) {
    elements.monitorBody.innerHTML = '<tr><td colspan="5" class="empty-row">暂无监控项</td></tr>';
    return;
  }

  elements.monitorBody.innerHTML = state.monitorGroups
    .map((group) => renderMonitorGroup(group))
    .join("");

  document.querySelectorAll("[data-group-toggle]").forEach((row) => {
    row.addEventListener("click", () => {
      toggleMonitorGroup(row.dataset.groupToggle);
    });
  });

  document.querySelectorAll("[data-group-rename]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      void renameMonitorGroup(button.dataset.groupRename, button.dataset.groupName);
    });
  });

  document.querySelectorAll("[data-group-refresh]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      void refreshMonitorGroup(button.dataset.groupRefresh, button.dataset.groupName);
    });
  });

  document.querySelectorAll("[data-group-enabled]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      void updateMonitorGroupEnabled(
        button.dataset.groupEnabled,
        button.dataset.groupName,
        button.dataset.groupEnabledNext === "true",
      );
    });
  });

  document.querySelectorAll("[data-group-delete]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      void deleteMonitorGroup(button.dataset.groupDelete, button.dataset.groupName);
    });
  });

  document.querySelectorAll("[data-delete-id]").forEach((button) => {
    button.addEventListener("click", () => {
      void deleteMonitorTarget(button.dataset.deleteId);
    });
  });
}

function renderMonitorGroup(group) {
  const expanded = state.expandedGroupIds.has(String(group.id));
  const monitoringLabel = getGroupMonitoringLabel(group);
  const innerRows = group.targets
    .map(
      (target) => `
        <tr>
          <td>
            <div class="hotel-cell">
              <div class="hotel-name">${escapeHtml(target.hotel_name)}</div>
              <div class="hotel-sub">
                ${escapeHtml(target.subarea_label)} · ${escapeHtml(target.room_type_name)}
                ${target.room_type_smoking ? ` · ${escapeHtml(target.room_type_smoking)}` : ""}
              </div>
            </div>
          </td>
          <td>${escapeHtml(target.start_date)} → ${escapeHtml(target.end_date)}</td>
          <td>${renderStatusBadge(target)}</td>
          <td>${target.available_room_count ?? "-"}</td>
          <td>${formatRoomPrice(target.general_price, target.member_price)}</td>
          <td>${target.last_checked_at ? formatDateTime(target.last_checked_at) : "-"}</td>
          <td><button class="action-link" data-delete-id="${target.id}">删除</button></td>
        </tr>
      `,
    )
    .join("");

  return `
    <tr class="monitor-group-row ${expanded ? "is-expanded" : ""} ${group.enabled ? "" : "is-disabled"}" data-group-toggle="${group.id}">
      <td>
        <div class="monitor-group-cell">
          <span class="monitor-group-marker" aria-hidden="true"></span>
          <div>
            <div class="monitor-group-name">${escapeHtml(group.name)}</div>
            <div class="monitor-group-meta">
              ${group.targets.length} 个房型监控 ·
              <span class="monitor-group-state ${group.enabled ? "is-enabled" : group.partiallyEnabled ? "is-partial" : "is-disabled"}">
                ${escapeHtml(monitoringLabel)}
              </span>
            </div>
          </div>
        </div>
      </td>
      <td>${group.targets.length}</td>
      <td>
        <span class="monitor-total-badge ${group.totalAvailableCount > 0 ? "has-available" : ""}">
          ${group.totalAvailableCount}
        </span>
      </td>
      <td>${group.lastCheckedAt ? formatDateTime(group.lastCheckedAt) : "-"}</td>
      <td>
        <div class="group-action-row">
          <button
            type="button"
            class="btn btn-small group-action-btn group-action-rename"
            data-group-rename="${group.id}"
            data-group-name="${escapeHtml(group.name)}"
          >
            改名
          </button>
          <button
            type="button"
            class="btn btn-small group-action-btn group-action-refresh"
            data-group-refresh="${group.id}"
            data-group-name="${escapeHtml(group.name)}"
          >
            刷新分组
          </button>
          <button
            type="button"
            class="btn btn-small group-action-btn ${group.enabled ? "group-action-pause" : "group-action-enable"}"
            data-group-enabled="${group.id}"
            data-group-enabled-next="${group.enabled ? "false" : "true"}"
            data-group-name="${escapeHtml(group.name)}"
          >
            ${group.enabled ? "暂停监控" : "开启监控"}
          </button>
          <button
            type="button"
            class="btn btn-small group-action-btn group-action-delete"
            data-group-delete="${group.id}"
            data-group-name="${escapeHtml(group.name)}"
          >
            删除整组
          </button>
        </div>
      </td>
    </tr>
    <tr class="monitor-group-detail-row ${expanded ? "" : "is-collapsed"}">
      <td colspan="5">
        <div class="monitor-group-detail">
          <div class="table-wrap monitor-inner-wrap">
            <table class="monitor-inner-table">
              <thead>
                <tr>
                  <th>酒店 / 房型</th>
                  <th>日期</th>
                  <th>状态</th>
                  <th>空房数</th>
                  <th>价格</th>
                  <th>上次刷新</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                ${innerRows}
              </tbody>
            </table>
          </div>
        </div>
      </td>
    </tr>
  `;
}

function buildMonitorGroups(targets) {
  const groups = new Map();

  targets.forEach((target) => {
    const groupId = String(target.group_id);
    if (!groups.has(groupId)) {
      groups.set(groupId, {
        id: target.group_id,
        name: target.group_name,
        targets: [],
        totalAvailableCount: 0,
        lastCheckedAt: null,
        enabledTargetCount: 0,
      });
    }

    const group = groups.get(groupId);
    group.targets.push(target);
    group.totalAvailableCount += Number(target.available_room_count || 0);
    if (target.enabled) {
      group.enabledTargetCount += 1;
    }

    if (target.last_checked_at) {
      if (!group.lastCheckedAt) {
        group.lastCheckedAt = target.last_checked_at;
      } else if (new Date(target.last_checked_at) > new Date(group.lastCheckedAt)) {
        group.lastCheckedAt = target.last_checked_at;
      }
    }
  });

  return [...groups.values()]
    .map((group) => ({
      ...group,
      enabled: group.enabledTargetCount === group.targets.length,
      partiallyEnabled: group.enabledTargetCount > 0 && group.enabledTargetCount < group.targets.length,
    }))
    .sort((left, right) => right.id - left.id);
}

function toggleMonitorGroup(groupId) {
  const normalizedGroupId = String(groupId);
  if (state.expandedGroupIds.has(normalizedGroupId)) {
    state.expandedGroupIds.delete(normalizedGroupId);
  } else {
    state.expandedGroupIds.add(normalizedGroupId);
  }
  renderMonitorTargets();
}

async function renameMonitorGroup(groupId, currentName) {
  const nextNameInput = window.prompt("请输入新的组名", currentName);
  if (nextNameInput === null) {
    return;
  }
  const nextName = nextNameInput.trim();
  if (!nextName) {
    setStatus("组名不能为空");
    return;
  }

  setStatus(`正在修改组名: ${currentName} -> ${nextName}`);
  try {
    await api(`/api/monitor-groups/${groupId}`, {
      method: "PATCH",
      body: JSON.stringify({ name: nextName }),
    });
    await loadMonitorTargets();
    state.expandedGroupIds.add(String(groupId));
    renderMonitorTargets();
    setStatus(`组名已更新: ${nextName}`);
  } catch (error) {
    console.error(error);
    setStatus(`组名更新失败: ${error.message}`);
  }
}

async function refreshMonitorGroup(groupId, groupName) {
  setStatus(`正在刷新分组: ${groupName}`);
  try {
    const result = await api(`/api/monitor-groups/${groupId}/refresh`, {
      method: "POST",
      body: "{}",
    });
    state.expandedGroupIds.add(String(groupId));
    await loadMonitorTargets();
    setStatus(`分组刷新完成: ${groupName} (${result.refreshed_count} 项)`);
  } catch (error) {
    console.error(error);
    setStatus(`分组刷新失败: ${error.message}`);
  }
}

async function updateMonitorGroupEnabled(groupId, groupName, enabled) {
  setStatus(`${enabled ? "正在开启" : "正在暂停"}分组监控: ${groupName}`);
  try {
    await api(`/api/monitor-groups/${groupId}/enabled`, {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    });
    state.expandedGroupIds.add(String(groupId));
    await loadMonitorTargets();
    setStatus(`${enabled ? "已开启" : "已暂停"}分组监控: ${groupName}`);
  } catch (error) {
    console.error(error);
    setStatus(`分组监控状态更新失败: ${error.message}`);
  }
}

async function deleteMonitorGroup(groupId, groupName) {
  const confirmed = window.confirm(`确定删除整个分组「${groupName}」吗？这会删除组内全部监控项。`);
  if (!confirmed) {
    return;
  }

  setStatus(`正在删除分组: ${groupName}`);
  try {
    await api(`/api/monitor-groups/${groupId}`, { method: "DELETE" });
    state.expandedGroupIds.delete(String(groupId));
    await loadMonitorTargets();
    setStatus(`分组已删除: ${groupName}`);
  } catch (error) {
    console.error(error);
    setStatus(`删除分组失败: ${error.message}`);
  }
}

async function deleteMonitorTarget(targetId) {
  setStatus("正在删除监控项");
  try {
    await api(`/api/monitor-targets/${targetId}`, { method: "DELETE" });
    await loadMonitorTargets();
    setStatus("监控项已删除");
  } catch (error) {
    console.error(error);
    setStatus(`删除失败: ${error.message}`);
  }
}

async function refreshMonitorTargets() {
  elements.refreshMonitorButton.disabled = true;
  setStatus("正在刷新全部监控项");
  try {
    const result = await api("/api/monitor/run", {
      method: "POST",
      body: "{}",
    });
    await loadMonitorTargets();
    setStatus(`刷新完成: ${result.refreshed_count} 项`);
  } catch (error) {
    console.error(error);
    setStatus(`刷新失败: ${error.message}`);
  } finally {
    elements.refreshMonitorButton.disabled = false;
  }
}

function buildSuggestedGroupName() {
  const startDate = formatShortDate(elements.startDate.value);
  const endDate = formatShortDate(elements.endDate.value);
  const area = state.areas.find((item) => item.key === elements.areaSelect.value);
  const subarea = area?.subareas?.find((item) => item.key === elements.subareaSelect.value);
  const regionLabel = subarea?.label || area?.label || "监控组";
  return `${startDate}-${endDate}${trimRegionLabel(regionLabel)}`;
}

function renderMonitorSettings() {
  const interval = state.monitorSettings?.check_interval_minutes || 15;
  elements.monitorCheckIntervalInput.value = String(interval);
  elements.monitorToolbarNote.textContent =
    `监控项会保存到本地 SQLite，按组折叠展示；点击组行即可展开或收起。当前统一刷新间隔为 ${interval} 分钟。`;
}

function collectCriteria() {
  return {
    start_date: elements.startDate.value,
    end_date: elements.endDate.value,
    people: Number(elements.peopleInput.value || 1),
    rooms: Number(elements.roomsInput.value || 1),
    smoking: elements.smokingSelect.value,
  };
}

function syncAddMonitorButton() {
  const count = state.selectedRoomTargets.size;
  elements.addMonitorButton.disabled = count === 0;
  elements.addMonitorButton.textContent = count > 0 ? `加入房型监控 (${count})` : "加入房型监控";
}

function renderStatusBadge(item) {
  if (item.error_message) {
    return '<span class="badge badge-error">错误</span>';
  }
  if (item.last_status === "available" || item.has_vacancy) {
    return '<span class="badge badge-available">有空房</span>';
  }
  if (item.last_status === "error") {
    return '<span class="badge badge-error">错误</span>';
  }
  return '<span class="badge badge-unavailable">无空房</span>';
}

function getGroupMonitoringLabel(group) {
  if (group.partiallyEnabled) {
    return `部分监控(${group.enabledTargetCount}/${group.targets.length})`;
  }
  return group.enabled ? "监控中" : "已暂停";
}

function composeAddress(item) {
  return [item.city, item.address].filter(Boolean).join(" · ") || "未提供地址";
}

function formatRoomPrice(generalPrice, memberPrice) {
  if (generalPrice === null && memberPrice === null) {
    return "价格未返回";
  }
  const parts = [];
  if (generalPrice !== null && generalPrice !== undefined) {
    parts.push(`一般 ${formatPrice(generalPrice)}`);
  }
  if (memberPrice !== null && memberPrice !== undefined) {
    parts.push(`会员 ${formatPrice(memberPrice)}`);
  }
  return parts.join(" / ");
}

function formatPrice(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  return `¥${Number(value).toLocaleString("zh-CN")}`;
}

function formatDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatShortDate(value) {
  if (!value) {
    return "--.--";
  }
  const [, month, day] = value.split("-");
  return `${Number(month)}.${Number(day)}`;
}

function parseCheckInterval(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 1) {
    return 15;
  }
  return Math.min(1440, Math.round(parsed));
}

function toInputDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function buildRoomSelectionKey(hotelCode, roomTypeId) {
  return `${hotelCode}::${roomTypeId}`;
}

function trimRegionLabel(value) {
  return String(value).replace(/(都|道|府|県)$/, "");
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
    },
    ...options,
  });

  if (response.status === 204) {
    return null;
  }

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail = typeof payload === "object" && payload && payload.detail ? payload.detail : response.statusText;
    throw new Error(detail);
  }

  return payload;
}

function setStatus(text) {
  elements.appStatus.textContent = text;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
