# ServiceDesk frontend

React 19 operator console for the ServiceDesk ticketing API, built with Vite and TypeScript.

## What the console does

- Shows the queue summary: total, open, pending, resolved, closed and SLA-breached counts, read
  from `GET /api/tickets/stats`.
- Lists every ticket from `GET /api/tickets` with its severity, status, category, requester and
  SLA state.
- Raises a ticket through `POST /api/tickets`.
- Changes status, severity, category and assignee inline through `PUT /api/tickets/{id}`.
- Deletes a ticket through `DELETE /api/tickets/{id}`.
- Filters the queue by status, by SLA breach, and by a free-text search across subject, requester
  and assignee.

## API base URL

`src/api.ts` reads `VITE_API_BASE_URL` at build time. Leaving it empty — the default — makes every
call same-origin, which is what the Nginx runtime image and the Kubernetes Ingress expect, because
both serve the static bundle and proxy `/api` to the backend from the same host.

Set it only when the bundle is served from a different origin than the API:

```sh
VITE_API_BASE_URL=http://127.0.0.1:8010 npm run build
```

`VITE_DEV_API_TARGET` controls where the Vite dev-server proxy forwards `/api`, `/health` and
`/ready` during `npm run dev`. It defaults to `http://127.0.0.1:8010`.

## Commands

```sh
npm ci            install the exact versions from package-lock.json
npm run dev       dev server on http://127.0.0.1:5173 with the API proxy
npm run typecheck tsc --noEmit
npm run build     typecheck then emit the production bundle into dist/
npm run preview   serve the built bundle on http://127.0.0.1:5180
```

## Layout

```text
src/
  api.ts                 typed fetch client and ApiError
  sla.ts                 SLA breach calculation and timestamp formatting
  types.ts               Ticket, Category, Stats and the severity/status unions
  App.tsx                queue state, filtering and the mutation handlers
  components/
    StatsBar.tsx         the six summary tiles
    TicketForm.tsx       the new-ticket form
    TicketCard.tsx       one ticket with its inline controls
  styles.css             the whole stylesheet, responsive down to 360px
```
