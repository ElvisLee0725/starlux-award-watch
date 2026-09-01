# Linux (amd64) image: real Google Chrome under Xvfb + the monitor loop.
# Best for a home box / mini-PC on a residential IP. A cloud datacenter IP
# gets Akamai-challenged constantly with no human to clear it — see deploy/README.md.
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    STARLUX_CONFIG=/app/config.yaml

# Chrome + a virtual display + the shared libs Chrome needs
RUN apt-get update && apt-get install -y --no-install-recommends \
      wget gnupg ca-certificates xvfb fonts-liberation tini \
      libasound2 libnss3 libnspr4 libxss1 libgbm1 libgtk-3-0 libxshmfence1 \
      libx11-xcb1 libdrm2 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
 && wget -qO- https://dl.google.com/linux/linux_signing_key.pub \
      | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
 && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] \
https://dl.google.com/linux/chrome/deb/ stable main" \
      > /etc/apt/sources.list.d/google-chrome.list \
 && apt-get update && apt-get install -y --no-install-recommends google-chrome-stable \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY config.yaml ./
COPY scripts ./scripts

# chrome-profile + state.db + agent state live here; mount a volume
VOLUME ["/app/data"]

# tini reaps zombie Chrome procs; xvfb-run gives Chrome a headed display
ENTRYPOINT ["tini", "--", "xvfb-run", "-a", "--server-args=-screen 0 1440x950x24"]
CMD ["python", "-m", "starlux_award_watch"]
