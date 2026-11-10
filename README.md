<div align="center">
  <img src="assets/hero.svg" alt="YouTube video to searchable transcript to AI assistant" width="100%" />

  # YouTube Transcript MCP

  **Ask your AI about a YouTube video. Get an answer you can click back to.**

  [![Checks](https://github.com/scandolo/youtube-transcript-mcp/actions/workflows/checks.yml/badge.svg)](https://github.com/scandolo/youtube-transcript-mcp/actions/workflows/checks.yml) [![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) [![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB.svg)](pyproject.toml) [![MCP](https://img.shields.io/badge/protocol-MCP-8B8DFB.svg)](https://modelcontextprotocol.io/)

  [Claude Desktop](#claude-desktop-and-cowork) · [Claude Code](#claude-code) · [Remote (optional)](#remote-hosting-optional) · [What it does](#what-it-does)
</div>

Turn YouTube captions into readable paragraphs with chapters, timestamps, and links to the exact moment in the video. It runs **on your own computer**: download one file, open it in Claude Desktop, done. No account, proxy, or API key needed, because YouTube sees your normal home connection.

<p align="center">
  <a href="https://github.com/scandolo/youtube-transcript-mcp/releases/latest/download/youtube-transcript-mcp.mcpb"><img src="https://img.shields.io/badge/Download%20for%20Claude%20Desktop-.mcpb-8B8DFB?style=for-the-badge" alt="Download the Claude Desktop extension" /></a>
</p>

Want it on your phone or in Claude on the web too? You can [host it remotely](#remote-hosting-optional), but that needs a paid residential proxy.

## Contents

- [Claude Desktop and Cowork](#claude-desktop-and-cowork)
- [Claude Code](#claude-code)
- [Give setup to your agent](#give-setup-to-your-agent)
- [Try it](#try-it)
- [What it does](#what-it-does)
- [Other MCP clients](#other-mcp-clients)
- [Remote hosting (optional)](#remote-hosting-optional)
- [Troubleshooting](#troubleshooting)
- [Configuration and security](#configuration-and-security)
- [License](#license)

## Claude Desktop and Cowork

Works in regular Claude Desktop chats and in **Cowork in the desktop app**. Cowork on the web cannot run an MCP server on your laptop. [Anthropic's Cowork guide](https://support.claude.com/en/articles/15520349-use-claude-cowork-on-web-desktop-and-mobile) describes this desktop requirement.

1. Click the **Download for Claude Desktop** button above to get `youtube-transcript-mcp.mcpb`.
2. Open the file in [Claude Desktop](https://claude.com/download). If it does not open automatically, use **Settings → Extensions → Advanced settings → Install Extension…** and select the file. Claude installs its Python dependencies automatically. [Anthropic's extension guide](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop) shows the Settings flow.
3. Start a chat (or a Cowork task) and ask about a YouTube video. If Claude asks to enable or allow the tool, approve it.

Keep Claude Desktop open while using the local connector. If your organization disables local MCP servers or desktop extensions, ask your admin to enable them.

## Claude Code

1. Install [Claude Code](https://docs.anthropic.com/en/docs/claude-code/setup) and [uv](https://docs.astral.sh/uv/getting-started/installation/) if you do not already have them. `uv` installs the right Python version and this server's dependencies for you.
2. Copy and run this command in your terminal:

   ```bash
   claude mcp add --scope user youtube-transcript -- "$(command -v uvx)" --from git+https://github.com/scandolo/youtube-transcript-mcp youtube-transcript-mcp
   ```

3. Open Claude Code (or start a new session) and ask it to use the **YouTube Transcript** tools on a video URL. Run `/mcp` if you want to check the connection.

The `--scope user` flag makes the tool available across your projects. The first launch downloads the package; later launches use uv's cache. To remove it, run `claude mcp remove --scope user youtube-transcript`.

## Give setup to your agent

Copy this into Claude Code or another coding agent if you prefer guided setup:

```text
Help me set up https://github.com/scandolo/youtube-transcript-mcp locally.
Read its current README first. Ask whether I use Claude Desktop (or Cowork) or Claude Code
and follow the matching short path. For Claude Code,
install uv if needed and add the server with `claude mcp add --scope user`.
For Claude Desktop, download the latest .mcpb release and walk me through installing
it in Claude Desktop Settings > Extensions. Verify the tools are connected,
then have me try a YouTube URL. Do not set up remote hosting, a proxy, an OAuth app,
or API keys unless I ask for remote hosting or a specific optional feature.
```

## Try it

Paste a video URL into Claude and ask:

> Use the YouTube Transcript tools to summarize this video. Link the exact moment that supports each point: `https://www.youtube.com/watch?v=kCc8FmEb1nY`

For a long video, ask for its chapters first, then ask about one chapter. To find a passage, ask: “Where does this video discuss attention? Give me the timestamp and link.”

<p align="center">
  <img src="assets/demo.gif" alt="Illustrated Claude chat with a user prompt, thinking status, YouTube Transcript tool calls, and a timestamped answer" width="900" />
</p>

Illustrated example with the server's real tool names and [a moment from the sample video](https://www.youtube.com/watch?v=kCc8FmEb1nY&t=98s). [View the still image](assets/demo.png).

## What it does

| Tool | What your AI can do with it |
|---|---|
| `search_youtube` | Find videos with YouTube's search ranking. An optional YouTube Data API key enables reliable cloud search and filters. |
| `youtube_video_info` | Read title, duration, description, available captions, and chapters before fetching a long transcript. |
| `youtube_transcript` | Read the whole video, one chapter, matching passages, or a time window. Supports caption languages such as `en` and `it`. |
| `health` | Check which optional backends and settings are available without exposing secret values. |

The server tries `youtube-transcript-api`, then `yt-dlp`. An optional Groq Whisper fallback can transcribe audio when captions are unavailable; it may incur Groq charges.

## Other MCP clients

The server speaks MCP over **stdio** by default. If your app supports local stdio MCP servers, set its command to `uvx` and its arguments to:

```text
--from git+https://github.com/scandolo/youtube-transcript-mcp youtube-transcript-mcp
```

For development, clone the repo and run `uv sync`, then `uv run youtube-transcript-mcp`. No `.env` file is needed.

## Remote hosting (optional)

Only needed if you want the tools in Claude on your phone, on the web, or in ChatGPT. You can deploy the server to [Vercel](https://vercel.com) (the free Hobby plan is enough), but two things make it harder than the local setup:

- **A residential proxy is required.** YouTube blocks caption requests from cloud IPs, so the server has to send them through home connections. [Webshare](https://www.webshare.io/pricing)'s **Rotating Residential** plan works; their free datacenter proxies do not.
- **Sign-in protects the public URL.** A GitHub OAuth app and an allowlist of usernames keep strangers from using your tools and your proxy bandwidth.

The [remote setup guide](docs/remote-setup.md) walks through it in about 15 minutes. A proxy improves reliability but cannot guarantee every video works.

## Troubleshooting

| Symptom | Check |
|---|---|
| Claude Code cannot find `uvx` | Install [uv](https://docs.astral.sh/uv/getting-started/installation/), open a new terminal, and rerun the command. `command -v uvx` should print a path. |
| Claude Desktop cannot see the tools | Use the **desktop app** (not the web), check that the extension is enabled in **Settings → Extensions**, and start a new chat or Cowork task. A web custom connector cannot reach this local server. |
| `IpBlocked` or no transcript | Your own IP may still be blocked by YouTube, or the video may have no captions. Try another captioned video first. If you host it remotely, see the [remote setup guide](docs/remote-setup.md). |
| Search or chapters are missing | Add `YOUTUBE_API_KEY` with YouTube Data API v3 enabled. Search costs 100 quota units per request. |
| A working video stops working | Update the package or extension to pick up newer YouTube extraction libraries; YouTube changes its site often. |

## Configuration and security

Local stdio runs on your computer and does not need GitHub sign-in. It can make network requests to YouTube and any optional backend you configure. Only install local MCP software from sources you trust.

For advanced settings, see [.env.example](.env.example). You can add `YOUTUBE_API_KEY` for metadata and search, `GROQ_API_KEY` for audio transcription, or `YTM_PROXY` if your connection gets blocked.

## License

[MIT](LICENSE) © Federico Scandolara.
