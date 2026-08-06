# youtube-transcript-mcp

A private MCP server that turns a YouTube link into a transcript an agent can
actually work with — reachable from Claude Code anywhere, and from Claude on
mobile.

Built for one use case: watching a lot of educational YouTube and then
discussing it with Claude, where Claude needs to genuinely know what's in the
video.

## What makes the output good

Raw YouTube captions are bad input for a model. Measured on Karpathy's
*Let's build GPT* (1h56m):

| | Raw captions | This server |
|---|---|---|
| Units to read | 2,955 fragments | 187 blocks |
| Avg words per unit | 7.1 | 112.4 |
| Fragments split mid-sentence | constant | merged |
| Chapter structure | none | 30 chapters, with deep links |
| Answering one question | ~28k tokens | ~1–3k tokens |

Concretely:

- **Fragments are merged into paragraphs** aligned to the video's own chapters.
  16× fewer units to read, and no more mid-sentence breaks.
- **Every block carries a timestamp and a deep link** (`youtu.be/ID?t=1234`), so
  Claude can cite the exact moment back to you instead of paraphrasing vaguely.
- **You rarely need the whole transcript.** Fetch one chapter by number or
  title, or search for a term and get just the matching passages with context.
- **Search is punctuation-insensitive.** Auto-captions never hyphenate
  ("self attention") but chapter titles do ("self-attention"). Searching the
  term you saw in the chapter list has to work, so both sides are normalised.
  Phrase match first, then falls back to any-term.

## Tools

### `search_youtube(query, ...)`
YouTube's own search, not a web search that happens to return videos. The
distinction is the point: a web index ranks on links and coverage, so it hands
back the famous videos, while YouTube ranks within its own catalogue on watch
behaviour, freshness and channel authority. This is what you would have found by
typing into the search box.

| Arg | Purpose |
|---|---|
| `limit` | 1–50, default 10 |
| `order` | `relevance` (default), `date`, `viewCount`, `rating`, `title` |
| `duration` | `any` (default), `short` <4min, `medium` 4–20min, `long` >20min |
| `published_after` | `YYYY-MM-DD` |
| `channel_id` | Restrict to one channel (a `UC…` id, not a handle) |

Every result carries a `url`, so hand one straight to the tools below. Served by
the Data API, which costs **100 quota units per search** against the 10,000/day
free allowance — roughly **100 searches a day**. Past that it falls back to
yt-dlp, which has no quota but ignores the filters and says so in `warnings`.

### `youtube_video_info(url)`
Cheap orientation, no transcript. Title, channel, duration, chapter list with
deep links, description, available caption languages. Call this first for a long
video, then pull only the part you need.

### `youtube_transcript(url, ...)`
| Arg | Purpose |
|---|---|
| `format` | `chapters` (headed sections, default), `timestamped`, `plain` |
| `chapter` | `"5"` or `"attention"` — one section by number or title |
| `query` | Only passages mentioning these words, plus context |
| `start` / `end` | Explicit time window in seconds |
| `language` | Caption language code; most videos offer 100+ auto-translations |
| `max_chars` | Response cap (default 40k chars ≈ 10k tokens) |

Truncated responses say so and carry `resume_at_seconds` to continue from.

### `health()`
Config and backend availability. No secrets. Useful for debugging a deploy.

## Backends

Three, tried in order, degrading rather than failing:

1. **`youtube-transcript-api`** — one request to the caption endpoint. Fastest.
2. **`yt-dlp`** — heavier, but carries chapters and full metadata.
3. **Groq Whisper** — only for videos with captions disabled. Needs `GROQ_API_KEY`
   and ffmpeg; never runs unless the first two come back empty.

Measured note: on a video with captions, backends 1 and 2 return *byte-identical*
text. They're redundancy for uptime, not a quality tradeoff. Backend 2 does add
chapters and metadata, which backend 1 has no concept of.

## Auth

OAuth proves *someone* authenticated; the allowlist is what makes it *you*.

**The identity you allowlist depends on the provider:**

| Provider | `YTM_ALLOWED_USERS` contains | Example |
|---|---|---|
| `github` | GitHub **usernames** | `scandolo` |
| `google` | **email addresses** | `you@gmail.com` |

So if you want to allow specific *emails*, use Google. GitHub identifies you by
username — GitHub's API only exposes an email if you've made it public, so
username is the reliable claim.

Enforcement is in middleware, not per-tool, so a tool added later can't ship
unprotected. It fails closed: no resolvable identity means no tool call. The
server refuses to start if auth is on and the allowlist is empty.

## Where to run it

**Measured, not theorised:** deployed to Railway, the very first transcript
request returned `IpBlocked` in 6 seconds. YouTube blocks by ASN, not by request
rate, so low personal volume does not help — the block is on the network.
Every backend failed identically, because they all share the one exit IP.

**A cloud deploy therefore needs a residential proxy.** Set
`WEBSHARE_PROXY_USERNAME` / `WEBSHARE_PROXY_PASSWORD` from a Webshare
**"Residential"** package — not "Proxy Server" (that is the free datacenter
tier, blocked exactly like the host is) and not "Static Residential".

*Rotating* is the operative word, and it is a configuration detail with teeth:
Webshare hands out per-session usernames like `user-1`, each pinned to one
residential IP, and one flagged IP then fails every request. The rotating form
is `user-rotate`, which draws a fresh IP per request. This server appends that
suffix for you and retries a blocked request onto a new IP, so supply the plain
username. Measured: `user-1` was blocked outright; `user-rotate` was not.

Budget a few £/month. The alternative is running somewhere that already has a
residential IP (a machine at home, published via a tunnel).

Not a serverless workload, either. FastMCP's streamable HTTP initialises its
session manager in the ASGI lifespan and holds MCP sessions in memory between
requests. Vercel's Python builder also ignores `api/` when a `pyproject.toml` is
present, and never produced a function at all. Use a persistent container.

## Deploying on Railway

The `Dockerfile` and `railway.json` are ready; Railway builds from the
Dockerfile and healthchecks `/healthz`.

`RAILWAY_PUBLIC_DOMAIN` is injected by the platform, so **`YTM_BASE_URL`
configures itself** — OAuth discovery advertises the right domain with no
manual step. `PORT` is honoured automatically too.

| Variable | When | Value |
|---|---|---|
| `WEBSHARE_PROXY_USERNAME` / `WEBSHARE_PROXY_PASSWORD` | **required in the cloud** | from Webshare's proxy settings, plain username |
| `YTM_PROXY` | instead of the pair above | `http://user:pass@host:port` |
| `YTM_AUTH_PROVIDER` | for remote access | `github` or `google` |
| `YTM_ALLOWED_USERS` | with auth | GitHub username, or email for Google |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | with GitHub auth | from the OAuth app |
| `JWT_SIGNING_KEY` | with auth | `openssl rand -hex 32` |
| `GROQ_API_KEY` | optional | enables the Whisper fallback |

The GitHub OAuth app's callback URL must be exactly
`https://<your-railway-domain>/auth/callback`.

### Mount a volume, or you will reauthorize on every deploy

FastMCP stores registered OAuth clients on disk. Railway rebuilds the container
filesystem on every deploy — and again whenever the app wakes from sleep — so
without a volume those registrations vanish, the connector's `client_id` stops
being recognised, and the client is told to authorize again after every ship.

Attach a volume to the service (any mount path, e.g. `/data`). Railway then
injects `RAILWAY_VOLUME_MOUNT_PATH` and the server stores OAuth state there
automatically. `health` reports `oauth_state_persisted`; if that is `false`,
sessions will not survive the next deploy.

## Setup

```bash
uv venv --python 3.12
uv pip install -e .
cp .env.example .env
```

### Local (Claude Code on this machine)

Defaults are stdio, no auth:

```bash
claude mcp add youtube-transcript --scope user -- \
  ~/code/youtube-transcript-mcp/.venv/bin/youtube-transcript-mcp
```

### Remote with OAuth

Claude Code accepts a static bearer header, but claude.ai custom connectors do
OAuth discovery and give you no field for one — so mobile needs real OAuth.

1. GitHub OAuth app at <https://github.com/settings/developers>. Callback URL
   must be exactly `${YTM_BASE_URL}/auth/callback`.
2. In `.env`:
   ```
   YTM_TRANSPORT=http
   YTM_AUTH_PROVIDER=github
   YTM_BASE_URL=https://your-hostname
   YTM_ALLOWED_USERS=your-github-username
   GITHUB_CLIENT_ID=...
   GITHUB_CLIENT_SECRET=...
   JWT_SIGNING_KEY=$(openssl rand -hex 32)
   ```
3. claude.ai → Settings → Connectors → Add custom connector.

`JWT_SIGNING_KEY` signs issued sessions. Setting it keeps them independent of
the OAuth client secret, so rotating that secret doesn't sign everyone out. It
is not what carries sessions across a deploy — a mounted volume is.

## Maintenance

`yt-dlp` is in a permanent arms race with YouTube; most "it suddenly stopped
working" reports are a stale copy.

```bash
uv pip install -U yt-dlp youtube-transcript-api
```
