/**
 * Sentinel Studio — app.js
 * Full SPA logic: auth, navigation, Table Editor, SQL, Users, Logs, API Docs, Settings
 */
'use strict';

// ── Config ────────────────────────────────────────────────────────────────
const BASE = (window.SENTINEL_CONFIG || {}).GATEWAY_URL || 'http://localhost:8010';

// ── State ─────────────────────────────────────────────────────────────────
let _token = localStorage.getItem('sentinel:studio:token') || null;
let _user  = null;
try { _user = JSON.parse(localStorage.getItem('sentinel:studio:user') || 'null'); } catch(_) {}
let _currentTable  = null;
let _tableColumns  = {};  // table -> [{column_name, data_type, ...}]
let _allTables     = [];  // [{table_name, column_count}]
let _usersRaw      = [];  // raw user list for search
let _currentView   = 'overview';

// ── HTTP ──────────────────────────────────────────────────────────────────
async function api(method, path, body, opts = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (_token) headers['Authorization'] = `Bearer ${_token}`;
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    ...opts,
  });
  const json = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data: json };
}

async function apiGet(path)          { return api('GET', path); }
async function apiPost(path, body)   { return api('POST', path, body); }
async function apiPatch(path, body)  { return api('PATCH', path, body); }
async function apiDelete(path)       { return api('DELETE', path); }

// ── Toast ─────────────────────────────────────────────────────────────────
function toast(msg, type = 'info', duration = 3500) {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.getElementById('toastContainer').appendChild(el);
  setTimeout(() => el.remove(), duration);
}

// ── Auth helpers ──────────────────────────────────────────────────────────
function saveSession(accessToken, user) {
  _token = accessToken;
  _user  = user;
  localStorage.setItem('sentinel:studio:token', accessToken);
  localStorage.setItem('sentinel:studio:user', JSON.stringify(user));
}

function clearSession() {
  _token = null; _user = null;
  localStorage.removeItem('sentinel:studio:token');
  localStorage.removeItem('sentinel:studio:user');
}

function isLoggedIn() { return !!_token; }

// ── Navigation ────────────────────────────────────────────────────────────
function showView(name) {
  _currentView = name;
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const view = document.getElementById(`view-${name}`);
  const navBtn = document.getElementById(`nav-${name}`);
  if (view)   view.classList.add('active');
  if (navBtn) navBtn.classList.add('active');

  // Lazy-load data when switching views
  if (name === 'overview') loadOverview();
  if (name === 'editor')   initTableEditor();
  if (name === 'users')    loadUsers();
  if (name === 'logs')     loadLogs();
  if (name === 'apidocs')  initApiDocs();
  if (name === 'settings') populateSettings();
}

// ── Render helpers ────────────────────────────────────────────────────────
function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('en-GB', { day:'numeric', month:'short' }) +
    ' ' + d.toLocaleTimeString('en-GB', { hour:'2-digit', minute:'2-digit' });
}

function statusBadge(status) {
  const cls = { success: 'badge-success', failed: 'badge-danger', blocked: 'badge-warn', ignored: 'badge', conflict: 'badge-warn' };
  return `<span class="badge ${cls[status] || ''}">${status}</span>`;
}

function verifiedBadge(v) {
  return v ? '<span class="badge badge-success">✓ verified</span>' : '<span class="badge badge-warn">unverified</span>';
}

function roleBadge(role) {
  if (role === 'super_admin') return '<span class="badge badge-danger">super_admin</span>';
  if (role === 'admin')       return '<span class="badge badge-warn">admin</span>';
  return `<span class="badge">${role}</span>`;
}

// ── Login / Signup ────────────────────────────────────────────────────────
function showLoginScreen() {
  document.getElementById('studioApp').classList.add('hidden');
  document.getElementById('loginScreen').classList.remove('hidden');
  document.getElementById('loginCard') && document.getElementById('loginCard').classList.remove('hidden');
}

function showApp() {
  document.getElementById('loginScreen').classList.add('hidden');
  document.getElementById('studioApp').classList.remove('hidden');
  document.getElementById('sideProjectName').textContent = _user?.name || _user?.email || '—';
  document.getElementById('sideProjectSlug').textContent = _user?.tenant_slug || '—';
  showView('overview');
}

// Login form
document.getElementById('loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = document.getElementById('loginBtn');
  btn.disabled = true;
  document.querySelector('#loginBtn .btn-spinner').classList.remove('hidden');
  const errEl = document.getElementById('loginError');
  errEl.classList.add('hidden');

  const tenantSlug = document.getElementById('loginTenant').value.trim() || 'default';
  const email    = document.getElementById('loginEmail').value.trim();
  const password = document.getElementById('loginPassword').value;

  const { ok, data } = await apiPost(`/auth/${tenantSlug}/login`, { email, password });
  btn.disabled = false;
  document.querySelector('#loginBtn .btn-spinner').classList.add('hidden');

  if (!ok) {
    errEl.textContent = data?.detail || 'Invalid credentials';
    errEl.classList.remove('hidden');
    return;
  }

  saveSession(data.access_token, { ...data.user, tenant_slug: tenantSlug });
  showApp();
});

// Show signup
document.getElementById('showSignupBtn').addEventListener('click', () => {
  document.querySelectorAll('.login-card').forEach(c => c.classList.add('hidden'));
  document.getElementById('signupCard').classList.remove('hidden');
});
document.getElementById('showLoginBtn').addEventListener('click', () => {
  document.querySelectorAll('.login-card').forEach(c => c.classList.add('hidden'));
  document.getElementById('loginForm').closest('.login-card').classList.remove('hidden');
});

// Signup form
document.getElementById('signupForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const errEl = document.getElementById('signupError');
  const okEl  = document.getElementById('signupSuccess');
  errEl.classList.add('hidden'); okEl.classList.add('hidden');

  const { ok, data } = await apiPost('/auth/onboard', {
    startup_name:      document.getElementById('startupName').value.trim(),
    startup_slug:      document.getElementById('startupSlug').value.trim(),
    founder_name:      document.getElementById('founderName').value.trim(),
    founder_email:     document.getElementById('founderEmail').value.trim(),
    founder_password:  document.getElementById('founderPassword').value,
  });

  if (!ok) {
    errEl.textContent = data?.detail || 'Error creating project';
    errEl.classList.remove('hidden');
    return;
  }

  let msg = `Project created! Check your email to verify your account, then sign in.`;
  if (data.verification_token) {
    msg = `Project created! Verify with token: ${data.verification_token}`;
  }
  okEl.textContent = msg;
  okEl.classList.remove('hidden');
});

// Sign out
document.getElementById('signOutBtn').addEventListener('click', async () => {
  const refreshToken = localStorage.getItem('sentinel:refresh_token');
  if (refreshToken) {
    await apiPost('/auth/logout', { refresh_token: refreshToken }).catch(() => {});
  }
  clearSession();
  showLoginScreen();
  toast('Signed out', 'info');
});

// Nav buttons
document.querySelectorAll('.nav-item[data-view]').forEach(btn => {
  btn.addEventListener('click', () => showView(btn.dataset.view));
});

// ── Overview ──────────────────────────────────────────────────────────────
async function loadOverview() {
  const { ok, data } = await apiGet('/auth/admin/dashboard');
  if (!ok) {
    // Try startup overview for non-superadmin
    const { ok: ok2, data: data2 } = await apiGet('/auth/startup/overview');
    if (ok2) renderOverview(data2);
    return;
  }
  renderOverview(data);
}

function renderOverview(data) {
  const m = data.metrics || {};
  document.getElementById('m-totalUsers').textContent   = m.total_users   ?? '—';
  document.getElementById('m-verified').textContent     = m.verified_users ?? '—';
  document.getElementById('m-sessions').textContent     = m.active_sessions ?? '—';
  document.getElementById('m-failedLogins').textContent = m.failed_logins_24h ?? '—';
  document.getElementById('m-admins').textContent       = m.admin_users   ?? '—';
  document.getElementById('m-pending').textContent      = m.pending_verifications ?? '—';

  const users = data.recent_users || [];
  document.getElementById('recentUsersTbody').innerHTML = users.length
    ? users.map(u => `<tr>
        <td title="${u.email}">${u.email}</td>
        <td>${roleBadge(u.role)}</td>
        <td>${verifiedBadge(u.email_verified)}</td>
        <td>${fmtDate(u.created_at)}</td>
      </tr>`).join('')
    : '<tr><td colspan="4" class="empty">No users yet</td></tr>';

  const events = data.recent_audit_events || [];
  document.getElementById('recentAuditTbody').innerHTML = events.length
    ? events.map(ev => `<tr>
        <td><code style="color:var(--info);font-size:0.78rem">${ev.event_type}</code></td>
        <td>${statusBadge(ev.status)}</td>
        <td title="${ev.email || ''}">${ev.email || '—'}</td>
        <td>${fmtDate(ev.created_at)}</td>
      </tr>`).join('')
    : '<tr><td colspan="4" class="empty">No events yet</td></tr>';
}

document.getElementById('refreshMetricsBtn').addEventListener('click', loadOverview);

// ── Table Editor ──────────────────────────────────────────────────────────
async function initTableEditor() {
  const { ok, data } = await apiGet('/rest/v1/schema');
  if (!ok) { toast('Could not load schema. Is the data-service running?', 'error'); return; }

  _allTables = data;
  _tableColumns = {};
  data.forEach(t => { _tableColumns[t.table] = t.columns; });

  const sel = document.getElementById('tableSelect');
  sel.innerHTML = '<option value="">Select a table…</option>' +
    data.map(t => `<option value="${t.table}">${t.table} (${t.column_count} cols)</option>`).join('');
  sel.addEventListener('change', () => loadTableRows(sel.value));
}

async function loadTableRows(table) {
  _currentTable = table;
  const wrap = document.getElementById('tableEditorWrap');
  if (!table) {
    wrap.innerHTML = `<div class="empty-state"><svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#333" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="9" x2="9" y2="21"/></svg><p>Select a table to view its rows</p></div>`;
    return;
  }
  wrap.innerHTML = '<table class="data-table"><tbody><tr><td class="empty">Loading…</td></tr></tbody></table>';

  const { ok, data } = await apiGet(`/rest/v1/${table}?limit=100`);
  if (!ok) { wrap.innerHTML = `<div class="empty-state"><p style="color:var(--danger)">${data?.detail || 'Error loading rows'}</p></div>`; return; }

  if (!data.length) {
    wrap.innerHTML = `<div class="empty-state"><p>No rows in <strong>${table}</strong> yet</p></div>`;
    return;
  }

  const cols = Object.keys(data[0]);
  wrap.innerHTML = `
    <table class="data-table">
      <thead><tr>${cols.map(c => `<th>${c}</th>`).join('')}<th></th></tr></thead>
      <tbody>
        ${data.map((row, i) => `<tr>
          ${cols.map(c => `<td title="${row[c] ?? ''}">${row[c] ?? '<span style="color:var(--text-3)">null</span>'}</td>`).join('')}
          <td><button class="delete-row-btn" data-id="${row.id}" data-idx="${i}">✕</button></td>
        </tr>`).join('')}
      </tbody>
    </table>`;

  wrap.querySelectorAll('.delete-row-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset.id;
      if (!id) { toast('Row has no id column — cannot delete', 'error'); return; }
      if (!confirm('Delete this row?')) return;
      const { ok } = await api('DELETE', `/rest/v1/${_currentTable}?id=eq.${id}`);
      if (ok) { toast('Row deleted', 'success'); loadTableRows(_currentTable); }
      else    { toast('Delete failed', 'error'); }
    });
  });
}

// Insert Row modal
document.getElementById('insertRowBtn').addEventListener('click', () => {
  if (!_currentTable) { toast('Select a table first', 'info'); return; }
  const cols = (_tableColumns[_currentTable] || []).filter(c =>
    !['id','tenant_id','created_at','updated_at'].includes(c.column_name)
  );
  document.getElementById('insertFields').innerHTML = cols.map(c => `
    <div class="field">
      <label>${c.column_name} <span style="color:var(--text-3);font-weight:400">(${c.data_type})</span></label>
      <input type="text" id="ins_${c.column_name}" placeholder="${c.column_name}" ${c.is_nullable === 'NO' ? 'required' : ''} />
    </div>`).join('');
  document.getElementById('insertModal').classList.remove('hidden');
});

document.getElementById('closeInsertModal').addEventListener('click', () =>
  document.getElementById('insertModal').classList.add('hidden'));
document.getElementById('cancelInsertBtn').addEventListener('click', () =>
  document.getElementById('insertModal').classList.add('hidden'));

document.getElementById('confirmInsertBtn').addEventListener('click', async () => {
  const cols = (_tableColumns[_currentTable] || []).filter(c =>
    !['id','tenant_id','created_at','updated_at'].includes(c.column_name)
  );
  const body = {};
  cols.forEach(c => {
    const val = document.getElementById(`ins_${c.column_name}`)?.value;
    if (val !== undefined && val !== '') body[c.column_name] = val;
  });

  const errEl = document.getElementById('insertError');
  errEl.classList.add('hidden');
  const { ok, data } = await apiPost(`/rest/v1/${_currentTable}`, body);
  if (!ok) { errEl.textContent = data?.detail || 'Insert failed'; errEl.classList.remove('hidden'); return; }
  toast('Row inserted', 'success');
  document.getElementById('insertModal').classList.add('hidden');
  loadTableRows(_currentTable);
});

// ── SQL Editor ────────────────────────────────────────────────────────────
document.getElementById('runSqlBtn').addEventListener('click', runSql);
document.getElementById('sqlInput').addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') runSql();
});

async function runSql() {
  const query = document.getElementById('sqlInput').value.trim();
  if (!query) return;
  const resultsEl = document.getElementById('sqlResults');
  resultsEl.innerHTML = '<p class="empty-state-inline">Running…</p>';

  const { ok, data } = await apiPost('/rest/v1/sql', { query });
  if (!ok) {
    resultsEl.innerHTML = `<p class="empty-state-inline" style="color:var(--danger)">${data?.detail || 'Query error'}</p>`;
    return;
  }

  const rows = data.rows || [];
  if (!rows.length) { resultsEl.innerHTML = '<p class="empty-state-inline">Query returned 0 rows</p>'; return; }

  const cols = Object.keys(rows[0]);
  resultsEl.innerHTML = `
    <table class="data-table">
      <thead><tr>${cols.map(c => `<th>${c}</th>`).join('')}</tr></thead>
      <tbody>${rows.map(r =>
        `<tr>${cols.map(c => `<td title="${r[c] ?? ''}">${r[c] ?? '<span style="color:var(--text-3)">null</span>'}</td>`).join('')}</tr>`
      ).join('')}</tbody>
    </table>
    <div style="padding:8px 14px;font-size:0.75rem;color:var(--text-3);border-top:1px solid var(--border)">
      ${rows.length} row${rows.length !== 1 ? 's' : ''} — ${data.count ?? rows.length} total
    </div>`;
}

// ── Users ─────────────────────────────────────────────────────────────────
async function loadUsers() {
  const { ok, data } = await apiGet('/users');
  const tbody = document.getElementById('usersTbody');
  if (!ok) { tbody.innerHTML = `<tr><td colspan="6" class="empty" style="color:var(--danger)">${data?.detail || 'Could not load users'}</td></tr>`; return; }
  _usersRaw = Array.isArray(data) ? data : (data.users || []);
  renderUsers(_usersRaw);
}

function renderUsers(users) {
  const tbody = document.getElementById('usersTbody');
  if (!users.length) { tbody.innerHTML = '<tr><td colspan="6" class="empty">No users found</td></tr>'; return; }
  tbody.innerHTML = users.map(u => `<tr>
    <td>${u.name || '—'}</td>
    <td title="${u.email}">${u.email}</td>
    <td>${roleBadge(u.role)}</td>
    <td>${verifiedBadge(u.email_verified)}</td>
    <td>${fmtDate(u.last_login_at)}</td>
    <td>${fmtDate(u.created_at)}</td>
  </tr>`).join('');
}

document.getElementById('refreshUsersBtn').addEventListener('click', loadUsers);
document.getElementById('userSearchInput').addEventListener('input', e => {
  const q = e.target.value.toLowerCase();
  renderUsers(_usersRaw.filter(u => u.email?.toLowerCase().includes(q) || u.name?.toLowerCase().includes(q)));
});

// ── Audit Logs ────────────────────────────────────────────────────────────
async function loadLogs() {
  const eventFilter  = document.getElementById('logEventFilter').value;
  const statusFilter = document.getElementById('logStatusFilter').value;
  const { ok, data } = await apiGet('/auth/admin/audit-logs');
  const tbody = document.getElementById('logsTbody');
  if (!ok) {
    // Fallback: try admin dashboard audit events
    const { ok: ok2, data: data2 } = await apiGet('/auth/admin/dashboard');
    if (ok2 && data2.recent_audit_events) renderLogs(data2.recent_audit_events, eventFilter, statusFilter);
    else tbody.innerHTML = `<tr><td colspan="6" class="empty" style="color:var(--danger)">${data?.detail || 'Could not load logs'}</td></tr>`;
    return;
  }
  renderLogs(Array.isArray(data) ? data : (data.events || []), eventFilter, statusFilter);
}

function renderLogs(logs, eventFilter, statusFilter) {
  const filtered = logs.filter(l =>
    (!eventFilter  || l.event_type === eventFilter) &&
    (!statusFilter || l.status === statusFilter)
  );
  const tbody = document.getElementById('logsTbody');
  if (!filtered.length) { tbody.innerHTML = '<tr><td colspan="6" class="empty">No events match the filter</td></tr>'; return; }
  tbody.innerHTML = filtered.map(l => `<tr>
    <td><code style="color:var(--info);font-size:0.78rem">${l.event_type}</code></td>
    <td>${statusBadge(l.status)}</td>
    <td title="${l.email || ''}">${l.email || '—'}</td>
    <td><code style="font-size:0.75rem;color:var(--text-3)">${l.ip_address || '—'}</code></td>
    <td style="color:var(--text-3);font-size:0.78rem">${l.details || '—'}</td>
    <td>${fmtDate(l.created_at)}</td>
  </tr>`).join('');
}

document.getElementById('refreshLogsBtn').addEventListener('click', loadLogs);
document.getElementById('logEventFilter').addEventListener('change', loadLogs);
document.getElementById('logStatusFilter').addEventListener('change', loadLogs);

// ── API Docs ──────────────────────────────────────────────────────────────
async function initApiDocs() {
  const { ok, data } = await apiGet('/rest/v1/schema');
  if (!ok) return;

  const sel = document.getElementById('docsTableSelect');
  sel.innerHTML = '<option value="">Select a table…</option>' +
    data.map(t => `<option value="${t.table}">${t.table}</option>`).join('');
  sel.addEventListener('change', () => renderApiDocs(sel.value, data.find(t => t.table === sel.value)));
}

function renderApiDocs(table, meta) {
  const el = document.getElementById('apiDocsContent');
  if (!table || !meta) {
    el.innerHTML = `<div class="empty-state"><p>Select a table to view its API reference</p></div>`;
    return;
  }
  const base = `${BASE}/rest/v1/${table}`;
  const exampleRow = '{ "display_name": "Krish", "bio": "Builder" }';

  el.innerHTML = `
    <div class="api-section">
      <h3 class="section-title" style="margin-bottom:1.5rem">/${table}</h3>

      <div class="api-method">
        <span class="method-badge method-get">GET</span>
        <code class="api-path">/rest/v1/${table}</code>
        <span class="badge">Auth required</span>
      </div>
      <p style="color:var(--text-2);font-size:0.82rem;margin-bottom:0.5rem">Fetch rows. Supports filters, select, order, limit, offset.</p>
      <pre class="code-block">curl -H "Authorization: Bearer &lt;token&gt;" \\
  "${base}?select=id,display_name&limit=10"

# Filter operators: eq, neq, gt, gte, lt, lte, like, ilike, in, is
curl -H "Authorization: Bearer &lt;token&gt;" \\
  "${base}?display_name=ilike.krish%"</pre>

      <div class="api-method" style="margin-top:1.5rem">
        <span class="method-badge method-post">POST</span>
        <code class="api-path">/rest/v1/${table}</code>
      </div>
      <p style="color:var(--text-2);font-size:0.82rem;margin-bottom:0.5rem">Insert a new row. tenant_id is injected automatically.</p>
      <pre class="code-block">curl -X POST -H "Authorization: Bearer &lt;token&gt;" \\
  -H "Content-Type: application/json" \\
  -d '${exampleRow}' \\
  "${base}"</pre>

      <div class="api-method" style="margin-top:1.5rem">
        <span class="method-badge method-patch">PATCH</span>
        <code class="api-path">/rest/v1/${table}?id=eq.&lt;uuid&gt;</code>
      </div>
      <p style="color:var(--text-2);font-size:0.82rem;margin-bottom:0.5rem">Update rows matching the filter.</p>
      <pre class="code-block">curl -X PATCH -H "Authorization: Bearer &lt;token&gt;" \\
  -H "Content-Type: application/json" \\
  -d '{ "bio": "Updated bio" }' \\
  "${base}?id=eq.&lt;uuid&gt;"</pre>

      <div class="api-method" style="margin-top:1.5rem">
        <span class="method-badge method-delete">DELETE</span>
        <code class="api-path">/rest/v1/${table}?id=eq.&lt;uuid&gt;</code>
      </div>
      <p style="color:var(--text-2);font-size:0.82rem;margin-bottom:0.5rem">Delete rows matching the filter. A filter is always required.</p>
      <pre class="code-block">curl -X DELETE -H "Authorization: Bearer &lt;token&gt;" \\
  "${base}?id=eq.&lt;uuid&gt;"</pre>

      <h3 class="section-title" style="margin:2rem 0 1rem">SDK Usage</h3>
      <pre class="code-block">const db = Sentinel.createClient('${BASE}')

// After sign in, the token is stored automatically
const { data, error } = await db.from('${table}')
  .select('*')
  .order('created_at', { ascending: false })
  .limit(10)
  .fetch()

await db.from('${table}').insert(${exampleRow})
await db.from('${table}').eq('id', '&lt;uuid&gt;').update({ bio: 'new bio' })
await db.from('${table}').eq('id', '&lt;uuid&gt;').delete()</pre>

      ${meta.columns ? `
      <h3 class="section-title" style="margin:2rem 0 1rem">Columns</h3>
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr><th>Column</th><th>Type</th><th>Nullable</th><th>Default</th></tr></thead>
          <tbody>
            ${meta.columns.map(c => `<tr>
              <td><code style="color:var(--accent)">${c.column_name}</code></td>
              <td><code style="color:var(--text-2)">${c.data_type}</code></td>
              <td>${c.is_nullable === 'YES' ? '<span class="badge">yes</span>' : '<span class="badge badge-info">no</span>'}</td>
              <td><code style="color:var(--text-3);font-size:0.76rem">${c.column_default || '—'}</code></td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>` : ''}
    </div>`;
}

// ── Settings ──────────────────────────────────────────────────────────────
function populateSettings() {
  document.getElementById('settingGateway').textContent  = BASE;
  document.getElementById('settingDataApi').textContent  = `${BASE}/rest/v1`;
  document.getElementById('settingAuthApi').textContent  = `${BASE}/auth`;
  document.getElementById('settingSlug').textContent     = _user?.tenant_slug || '—';
  document.getElementById('settingRole').textContent     = _user?.role        || '—';
  document.getElementById('settingEmail').textContent    = _user?.email       || '—';
  document.getElementById('sdkQuickstart').textContent   =
`// Copy sentinel.js to your project

const db = Sentinel.createClient('${BASE}')

// Sign in
await db.auth.signIn({ email, password, tenantSlug: '${_user?.tenant_slug || 'default'}' })

// Query a table
const { data } = await db.from('profiles')
  .select('*').limit(10).fetch()`;
}

// ── Boot ──────────────────────────────────────────────────────────────────
if (isLoggedIn()) {
  showApp();
} else {
  showLoginScreen();
}
