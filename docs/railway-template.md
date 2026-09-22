# Railway template checklist (maintainer)

Build the template in the [Railway template editor](https://docs.railway.com/templates/create) and copy its template URL into the README once published. Railway's old `railway.json` config format is [deprecated for new services](https://docs.railway.com/infrastructure-as-code); the template itself must hold the service configuration.

1. Create a **YouTube Transcript MCP** template with source `https://github.com/scandolo/youtube-transcript-mcp` on `main`.
2. Enable **HTTP public networking** and generate a Railway domain. Attach a volume at `/data`. Set the healthcheck path to `/healthz`, timeout to 60 seconds, and one replica. Railway detects the Dockerfile, which runs the server on Railway’s assigned `PORT`.
3. Add required variables with clear descriptions: `YTM_AUTH_PROVIDER=github`, `YTM_ALLOWED_USERS` (deployer’s GitHub username), `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `WEBSHARE_PROXY_USERNAME`, `WEBSHARE_PROXY_PASSWORD`. Generate `JWT_SIGNING_KEY` with `${{secret(64, "abcdef0123456789")}}`. Do not set `YTM_BASE_URL`; Railway injects `RAILWAY_PUBLIC_DOMAIN`.
4. Mark `YOUTUBE_API_KEY` and `GROQ_API_KEY` optional. Explain that the former enables reliable cloud metadata/search and the latter enables the Whisper fallback. If the template editor cannot collect the OAuth credentials after the domain exists, tell deployers to create the GitHub OAuth app with `https://<domain>/auth/callback`, then fill those variables and redeploy.
5. Deploy a fresh copy with a test GitHub account and Residential proxy. Confirm `/healthz`, OAuth login, `health()` reporting persisted state, `youtube_video_info`, and `youtube_transcript` on a captioned video. Then [publish](https://docs.railway.com/templates/publish-and-share), copy the actual template URL and button code into the README, and repeat the fresh-deploy check from that button.

The first deployment serves only `/healthz` with `setup_required` until its domain, OAuth app, and required secrets are filled in. `/mcp` returns 503 during setup. This sequence is inherent to GitHub’s exact callback URL requirement; describe it clearly in the template overview.
