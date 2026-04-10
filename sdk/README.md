# @sentinel/client — JavaScript SDK

A lightweight, zero-dependency JavaScript client for the [Sentinel BaaS](../) platform.
Mirrors the Supabase JS SDK API surface.

## Quick Start

```html
<script src="sentinel.js"></script>
<script>
  const db = Sentinel.createClient('http://your-gateway.com')
</script>
```

Or CommonJS / Node:
```js
const { createClient } = require('./sentinel.js')
const db = createClient('http://your-gateway.com')
```

---

## Auth

```js
// Sign up
const { data, error } = await db.auth.signUp({
  email: 'user@example.com',
  password: 'Password123',
  name: 'Jane Smith',
  tenantSlug: 'my-project',   // defaults to 'default'
})

// Sign in
await db.auth.signIn({ email, password, tenantSlug })

// Sign out
await db.auth.signOut()

// Get current user (from stored JWT — no network call)
const user = db.auth.getUser()

// Verify email
await db.auth.verifyEmail(token)

// Password reset
await db.auth.forgotPassword({ email, tenantSlug })
await db.auth.resetPassword({ token, newPassword })

// Refresh session
await db.auth.refreshSession()
```

---

## Data API

The Data API wraps `/rest/v1/{table}` endpoints with a chainable query builder.

```js
// SELECT with filters
const { data, error } = await db.from('profiles')
  .select('id, display_name, bio')
  .eq('role', 'admin')
  .order('created_at', { ascending: false })
  .limit(10)
  .offset(0)
  .fetch()

// INSERT
const { data } = await db.from('profiles')
  .insert({ display_name: 'Krish', bio: 'Builder' })

// UPDATE
await db.from('profiles')
  .eq('id', '<uuid>')
  .update({ bio: 'Updated bio' })

// DELETE
await db.from('profiles')
  .eq('id', '<uuid>')
  .delete()
```

### Filter Operators

| Method | SQL |
|---|---|
| `.eq(col, val)` | `col = val` |
| `.neq(col, val)` | `col != val` |
| `.gt(col, val)` | `col > val` |
| `.gte(col, val)` | `col >= val` |
| `.lt(col, val)` | `col < val` |
| `.lte(col, val)` | `col <= val` |
| `.like(col, val)` | `col LIKE val` |
| `.ilike(col, val)` | `col ILIKE val` |
| `.isNull(col)` | `col IS NULL` |
| `.in(col, [a,b,c])` | `col = ANY(...)` |

---

## Schema

```js
// List all user-accessible tables
const { data } = await db.schema.list()

// Describe a specific table's columns
const { data } = await db.schema.describe('profiles')
```

## SQL (SELECT only)

```js
const { data } = await db.sql('SELECT * FROM profiles LIMIT 5')
// data.rows → array of objects
// data.count → total rows returned
```

---

## Token Storage

Tokens are stored in `localStorage` under:
- `sentinel:access_token`
- `sentinel:refresh_token`
- `sentinel:user`

The SDK automatically attaches the token header on every request.
