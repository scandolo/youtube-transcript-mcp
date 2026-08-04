# Persistent process, not serverless — see README "Where to run it".
# FastMCP's streamable HTTP initialises its session manager in the ASGI
# lifespan and keeps MCP sessions in memory, so it needs a process that stays
# up between requests.
FROM python:3.12-slim

# ffmpeg is only needed for the Whisper fallback (videos with captions disabled).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY youtube_transcript_mcp ./youtube_transcript_mcp

ENV YTM_TRANSPORT=http \
    YTM_HOST=0.0.0.0 \
    YTM_PORT=8080 \
    PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["python", "-m", "youtube_transcript_mcp.server"]
