# Remote setup on Vercel

[← Back to local setup](../README.md)

Use this only when you want a public MCP URL, for Claude on your phone or the web, or for ChatGPT. For Claude Desktop, Cowork or Claude Code, the [local setup](../README.md) is shorter and more reliable.

Two things are needed that the local setup avoids:

- **A rotating residential proxy (paid).** Vercel sends requests from cloud IPs, which [YouTube blocks for captions](https://github.com/jdepoix/youtube-transcript-api#working-around-ip-bans-requestblocked-or-ipblocked-exception). A residential proxy sends them through ordinary home connections instead.
- **A GitHub OAuth app.** It protects your public URL: only the GitHub usernames you allowlist can call the tools and spend your proxy bandwidth. It only asks GitHub for read access to your profile.

Vercel's free Hobby plan and Upstash's free Redis plan are enough for personal use.

### 1. Create the Vercel project

1. Fork this repo, then in Vercel choose **Add New → Project** and import your fork. No build settings are needed: Vercel runs the ASGI app in [`app.py`](../app.py).
2. Deploy once. The first deployment fails to start until step 5; that is expected. Note your production URL, for example `https://your-project.vercel.app`.

### 2. Add Redis

In the project, open **Storage → Create Database → Upstash for Redis**, pick the **Free** plan and connect it to the project. Vercel sets `REDIS_URL` for you. The server keeps its sign-in state there, encrypted, because serverless functions have no disk that lasts between requests.

### 3. Get a residential proxy

1. Create a [Webshare account](https://dashboard.webshare.io/) and buy a **Rotating Residential** plan. Webshare's free **Proxy Server** and **Static Residential** products do not work for this. See [Webshare's plans](https://www.webshare.io/pricing).
2. Open [Webshare Proxy Settings](https://dashboard.webshare.io/proxy/settings) and copy **Proxy Username** and **Proxy Password**. A username ending in `-rotate` is fine.

Using another provider? Put its full proxy URL in `YTM_PROXY` instead. See [.env.example](../.env.example).

### 4. Create a GitHub OAuth app

Open [GitHub Developer settings → OAuth Apps → New OAuth App](https://github.com/settings/developers). Use any name, set **Homepage URL** to your Vercel URL and **Authorization callback URL** to:

```text
https://YOUR-PROJECT.vercel.app/auth/callback
```

Copy the **Client ID** and generate a **Client secret**.

### 5. Add the environment variables

In **Settings → Environment Variables**, add these for Production, then redeploy:

| Variable | Value |
|---|---|
| `YTM_AUTH_PROVIDER` | `github` |
| `YTM_ALLOWED_USERS` | Your GitHub username. Separate several with commas. |
| `GITHUB_CLIENT_ID` | The OAuth app's client ID |
| `GITHUB_CLIENT_SECRET` | The OAuth app's client secret |
| `JWT_SIGNING_KEY` | A random value: run `openssl rand -hex 32` |
| `WEBSHARE_PROXY_USERNAME` | Webshare **Proxy Username** |
| `WEBSHARE_PROXY_PASSWORD` | Webshare **Proxy Password** |

Optional: `YOUTUBE_API_KEY` for faster metadata and filtered search. If you restrict the key to websites in Google Cloud, allow your Vercel URL.

Visit `https://YOUR-PROJECT.vercel.app/healthz`. You are ready when it says `"status":"ok"`.

### 6. Connect your AI app

Your MCP URL is **`https://YOUR-PROJECT.vercel.app/mcp`**. Add it, then sign in with an allowlisted GitHub account.

| Client | Where to add the MCP URL |
|---|---|
| **Claude** (web and mobile) | **Customize → Connectors → + → Add custom connector**. Connectors added on the web also appear in the mobile apps. [Claude instructions](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp). |
| **ChatGPT** | On a supported plan, enable developer mode; in **Settings → Apps → Create**, enter the MCP URL and choose OAuth. [ChatGPT instructions](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt). |
| **Claude Code** | `claude mcp add --transport http --scope user youtube-transcript https://YOUR-PROJECT.vercel.app/mcp`, then `/mcp` to sign in. |

## Troubleshooting

| Symptom | Check |
|---|---|
| Every request returns 500 | Open the deployment's runtime logs. Usually a missing variable from step 5, or Redis not connected (no `REDIS_URL`). |
| GitHub sign-in fails | The callback URL must exactly match `https://YOUR-PROJECT.vercel.app/auth/callback`. `YTM_ALLOWED_USERS` takes GitHub usernames, not emails. |
| "Not authorized: … is not on the allowlist" | You signed in with a different GitHub account. Sign out of GitHub in that browser, or add the username. |
| `IpBlocked` or no transcript | Confirm the plan is **Rotating Residential** and both Webshare variables are set. Some videos have no captions. |
| Search ignores filters | Add `YOUTUBE_API_KEY`; without it search falls back to yt-dlp. If the key is website-restricted, allow your Vercel URL. |

Videos with captions disabled need the Whisper fallback (`GROQ_API_KEY`), which also needs ffmpeg and so does not run on Vercel. Use the local setup for those.
