# Sentinel Startup Console

This is a static startup onboarding and tenant-management console for Sentinel API, designed to hit the live Azure deployment through `https://sentinel.codexarena.app`.

## What it does

- checks the shared gateway health
- creates a startup and founder admin in one request
- verifies the founder account
- logs the founder into the startup tenant
- fetches the active founder session and founder profile
- loads startup metrics and recent users
- creates additional team members from the founder dashboard
- sends the tenant slug automatically so multiple startups can share one Sentinel deployment safely

## Deploy on Vercel

1. Import the repository into Vercel.
2. Set the root directory to `frontend`.
3. Deploy as a static project.
4. If needed, update `config.js` with your latest gateway URL.
5. Use the startup onboarding flow in the UI to create a startup and founder admin.
6. After founder login, use the dashboard area to inspect metrics and create team members.

Default gateway URL:

- `https://sentinel.codexarena.app`

Live stack:

- frontend on Vercel
- API gateway on Azure VM
- Redis + Postgres via Docker Compose
- HTTPS routing via Pangolin / Traefik

## Files

- `index.html` contains the founder onboarding and startup dashboard UI
- `styles.css` contains the visual design
- `app.js` contains the onboarding, login, dashboard, and team-management API calls
- `config.js` stores endpoint paths and the default base URL
- `config.js` also stores startup onboarding, dashboard, and tenant header settings
- `vercel.json` adds basic static deployment settings
