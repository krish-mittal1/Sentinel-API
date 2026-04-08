# Sentinel Frontend Demo

This is a static demo UI for Sentinel API, designed to hit the live Azure deployment through `https://sentinel.codexarena.app`.

## What it does

- checks your gateway health
- signs up a user
- verifies email with the returned token
- logs the user in
- fetches the user profile with a bearer token

## Deploy on Vercel

1. Import the repository into Vercel.
2. Set the root directory to `frontend`.
3. Deploy as a static project.
4. If needed, update `config.js` with your latest gateway URL.

Default gateway URL:

- `https://sentinel.codexarena.app`

Live stack:

- frontend on Vercel
- API gateway on Azure VM
- Redis + Postgres via Docker Compose
- HTTPS routing via Pangolin / Traefik

## Files

- `index.html` contains the UI
- `styles.css` contains the visual design
- `app.js` contains the API calls
- `config.js` stores endpoint paths and the default base URL
- `vercel.json` adds basic static deployment settings
