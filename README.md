<div align="center">
  <img src="assets/hero.svg" alt="YouTube video to searchable transcript to AI assistant" width="100%" />

  # YouTube Transcript MCP

  **Ask your AI about a YouTube video. Get an answer you can click back to.**

  [![Checks](https://github.com/scandolo/youtube-transcript-mcp/actions/workflows/checks.yml/badge.svg)](https://github.com/scandolo/youtube-transcript-mcp/actions/workflows/checks.yml) [![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) [![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB.svg)](pyproject.toml) [![MCP](https://img.shields.io/badge/protocol-MCP-8B8DFB.svg)](https://modelcontextprotocol.io/)

  <a href="https://railway.com/deploy/youtube-transcript-mcp"><img src="https://railway.com/button.svg" alt="Deploy on Railway" /></a>

  [Get started](#get-started) · [Give setup to your agent](#give-setup-to-your-agent) · [Run locally](#run-locally) · [What it does](#what-it-does)
</div>

Turn raw captions into readable paragraphs with chapters, timestamps, and links to the exact moment in the video. Search YouTube, inspect a video, then pull only the chapter or passages you need. Works as a remote MCP connector for Claude and supported ChatGPT plans, or as a local stdio server.

> [!IMPORTANT]
> Railway hosting and a **rotating residential proxy** can cost money. The local setup needs neither. The Railway deployment stays in safe setup mode until its proxy and sign-in settings are complete.

## Contents

- [Get started](#get-started)
- [Give setup to your agent](#give-setup-to-your-agent)
- [Try your first question](#try-your-first-question)
- [What it does](#what-it-does)
- [Run locally](#run-locally)
- [Troubleshooting](#troubleshooting)
- [Configuration and security](#configuration-and-security)
- [License](#license)

## Get started

**On your laptop:** [Run locally](#run-locally) with Claude Code or another local MCP client. Start without a proxy or GitHub OAuth app. Your own connection may still be blocked by YouTube, but it usually avoids the cloud-IP problem.

**In Claude or ChatGPT as a remote connector:** use the Railway steps below. Railway's server sends requests from a cloud IP, which [YouTube often blocks for captions](https://github.com/jdepoix/youtube-transcript-api#working-around-ip-bans-requestblocked-or-ipblocked-exception). A **residential proxy** sends those requests through ordinary home internet IPs instead. GitHub sign-in protects your public MCP URL and your proxy bandwidth; it is unrelated to reading YouTube. This Railway template currently requires both for a working remote deployment. A proxy improves reliability but cannot guarantee every video will work.

### 1. Deploy

Click **Deploy on Railway** above, choose your Railway workspace, and click **Deploy**. The template uses this GitHub repo and sets up the public domain, `/healthz` health check, and persistent `/data` volume for you. Open the new service in Railway and copy its `https://…up.railway.app` URL from **Settings → Networking**.

The first deployment is intentionally in setup mode: `/healthz` tells you which settings remain, and `/mcp` does not serve tools until setup is complete.

### 2. Get a residential proxy

1. Create a [Webshare account](https://dashboard.webshare.io/) and choose a **Rotating Residential** plan in **Plans & Pricing**. This is a paid plan; Webshare's free **Proxy Server** and **Static Residential** products are different. See [Webshare's plan comparison](https://www.webshare.io/pricing).
2. Open [Webshare Proxy Settings](https://dashboard.webshare.io/proxy/settings). Copy **Proxy Username** and **Proxy Password**. You do not need to configure an endpoint or choose a country; the server uses Webshare's rotating residential endpoint automatically. A username ending in `-rotate` is fine.
3. Keep those credentials for step 4. Enter them only in Railway Variables, never in an AI chat or GitHub file.

If you already use another rotating residential provider, set its full proxy URL in `YTM_PROXY` instead of the two Webshare variables. See [.env.example](.env.example).

### 3. Create a GitHub OAuth app

**Why?** Railway gives your server a public URL. The GitHub sign-in checks your username against `YTM_ALLOWED_USERS` so strangers cannot call your tools or spend your proxy bandwidth. This project only asks GitHub for **read access to your profile** to identify your username; it does not request repository access. Local stdio runs on your computer and skips this step. [GitHub's OAuth app guide](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app) explains the registration screen.

Open [GitHub Developer settings → OAuth Apps](https://github.com/settings/developers) and choose **New OAuth App**. Use any name. Set **Homepage URL** to your Railway URL and **Authorization callback URL** to:

```text
https://YOUR-DOMAIN/auth/callback
```

Replace `YOUR-DOMAIN` with your actual Railway hostname, without `https://` inside that placeholder. Copy the **Client ID** and generate a **Client secret**.

### 4. Add five Railway variables

In your Railway service, open **Variables** and add these values. Railway redeploys after you save them.

| Variable | What to enter |
|---|---|
| `YTM_ALLOWED_USERS` | Your GitHub username, for example `scandolo`. Separate multiple usernames with commas. |
| `GITHUB_CLIENT_ID` | The OAuth app's client ID. |
| `GITHUB_CLIENT_SECRET` | The OAuth app's client secret. |
| `WEBSHARE_PROXY_USERNAME` | **Proxy Username** from Webshare Proxy Settings; a trailing `-rotate` is okay. |
| `WEBSHARE_PROXY_PASSWORD` | **Proxy Password** from Webshare Proxy Settings. |

Visit `https://YOUR-DOMAIN/healthz`. You are ready when it says `"status":"ok"`. Railway supplies the domain and port automatically; GitHub is the default OAuth provider on Railway.

### 5. Connect your AI app

Your MCP URL is **`https://YOUR-DOMAIN/mcp`**. Use that URL, then sign in with an allowlisted GitHub account.

| Client | Where to paste the MCP URL |
|---|---|
| **Claude** | **Customize → Connectors → + → Add custom connector**, then enable it in a chat with **+ → Connectors**. On Team or Enterprise, an owner adds it in organization settings. [Claude instructions](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp). |
| **ChatGPT** | On a supported plan, enable developer mode; in **Settings → Apps → Create**, enter the MCP URL, choose OAuth, scan tools, and create the app. Availability varies by plan and workspace. [ChatGPT instructions](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt). |
| **Claude Code** | Run the command below, then use `/mcp` in Claude Code to sign in. |

```bash
claude mcp add --transport http --scope user youtube-transcript https://YOUR-DOMAIN/mcp
```

## Give setup to your agent

Copy this into your coding agent if you want it to guide you through Railway. Keep passwords and client secrets in Railway's Variables UI, not in the chat.

```text
Help me set up https://github.com/scandolo/youtube-transcript-mcp on Railway.
Read the current README first. Start with the Deploy on Railway button:
https://railway.com/deploy/youtube-transcript-mcp
Explain why the remote setup needs a rotating residential proxy and GitHub sign-in,
and that the local setup needs neither. Walk me through the shortest path:
deploy, copy my Railway domain, choose a Webshare Rotating Residential plan,
find its Proxy Username and Proxy Password, create a GitHub OAuth app with
the exact callback URL, add the five Railway variables, verify
/healthz says ok, and connect /mcp to my AI app. Ask me which AI app I use.
I will enter secrets directly in Railway; do not ask me to paste them here.
Pause before any paid signup or purchase.
```

## Try your first question

Paste a video URL into your AI app and ask:

> Use the YouTube Transcript connector to summarize this video. Link the exact moment that supports each point: `https://www.youtube.com/watch?v=kCc8FmEb1nY`

For a long video, ask for its chapter list first, then ask about one chapter. To find a passage, ask: “Where does this video discuss attention? Give me the timestamp and link.” For example, in the video above, Karpathy explains that a language model predicts what comes next in a sequence of tokens **[01:21 — watch the moment](https://www.youtube.com/watch?v=kCc8FmEb1nY&t=81s)**.

## What it does

| Tool | What your AI can do with it |
|---|---|
| `search_youtube` | Find videos with YouTube's own search ranking. An optional YouTube Data API key enables reliable cloud search and filters. |
| `youtube_video_info` | Read title, duration, description, available captions, and chapters before fetching a long transcript. |
| `youtube_transcript` | Read the whole video, one chapter, matching passages, or a time window. Supports caption languages such as `en` and `it`. |
| `health` | Check which optional backends and deployment settings are available without exposing secret values. |

The server tries `youtube-transcript-api`, then `yt-dlp`. An optional Groq Whisper fallback can transcribe audio when captions are unavailable. It has an upload size limit and may incur Groq charges.

## Run locally

For a quick local setup, you need Python 3.10+ and Claude Code. Local stdio does not require Railway, GitHub OAuth, or a proxy. Start with your normal internet connection; add a proxy only if YouTube blocks it. This local command connects to Claude Code on your computer. Claude's web connector and ChatGPT connect to remote MCP servers, so use the Railway path for those clients.

```bash
git clone https://github.com/scandolo/youtube-transcript-mcp.git
cd youtube-transcript-mcp
python3 -m venv .venv
.venv/bin/pip install -e .
claude mcp add youtube-transcript --scope user -- "$PWD/.venv/bin/youtube-transcript-mcp"
```

For another local MCP client, run `.venv/bin/youtube-transcript-mcp` as a stdio server. No `.env` file is needed. Your network may still be blocked by YouTube, and some videos have no captions.

## Troubleshooting

| Symptom | Check |
|---|---|
| `/healthz` says `setup_required` | Add the variables it lists in Railway. Generate a public domain if one is missing. `/mcp` stays unavailable until setup is complete. |
| GitHub sign-in fails | The callback URL must exactly match `https://YOUR-DOMAIN/auth/callback`. `YTM_ALLOWED_USERS` needs GitHub usernames, not email addresses. |
| You must reconnect after every deploy | Confirm the template's volume is attached at `/data`. The `health` tool should report `oauth_state_persisted: true`. |
| `IpBlocked` or no transcript | On Railway, confirm you bought **Rotating Residential**, copied credentials from Webshare Proxy Settings, and added both variables. A proxy cannot guarantee access to every video; some videos have no captions. Locally, try your normal connection first. |
| Search or chapters are missing | Add `YOUTUBE_API_KEY` with YouTube Data API v3 enabled. YouTube search costs 100 quota units per request. |
| A working video stops working | Redeploy to pick up newer YouTube extraction libraries; YouTube changes its site often. |

## Configuration and security

The remote endpoint requires GitHub OAuth and checks usernames against `YTM_ALLOWED_USERS` before it runs tools. A new Railway clone starts with MCP disabled until the required settings exist. The health endpoint reports settings status, never secret values. The attached volume keeps OAuth registrations across deploys.

For advanced settings, see [.env.example](.env.example). You can choose Google OAuth instead, use another residential proxy through `YTM_PROXY`, add `YOUTUBE_API_KEY` for metadata and search, or set `GROQ_API_KEY` for audio transcription. Set `JWT_SIGNING_KEY` to a stable random value if you want existing sessions to survive a GitHub client secret rotation.

## License

[MIT](LICENSE) © Federico Scandolara.
