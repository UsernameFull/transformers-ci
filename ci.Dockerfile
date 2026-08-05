# CI image for the transformers daily sync + full test coverage on ARM64 Ascend runners.
# Base: CANN 9.0.0 (Ascend 910B), Ubuntu 22.04, Python 3.11.
# Pre-bakes the heavy/stable stack (torch, extras deps, ffmpeg) so per-run CI only
# installs the transformers editable package itself. Rebuilt weekly by build-ci-image.yml.
FROM ascendai/cann:9.0.0-910b-ubuntu22.04-py3.11

ENV DEBIAN_FRONTEND=noninteractive

# System dependencies: ffmpeg (torchcodec audio/video decoding), git, curl
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        git \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Bake the ML stack matching transformers [torch,testing,vision] extras plus audio helpers.
# Snapshot from upstream main; versions follow the pins in upstream setup.py at build time.
RUN python3 -m pip install --no-cache-dir --upgrade pip \
    && git clone --depth=1 https://github.com/huggingface/transformers.git /opt/transformers-snapshot \
    && python3 -m pip install --no-cache-dir "/opt/transformers-snapshot[torch,testing,vision]" \
    && python3 -m pip install --no-cache-dir librosa torchcodec \
    && rm -rf /opt/transformers-snapshot /root/.cache/pip
