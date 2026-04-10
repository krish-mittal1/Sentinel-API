/**
 * sentinel.js — Official JavaScript client for the Sentinel BaaS platform.
 *
 * Usage:
 *   const db = createClient('https://api.myapp.com', '<your-jwt-token>')
 *
 *   // Auth
 *   const { data } = await db.auth.signUp({ email, password, name })
 *   const { data } = await db.auth.signIn({ email, password, tenantSlug })
 *   db.auth.signOut()
 *   db.auth.getUser()
 *
 *   // Data API
 *   const { data, error } = await db.from('profiles')
 *     .select('id, display_name, bio')
 *     .eq('display_name', 'krish')
 *     .order('created_at', { ascending: false })
 *     .limit(10)
 *     .fetch()
 *
 *   await db.from('profiles').insert({ display_name: 'Krish', bio: 'Builder' })
 *   await db.from('profiles').eq('id', uuid).update({ bio: 'Updated' })
 *   await db.from('profiles').eq('id', uuid).delete()
 *
 *   // Schema
 *   const { data } = await db.schema.list()
 *   const { data } = await db.schema.describe('profiles')
 *
 *   // SQL (SELECT only)
 *   const { data } = await db.sql('SELECT * FROM profiles LIMIT 5')
 *
 * @version 1.0.0
 * @license MIT
 */

(function (global, factory) {
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = factory();          // CommonJS / Node
  } else if (typeof define === 'function' && define.amd) {
    define(factory);                     // AMD
  } else {
    global.Sentinel = factory();         // Browser global
  }
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  // ── Token storage ──────────────────────────────────────────────────────
  const TOKEN_KEY = 'sentinel:access_token';
  const REFRESH_KEY = 'sentinel:refresh_token';
  const USER_KEY = 'sentinel:user';

  function _storeSession(accessToken, refreshToken, user) {
    try {
      localStorage.setItem(TOKEN_KEY, accessToken);
      if (refreshToken) localStorage.setItem(REFRESH_KEY, refreshToken);
      if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
    } catch (_) { /* SSR fallback */ }
  }

  function _clearSession() {
    try {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(REFRESH_KEY);
      localStorage.removeItem(USER_KEY);
    } catch (_) { }
  }

  function _getToken() {
    try { return localStorage.getItem(TOKEN_KEY); } catch (_) { return null; }
  }

  function _getStoredUser() {
    try {
      const raw = localStorage.getItem(USER_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (_) { return null; }
  }

  // ── HTTP helper ────────────────────────────────────────────────────────
  async function _request(baseUrl, method, path, body, token, params) {
    const url = new URL(path, baseUrl);
    if (params) {
      Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
    }

    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const opts = { method, headers };
    if (body !== undefined && body !== null) opts.body = JSON.stringify(body);

    try {
      const res = await fetch(url.toString(), opts);
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        return { data: null, error: json.detail || json.message || `HTTP ${res.status}` };
      }
      return { data: json, error: null };
    } catch (err) {
      return { data: null, error: err.message || 'Network error' };
    }
  }

  // ── Auth module ────────────────────────────────────────────────────────
  function _createAuth(baseUrl) {
    return {
      /**
       * Sign up a new user for the default tenant.
       */
      async signUp({ email, password, name, tenantSlug = 'default' }) {
        const { data, error } = await _request(
          baseUrl, 'POST',
          `/auth/${tenantSlug}/signup`,
          { email, password, name }
        );
        if (data && data.access_token) {
          _storeSession(data.access_token, data.refresh_token, data.user);
        }
        return { data, error };
      },

      /**
       * Sign in with email + password.
       */
      async signIn({ email, password, tenantSlug = 'default' }) {
        const { data, error } = await _request(
          baseUrl, 'POST',
          `/auth/${tenantSlug}/login`,
          { email, password }
        );
        if (data && data.access_token) {
          _storeSession(data.access_token, data.refresh_token, data.user);
        }
        return { data, error };
      },

      /**
       * Sign out — clears stored tokens.
       */
      async signOut() {
        const token = _getToken();
        const refreshToken = localStorage.getItem(REFRESH_KEY);
        if (refreshToken) {
          await _request(baseUrl, 'POST', '/auth/logout', { refresh_token: refreshToken }, token);
        }
        _clearSession();
        return { error: null };
      },

      /**
       * Verify email with the token received by email.
       */
      async verifyEmail(token) {
        const { data, error } = await _request(
          baseUrl, 'POST', '/auth/verify-email', { token }
        );
        if (data && data.access_token) {
          _storeSession(data.access_token, data.refresh_token, data.user);
        }
        return { data, error };
      },

      /**
       * Request a password reset email.
       */
      async forgotPassword({ email, tenantSlug = 'default' }) {
        return _request(baseUrl, 'POST', `/auth/${tenantSlug}/forgot-password`, { email });
      },

      /**
       * Complete password reset with the emailed token.
       */
      async resetPassword({ token, newPassword }) {
        return _request(baseUrl, 'POST', '/auth/reset-password', {
          token,
          new_password: newPassword,
        });
      },

      /**
       * Refresh the access token using the stored refresh token.
       */
      async refreshSession() {
        let refreshToken;
        try { refreshToken = localStorage.getItem(REFRESH_KEY); } catch (_) { }
        if (!refreshToken) return { data: null, error: 'No refresh token stored' };
        const { data, error } = await _request(
          baseUrl, 'POST', '/auth/refresh', { refresh_token: refreshToken }
        );
        if (data && data.access_token) {
          _storeSession(data.access_token, data.refresh_token, data.user);
        }
        return { data, error };
      },

      /**
       * Returns the current user from the stored JWT payload (no network call).
       */
      getUser() {
        return _getStoredUser();
      },

      /**
       * Get the current raw access token (if you need it externally).
       */
      getToken() {
        return _getToken();
      },
    };
  }

  // ── Query Builder ──────────────────────────────────────────────────────
  function _createQueryBuilder(baseUrl, table) {
    const _params = {};
    let _method = 'GET';
    let _body = null;

    const builder = {
      /**
       * SELECT columns (comma-separated string or array).
       */
      select(cols) {
        if (Array.isArray(cols)) cols = cols.join(',');
        _params.select = cols;
        return builder;
      },

      eq(col, val)    { _params[col] = `eq.${val}`;    return builder; },
      neq(col, val)   { _params[col] = `neq.${val}`;   return builder; },
      gt(col, val)    { _params[col] = `gt.${val}`;    return builder; },
      gte(col, val)   { _params[col] = `gte.${val}`;   return builder; },
      lt(col, val)    { _params[col] = `lt.${val}`;    return builder; },
      lte(col, val)   { _params[col] = `lte.${val}`;   return builder; },
      like(col, val)  { _params[col] = `like.${val}`;  return builder; },
      ilike(col, val) { _params[col] = `ilike.${val}`; return builder; },
      isNull(col)     { _params[col] = 'is.null';       return builder; },
      in(col, vals)   { _params[col] = `in.(${vals.join(',')})`; return builder; },

      /**
       * Order results by a column.
       */
      order(col, { ascending = true } = {}) {
        _params.order = `${col}.${ascending ? 'asc' : 'desc'}`;
        return builder;
      },

      limit(n)  { _params.limit = n;  return builder; },
      offset(n) { _params.offset = n; return builder; },

      /**
       * Execute a SELECT query.
       */
      async fetch() {
        _method = 'GET';
        const token = _getToken();
        return _request(baseUrl, _method, `/rest/v1/${table}`, null, token, _params);
      },

      /**
       * Insert a row (or multiple rows).
       */
      async insert(data) {
        const token = _getToken();
        return _request(baseUrl, 'POST', `/rest/v1/${table}`, data, token);
      },

      /**
       * Update rows matching the current filters.
       */
      async update(data) {
        const token = _getToken();
        return _request(baseUrl, 'PATCH', `/rest/v1/${table}`, data, token, _params);
      },

      /**
       * Delete rows matching the current filters.
       */
      async delete() {
        const token = _getToken();
        return _request(baseUrl, 'DELETE', `/rest/v1/${table}`, null, token, _params);
      },
    };

    return builder;
  }

  // ── Schema module ──────────────────────────────────────────────────────
  function _createSchema(baseUrl) {
    return {
      /** List all user-accessible tables with column counts. */
      async list() {
        return _request(baseUrl, 'GET', '/rest/v1/schema', null, _getToken());
      },
      /** Describe columns of a specific table. */
      async describe(table) {
        return _request(baseUrl, 'GET', `/rest/v1/schema/${table}`, null, _getToken());
      },
    };
  }

  // ── Public API ─────────────────────────────────────────────────────────
  function createClient(baseUrl, token) {
    // Normalise trailing slash
    baseUrl = baseUrl.replace(/\/$/, '');

    // If a token is provided at client creation, store it
    if (token) {
      try { localStorage.setItem(TOKEN_KEY, token); } catch (_) { }
    }

    return {
      auth: _createAuth(baseUrl),
      schema: _createSchema(baseUrl),

      /**
       * Start a query builder for the given table.
       */
      from(table) {
        return _createQueryBuilder(baseUrl, table);
      },

      /**
       * Run a SELECT-only raw SQL query.
       */
      async sql(query) {
        return _request(baseUrl, 'POST', '/rest/v1/sql', { query }, _getToken());
      },
    };
  }

  return { createClient };
}));
