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

**The constraint that drives this:** YouTube blocks datacenter IPs by ASN, not by
request rate — AWS/GCP/Azure/Vercel ranges are identifiable and routinely
blocked. `youtube-transcript-api`'s own docs say you will "most likely" hit
`RequestBlocked` on any cloud deployment. Low personal volume does not
necessarily help, because the block is on the network, not the frequency.

If a cloud deploy gets blocked, the fix is `YTM_PROXY` pointed at a rotating
residential proxy (a few £/month), or running somewhere with a residential IP.

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

`JWT_SIGNING_KEY` keeps sessions valid across restarts.

## Maintenance

`yt-dlp` is in a permanent arms race with YouTube; most "it suddenly stopped
working" reports are a stale copy.

```bash
uv pip install -U yt-dlp youtube-transcript-api
```
