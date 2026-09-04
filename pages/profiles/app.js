/* 心迹画像 · Profile Weaver — Dashboard Page 前端
 *
 * 后端接口通过 context.register_web_api 注册，前端一律走 window.AstrBotPluginPage
 * 提供的 bridge（apiGet / apiPost / upload / download），不手写 /api/plug 路径。
 */

const bridge = window.AstrBotPluginPage;

/* ------------------------------------------------------------------ 小工具 */

const SVG_NS = "http://www.w3.org/2000/svg";

const ICONS = {
  gauge: ["M4 16a8 8 0 1 1 16 0", "M12 16l4.2-4.6", "M4 16h2", "M18 16h2"],
  users: [
    "M9.5 12.5a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4",
    "M3 19.5v-1a4 4 0 0 1 4-4h5a4 4 0 0 1 4 4v1",
    "M16.6 6.6a3.2 3.2 0 0 1 0 5.6",
    "M18.2 14.7a4 4 0 0 1 2.8 3.8v1",
  ],
  history: [
    "M3.6 9.2A9 9 0 1 1 3 12.4",
    "M3 4.5V9.4h4.9",
    "M12 8v4.4l3.2 2",
  ],
  swap: ["M4 9h12", "M13.2 5.8 16.4 9l-3.2 3.2", "M20 16H8", "M10.8 12.8 7.6 16l3.2 3.2"],
  info: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18", "M12 11.2v5", "M12 8h.02"],
  refresh: ["M20.4 12a8.4 8.4 0 1 1-2.5-6", "M20.4 3.6v4.6h-4.6"],
  search: ["M10.6 17.2a6.6 6.6 0 1 0 0-13.2 6.6 6.6 0 0 0 0 13.2", "M15.4 15.4 20 20"],
  download: ["M12 3.4v11.2", "M7.8 10.6 12 14.8l4.2-4.2", "M4 20h16"],
  upload: ["M12 15.4V4.2", "M7.8 8.4 12 4.2l4.2 4.2", "M4 20h16"],
  trash: ["M4 7h16", "M9.4 7V4.6h5.2V7", "M6.2 7 7.2 20h9.6L17.8 7"],
  check: ["M4.5 12.6 9.6 17.8 19.6 6.6"],
  pencil: ["M4 20h4.2L20.2 8 16 3.8 4 15.8z", "M14.6 5.2 18.8 9.4"],
  close: ["M6.2 6.2 17.8 17.8", "M17.8 6.2 6.2 17.8"],
  shield: ["M12 3.2 20 6.2v5.6c0 5-3.6 8.2-8 9.2-4.4-1-8-4.2-8-9.2V6.2z", "M9.4 12.2 11.6 14.4l3.4-3.8"],
  archive: ["M3.4 6.6h17.2v4H3.4z", "M5.4 10.6V20h13.2v-9.4", "M10 14.4h4"],
  merge: ["M7 20.4V10.4a4 4 0 0 1 4-4h6", "M14 3.4l3 3-3 3", "M7 6.4v-3"],
  chart: ["M4 19.4h16", "M7.4 16.4V10", "M12 16.4V4.8", "M16.6 16.4v-4.4"],
  plus: ["M12 5.4v13.2", "M5.4 12h13.2"],
  link: ["M9.4 14.6 14.6 9.4", "M11.6 6.6 13 5.2a3.8 3.8 0 0 1 5.6 5.4l-1.4 1.4", "M12.4 17.4 11 18.8a3.8 3.8 0 0 1-5.6-5.4l1.4-1.4"],
  tag: ["M4 11.4V4.4h7L20 13.4 13 20.4z", "M8 8h.02"],
  eye: ["M2.6 12S6 6.2 12 6.2 21.4 12 21.4 12 18 17.8 12 17.8 2.6 12 2.6 12", "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6"],
  lock: ["M6.4 10.6h11.2V20H6.4z", "M8.8 10.6V7.8a3.2 3.2 0 0 1 6.4 0v2.8"],
  bolt: ["M13.4 3 6 13.4h4.6L10 21l7.4-10.4h-4.6z"],
  clock: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18", "M12 7.4V12l3.2 2"],
  db: ["M12 3.4c4.4 0 8 1.2 8 2.6S16.4 8.6 12 8.6 4 7.4 4 6s3.6-2.6 8-2.6", "M4 6v12c0 1.4 3.6 2.6 8 2.6s8-1.2 8-2.6V6", "M4 12c0 1.4 3.6 2.6 8 2.6s8-1.2 8-2.6"],
  ghost: ["M4.6 20V10.6a7.4 7.4 0 0 1 14.8 0V20l-2.5-1.8L14.4 20 12 18.2 9.6 20 7.1 18.2z", "M9.6 10.4h.02", "M14.4 10.4h.02"],
  unlock: ["M6.4 10.6h11.2V20H6.4z", "M8.8 10.6V7.8a3.2 3.2 0 0 1 6.2-1"],
  sheet: ["M4.4 4h15.2v16H4.4z", "M4.4 9.4h15.2", "M4.4 14.6h15.2", "M10.2 4v16"],
  target: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18", "M12 16.6a4.6 4.6 0 1 0 0-9.2 4.6 4.6 0 0 0 0 9.2", "M12 13.2a1.2 1.2 0 1 0 0-2.4 1.2 1.2 0 0 0 0 2.4"],
};

function icon(name, className) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.7");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  if (className) svg.setAttribute("class", className);
  for (const d of ICONS[name] || ICONS.info) {
    const p = document.createElementNS(SVG_NS, "path");
    p.setAttribute("d", d);
    svg.appendChild(p);
  }
  return svg;
}

function appendKids(node, kids) {
  for (const kid of kids) {
    if (kid === null || kid === undefined || kid === false || kid === true) continue;
    if (Array.isArray(kid)) {
      appendKids(node, kid);
    } else if (kid instanceof Node) {
      node.appendChild(kid);
    } else {
      node.appendChild(document.createTextNode(String(kid)));
    }
  }
}

/** 极简 hyperscript：只做 DOM 拼装，永不使用 innerHTML，天然免疫 XSS。 */
function h(tag, props, ...kids) {
  const node = document.createElement(tag);
  if (props) {
    for (const key of Object.keys(props)) {
      const value = props[key];
      if (value === null || value === undefined || value === false) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = String(value);
      else if (key === "dataset") Object.assign(node.dataset, value);
      else if (key === "style") Object.assign(node.style, value);
      else if (key.startsWith("on") && typeof value === "function")
        node.addEventListener(key.slice(2).toLowerCase(), value);
      else if (value === true) node.setAttribute(key, "");
      else node.setAttribute(key, String(value));
    }
  }
  appendKids(node, kids);
  return node;
}

function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}

function fill(node, ...kids) {
  clear(node);
  appendKids(node, kids);
  return node;
}

const $ = (id) => document.getElementById(id);

function fmtBytes(size) {
  const value = Number(size) || 0;
  if (value < 1024) return value + " B";
  const units = ["KB", "MB", "GB"];
  let num = value / 1024;
  let index = 0;
  while (num >= 1024 && index < units.length - 1) {
    num /= 1024;
    index += 1;
  }
  return num.toFixed(num >= 10 ? 1 : 2) + " " + units[index];
}

function fmtNum(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "0";
  return num.toLocaleString("en-US");
}

function shortTime(text) {
  const raw = String(text || "").trim();
  if (!raw) return "—";
  return raw.length > 16 ? raw.slice(5, 16) : raw;
}

function relTime(text) {
  const raw = String(text || "").trim();
  if (!raw) return "—";
  const parsed = Date.parse(raw.replace(" ", "T"));
  if (!Number.isFinite(parsed)) return raw;
  const diff = Date.now() - parsed;
  if (diff < 0) return raw;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return mins + " 分钟前";
  const hours = Math.floor(mins / 60);
  if (hours < 24) return hours + " 小时前";
  const days = Math.floor(hours / 24);
  if (days < 30) return days + " 天前";
  return raw.slice(0, 10);
}

function initials(name, fallback) {
  const raw = String(name || fallback || "?").trim();
  if (!raw) return "?";
  const code = raw.codePointAt(0);
  if (code > 0x2e80) return String.fromCodePoint(code);
  return raw.slice(0, 2).toUpperCase();
}

const CHAT_TYPE_TEXT = { private: "私聊", group: "群聊", unknown: "未知" };
const chatTypeText = (value) => CHAT_TYPE_TEXT[value] || value || "未知";

const SOURCE_TEXT = {
  llm: "LLM 提取",
  llm_tool: "LLM 工具",
  auto_extract: "自动抽取",
  user: "用户操作",
  user_command: "用户指令",
  admin: "管理员",
  admin_command: "管理员指令",
  webui: "WebUI",
  system: "系统",
  import: "导入",
  field_lock: "字段锁",
  unknown: "未知",
};
const sourceText = (value) => SOURCE_TEXT[value] || value || "未知";

const ACTION_TEXT = {
  upsert_field: "写入字段",
  append_note: "追加备注",
  delete_field: "删除字段",
  delete_note: "删除备注",
  lock_field: "锁定字段",
  unlock_field: "解锁字段",
  clear_profile: "清空画像",
  merge_profile: "合并画像",
  import_bundle: "导入数据",
  restore_backup: "恢复备份",
  delete_backup: "删除备份",
};
const actionText = (value) => ACTION_TEXT[value] || value || "—";

/* -------------------------------------------------------------------- Toast */

let toastSeq = 0;

function toast(message, kind) {
  const host = $("pw-toasts");
  if (!host) return;
  const id = ++toastSeq;
  const node = h(
    "div",
    { class: "pw-toast" + (kind ? " pw-toast--" + kind : ""), dataset: { id: String(id) } },
    h("div", { text: String(message || "") }),
  );
  host.appendChild(node);
  const timer = setTimeout(() => {
    node.classList.add("is-out");
    setTimeout(() => node.remove(), 200);
  }, kind === "err" ? 6200 : 3600);
  node.addEventListener("click", () => {
    clearTimeout(timer);
    node.remove();
  });
  while (host.children.length > 4) host.firstChild.remove();
}

/* ---------------------------------------------------------------- 接口封装 */

function unwrap(raw) {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    if ("ok" in raw) return raw;
    if (raw.data && typeof raw.data === "object") return raw.data;
  }
  return raw;
}

function errorText(err) {
  if (!err) return "请求失败";
  for (const holder of [err.response, err.body, err.data, err.payload]) {
    if (holder && typeof holder === "object" && holder.message) return String(holder.message);
  }
  return String(err.message || err) || "请求失败";
}

async function apiGet(endpoint, params) {
  let raw;
  try {
    raw = await bridge.apiGet(endpoint, params || {});
  } catch (err) {
    throw new Error(errorText(err));
  }
  const data = unwrap(raw) || {};
  if (data.ok === false) throw new Error(data.message || "请求失败");
  return data;
}

async function apiPost(endpoint, body) {
  let raw;
  try {
    raw = await bridge.apiPost(endpoint, body || {});
  } catch (err) {
    throw new Error(errorText(err));
  }
  const data = unwrap(raw) || {};
  if (data.ok === false) throw new Error(data.message || "请求失败");
  return data;
}

/* ------------------------------------------------------------------ 状态 */

const LS_THEME = "profileweaver.theme";
const LS_DENSITY = "profileweaver.density";
const LS_TAB = "profileweaver.tab";

const state = {
  ctx: null,
  meta: null,
  stats: null,
  coverage: [],
  customFields: [],
  list: { items: [], total: 0, page: 1, page_size: 12, page_count: 1 },
  filters: {
    query: "",
    platform: "all",
    chat_type: "all",
    field: "",
    sort: "updated_desc",
    locked_only: false,
  },
  selected: new Set(),
  detail: null,
  history: { field: "", items: [], loading: false, total: 0 },
  audit: { items: [], total: 0, offset: 0, limit: 50 },
  auditFilters: { query: "", action: "", actor_type: "", user_id: "", include_rotated: false },
  backups: [],
  exportOptions: { include_audit: false, mask: false, selection_only: false },
  importMode: "merge",
  tab: "overview",
  ready: false,
};

const canEdit = () => Boolean(state.meta && state.meta.allow_edit);

function readStore(key, fallback) {
  try {
    return window.localStorage.getItem(key) || fallback;
  } catch (err) {
    return fallback;
  }
}

function writeStore(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch (err) {
    /* localStorage 不可用时静默降级 */
  }
}

/* ------------------------------------------------------------ 主题与密度 */

function applyTheme(themeId) {
  const themes = (state.meta && state.meta.themes) || [];
  const known = themes.some((item) => item.id === themeId);
  const target = known ? themeId : (themes[0] && themes[0].id) || "aurora";
  document.documentElement.setAttribute("data-pw-theme", target);
  writeStore(LS_THEME, target);
  const select = $("pw-theme");
  if (select && select.value !== target) select.value = target;
}

function applyDensity(mode) {
  const target = mode === "compact" ? "compact" : "cozy";
  document.documentElement.setAttribute("data-pw-density", target);
  writeStore(LS_DENSITY, target);
  const label = $("pw-density-label");
  if (label) label.textContent = target === "compact" ? "宽松" : "紧凑";
  const button = $("pw-density");
  if (button) button.title = target === "compact" ? "切换到宽松布局" : "切换到紧凑布局";
}

function buildThemeSelect() {
  const select = $("pw-theme");
  if (!select) return;
  fill(
    select,
    ((state.meta && state.meta.themes) || []).map((item) =>
      h("option", { value: item.id, text: item.name }),
    ),
  );
  select.onchange = () => applyTheme(select.value);
}

/* -------------------------------------------------------------------- 标签页 */

const TABS = [
  { id: "overview", label: "总览", icon: "gauge" },
  { id: "library", label: "画像库", icon: "users", badge: () => state.list.total },
  { id: "audit", label: "审计", icon: "history", badge: () => state.audit.total },
  { id: "migrate", label: "迁移", icon: "swap" },
  { id: "about", label: "关于", icon: "info" },
];

function renderTabs() {
  const host = $("pw-tabs");
  if (!host) return;
  fill(
    host,
    TABS.map((tab) => {
      const count = tab.badge ? Number(tab.badge()) || 0 : 0;
      return h(
        "button",
        {
          class: "pw-tab",
          id: "pw-tab-" + tab.id,
          type: "button",
          role: "tab",
          "aria-selected": state.tab === tab.id ? "true" : "false",
          "aria-controls": "pw-panel-" + tab.id,
          onclick: () => switchTab(tab.id),
        },
        icon(tab.icon),
        h("span", { text: tab.label }),
        count > 0 ? h("span", { class: "pw-tab-badge", text: fmtNum(count) }) : null,
      );
    }),
  );
}

function switchTab(tabId) {
  state.tab = tabId;
  writeStore(LS_TAB, tabId);
  for (const tab of TABS) {
    const panel = $("pw-panel-" + tab.id);
    if (panel) panel.hidden = tab.id !== tabId;
  }
  renderTabs();
  if (tabId === "library" && !state.list.items.length && state.ready) loadProfiles();
  if (tabId === "audit" && !state.audit.items.length && state.ready) loadAudit();
  if (tabId === "migrate" && !state.backups.length && state.ready) loadBackups();
}

/* ---------------------------------------------------------------- 通用积木 */

function card(label, title, options, ...body) {
  const opts = options || {};
  return h(
    "section",
    { class: "pw-card" },
    h(
      "div",
      { class: "pw-card-head" },
      h(
        "div",
        null,
        h("div", { class: "pw-card-label", text: label }),
        h("h2", { class: "pw-card-title", text: title }),
        opts.desc ? h("p", { class: "pw-card-desc", text: opts.desc }) : null,
      ),
      opts.tools && opts.tools.length ? h("div", { class: "pw-card-tools" }, opts.tools) : null,
    ),
    body,
  );
}

function kv(rows) {
  return h(
    "div",
    { class: "pw-kv" },
    rows
      .filter(Boolean)
      .map((row) =>
        h(
          "div",
          { class: "pw-kv-row" },
          h("div", { class: "pw-kv-k", text: row[0] }),
          h("div", { class: "pw-kv-v", text: row[1] === "" || row[1] === null || row[1] === undefined ? "—" : String(row[1]) }),
        ),
      ),
  );
}

function metric(label, value, extra) {
  return h(
    "div",
    { class: "pw-metric" },
    h("div", { class: "pw-metric-k", text: label }),
    h("div", { class: "pw-metric-v", text: String(value) }),
    extra ? h("div", { class: "pw-metric-x", text: extra }) : null,
  );
}

/** 画像完整度进度条：低 / 中 / 高三档配色，随主题变量走。 */
function completenessBar(value, options) {
  const opts = options || {};
  const pct = Math.max(0, Math.min(100, Number(value) || 0));
  const level = pct >= 70 ? "high" : pct >= 35 ? "mid" : "low";
  return h(
    "div",
    {
      class: "pw-meter" + (opts.slim ? " pw-meter--slim" : ""),
      title: "画像完整度 " + pct.toFixed(1) + "%" + (opts.hint ? " · " + opts.hint : ""),
    },
    opts.label ? h("span", { class: "pw-meter-label", text: opts.label }) : null,
    h(
      "div",
      { class: "pw-meter-track" },
      h("div", { class: "pw-meter-fill is-" + level, style: { width: pct + "%" } }),
    ),
    opts.hideValue ? null : h("span", { class: "pw-meter-val mono", text: pct.toFixed(0) + "%" }),
  );
}

function switchControl(checked, label, onChange, title) {
  const box = h("input", { type: "checkbox", checked: checked ? true : null });
  box.onchange = () => onChange(box.checked);
  return h("label", { class: "pw-switch", title: title || label }, box, h("span", { text: label }));
}

function notice(text, kind, iconName) {
  return h(
    "div",
    { class: "pw-notice" + (kind ? " pw-notice--" + kind : "") },
    icon(iconName || "info"),
    h("div", { text: text }),
  );
}

function emptyState(title, desc, iconName) {
  return h(
    "div",
    { class: "pw-empty" },
    icon(iconName || "ghost"),
    h("div", { class: "pw-empty-title", text: title }),
    desc ? h("div", { class: "pw-empty-desc", text: desc }) : null,
  );
}

function iconBtn(iconName, title, onClick, extraClass) {
  return h(
    "button",
    {
      class: "pw-btn pw-btn--icon pw-btn--sm" + (extraClass ? " " + extraClass : ""),
      type: "button",
      title: title,
      "aria-label": title,
      onclick: onClick,
    },
    icon(iconName),
  );
}

function textBtn(iconName, label, onClick, extraClass, disabled) {
  return h(
    "button",
    {
      class: "pw-btn pw-btn--sm" + (extraClass ? " " + extraClass : ""),
      type: "button",
      disabled: disabled ? true : null,
      onclick: onClick,
    },
    iconName ? icon(iconName) : null,
    h("span", { text: label }),
  );
}

async function guard(button, task) {
  if (button) {
    button.disabled = true;
    button.classList.add("is-busy");
  }
  try {
    return await task();
  } catch (err) {
    toast(errorText(err), "err");
    return null;
  } finally {
    if (button) {
      button.disabled = false;
      button.classList.remove("is-busy");
    }
  }
}

/* -------------------------------------------------------------------- 顶栏 */

function renderHeader() {
  const meta = state.meta || {};
  const title = $("pw-title");
  const subtitle = $("pw-subtitle");
  const version = $("pw-version");
  const hint = $("pw-mode-hint");
  if (title) title.textContent = meta.display_name || "心迹画像";
  if (subtitle) subtitle.textContent = meta.subtitle || "Profile Weaver";
  if (version) version.textContent = "v" + (meta.version || "3.1.0");
  if (hint) hint.textContent = canEdit() ? "画像管理面板" : "只读模式";
  document.title = (meta.display_name || "心迹画像") + " · " + (meta.subtitle || "Profile Weaver");
}

function renderStatus() {
  const left = $("pw-status-left");
  const right = $("pw-status-right");
  const stats = state.stats || {};
  const meta = state.meta || {};
  if (left) {
    fill(
      left,
      h("span", null, "画像 "),
      h("span", { class: "mono", text: fmtNum(stats.profile_count || 0) }),
      h("span", null, " · 字段 "),
      h("span", { class: "mono", text: fmtNum(stats.filled_field_count || 0) }),
      h("span", null, " · 会话 "),
      h("span", { class: "mono", text: fmtNum(stats.session_count || 0) }),
      h("span", null, " · 备注 "),
      h("span", { class: "mono", text: fmtNum(stats.note_count || 0) }),
      h("span", null, " · 完整度 "),
      h("span", { class: "mono", text: (Number(stats.avg_completeness || 0)).toFixed(0) + "%" }),
      Number(stats.locked_field_count || 0)
        ? [h("span", null, " · 锁定 "), h("span", { class: "mono", text: fmtNum(stats.locked_field_count) })]
        : null,
      canEdit() ? null : h("span", null, " · 只读"),
    );
  }
  if (right) {
    const current = TABS.find((tab) => tab.id === state.tab);
    fill(
      right,
      h("span", { text: (current && current.label) || "总览" }),
      h("span", { text: " · " }),
      h("span", { text: meta.plugin || "astrbot_plugin_profile_weaver" }),
      h("span", { text: " · v" + (meta.version || "3.1.0") }),
    );
  }
}

/* -------------------------------------------------------------------- 总览 */

function renderOverview() {
  const host = $("pw-panel-overview");
  if (!host) return;
  const meta = state.meta || {};
  const stats = state.stats || {};

  const hero = h(
    "div",
    { class: "pw-hero" },
    h("span", { class: "pw-chip pw-chip--accent", text: meta.plugin || "astrbot_plugin_profile_weaver" }),
    h("span", { class: "pw-hero-name", text: meta.display_name || "心迹画像" }),
    h("span", { class: "pw-hero-sub", text: "· " + (meta.subtitle || "Profile Weaver") }),
    h("span", {
      class: "pw-hero-desc",
      text: "把聊天里自然出现的偏好、习惯与约定沉淀成结构化画像，可查、可改、可审计、可迁移。",
    }),
    h(
      "div",
      { class: "pw-hero-tail" },
      h("span", { class: "pw-chip pw-chip--accent", text: "v" + (meta.version || "3.1.0") }),
      h("span", { class: "pw-chip", text: fmtNum(stats.profile_count || 0) + " 条画像" }),
      h("span", { class: "pw-chip", text: (meta.builtin_fields || []).length + " 个内置字段" }),
      h("span", { class: "pw-chip", text: ((meta.themes || []).length || 7) + " 套主题" }),
      meta.repo
        ? h(
            "a",
            { class: "pw-btn pw-btn--sm", href: meta.repo, target: "_blank", rel: "noreferrer noopener" },
            icon("link"),
            h("span", { text: "GitHub" }),
          )
        : null,
    ),
  );

  const metrics = h(
    "div",
    { class: "pw-grid pw-grid--metrics", style: { marginBottom: "var(--pw-gap)" } },
    metric("PROFILES", fmtNum(stats.profile_count || 0), fmtNum(stats.user_count || 0) + " 位用户"),
    metric("FIELDS", fmtNum(stats.filled_field_count || 0), "均 " + (stats.avg_fields_per_profile || 0) + " 项/人"),
    metric("NOTES", fmtNum(stats.note_count || 0), "上限 " + (meta.max_notes_count || 5) + " 条/人"),
    metric("ACTIVE 7D", fmtNum(stats.active_profiles_7d || 0), "近 7 天有更新"),
    metric("SESSIONS", fmtNum(stats.session_count || 0), (meta.session_based ? "会话隔离" : "全局共享")),
    metric("CUSTOM", fmtNum(stats.custom_field_kind_count || 0), "种自定义字段"),
    metric(
      "COMPLETENESS",
      (Number(stats.avg_completeness || 0)).toFixed(1) + "%",
      "平均画像完整度",
    ),
    metric(
      "LOCKED",
      fmtNum(stats.locked_field_count || 0),
      fmtNum(stats.locked_profile_count || 0) + " 条画像有锁",
    ),
  );

  const coverage = state.coverage || [];
  const total = Number(stats.profile_count || 0);
  const coverageCard = card(
    "COVERAGE",
    "字段覆盖率",
    { desc: "每个内置字段在全部画像中的填充比例，可用来判断哪些维度还很空。" },
    coverage.length
      ? h(
          "div",
          { class: "pw-bars" },
          coverage.map((row) =>
            h(
              "div",
              { class: "pw-bar-row" },
              h("div", { class: "pw-bar-name", title: row.name, text: row.name }),
              h(
                "div",
                { class: "pw-bar-track" },
                h("div", { class: "pw-bar-fill", style: { width: Math.max(0, Math.min(100, row.ratio)) + "%" } }),
              ),
              h("div", { class: "pw-bar-val", text: fmtNum(row.count) + " / " + fmtNum(total) }),
            ),
          ),
        )
      : emptyState("还没有画像数据", "让机器人在聊天里跑一会儿，或先从「迁移」页导入一份备份。", "chart"),
  );

  const sources = Object.keys(stats.source_counts || {}).map((key) => [
    sourceText(key),
    fmtNum(stats.source_counts[key]) + " 次写入",
  ]);
  sources.sort((a, b) => a[0].localeCompare(b[0]));

  const runtimeCard = card(
    "RUNTIME",
    "运行与存储",
    { tools: [iconBtn("refresh", "刷新统计", (event) => guard(event.currentTarget, () => loadStats()))] },
    kv([
      ["画像文件", fmtBytes(stats.profiles_file_bytes || 0)],
      ["审计日志", fmtBytes(stats.audit_log_bytes || 0) + "（另有 " + fmtNum(stats.audit_rotated_count || 0) + " 份归档）"],
      ["本地快照", fmtNum(stats.backup_count || 0) + " 份 · 上限 " + fmtNum(meta.backup_max_count || 60) + " 份"],
      ["近 30 天活跃", fmtNum(stats.active_profiles_30d || 0) + " 条画像有更新"],
      ["最近更新", stats.latest_updated_at ? stats.latest_updated_at + "（" + relTime(stats.latest_updated_at) + "）" : "—"],
      ["会话隔离", meta.session_based ? "已开启（同一用户在不同会话独立成档）" : "已关闭（全局共享一份画像）"],
      ["LLM 工具", meta.llm_tools_enabled ? "已开启" : "已关闭"],
      ["被动提取", meta.proactive_extraction ? "已开启" : "已关闭"],
      ["字段锁范围", stats.field_lock_scope_label || meta.field_lock_scope_label || "—"],
      ["WebUI 写权限", canEdit() ? "已开启" : "只读"],
      ["服务器时间", meta.server_time || "—"],
    ]),
  );

  const sourceCard = card(
    "SOURCES",
    "数据来源分布",
    { desc: "按字段元数据里的写入者统计，可快速看出画像主要由谁在维护。" },
    sources.length ? kv(sources) : emptyState("暂无写入记录", "字段被写入后这里会出现来源统计。", "chart"),
  );

  const customs = state.customFields || [];
  const customCard = card(
    "CUSTOM FIELDS",
    "自定义字段热度",
    { desc: "LLM 或用户临时创建的字段，出现频次高的可以考虑升级为内置字段。" },
    customs.length
      ? h(
          "div",
          { style: { display: "flex", flexWrap: "wrap", gap: "8px" } },
          customs.slice(0, 40).map((item) =>
            h(
              "span",
              {
                class: "pw-pill" + (item.count >= 3 ? " pw-pill--accent" : ""),
                title: item.name + "：" + item.count + " 条画像使用",
              },
              h("span", { text: item.name }),
              h("span", { class: "mono", text: String(item.count) }),
            ),
          ),
        )
      : emptyState("还没有自定义字段", "开启「允许 LLM 创建自定义字段」后，模型可以按需扩展维度。", "tag"),
  );

  const denylist = meta.llm_write_denylist || [];
  const guardCard = card(
    "GUARDRAILS",
    "写入防线",
    { desc: "这些约束共同防止模型把猜测、他人信息或敏感内容写进画像。" },
    kv([
      ["证据校验模式", meta.evidence_match_mode || "normalized"],
      ["单字段长度上限", (meta.field_value_max_length || 160) + " 字"],
      ["备注条数上限", (meta.max_notes_count || 5) + " 条"],
      ["LLM 禁写字段", denylist.length ? denylist.join("、") : "（无）"],
      ["字段锁范围", meta.field_lock_scope_label || "—"],
      ["群聊查看他人画像", meta.allow_profile_in_group ? "允许" : "禁止（默认）"],
      ["身份护栏", meta.strict_identity_guard ? "严格模式" : "宽松模式"],
      ["导出默认脱敏", meta.export_mask_default ? "开启" : "关闭"],
    ]),
  );

  fill(
    host,
    hero,
    metrics,
    h("div", { class: "pw-grid pw-grid--3" }, coverageCard, runtimeCard, h("div", { class: "pw-grid" }, sourceCard, guardCard)),
    h("div", { class: "pw-grid", style: { marginTop: "var(--pw-gap)" } }, customCard),
  );
}

/* ------------------------------------------------------------------ 画像库 */

const SORT_OPTIONS = [
  ["updated_desc", "最近更新"],
  ["updated_asc", "最早更新"],
  ["created_desc", "最近建档"],
  ["created_asc", "最早建档"],
  ["fields_desc", "字段最多"],
  ["fields_asc", "字段最少"],
  ["completeness_desc", "完整度高→低"],
  ["completeness_asc", "完整度低→高"],
  ["locked_desc", "锁定字段最多"],
  ["name_asc", "名称 A→Z"],
  ["name_desc", "名称 Z→A"],
];

let searchTimer = 0;

function selectControl(value, options, onChange, extra) {
  const select = h(
    "select",
    Object.assign({ class: "pw-select", onchange: (event) => onChange(event.target.value) }, extra || {}),
    options.map((option) => h("option", { value: option[0], text: option[1] })),
  );
  select.value = value;
  return select;
}

function renderLibrary() {
  const host = $("pw-panel-library");
  if (!host) return;
  const meta = state.meta || {};
  const filters = state.filters;

  const searchInput = h("input", {
    class: "pw-input pw-grow",
    type: "search",
    placeholder: "搜索昵称 / 用户 ID / 会话 / 字段内容…",
    value: filters.query,
    oninput: (event) => {
      filters.query = event.target.value;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => loadProfiles(1), 320);
    },
  });

  const fieldOptions = [["", "全部字段"]].concat(
    (meta.builtin_fields || []).map((item) => [item.name, item.name]),
    (state.customFields || []).map((item) => [item.name, item.name + "（自定义）"]),
  );

  const platformOptions = [["all", "全部平台"]].concat(
    (meta.platforms || []).map((item) => [item, item]),
  );

  const toolbar = h(
    "div",
    { class: "pw-toolbar" },
    h("label", { class: "pw-field pw-grow" }, icon("search"), searchInput),
    selectControl(filters.platform, platformOptions, (value) => {
      filters.platform = value;
      loadProfiles(1);
    }, { title: "平台筛选" }),
    selectControl(
      filters.chat_type,
      [["all", "全部会话"], ["private", "仅私聊"], ["group", "仅群聊"], ["unknown", "未知来源"]],
      (value) => {
        filters.chat_type = value;
        loadProfiles(1);
      },
      { title: "会话类型" },
    ),
    selectControl(filters.field, fieldOptions, (value) => {
      filters.field = value;
      loadProfiles(1);
    }, { title: "必须包含某字段" }),
    selectControl(filters.sort, SORT_OPTIONS, (value) => {
      filters.sort = value;
      loadProfiles(1);
    }, { title: "排序方式" }),
    h(
      "div",
      { class: "pw-toolbar-tail" },
      selectControl(
        String(state.list.page_size),
        [["12", "12 / 页"], ["24", "24 / 页"], ["48", "48 / 页"], ["96", "96 / 页"]],
        (value) => {
          state.list.page_size = Number(value) || 12;
          loadProfiles(1);
        },
        { title: "每页数量" },
      ),
      switchControl(
        filters.locked_only,
        "只看有锁",
        (checked) => {
          filters.locked_only = checked;
          loadProfiles(1);
        },
        "只显示至少有一个字段被锁定的画像",
      ),
      textBtn("check", state.selected.size ? "已选 " + state.selected.size : "全选本页", () => toggleSelectPage()),
      textBtn(
        "download",
        "导出所选",
        (event) => guard(event.currentTarget, () => exportBundle({ selectionOnly: true })),
        null,
        state.selected.size === 0,
      ),
      textBtn(
        "trash",
        "删除所选",
        (event) => guard(event.currentTarget, () => deleteSelected()),
        "pw-btn--danger",
        !canEdit() || state.selected.size === 0,
      ),
      iconBtn("refresh", "重新载入列表", (event) => guard(event.currentTarget, () => loadProfiles())),
    ),
  );

  const items = state.list.items || [];
  const grid = items.length
    ? h(
        "div",
        { class: "pw-cards" },
        items.map((item) => profileCard(item)),
      )
    : emptyState(
        "没有匹配的画像",
        "试着放宽筛选条件；如果本来就是空的，可以在「迁移」页导入历史数据。",
        "users",
      );

  const pager = h(
    "div",
    { class: "pw-pager" },
    textBtn(null, "上一页", () => loadProfiles(state.list.page - 1), null, state.list.page <= 1),
    h("span", null, "第 "),
    h("span", { class: "mono", text: String(state.list.page) }),
    h("span", null, " / "),
    h("span", { class: "mono", text: String(state.list.page_count) }),
    h("span", null, " 页 · 共 "),
    h("span", { class: "mono", text: fmtNum(state.list.total) }),
    h("span", null, " 条"),
    textBtn(null, "下一页", () => loadProfiles(state.list.page + 1), null, state.list.page >= state.list.page_count),
  );

  fill(host, canEdit() ? null : notice("当前为只读模式，所有写操作已禁用。可在插件配置中开启「WebUI 是否允许写操作」。", "warn", "lock"), toolbar, grid, items.length ? pager : null);
}

function profileCard(item) {
  const checked = state.selected.has(item.key);
  const check = h("input", {
    class: "pw-check pw-pcard-check",
    type: "checkbox",
    title: "选择该画像",
    "aria-label": "选择 " + item.display_name,
    onclick: (event) => {
      event.stopPropagation();
      if (event.target.checked) state.selected.add(item.key);
      else state.selected.delete(item.key);
      renderLibrary();
    },
  });
  check.checked = checked;

  return h(
    "div",
    {
      class: "pw-pcard" + (state.detail && state.detail.key === item.key ? " is-active" : ""),
      role: "button",
      tabindex: "0",
      onclick: () => openDetail(item.key),
      onkeydown: (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openDetail(item.key);
        }
      },
    },
    h(
      "div",
      { class: "pw-pcard-top" },
      h("div", { class: "pw-avatar", text: initials(item.display_name, item.user_id) }),
      h(
        "div",
        { style: { minWidth: "0", flex: "1 1 auto" } },
        h("div", { class: "pw-pcard-name", title: item.display_name, text: item.display_name || item.user_id }),
        h("div", { class: "pw-pcard-id mono", title: item.key, text: item.user_id }),
      ),
      check,
    ),
    h(
      "div",
      { class: "pw-pcard-meta" },
      h("span", { class: "pw-pill pw-pill--accent", text: chatTypeText(item.chat_type) }),
      item.platform ? h("span", { class: "pw-pill pw-pill--mono", text: item.platform }) : null,
      h("span", { class: "pw-pill", text: item.field_count + " 字段" }),
      item.note_count ? h("span", { class: "pw-pill", text: item.note_count + " 备注" }) : null,
      item.custom_field_count ? h("span", { class: "pw-pill pw-pill--warn", text: item.custom_field_count + " 自定义" }) : null,
      item.locked_count
        ? h(
            "span",
            {
              class: "pw-pill pw-pill--lock",
              title: "已锁定字段：" + ((item.locked_fields || []).join("、") || "—"),
            },
            icon("lock", "pw-pill-icon"),
            h("span", { text: item.locked_count + " 锁定" }),
          )
        : null,
    ),
    completenessBar(item.completeness, { slim: true, hint: item.field_count + " 个字段已填" }),
    (item.preview || []).length
      ? h(
          "div",
          { class: "pw-pcard-preview" },
          (item.preview || []).map((row) =>
            h("div", null, h("b", { text: row.name }), h("span", { title: row.value, text: row.value })),
          ),
        )
      : h("div", { class: "pw-pcard-preview" }, h("div", null, h("span", { text: "暂无字段内容" }))),
    h(
      "div",
      { class: "pw-pcard-foot" },
      icon("clock"),
      h("span", { text: relTime(item.updated_at) }),
      h("span", { style: { marginLeft: "auto" }, text: shortTime(item.created_at) + " 建档" }),
    ),
  );
}

function toggleSelectPage() {
  const keys = (state.list.items || []).map((item) => item.key);
  const allSelected = keys.length > 0 && keys.every((key) => state.selected.has(key));
  if (allSelected) keys.forEach((key) => state.selected.delete(key));
  else keys.forEach((key) => state.selected.add(key));
  renderLibrary();
}

async function loadProfiles(page) {
  const filters = state.filters;
  const target = Math.max(1, Number(page || state.list.page || 1));
  try {
    const data = await apiGet("profiles", {
      query: filters.query,
      platform: filters.platform,
      chat_type: filters.chat_type,
      field: filters.field,
      sort: filters.sort,
      locked_only: filters.locked_only ? "1" : "0",
      page: target,
      page_size: state.list.page_size,
    });
    state.list = {
      items: data.items || [],
      total: Number(data.total || 0),
      page: Number(data.page || 1),
      page_size: Number(data.page_size || state.list.page_size),
      page_count: Number(data.page_count || 1),
    };
    const present = new Set(state.list.items.map((item) => item.key));
    renderLibrary();
    renderTabs();
    renderStatus();
    return present;
  } catch (err) {
    toast(errorText(err), "err");
    return null;
  }
}

async function deleteSelected() {
  const keys = Array.from(state.selected);
  if (!keys.length) return;
  const ok = window.confirm(
    "将永久删除 " + keys.length + " 条画像及其全部字段与备注。\n此操作不可撤销（删除前系统会保留每日快照备份）。\n确认继续？",
  );
  if (!ok) return;
  const data = await apiPost("profile-delete", { keys: keys });
  toast(data.message || "已删除", "ok");
  state.selected.clear();
  if (state.detail && keys.includes(state.detail.key)) closeDrawer();
  await Promise.all([loadProfiles(1), loadStats()]);
}

/* -------------------------------------------------------------- 画像详情抽屉 */

function closeDrawer() {
  state.detail = null;
  state.history = { field: "", items: [], loading: false, total: 0 };
  const drawer = $("pw-drawer");
  const mask = $("pw-mask");
  if (drawer) {
    drawer.hidden = true;
    clear(drawer);
  }
  if (mask) mask.hidden = true;
  renderLibrary();
}

async function openDetail(key) {
  try {
    const data = await apiGet("profile", { key: key });
    if (!state.detail || state.detail.key !== key) {
      state.history = { field: "", items: [], loading: false, total: 0 };
    }
    state.detail = data.profile || null;
    renderDrawer();
    renderLibrary();
  } catch (err) {
    toast(errorText(err), "err");
  }
}

async function refreshDetail(fromResponse) {
  if (fromResponse && fromResponse.profile) {
    state.detail = fromResponse.profile;
    renderDrawer();
    renderLibrary();
    return;
  }
  if (state.detail) await openDetail(state.detail.key);
}

/** 字段改动历史折叠面板（配合 state.history 使用）。 */
function fieldHistoryPanel(entry) {
  const hist = state.history;
  if (hist.loading) {
    return h(
      "div",
      { class: "pw-history" },
      h("div", { class: "pw-history-empty" }, h("span", { class: "pw-spinner" }), h("span", { text: "正在读取改动历史…" })),
    );
  }
  if (!hist.items.length) {
    return h(
      "div",
      { class: "pw-history" },
      h("div", { class: "pw-history-empty" }, icon("history"), h("span", { text: "没有找到该字段的审计记录（可能早于日志归档保留范围）。" })),
    );
  }
  return h(
    "div",
    { class: "pw-history" },
    h(
      "div",
      { class: "pw-history-head" },
      icon("history"),
      h("span", { text: "「" + entry.name + "」改动历史" }),
      h("span", { class: "pw-history-count mono", text: hist.items.length + " / " + hist.total }),
    ),
    h(
      "div",
      { class: "pw-history-list" },
      hist.items.map((row, idx) =>
        h(
          "div",
          { class: "pw-history-row" },
          h("span", { class: "pw-history-idx mono", text: String(idx + 1).padStart(2, "0") }),
          h(
            "div",
            { class: "pw-history-body" },
            h(
              "div",
              { class: "pw-history-val" },
              row.old_value ? h("del", { title: row.old_value, text: row.old_value }) : null,
              row.old_value && row.new_value ? h("span", { class: "pw-history-arrow", text: "→" }) : null,
              h("span", { title: row.new_value || "", text: row.new_value || "（已清空）" }),
            ),
            h("div", {
              class: "pw-history-meta mono",
              text:
                shortTime(row.at) +
                " · " +
                actionText(row.action) +
                " · " +
                sourceText(row.actor_type) +
                (row.actor_name ? "（" + row.actor_name + "）" : "") +
                (row.field_name === "*" ? " · 全量动作" : ""),
            }),
            row.evidence ? h("div", { class: "pw-history-evi", text: "依据：" + row.evidence }) : null,
          ),
        ),
      ),
    ),
  );
}

/** 拉取单字段改动历史（默认含归档日志，取最近 20 条）。 */
async function loadFieldHistory(fieldName) {
  const detail = state.detail;
  if (!detail) return;
  state.history = { field: fieldName, items: [], loading: true, total: 0 };
  renderDrawer();
  try {
    const data = await apiGet("field-history", {
      key: detail.key,
      field: fieldName,
      limit: 20,
      include_rotated: "1",
    });
    if (state.history.field !== fieldName) return;
    state.history = {
      field: fieldName,
      items: data.items || [],
      loading: false,
      total: Number(data.total || (data.items || []).length),
    };
  } catch (err) {
    state.history = { field: fieldName, items: [], loading: false, total: 0 };
    toast(errorText(err), "err");
  }
  renderDrawer();
}

function fieldRow(entry) {
  const detail = state.detail;
  const locked = Boolean(entry.locked);
  const editable = canEdit() && !locked;
  const historyOpen = state.history.field === entry.name;
  const input = h("input", {
    class: "pw-input",
    type: "text",
    value: Array.isArray(entry.value) ? entry.value.join(" | ") : String(entry.value ?? ""),
    maxlength: String((state.meta && state.meta.field_value_max_length) || 160),
    disabled: !editable ? true : null,
    title: locked ? "该字段已锁定，需先解锁才能改。" : null,
  });

  const save = async (event) => {
    const value = input.value.trim();
    if (!value) {
      toast("值不能为空；如需清除请点删除。", "warn");
      return;
    }
    await guard(event.currentTarget, async () => {
      const data = await apiPost("profile-field", { key: detail.key, field: entry.name, value: value });
      toast(data.message || "已保存", data.ok === false ? "err" : "ok");
      await refreshDetail(data);
      await loadStats();
    });
  };

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      save({ currentTarget: null });
    }
  });

  const remove = async (event) => {
    if (!window.confirm("确认删除字段「" + entry.name + "」？")) return;
    await guard(event.currentTarget, async () => {
      const data = await apiPost("profile-field-delete", { key: detail.key, field: entry.name });
      toast(data.message || "已删除", data.ok === false ? "err" : "ok");
      await refreshDetail(data);
      await loadStats();
    });
  };

  const toggleLock = async (event) => {
    await guard(event.currentTarget, async () => {
      const data = await apiPost("field-lock", {
        key: detail.key,
        field: entry.name,
        locked: locked ? "0" : "1",
      });
      toast(data.message || (locked ? "已解锁" : "已锁定"), data.ok === false ? "err" : "ok");
      await refreshDetail(data);
      await Promise.all([loadProfiles(state.list.page), loadStats()]);
    });
  };

  const toggleHistory = () => {
    if (historyOpen) {
      state.history = { field: "", items: [], loading: false, total: 0 };
      renderDrawer();
      return;
    }
    loadFieldHistory(entry.name);
  };

  return h(
    "div",
    { class: "pw-frow" + (locked ? " is-locked" : "") },
    h(
      "div",
      { class: "pw-frow-top" },
      h("span", { class: "pw-frow-name", text: entry.name }),
      locked
        ? h(
            "span",
            { class: "pw-pill pw-pill--lock", title: "已锁定：" + (state.detail && state.detail.field_lock_scope_label ? state.detail.field_lock_scope_label : "禁止自动覆写") },
            icon("lock", "pw-pill-icon"),
            h("span", { text: "已锁定" }),
          )
        : null,
      entry.is_custom ? h("span", { class: "pw-pill pw-pill--warn", text: "自定义" }) : null,
      entry.source_kind ? h("span", { class: "pw-pill pw-pill--mono", text: entry.source_kind }) : null,
      h(
        "div",
        { class: "pw-frow-tools" },
        iconBtn(
          "history",
          historyOpen ? "收起改动历史" : "查看改动历史",
          toggleHistory,
          historyOpen ? "pw-btn--accent" : "pw-btn--ghost",
        ),
        canEdit()
          ? iconBtn(
              locked ? "unlock" : "lock",
              locked ? "解锁：允许再次自动写入" : "锁定：保护该字段不被自动覆写",
              toggleLock,
              locked ? "pw-btn--lock is-on" : "pw-btn--lock",
            )
          : null,
        editable ? iconBtn("check", "保存修改", save, "pw-btn--accent") : null,
        canEdit() ? iconBtn("trash", "删除该字段", remove, "pw-btn--danger") : null,
      ),
    ),
    h("div", { class: "pw-frow-edit" }, input),
    h(
      "div",
      { class: "pw-frow-meta" },
      entry.description ? h("span", { text: "说明：" + entry.description }) : null,
      h("span", {
        text:
          "更新：" +
          (entry.updated_at || "—") +
          " · " +
          sourceText(entry.updated_by) +
          (entry.actor_name ? "（" + entry.actor_name + "）" : ""),
      }),
      entry.evidence ? h("span", { text: "原话依据：" + entry.evidence }) : null,
    ),
    historyOpen ? fieldHistoryPanel(entry) : null,
  );
}

function addFieldForm() {
  const detail = state.detail;
  const nameInput = h("input", { class: "pw-input", type: "text", placeholder: "字段名，如 咖啡口味" });
  const valueInput = h("input", { class: "pw-input pw-grow", type: "text", placeholder: "字段值" });
  const submit = async (event) => {
    const name = nameInput.value.trim();
    const value = valueInput.value.trim();
    if (!name || !value) {
      toast("字段名与值都要填。", "warn");
      return;
    }
    await guard(event.currentTarget, async () => {
      const data = await apiPost("profile-field", {
        key: detail.key,
        field: name,
        value: value,
        allow_custom_field: true,
      });
      toast(data.message || "已写入", data.ok === false ? "err" : "ok");
      if (data.ok !== false) {
        nameInput.value = "";
        valueInput.value = "";
      }
      await refreshDetail(data);
      await loadStats();
    });
  };
  return h(
    "div",
    { style: { display: "flex", gap: "8px", flexWrap: "wrap" } },
    nameInput,
    valueInput,
    textBtn("plus", "写入", submit, "pw-btn--accent"),
  );
}

function mergeForm() {
  const detail = state.detail;
  const options = [["", "选择要并入当前画像的来源…"]].concat(
    (state.list.items || [])
      .filter((item) => item.key !== detail.key)
      .map((item) => [item.key, (item.display_name || item.user_id) + " · " + item.key]),
  );
  const select = selectControl("", options, () => {}, { class: "pw-select pw-grow", title: "来源画像" });
  const dropSource = h("input", { type: "checkbox", checked: true });
  const submit = async (event) => {
    const source = select.value;
    if (!source) {
      toast("先选一个来源画像。", "warn");
      return;
    }
    if (!window.confirm("将「" + source + "」并入「" + detail.key + "」" + (dropSource.checked ? "，并删除来源画像" : "") + "。\n确认继续？")) return;
    await guard(event.currentTarget, async () => {
      const data = await apiPost("profile-merge", {
        source: source,
        target: detail.key,
        drop_source: dropSource.checked,
      });
      toast(data.message || "已合并", data.ok === false ? "err" : "ok");
      await refreshDetail(null);
      await Promise.all([loadProfiles(), loadStats()]);
    });
  };
  return h(
    "div",
    { style: { display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" } },
    select,
    h("label", { class: "pw-switch" }, dropSource, h("span", { text: "合并后删除来源" })),
    textBtn("merge", "合并", submit),
  );
}

function renderDrawer() {
  const drawer = $("pw-drawer");
  const mask = $("pw-mask");
  const detail = state.detail;
  if (!drawer || !mask) return;
  if (!detail) {
    closeDrawer();
    return;
  }
  mask.hidden = false;
  mask.onclick = closeDrawer;
  drawer.hidden = false;

  const head = h(
    "div",
    { class: "pw-drawer-head" },
    h("div", { class: "pw-avatar", text: initials(detail.display_name, detail.user_id) }),
    h(
      "div",
      { style: { minWidth: "0", flex: "1 1 auto" } },
      h("h2", { class: "pw-card-title", id: "pw-drawer-title", text: detail.display_name || detail.user_id }),
      h("div", { class: "pw-pcard-id mono", title: detail.key, text: detail.key }),
    ),
    iconBtn("close", "关闭详情", closeDrawer),
  );

  const builtinAvail = (detail.available_fields || []).filter((item) => !item.is_custom);
  const filledBuiltin = builtinAvail.filter((item) => item.filled).length;
  const basics = h(
    "div",
    null,
    h("div", { class: "pw-section-label", text: "IDENTITY" }),
    h(
      "div",
      { style: { marginBottom: "12px" } },
      completenessBar(detail.completeness, {
        label: "完整度",
        hint: builtinAvail.length ? filledBuiltin + " / " + builtinAvail.length + " 项内置字段已填" : "",
      }),
    ),
    kv([
      ["用户 ID", detail.user_id],
      ["昵称", detail.subject_name || "—"],
      ["会话", detail.session_id || "（全局画像）"],
      ["平台 / 类型", (detail.platform || "unknown") + " · " + chatTypeText(detail.chat_type)],
      [
        "锁定字段",
        detail.locked_count
          ? detail.locked_count + " 个 · " + (detail.locked_fields || []).join("、")
          : "无",
      ],
      ["字段锁范围", detail.field_lock_scope_label || (state.meta && state.meta.field_lock_scope_label) || "—"],
      ["建档时间", detail.created_at || "—"],
      ["最近更新", (detail.updated_at || "—") + (detail.updated_at ? "（" + relTime(detail.updated_at) + "）" : "")],
    ]),
  );

  const fields = h(
    "div",
    null,
    h(
      "div",
      { class: "pw-section-label" },
      h("span", { text: "FIELDS · " + (detail.fields || []).length }),
      detail.locked_count
        ? h(
            "span",
            { class: "pw-pill pw-pill--lock" },
            icon("lock", "pw-pill-icon"),
            h("span", { text: detail.locked_count + " 锁定" }),
          )
        : null,
    ),
    (detail.fields || []).length
      ? (detail.fields || []).map((entry) => fieldRow(entry))
      : notice("这条画像还没有任何字段。", null, "ghost"),
    canEdit() ? h("div", { style: { marginTop: "12px" } }, addFieldForm()) : null,
  );

  const notes = h(
    "div",
    null,
    h("div", { class: "pw-section-label" }, h("span", { text: "NOTES · " + (detail.notes || []).length })),
    (detail.notes || []).length
      ? (detail.notes || []).map((note, index) =>
          h(
            "div",
            { class: "pw-note" },
            h("span", { class: "pw-note-idx", text: "#" + (index + 1) }),
            h("span", { text: String(note) }),
          ),
        )
      : notice("暂无备注。备注由「记住 …」这类指令或 LLM 提取写入。", null, "ghost"),
    (detail.notes_meta && detail.notes_meta.updated_at)
      ? h("div", { class: "pw-frow-meta" }, h("span", { text: "最近备注更新：" + detail.notes_meta.updated_at + " · " + sourceText(detail.notes_meta.updated_by) }))
      : null,
  );

  const summary = h(
    "div",
    null,
    h("div", { class: "pw-section-label", text: "INJECTED SUMMARY" }),
    h("textarea", { class: "pw-input", readonly: true, rows: "8", text: detail.summary || "（空）" }),
    h("div", { class: "pw-frow-meta" }, h("span", { text: "这就是注入给模型的画像文本，可据此判断人格提示是否合理。" })),
  );

  const tools = canEdit()
    ? h(
        "div",
        null,
        h("div", { class: "pw-section-label", text: "MERGE" }),
        mergeForm(),
        h("div", { class: "pw-frow-meta", style: { marginTop: "8px" } }, h("span", { text: "合并会保留双方字段，冲突时以目标画像（当前这条）为准。" })),
      )
    : null;

  const foot = h(
    "div",
    { class: "pw-drawer-foot" },
    textBtn("download", "导出这条", (event) =>
      guard(event.currentTarget, () => exportBundle({ keys: [detail.key], filename: "profile-" + detail.user_id })),
    ),
    textBtn("link", "复制 Key", async () => {
      try {
        await navigator.clipboard.writeText(detail.key);
        toast("已复制会话键。", "ok");
      } catch (err) {
        toast("复制失败，请手动选择文本。", "warn");
      }
    }),
    h("span", { style: { marginLeft: "auto" } }),
    textBtn(
      "trash",
      "删除整条画像",
      async (event) => {
        if (!window.confirm("将永久删除「" + (detail.display_name || detail.user_id) + "」的整条画像。\n确认继续？")) return;
        await guard(event.currentTarget, async () => {
          const data = await apiPost("profile-delete", { keys: [detail.key] });
          toast(data.message || "已删除", "ok");
          closeDrawer();
          await Promise.all([loadProfiles(), loadStats()]);
        });
      },
      "pw-btn--danger",
      !canEdit(),
    ),
  );

  fill(drawer, head, h("div", { class: "pw-drawer-body" }, basics, fields, notes, summary, tools), foot);
}

/* -------------------------------------------------------------------- 审计 */

function renderAudit() {
  const host = $("pw-panel-audit");
  if (!host) return;
  const meta = state.meta || {};
  const filters = state.auditFilters;

  const searchInput = h("input", {
    class: "pw-input pw-grow",
    type: "search",
    placeholder: "搜索操作者 / 字段 / 值 / 依据…",
    value: filters.query,
    oninput: (event) => {
      filters.query = event.target.value;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => loadAudit(0), 320);
    },
  });

  const toolbar = h(
    "div",
    { class: "pw-toolbar" },
    h("label", { class: "pw-field pw-grow" }, icon("search"), searchInput),
    selectControl(
      filters.action,
      [["", "全部动作"]].concat((meta.audit_actions || []).map((item) => [item, actionText(item)])),
      (value) => {
        filters.action = value;
        loadAudit(0);
      },
      { title: "动作类型" },
    ),
    selectControl(
      filters.actor_type,
      [["", "全部来源"]].concat((meta.actor_types || []).map((item) => [item.id, item.label])),
      (value) => {
        filters.actor_type = value;
        loadAudit(0);
      },
      { title: "操作者类型" },
    ),
    h("input", {
      class: "pw-input",
      type: "text",
      placeholder: "指定用户 ID",
      value: filters.user_id,
      oninput: (event) => {
        filters.user_id = event.target.value.trim();
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => loadAudit(0), 360);
      },
    }),
    switchControl(
      filters.include_rotated,
      "含归档日志",
      (checked) => {
        filters.include_rotated = checked;
        loadAudit(0);
      },
      "把已轮转的 audit.log.1 … 一起纳入检索（数据量大时会略慢）",
    ),
    h(
      "div",
      { class: "pw-toolbar-tail" },
      selectControl(
        String(state.audit.limit),
        [["50", "50 条"], ["100", "100 条"], ["200", "200 条"], ["500", "500 条"]],
        (value) => {
          state.audit.limit = Number(value) || 50;
          loadAudit(0);
        },
        { title: "每页条数" },
      ),
      textBtn("sheet", "导出 CSV", (event) => guard(event.currentTarget, exportAuditCsv), "pw-btn--ghost"),
      iconBtn("refresh", "重新载入审计", (event) => guard(event.currentTarget, () => loadAudit())),
    ),
  );

  const rows = state.audit.items || [];
  const table = rows.length
    ? h(
        "div",
        { class: "pw-table-wrap" },
        h(
          "table",
          { class: "pw-table" },
          h(
            "thead",
            null,
            h(
              "tr",
              null,
              ["时间", "动作", "对象", "字段", "旧值 → 新值", "操作者", "依据"].map((label) =>
                h("th", { text: label }),
              ),
            ),
          ),
          h(
            "tbody",
            null,
            rows.map((row) =>
              h(
                "tr",
                null,
                h("td", { class: "nowrap mono", text: row.at || "—" }),
                h("td", { class: "nowrap" }, h("span", { class: "pw-pill pw-pill--accent", text: actionText(row.action) })),
                h(
                  "td",
                  { class: "clip", title: (row.subject_name || "") + " " + (row.subject_user_id || "") },
                  h("div", { text: row.subject_name || "—" }),
                  h("div", { class: "mono", style: { fontSize: "11px", opacity: "0.7" }, text: row.subject_user_id || "" }),
                ),
                h("td", { class: "nowrap", text: row.field_name || "—" }),
                h(
                  "td",
                  { class: "clip", title: (row.old_value || "") + " → " + (row.new_value || "") },
                  h("span", { style: { opacity: "0.6" }, text: row.old_value || "（空）" }),
                  h("span", { text: " → " }),
                  h("span", { text: row.new_value || "（空）" }),
                ),
                h(
                  "td",
                  { class: "nowrap" },
                  h("div", { text: sourceText(row.actor_type) }),
                  h("div", { class: "mono", style: { fontSize: "11px", opacity: "0.7" }, text: row.actor_name || row.actor_id || "" }),
                ),
                h("td", { class: "clip", title: row.evidence || "", text: row.evidence || "—" }),
              ),
            ),
          ),
        ),
      )
    : emptyState("暂无审计记录", "每次字段写入、删除、合并、导入都会在这里留痕。", "history");

  const pager = h(
    "div",
    { class: "pw-pager" },
    textBtn(null, "较新", () => loadAudit(Math.max(0, state.audit.offset - state.audit.limit)), null, state.audit.offset <= 0),
    h("span", null, "第 "),
    h("span", { class: "mono", text: String(state.audit.offset + 1) }),
    h("span", null, " – "),
    h("span", { class: "mono", text: String(Math.min(state.audit.total, state.audit.offset + rows.length)) }),
    h("span", null, " 条 / 共 "),
    h("span", { class: "mono", text: fmtNum(state.audit.total) }),
    textBtn(
      null,
      "更早",
      () => loadAudit(state.audit.offset + state.audit.limit),
      null,
      state.audit.offset + state.audit.limit >= state.audit.total,
    ),
  );

  fill(host, toolbar, table, rows.length ? pager : null);
}

/** 按当前审计筛选条件导出 CSV（Excel 友好，带 BOM，由后端生成）。 */
async function exportAuditCsv() {
  const filters = state.auditFilters;
  const stamp = new Date().toISOString().slice(0, 19).replace(/[-:]/g, "").replace("T", "-");
  const filename = "profileweaver-audit-" + stamp + ".csv";
  await bridge.download(
    "audit-csv",
    {
      query: filters.query,
      action: filters.action,
      actor_type: filters.actor_type,
      user_id: filters.user_id,
      include_rotated: filters.include_rotated ? "1" : "0",
      limit: 5000,
    },
    filename,
  );
  toast("已开始下载 " + filename + "（最多 5000 条，按当前筛选）", "ok");
}

async function loadAudit(offset) {
  const filters = state.auditFilters;
  try {
    const data = await apiGet("audit", {
      query: filters.query,
      action: filters.action,
      actor_type: filters.actor_type,
      user_id: filters.user_id,
      include_rotated: filters.include_rotated ? "1" : "0",
      limit: state.audit.limit,
      offset: offset === undefined || offset === null ? state.audit.offset : Math.max(0, offset),
    });
    state.audit = {
      items: data.items || [],
      total: Number(data.total || 0),
      offset: Number(data.offset || 0),
      limit: Number(data.limit || state.audit.limit),
    };
    renderAudit();
    renderTabs();
    renderStatus();
  } catch (err) {
    toast(errorText(err), "err");
  }
}

/* -------------------------------------------------------------------- 迁移 */

async function exportBundle(options) {
  const opts = options || {};
  const keys = opts.keys || (opts.selectionOnly ? Array.from(state.selected) : null);
  if (opts.selectionOnly && (!keys || !keys.length)) {
    toast("先勾选要导出的画像。", "warn");
    return;
  }
  const params = {
    include_audit: state.exportOptions.include_audit ? "1" : "0",
    mask: state.exportOptions.mask ? "1" : "0",
  };
  if (keys && keys.length) params.keys = keys.join("|");
  const stamp = new Date().toISOString().slice(0, 19).replace(/[-:]/g, "").replace("T", "-");
  const filename = (opts.filename || "profileweaver-" + stamp) + ".json";
  await bridge.download("export", params, filename);
  toast("已开始下载 " + filename, "ok");
}

function renderMigrate() {
  const host = $("pw-panel-migrate");
  if (!host) return;
  const meta = state.meta || {};

  const includeAudit = h("input", { type: "checkbox", checked: state.exportOptions.include_audit ? true : null });
  includeAudit.onchange = () => {
    state.exportOptions.include_audit = includeAudit.checked;
  };
  const maskIds = h("input", { type: "checkbox", checked: state.exportOptions.mask ? true : null });
  maskIds.onchange = () => {
    state.exportOptions.mask = maskIds.checked;
  };

  const exportCard = card(
    "EXPORT",
    "导出数据包",
    { desc: "导出为 " + (meta.bundle_format || "profileweaver.bundle") + " v" + (meta.bundle_version || 2) + " 格式的 JSON，可跨机器、跨 AstrBot 实例迁移。" },
    h(
      "div",
      { style: { display: "flex", flexDirection: "column", gap: "12px" } },
      h("label", { class: "pw-switch" }, includeAudit, h("span", { text: "同时导出最近 500 条审计记录" })),
      h("label", { class: "pw-switch" }, maskIds, h("span", { text: "脱敏用户 ID（仅供分享排查，导出后不可再导入）" })),
      h(
        "div",
        { style: { display: "flex", gap: "9px", flexWrap: "wrap" } },
        textBtn("download", "导出全部画像", (event) => guard(event.currentTarget, () => exportBundle({})), "pw-btn--accent"),
        textBtn(
          "download",
          "仅导出已勾选（" + state.selected.size + "）",
          (event) => guard(event.currentTarget, () => exportBundle({ selectionOnly: true })),
          null,
          state.selected.size === 0,
        ),
      ),
      state.exportOptions.mask
        ? notice("脱敏包里用户 ID 已被不可逆哈希，导入接口会直接拒绝这类文件。请另外保留一份未脱敏备份。", "warn", "shield")
        : null,
    ),
  );

  const modeSelect = selectControl(
    state.importMode,
    [
      ["merge", "合并（推荐）：同一用户逐字段智能合并，保留较新值"],
      ["overwrite", "覆盖：同 key 整条替换，其余保留"],
      ["replace", "重建：清空现有画像后完全使用文件内容"],
    ],
    (value) => {
      state.importMode = value;
      renderMigrate();
    },
    { class: "pw-select pw-grow", title: "导入模式" },
  );

  const fileInput = h("input", {
    class: "pw-input pw-grow",
    type: "file",
    accept: ".json,application/json",
    disabled: !canEdit() ? true : null,
  });

  const doImport = async (event) => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) {
      toast("先选择一个导出的 JSON 文件。", "warn");
      return;
    }
    if (state.importMode === "replace" && !window.confirm("「重建」会清空当前全部画像，只保留文件里的内容。\n系统会先自动生成一份 pre-import 备份。\n确认继续？")) return;
    await guard(event.currentTarget, async () => {
      let raw;
      try {
        raw = await bridge.upload("import?mode=" + encodeURIComponent(state.importMode), file);
      } catch (err) {
        throw new Error(errorText(err));
      }
      const data = unwrap(raw) || {};
      toast(data.message || (data.ok === false ? "导入失败" : "导入完成"), data.ok === false ? "err" : "ok");
      if (data.ok !== false) {
        fileInput.value = "";
        await Promise.all([loadProfiles(1), loadStats(), loadBackups(), loadAudit(0)]);
      }
    });
  };

  const importCard = card(
    "IMPORT",
    "导入数据包",
    { desc: "支持本插件导出的数据包，也能直接吃下裸 profiles.json。导入前会自动生成一份 pre-import 备份。" },
    h(
      "div",
      { style: { display: "flex", flexDirection: "column", gap: "12px" } },
      modeSelect,
      h("div", { style: { display: "flex", gap: "9px", flexWrap: "wrap", alignItems: "center" } }, fileInput, textBtn("upload", "开始导入", doImport, "pw-btn--accent", !canEdit())),
      state.importMode === "replace"
        ? notice("「重建」是破坏性操作：文件里没有的画像会被删除。请确认文件完整。", "danger", "shield")
        : null,
      canEdit() ? null : notice("只读模式下无法导入。", "warn", "lock"),
    ),
  );

  const backups = state.backups || [];
  const backupCard = card(
    "BACKUPS",
    "本地快照",
    {
      desc:
        "插件每天首次写入时自动快照一次，导入/恢复前也会额外快照，文件放在数据目录的 backups/ 下。保留策略：最多 " +
        (meta.backup_max_count ? meta.backup_max_count + " 份" : "不限份数") +
        " · " +
        (meta.backup_retention_days ? meta.backup_retention_days + " 天内" : "不按天清理") +
        "。",
      tools: [
        h("span", { class: "pw-pill pw-pill--mono", text: backups.length + " 份" }),
        iconBtn("refresh", "刷新备份列表", (event) => guard(event.currentTarget, () => loadBackups())),
      ],
    },
    h(
      "div",
      { style: { display: "flex", flexDirection: "column", gap: "12px" } },
      h(
        "div",
        { style: { display: "flex", gap: "9px", flexWrap: "wrap" } },
        textBtn(
          "archive",
          "立即创建备份",
          (event) =>
            guard(event.currentTarget, async () => {
              const data = await apiPost("backup-create", { tag: "manual" });
              toast(data.message || "已备份", "ok");
              state.backups = data.items || state.backups;
              renderMigrate();
            }),
          "pw-btn--accent",
          !canEdit(),
        ),
      ),
      backups.length
        ? h(
            "div",
            { class: "pw-table-wrap" },
            h(
              "table",
              { class: "pw-table", style: { minWidth: "520px" } },
              h("thead", null, h("tr", null, ["文件名", "大小", "创建时间", ""].map((label) => h("th", { text: label })))),
              h(
                "tbody",
                null,
                backups.map((item) =>
                  h(
                    "tr",
                    null,
                    h("td", { class: "mono", text: item.name }),
                    h("td", { class: "nowrap mono", text: fmtBytes(item.size) }),
                    h("td", { class: "nowrap mono", text: item.modified_at }),
                    h(
                      "td",
                      { class: "nowrap" },
                      h(
                        "div",
                        { style: { display: "flex", gap: "6px", justifyContent: "flex-end" } },
                        textBtn(
                          "download",
                          "下载",
                          (event) =>
                            guard(event.currentTarget, async () => {
                              await bridge.download("backup-download", { name: item.name }, item.name);
                              toast("已开始下载 " + item.name, "ok");
                            }),
                          "pw-btn--ghost",
                        ),
                        textBtn(
                          "history",
                          "恢复",
                          async (event) => {
                            if (!window.confirm("将用「" + item.name + "」覆盖当前全部画像。\n恢复前会自动备份当前状态。\n确认继续？")) return;
                            await guard(event.currentTarget, async () => {
                              const data = await apiPost("backup-restore", { name: item.name });
                              toast(data.message || "已恢复", data.ok === false ? "err" : "ok");
                              await Promise.all([loadProfiles(1), loadStats(), loadBackups()]);
                            });
                          },
                          "pw-btn--accent",
                          !canEdit(),
                        ),
                        textBtn(
                          "trash",
                          "删除",
                          async (event) => {
                            if (!window.confirm("将永久删除快照文件「" + item.name + "」，此操作不可撤销。\n确认继续？")) return;
                            await guard(event.currentTarget, async () => {
                              const data = await apiPost("backup-delete", { name: item.name });
                              toast(data.message || "已删除", data.ok === false ? "err" : "ok");
                              state.backups = data.items || state.backups;
                              renderMigrate();
                            });
                          },
                          "pw-btn--danger",
                          !canEdit(),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          )
        : emptyState("还没有快照", "点上面的「立即创建备份」，或等插件下一次自动快照。", "archive"),
    ),
  );

  fill(host, h("div", { class: "pw-grid pw-grid--2" }, exportCard, importCard), h("div", { class: "pw-grid", style: { marginTop: "var(--pw-gap)" } }, backupCard));
}

async function loadBackups() {
  try {
    const data = await apiGet("backups", {});
    state.backups = data.items || [];
    renderMigrate();
  } catch (err) {
    toast(errorText(err), "err");
  }
}

/* -------------------------------------------------------------------- 关于 */

function commandTable(rows) {
  if (!rows || !rows.length) return emptyState("没有可用指令", "指令列表由后端提供。", "info");
  return h(
    "div",
    { class: "pw-table-wrap" },
    h(
      "table",
      { class: "pw-table", style: { minWidth: "440px" } },
      h("thead", null, h("tr", null, ["指令", "说明"].map((label) => h("th", { text: label })))),
      h(
        "tbody",
        null,
        rows.map((row) =>
          h(
            "tr",
            null,
            h("td", { class: "mono nowrap", text: row.command || "" }),
            h("td", { text: row.desc || "" }),
          ),
        ),
      ),
    ),
  );
}

function renderAbout() {
  const host = $("pw-panel-about");
  if (!host) return;
  const meta = state.meta || {};
  const commands = meta.commands || {};

  const hero = h(
    "div",
    { class: "pw-hero" },
    h("span", { class: "pw-chip pw-chip--accent", text: meta.plugin || "astrbot_plugin_profile_weaver" }),
    h("span", { class: "pw-hero-name", text: meta.display_name || "心迹画像" }),
    h("span", { class: "pw-hero-sub", text: "· " + (meta.subtitle || "Profile Weaver") }),
    h("span", {
      class: "pw-hero-desc",
      text: "长期记忆型用户画像：聊天中自然浮现的偏好与约定被结构化沉淀，注入到人格提示里，并且每一次写入都留痕可查。",
    }),
    h(
      "div",
      { class: "pw-hero-tail" },
      h("span", { class: "pw-chip pw-chip--accent", text: "v" + (meta.version || "3.1.0") }),
      h("span", { class: "pw-chip", text: (meta.builtin_fields || []).length + " 内置字段" }),
      h("span", { class: "pw-chip", text: ((commands.user || []).length + (commands.admin || []).length) + " 条指令" }),
      h("span", { class: "pw-chip", text: ((meta.themes || []).length || 7) + " 套主题" }),
      meta.repo
        ? h(
            "a",
            { class: "pw-btn pw-btn--sm", href: meta.repo, target: "_blank", rel: "noreferrer noopener" },
            icon("link"),
            h("span", { text: "GitHub" }),
          )
        : null,
    ),
  );

  const securityCard = card(
    "SECURITY",
    "安全须知",
    { desc: "画像里可能包含相当私人的信息，部署前请把下面三点看完。" },
    h(
      "div",
      { style: { display: "flex", flexDirection: "column", gap: "10px" } },
      notice(
        "本页面的所有接口通过 register_web_api 注册，鉴权完全依赖 AstrBot Dashboard 自身的登录态，插件不做额外校验。请不要把 Dashboard 直接暴露到公网，建议只在内网或通过反向代理加认证后访问。",
        "danger",
        "lock",
      ),
      notice(
        "画像、审计日志与备份快照全部写在插件数据目录下（profiles.json / audit.log / backups/）。这些文件是明文 JSON，迁移与备份时请当作敏感数据对待；勾选「脱敏用户 ID」导出的包只能用于查看和统计，无法再导入。",
        "warn",
        "shield",
      ),
      notice(
        canEdit()
          ? "当前为可写模式：本面板可以增删改画像、合并档案、导入与恢复备份。若只想给他人查看，可在插件配置里关闭「WebUI 允许写操作」。"
          : "当前为只读模式：所有写操作接口都会返回 403。需要修改画像请先在插件配置里打开「WebUI 允许写操作」。",
        canEdit() ? null : "warn",
        canEdit() ? "eye" : "lock",
      ),
    ),
  );

  const userCard = card(
    "COMMANDS · USER",
    "用户指令",
    { desc: "任何用户都能对自己的画像使用的指令。" },
    commandTable(commands.user),
  );

  const adminCard = card(
    "COMMANDS · ADMIN",
    "管理员指令",
    { desc: "需要 AstrBot 管理员权限，作用于全部画像与存储。" },
    commandTable(commands.admin),
  );

  const fields = meta.builtin_fields || [];
  const fieldsCard = card(
    "FIELDS",
    "内置字段清单",
    {
      desc: "共 " + fields.length + " 个内置维度；字段说明会一并交给 LLM，用来判断某句话该写进哪一格。",
    },
    fields.length
      ? h(
          "div",
          { class: "pw-table-wrap" },
          h(
            "table",
            { class: "pw-table", style: { minWidth: "460px" } },
            h("thead", null, h("tr", null, ["字段", "含义"].map((label) => h("th", { text: label })))),
            h(
              "tbody",
              null,
              fields.map((item) =>
                h(
                  "tr",
                  null,
                  h("td", { class: "nowrap" }, h("span", { class: "pw-pill", text: item.name })),
                  h("td", { text: item.description || "" }),
                ),
              ),
            ),
          ),
        )
      : emptyState("字段列表为空", "检查插件配置里的「默认字段」。", "tag"),
  );

  const themes = meta.themes || [];
  const themesCard = card(
    "THEMES",
    "界面主题",
    { desc: "点一下即可切换，选择保存在浏览器本地；插件配置里的「WebUI 默认主题」决定首次打开时的样式。" },
    h(
      "div",
      { style: { display: "flex", flexWrap: "wrap", gap: "9px" } },
      themes.map((item) => {
        const current = document.documentElement.getAttribute("data-pw-theme") === item.id;
        return h(
          "button",
          {
            class: "pw-pill" + (current ? " pw-pill--accent" : ""),
            type: "button",
            title: "切换到「" + item.name + "」主题",
            style: { cursor: "pointer" },
            onclick: () => {
              applyTheme(item.id);
              renderAbout();
            },
          },
          h("span", {
            style: {
              width: "10px",
              height: "10px",
              borderRadius: "50%",
              background: item.accent,
              boxShadow: "0 0 0 2px rgba(255,255,255,.12)",
            },
          }),
          h("span", { text: item.name }),
          h("span", { class: "mono", text: item.id }),
        );
      }),
    ),
  );

  const runtimeCard = card(
    "RUNTIME",
    "当前配置快照",
    { desc: "只读展示；修改请到 AstrBot 插件配置页。" },
    kv([
      ["插件目录名", meta.plugin || "astrbot_plugin_profile_weaver"],
      ["版本", "v" + (meta.version || "3.1.0")],
      ["会话隔离", meta.session_based ? "开启" : "关闭"],
      ["LLM 函数工具", meta.llm_tools_enabled ? "开启" : "关闭"],
      ["被动提取", meta.proactive_extraction ? "开启" : "关闭"],
      ["群聊内查看画像", meta.allow_profile_in_group === false ? "禁止" : "允许"],
      ["身份严格校验", meta.strict_identity_guard === false ? "关闭" : "开启"],
      ["证据校验模式", meta.evidence_match_mode || "normalized"],
      ["LLM 自定义字段", meta.allow_llm_custom_fields === false ? "禁止" : "允许"],
      ["用户自定义字段", meta.allow_user_custom_fields === false ? "禁止" : "允许"],
      ["字段名长度上限", (meta.custom_field_name_max_length || 16) + " 字"],
      ["字段值长度上限", (meta.field_value_max_length || 160) + " 字"],
      ["备注上限", (meta.max_notes_count || 5) + " 条/人"],
      ["审计日志上限", (meta.audit_log_max_mb || 8) + " MB（超出自动轮转）"],
      ["归档日志保留", (meta.audit_log_keep_rotated || 0) + " 份（audit.log.1 …）"],
      ["备份保留", (meta.backup_retention_days ? meta.backup_retention_days + " 天" : "不按天清理") + " · 最多 " + (meta.backup_max_count ? meta.backup_max_count + " 份" : "不限")],
      ["字段锁范围", (meta.field_lock_scope_label || "—") + "（" + (meta.field_lock_scope || "llm_only") + "）"],
      ["新内置字段自动补齐", meta.auto_adopt_new_builtin_fields === false ? "关闭" : "开启"],
      ["迁移包格式", (meta.bundle_format || "profileweaver.bundle") + " v" + (meta.bundle_version || 2)],
      ["服务器时间", meta.server_time || "—"],
    ]),
  );

  const flowCard = card(
    "HOW IT WORKS",
    "画像是怎么长出来的",
    { desc: "三条写入路径，共用同一套校验与审计。" },
    h(
      "div",
      { style: { display: "flex", flexDirection: "column", gap: "12px" } },
      kv([
        ["① 用户主动写", "用户用「记住 字段 内容」自己填，来源记为 user，最可信。"],
        ["② LLM 函数工具", "对话中模型判断值得长期记住时调用工具写入，来源记为 llm。"],
        ["③ 被动提取", "对话结束后异步扫一遍消息，命中则补写，来源记为 auto。"],
        ["证据校验", "②③ 必须附带原话作为 evidence，且要能在本轮消息里匹配上，否则拒写。"],
        ["注入", "每次回复前把画像渲染进系统提示；画像为空时使用精简模板，避免污染人格。"],
        ["留痕", "所有写入 / 删除 / 合并 / 导入 / 恢复都会追加一行审计，可在「审计」页倒查。"],
      ]),
      notice(
        "如果发现模型乱写，优先收紧「证据校验模式」到 strict、关闭自定义字段，或把敏感字段加进「LLM 禁写字段」。",
        null,
        "bolt",
      ),
    ),
  );

  const lockScopes = meta.field_lock_scopes || [];
  const lockCard = card(
    "FIELD LOCK",
    "字段锁怎么用",
    { desc: "锁住的字段不再被自动写入覆盖，适合「已经核对过、不希望模型再改」的关键信息。" },
    h(
      "div",
      { style: { display: "flex", flexDirection: "column", gap: "12px" } },
      lockScopes.length
        ? h(
            "div",
            { style: { display: "flex", flexWrap: "wrap", gap: "9px" } },
            lockScopes.map((item) =>
              h(
                "span",
                {
                  class: "pw-pill" + (item.id === meta.field_lock_scope ? " pw-pill--accent" : ""),
                  title: item.id === meta.field_lock_scope ? "当前生效的范围" : "可在插件配置里切换到这一档",
                },
                icon(item.id === meta.field_lock_scope ? "check" : "lock", "pw-pill-icon"),
                h("span", { text: item.label }),
                h("span", { class: "mono", text: item.id }),
              ),
            ),
          )
        : null,
      kv([
        ["llm_only", "只挡 LLM 函数工具与被动提取；用户 / 管理员指令与本面板仍可改。"],
        ["llm_and_user", "再挡用户自己的「记住 …」；管理员指令与本面板仍可改。"],
        ["strict", "除了解锁本身，任何路径都不能再写这个字段。"],
      ]),
      notice(
        "锁定 / 解锁：字段行右侧的锁形按钮，或用指令「锁定画像 字段」「解锁画像 字段」（管理员用「锁定用户画像」）。每次开关都会写一行审计。",
        null,
        "lock",
      ),
      notice(
        "注意：整条清空（清除我的画像 / 清除用户画像）与删除整条画像不受字段锁保护——锁只针对单字段写入。",
        "warn",
        "shield",
      ),
    ),
  );

  fill(
    host,
    hero,
    h("div", { class: "pw-grid pw-grid--2" }, securityCard, runtimeCard),
    h("div", { class: "pw-grid pw-grid--2", style: { marginTop: "var(--pw-gap)" } }, userCard, adminCard),
    h(
      "div",
      { class: "pw-grid pw-grid--2", style: { marginTop: "var(--pw-gap)" } },
      h("div", { class: "pw-grid" }, fieldsCard, lockCard),
      h("div", { class: "pw-grid" }, flowCard, themesCard),
    ),
  );
}

/* ------------------------------------------------------------ 数据装载与启动 */

async function loadMeta() {
  const data = await apiGet("meta", {});
  state.meta = data;
  renderHeader();
  return data;
}

async function loadStats() {
  try {
    const data = await apiGet("stats", {});
    state.stats = data.stats || {};
    state.coverage = data.coverage || [];
    state.customFields = data.custom_fields || [];
    renderOverview();
    renderStatus();
  } catch (err) {
    toast(errorText(err), "err");
  }
}

async function refreshAll() {
  await loadMeta();
  buildThemeSelect();
  applyTheme(readStore(LS_THEME, state.meta.default_theme || "aurora"));
  const jobs = [loadStats()];
  if (state.tab === "library" || state.list.items.length) jobs.push(loadProfiles(state.list.page || 1));
  if (state.tab === "audit" || state.audit.items.length) jobs.push(loadAudit(state.audit.offset || 0));
  if (state.tab === "migrate" || state.backups.length) jobs.push(loadBackups());
  await Promise.all(jobs);
  renderAbout();
  renderTabs();
  renderStatus();
  toast("已刷新", "ok");
}

function renderAll() {
  renderHeader();
  renderTabs();
  renderOverview();
  renderLibrary();
  renderAudit();
  renderMigrate();
  renderAbout();
  renderStatus();
}

function bindChrome() {
  const refresh = $("pw-refresh");
  if (refresh) {
    fill(refresh, icon("refresh"));
    refresh.onclick = (event) => guard(event.currentTarget, () => refreshAll());
  }

  const density = $("pw-density");
  if (density) {
    density.onclick = () => {
      const now = document.documentElement.getAttribute("data-pw-density");
      applyDensity(now === "compact" ? "cozy" : "compact");
    };
  }

  const quickExport = $("pw-quick-export");
  if (quickExport) {
    fill(quickExport, icon("download"), h("span", { text: "导出" }));
    quickExport.onclick = (event) => guard(event.currentTarget, () => exportBundle({}));
  }

  const mask = $("pw-mask");
  if (mask) mask.onclick = () => closeDrawer();

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      const drawer = $("pw-drawer");
      if (drawer && !drawer.hidden) {
        event.preventDefault();
        closeDrawer();
      }
      return;
    }
    if (event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey) {
      const tag = (event.target && event.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      const panel = $("pw-panel-library");
      if (state.tab !== "library") switchTab("library");
      const input = panel && panel.querySelector("input[type=search]");
      if (input) {
        event.preventDefault();
        input.focus();
        input.select();
      }
    }
  });
}

function fatal(message) {
  const host = $("pw-panel-overview");
  if (host) {
    fill(
      host,
      card(
        "ERROR",
        "面板无法启动",
        { desc: "前端没能拿到后端数据，画像本体不受影响。" },
        h(
          "div",
          { style: { display: "flex", flexDirection: "column", gap: "10px" } },
          notice(message, "danger", "close"),
          notice(
            "常见原因：插件配置里关闭了「启用 WebUI 管理面板」（关闭时不会注册接口）、插件刚更新还没重载、或者当前 AstrBot 版本不支持插件 Page。重载插件后刷新本页再试。",
            "warn",
            "info",
          ),
          textBtn("refresh", "重新尝试", (event) => guard(event.currentTarget, () => boot()), "pw-btn--accent"),
        ),
      ),
    );
  }
  const left = $("pw-status-left");
  if (left) fill(left, h("span", { text: "启动失败：" + message }));
}

async function boot() {
  if (!bridge) {
    fatal("未找到 AstrBot 插件页面 Bridge（window.AstrBotPluginPage），请在 AstrBot Dashboard 的插件页面中打开本面板。");
    return;
  }
  try {
    state.ctx = await bridge.ready();
  } catch (err) {
    state.ctx = null;
  }

  applyDensity(readStore(LS_DENSITY, "cozy"));

  try {
    await loadMeta();
  } catch (err) {
    fatal(errorText(err));
    return;
  }

  buildThemeSelect();
  applyTheme(readStore(LS_THEME, state.meta.default_theme || "aurora"));
  bindChrome();
  renderAll();
  switchTab(readStore(LS_TAB, "overview"));
  state.ready = true;

  await Promise.all([loadStats(), loadProfiles(1), loadBackups()]);
  renderTabs();
  renderStatus();

  if (bridge.onContextChange) {
    bridge.onContextChange((ctx) => {
      state.ctx = ctx || state.ctx;
      renderAll();
    });
  }
}

boot();
