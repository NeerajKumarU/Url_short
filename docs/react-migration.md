# OrbitLink React migration audit

## Existing architecture

OrbitLink is a Django 4.2 SaaS application, not a static HTML site. Django currently owns URL routing, authentication, CSRF protection, workspace RBAC, form validation, database access, messages, redirects, exports, QR responses, and server-rendered HTML. The frontend is implemented by 41 page templates, five shared template fragments, eleven CSS files, and three vanilla JavaScript files.

The database domain includes workspaces and memberships, links, click events, campaigns, custom domains, redirect rules, experiments and variants, conversions, approvals, abuse reports, API credentials, webhook endpoints and deliveries, analytics anomalies, notification deliveries, versions, and audit logs.

## Existing page groups

- Public: landing/product, login, registration, unavailable/expired/blocked links, abuse reporting.
- Core SaaS: dashboard, link list, link creation/editing/deletion, QR library and downloads.
- Intelligence: analytics, audience, anomaly detection, realtime polling, AI analytics.
- Marketing: campaigns, UTM builder, campaign suggestions.
- Link intelligence: custom domains, routing rules, versions, experiments and conversions.
- Governance: approvals, governance settings, workspace audit log.
- Integrations: API credentials, webhooks, bulk CSV import, CSV export.
- Account: workspace selection and account/appearance settings.
- Platform administration: operations dashboard, users, reports, health, abuse assistant, Django Admin.

## Existing client behavior

`app.js` owns theme/accent persistence, responsive sidebar state, dropdown coordination, confirmations, loading states, clipboard actions, global search shortcuts, and toast dismissal. `landing.js` owns public navigation, scroll/reveal effects, spotlight/magnetic interactions, the command palette, cursor effects, and FAQ behavior. `cyber-scene.js` owns the WebGL lifecycle, animation, adaptive quality, pointer parallax, reduced-motion behavior, visibility pausing, and cleanup. The dashboard template also creates its SVG chart and polls realtime analytics.

## Backend integration constraints

Only a small part of the product is JSON-first today. Most reads are assembled as Django template contexts and most mutations are CSRF-protected form submissions. A big-bang SPA replacement would lose Django form errors, messages, role checks, redirects, file responses, and ownership enforcement. Existing API contracts must remain unchanged.

The migration therefore uses a strangler approach:

1. Keep Django as the authoritative backend and preserve all current endpoints.
2. Add a read-only, session-authenticated React bootstrap adapter without changing existing APIs.
3. Run the React application under `/react/` while current Django routes remain the fallback.
4. Convert page groups into React components and reuse existing mutation/download URLs.
5. Switch canonical page routes only after parity tests pass.
6. Remove obsolete templates and vanilla handlers only after the final cutover.

## React structure

```text
frontend/
  src/
    api/          CSRF-aware client and page data hooks
    app/          application root and route configuration
    components/   shared shell, navigation, cards, tables, controls
    features/     domain-specific reusable UI and logic
    hooks/        theme, storage, responsive, and polling hooks
    pages/        route-level components
    styles/       legacy CSS bridge and React-specific compatibility CSS
    utils/        formatting and URL helpers
    webgl/        React lifecycle integration for the holographic scene
```

## Risks and controls

- Authentication and CSRF: retain Django session cookies and CSRF middleware; never move authorization into React.
- RBAC/data leakage: every adapter query remains workspace-scoped through existing selectors and permission helpers.
- Form parity: keep existing POST targets until equivalent JSON actions are tested.
- CSS collisions: load existing styles in their current cascade, then use a small namespaced React compatibility layer.
- WebGL lifecycle: mount once in the persistent React shell and dispose only when the shell unmounts.
- Deep links: Django serves the React shell for `/react/*`; React Router resolves the client route.
- Deployment: Vite emits deterministic assets into Django static source; Docker builds them before `collectstatic`.
- Regression: retain all 98 Django tests and add frontend build/component tests as pages move.

## Cutover acceptance

Canonical Django templates are removed only after every page has a React equivalent, all existing actions work, permission tests pass, production assets build through Docker, responsive screenshots are compared, and the current HTML fallback is no longer needed.
