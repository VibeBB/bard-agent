# Score-render toolchain for bard: abcm2ps (SVG engraving), abcmidi (ABC ->
# MIDI), rsvg-convert (SVG -> PNG), and the IPA font covering Japanese lyrics.
# render_score_png.py falls back to this image when the host lacks the tools.
# Published to ghcr.io/<owner>/bard-tools by publish-bard-images.yml and pinned
# by digest in plugins/bard/skills/bard-render/tools-image.json.
FROM ubuntu:26.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        abcm2ps \
        abcmidi \
        fontconfig \
        fonts-ipafont \
        librsvg2-bin \
    && rm -rf /var/lib/apt/lists/* \
    && abcm2ps -V 2>&1 | grep -E "abcm2ps-[0-9]" \
    && abc2midi -v 2>&1 | grep -E "abc2midi" \
    && rsvg-convert --version | grep -E "rsvg-convert version" \
    && fc-list | grep -qi "IPA" \
    && printf 'X:1\nT:smoke\nM:4/4\nL:1/8\nK:C\nC D E F |]\n' > /tmp/smoke.abc \
    && abcm2ps -g /tmp/smoke.abc -O /tmp/smoke.svg \
    && rsvg-convert /tmp/smoke001.svg -o /tmp/smoke.png \
    && test -s /tmp/smoke.png \
    && rm -f /tmp/smoke*

# Callers bind-mount the song directory here and run the tools via sh -c.
WORKDIR /work
