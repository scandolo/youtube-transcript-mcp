# Remote setup on Railway

[← Back to local setup](../README.md)

Use this only when you need a public MCP URL for Claude on the web or ChatGPT. For Claude Code or Cowork in Claude Desktop, the [local setup](../README.md) is shorter and usually more reliable. Railway hosting and a rotating residential proxy can cost money.

Railway's server sends requests from a cloud IP, which [YouTube often blocks for captions](https://github.com/jdepoix/youtube-transcript-api#working-around-ip-bans-requestblocked-or-ipblocked-exception). A **residential proxy** sends those requests through ordinary home internet IPs instead. GitHub sign-in protects your public MCP URL and your proxy bandwidth; it is unrelated to reading YouTube. This Railway template currently requires both for a working remote deployment. A proxy improves reliability but cannot guarantee every video will work.

### 1. Deploy

Click **[Deploy on Railway](https://railway.com/deploy/youtube-transcript-mcp)**, choose your Railway workspace, and click **Deploy**. The template uses this GitHub repo and sets up the public domain, `/healthz` health check, and persistent `/data` volume for you. Open the new service in Railway and copy its `https://…up.railway.app` URL from **Settings → Networking**.

The first deployment is intentionally in setup mode: `/healthz` tells you which settings remain, and `/mcp` does not serve tools until setup is complete.

### 2. Get a residential proxy

1. Create a [Webshare account](https://dashboard.webshare.io/) and choose a **Rotating Residential** plan in **Plans & Pricing**. This is a paid plan; Webshare's free **Proxy Server** and **Static Residential** products are different. See [Webshare's plan comparison](https://www.webshare.io/pricing).
2. Open [Webshare Proxy Settings](https://dashboard.webshare.io/proxy/settings). Copy **Proxy Username** and **Proxy Password**. You do not need to configure an endpoint or choose a country; the server uses Webshare's rotating residential endpoint automatically. A username ending in `-rotate` is fine.
3. Keep those credentials for step 4. Enter them only in Railway Variables, never in an AI chat or GitHub file.

If you already use another rotating residential provider, set its full proxy URL in `YTM_PROXY` instead of the two Webshare variables. See [.env.example](../.env.example).

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

## Troubleshooting

| Symptom | Check |
|---|---|
| `/healthz` says `setup_required` | Add the variables it lists in Railway. Generate a public domain if one is missing. `/mcp` stays unavailable until setup is complete. |
| GitHub sign-in fails | The callback URL must exactly match `https://YOUR-DOMAIN/auth/callback`. `YTM_ALLOWED_USERS` needs GitHub usernames, not email addresses. |
| You must reconnect after every deploy | Confirm the template's volume is attached at `/data`. The `health` tool should report `oauth_state_persisted: true`. |
| `IpBlocked` or no transcript | Confirm you bought **Rotating Residential**, copied credentials from Webshare Proxy Settings, and added both variables. Some videos have no captions. |

## Advanced settings

See [.env.example](../.env.example) for other options. You can choose Google OAuth, use another residential proxy through `YTM_PROXY`, add `YOUTUBE_API_KEY` for metadata and search, or set `GROQ_API_KEY` for audio transcription. Set `JWT_SIGNING_KEY` to a stable random value if you want existing sessions to survive a GitHub client secret rotation.
