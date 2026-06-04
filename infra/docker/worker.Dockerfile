# Worker image — Python base + Marp CLI for slide rendering (Day 8 / Session 8B).
#
# Optional for POC: if Marp CLI is installed on the dev host (or reachable via
# `npx`), the studio pipeline runs without this image. It exists so slide
# generation can move to a containerised background worker post-POC without
# re-deriving the toolchain.

FROM python:3.12-slim

# Node is required for Marp CLI; chromium powers the pptx/pdf export backend.
RUN apt-get update && apt-get install -y --no-install-recommends \
        nodejs npm chromium \
    && rm -rf /var/lib/apt/lists/*

# Marp uses this Chromium instead of downloading its own bundled copy.
ENV CHROME_PATH=/usr/bin/chromium

RUN npm install -g @marp-team/marp-cli

# Project deps via uv (matches the dev toolchain).
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN uv pip install --system --no-cache .

# Marp CLI needs --no-sandbox under the slim image's unprivileged container user.
ENV MARP_CLI_CHROME_ARGS=--no-sandbox

CMD ["python", "-c", "print('ASAG worker image — invoke asag.studio.slides.generate_slides')"]
