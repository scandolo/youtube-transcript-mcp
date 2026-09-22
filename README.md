# YouTube Transcript MCP

Give Claude or ChatGPT a YouTube link and ask questions about the video. This MCP server fetches captions, merges them into readable paragraphs, and gives the model chapters, timestamps, and links back to exact moments. It can search YouTube too.

**Example:** “Summarize the main argument in this video, then show me the timestamp for each claim: `https://www.youtube.com/watch?v=kCc8FmEb1nY`”

## Get it working on Railway

You need a [Railway account](https://railway.com/), a [GitHub account](https://github.com/), and a **rotating residential** [Webshare](https://dashboard.webshare.io/) proxy. Railway hosting and the residential proxy can cost money. YouTube commonly blocks caption requests from cloud IPs, so a deploy without a residential proxy will not fetch transcripts.

> **Template status:** The deploy button will go here after the Railway template is published. Until then, use [Deploy from GitHub](https://railway.com/new) and select this repository. Railway detects the Dockerfile automatically; set `/healthz` as the service healthcheck in Settings.

1. **Deploy and get a domain.** In Railway, create a project from `scandolo/youtube-transcript-mcp`. On the service, choose **Settings → Networking → Generate Domain**. Copy the `https://…up.railway.app` URL. Attach a volume mounted at `/data` so OAuth connections survive redeploys.
2. **Create a GitHub OAuth app.** Open [GitHub Developer settings](https://github.com/settings/developers) → **New OAuth App**. Use any app name. Set Homepage URL to your Railway URL and Authorization callback URL to `https://YOUR-DOMAIN/auth/callback` (replace `YOUR-DOMAIN` with the actual Railway hostname). Copy the client ID and generate a client secret.
3. **Set Railway variables.** In the service’s **Variables** tab, add the values below and deploy. Use your own GitHub username for the allowlist. Get the proxy credentials from Webshare’s **Residential** proxy settings; enter the plain username, without `-rotate`.

   | Name | Value |
   |---|---|
   | `YTM_AUTH_PROVIDER` | `github` |
   | `YTM_ALLOWED_USERS` | Your GitHub username, for example `scandolo` |
   | `GITHUB_CLIENT_ID` | OAuth app client ID |
   | `GITHUB_CLIENT_SECRET` | OAuth app client secret |
   | `WEBSHARE_PROXY_USERNAME` | Residential proxy username |
   | `WEBSHARE_PROXY_PASSWORD` | Residential proxy password |
   | `JWT_SIGNING_KEY` | A random secret, for example the output of `openssl rand -hex 32` |

   The server reads Railway’s `RAILWAY_PUBLIC_DOMAIN` and `PORT` automatically. No `YTM_BASE_URL` or port setting is needed. Railway may show a failed initial deployment before these variables are set; redeploy after saving them.

4. **Connect your AI app.** The MCP URL is `https://YOUR-DOMAIN/mcp`. Sign in with the allowlisted GitHub account when prompted.

   - **Claude:** **Customize → Connectors → + → Add custom connector**, then paste the MCP URL. Enable it in a conversation under **+ → Connectors**. On Team or Enterprise, an owner adds it in organization settings first. [Claude’s guide](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)
   - **ChatGPT:** On a supported plan, enable developer mode, then **Settings → Apps → Create** and enter the MCP URL. Choose OAuth, scan tools, and create the app. Availability varies by plan and workspace. [OpenAI’s guide](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt)
   - **Claude Code:** `claude mcp add --transport http --scope user youtube-transcript https://YOUR-DOMAIN/mcp`, then run `/mcp` in Claude Code to sign in.

Ask: **“Use the YouTube Transcript connector to summarize this video and cite the moments that support each point: [URL].”** For a long video, ask for its chapter list first, then a particular chapter.

## Run locally

Local stdio needs Python 3.10+ and no Railway, OAuth app, or proxy. YouTube may still block your network or a particular video may have no captions.

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
claude mcp add youtube-transcript --scope user -- "$PWD/.venv/bin/youtube-transcript-mcp"
```

No `.env` file is needed for this path. For other local clients, run `.venv/bin/youtube-transcript-mcp` as a stdio MCP server. Copy `.env.example` if you want to configure optional backends or run HTTP yourself.

## What the tools do

| Tool | Use it for |
|---|---|
| `search_youtube` | Find videos using YouTube’s search ranking. A [YouTube Data API key](https://console.cloud.google.com/apis/library/youtube.googleapis.com) enables filters and reliable cloud search; without it, `yt-dlp` searches through the proxy. |
| `youtube_video_info` | Get title, duration, description, and chapters before pulling a long transcript. |
| `youtube_transcript` | Get the whole transcript, one chapter (`chapter="5"`), matching passages (`query="attention"`), or a time window. Use `language="it"` for another caption language. |
| `health` | Check which optional backends and deployment settings are present, without exposing secrets. |

Captions come from `youtube-transcript-api` first, then `yt-dlp`. If both find no captions and `GROQ_API_KEY` is set, Groq Whisper can transcribe downloaded audio. This fallback may incur Groq charges and has an upload size limit. `YOUTUBE_API_KEY` adds reliable metadata and search from cloud hosts; YouTube charges search requests at 100 quota units each against its daily quota.

## Troubleshooting

- **Railway deploy fails:** Check required variables, domain, and volume. The server refuses to start on Railway without OAuth or a proxy. Visit `https://YOUR-DOMAIN/healthz` after it is live.
- **OAuth callback error:** The GitHub OAuth callback must exactly match `https://YOUR-DOMAIN/auth/callback`. `YTM_ALLOWED_USERS` contains GitHub *usernames*, not email addresses.
- **Reauthorize after every deploy:** Attach a Railway volume at `/data`. The `health` tool should report `oauth_state_persisted: true`.
- **`IpBlocked` or no transcript:** Confirm your Webshare package says **Residential**, and use the plain proxy username. The free “Proxy Server” and static residential products do not provide the required rotation. Some videos have disabled or unavailable captions.
- **Search or chapters missing:** Set `YOUTUBE_API_KEY` with YouTube Data API v3 enabled. Restrict the key to that API. If using a website restriction, allow your Railway URL as a referrer.
- **It suddenly stopped working:** Redeploy to pick up a newer `yt-dlp` and `youtube-transcript-api` release. YouTube changes its site regularly.

See [all configuration options](.env.example).

## License

MIT. See [LICENSE](LICENSE).
