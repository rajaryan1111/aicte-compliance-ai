# AICTE Compliance Assistant — Frontend

React 18 + TypeScript + Vite UI for the implemented preliminary-validation contract.

## Scope

- Checks backend liveness at `GET /health`.
- Sends real checklist input to `POST /api/v1/validate`.
- Displays missing-document and expiry findings returned by the API.
- Clearly labels results as advisory and does not imply approval or authenticity verification.
- Uses no hardcoded/mock success response.

This is a prototype for preliminary checklist validation. Document upload/OCR processing, official AICTE rule evaluation, authentication, and human-review actions are not implemented in this UI.

## Deploy

Build command: `npm ci && npm run build`
Output directory: `dist`
Root directory: `frontend`

Set `VITE_API_BASE_URL` to the deployed backend origin. The backend must allow browser requests from the frontend origin (CORS). Keep the value empty only when the frontend and API share an origin or are routed through a same-origin reverse proxy.

```bash
npm ci
npm run build
```
