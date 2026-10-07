# Score-render toolchain for bard: abcm2ps (SVG engraving), abcmidi (ABC ->
# MIDI), rsvg-convert (SVG -> PNG), and the IPA font covering Japanese lyrics.
# render_score_png.py falls back to this image when the host lacks the tools.
# Published to ghcr.io/<owner>/bard-tools by publish-bard-images.yml and pinned
# by digest in plugins/bard/skills/bard-render/tools-image.json.
FROM debian:13-slim@sha256:a99cfc517144bc59b1978475ec53b46ecabec7e43635402ee5b77cc54cd1b20a

LABEL org.opencontainers.image.source="https://github.com/VibeBB/bard-agent" \
      org.opencontainers.image.licenses="BSD-3-Clause"

ENV DEBIAN_FRONTEND=noninteractive

# Fail the build when the left side of a verification pipe breaks instead
# of silently passing the right side.
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# apt resilience: Acquire::Retries covers single fetches, not a mirror that
# is down for minutes (archive.ubuntu.com outage killed several builds).
# Retry the whole update+install round with bounded backoff.
RUN for attempt in 1 2 3 4 5; do \
        apt-get -o Acquire::Retries=5 update \
        && apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
            abcm2ps \
            abcmidi \
            fontconfig \
            fonts-ipafont \
            librsvg2-bin \
        && rm -rf /var/lib/apt/lists/* \
        && break; \
        [ "$attempt" = 5 ] && exit 1; \
        echo "::warning::apt update+install attempt ${attempt} failed; retrying"; \
        sleep $((attempt * 30)); \
    done \
    && abcm2ps -V 2>&1 | grep -E "abcm2ps-[0-9]" \
    && abc2midi -ver 2>&1 | grep -E "abc2midi" \
    && rsvg-convert --version | grep -E "rsvg-convert version" \
    && fc-list | grep -qi "IPA" \
    && printf 'X:1\nT:smoke\nM:4/4\nL:1/8\nK:C\nC D E F |]\n' > /tmp/smoke.abc \
    && abcm2ps -g /tmp/smoke.abc -O /tmp/smoke.svg \
    && rsvg-convert /tmp/smoke001.svg -o /tmp/smoke.png \
    && test -s /tmp/smoke.png \
    && rm -f /tmp/smoke*

# The pinned debian:13-slim digest keeps shipping the debs Trivy flags at
# publish (CVE-2026-103111 libpcre2-8-0; CVE-2026-75804 and CVE-2026-84782
# openssl/libssl3t64). Upgrade just those packages inside the build so the
# publish gate stays green.
RUN for attempt in 1 2 3 4 5; do \
        apt-get -o Acquire::Retries=5 update \
        && apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
            --only-upgrade \
            libpcre2-8-0 \
            libssl3t64 \
            openssl-provider-legacy \
        && rm -rf /var/lib/apt/lists/* \
        && break; \
        [ "$attempt" = 5 ] && exit 1; \
        echo "::warning::apt update+install attempt ${attempt} failed; retrying"; \
        sleep $((attempt * 30)); \
    done

# Tighten the login.defs umask to 027 (Lynis AUTH-9328): the image has no
# interactive users, so files created at runtime stay group-readable only.
RUN printf 'UMASK 027\n' >> /etc/login.defs

# Callers bind-mount the song directory here and run the tools via sh -c.
WORKDIR /work
