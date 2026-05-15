# Cloudflare State Sync Setup

This enables your static dashboard to save/load UI state (theme, module order, open panels, One Piece tab/current chapter) across devices.

## 1. What this does

- `docs/app.js` reads/writes state to a Cloudflare Worker endpoint.
- Worker stores the JSON in Cloudflare KV (`DASH_STATE` binding).
- Dashboard still uses localStorage as fallback when API is not set/reachable.

## 2. Create the Worker + KV (Cloudflare website + CLI)

1. In Cloudflare dashboard, create a KV namespace (for example `my-dashboard-state`).
2. Copy both namespace IDs:
- Production Namespace ID
- Preview Namespace ID
3. In this repo, open [wrangler.toml](/c:/Users/mjrit/OneDrive/Desktop/my-dashboard/cloudflare-state-worker/wrangler.toml) and replace:
- `REPLACE_WITH_KV_NAMESPACE_ID`
- `REPLACE_WITH_KV_PREVIEW_NAMESPACE_ID`

## 3. Deploy the Worker

Run:

```powershell
cd cloudflare-state-worker
npx wrangler deploy
```

After deploy, copy the Worker URL (for example `https://my-dashboard-state.<your-subdomain>.workers.dev`).

## 4. Point the dashboard to your Worker

Open [index.html](/c:/Users/mjrit/OneDrive/Desktop/my-dashboard/docs/index.html) and update:

```html
<script>
  window.DASHBOARD_STATE_API = "https://YOUR-WORKER.workers.dev/state";
</script>
```

Use your real Worker URL with `/state` at the end.

## 5. Publish your static site

Deploy your `docs/` folder as usual (GitHub Pages/Cloudflare Pages/etc.).

## 6. Verify it works

1. Open dashboard on device A.
2. Change theme, reorder modules, set a current One Piece chapter.
3. Open dashboard on device B (or private window).
4. Confirm the same state appears.

If state does not sync, check browser devtools network for `GET/POST /state` calls and Worker logs in Cloudflare.
