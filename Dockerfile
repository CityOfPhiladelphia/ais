# syntax=docker/dockerfile:1
# =============================================================================
# Stage 1: Builder (installs Python deps + private passyunk data into venv)
# Private SSH key is used ONLY in this stage and never copied to runtime image.
# =============================================================================
FROM python:3.14-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VENV_PATH=/opt/venv

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        git \
        libpq-dev \
        openssh-client && \
    rm -rf /var/lib/apt/lists/*

# Configure SSH for private passyunk_automation repository (builder stage only)
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh && \
    ssh-keyscan -t rsa,ed25519 github.com >> /root/.ssh/known_hosts
COPY ssh-config /root/.ssh/config
COPY passyunk-private.key /root/.ssh/passyunk-private.key
RUN chmod 600 /root/.ssh/config /root/.ssh/passyunk-private.key

RUN python -m venv "$VENV_PATH"
ENV PATH="$VENV_PATH/bin:$PATH"

WORKDIR /ais
COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir --no-deps .

# Verify passyunk & passyunk_automation private data files exist at build time
RUN python -c "\
import site, pathlib, sys; \
sp = pathlib.Path(site.getsitepackages()[0]); \
p_files = ['alias','alias_streets','apt','apt_std','apte','centerline','centerline_streets','directional','landmarks','name_switch','saint','std','suffix']; \
pa_files = ['election_block','usps_alias','usps_cityzip','usps_zip4s']; \
missing = [str(sp/'passyunk'/'pdata'/f'{f}.csv') for f in p_files if not (sp/'passyunk'/'pdata'/f'{f}.csv').is_file()] + \
          [str(sp/'passyunk_automation'/'pdata'/f'{f}.csv') for f in pa_files if not (sp/'passyunk_automation'/'pdata'/f'{f}.csv').is_file()]; \
sys.exit(f'Missing pdata files: {missing}') if missing else print('All passyunk pdata files verified.')"

# =============================================================================
# Stage 2: Minimal Runtime Image (EKS-ready, no SSH keys, no build tools)
# =============================================================================
FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VENV_PATH=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 curl && \
    rm -rf /var/lib/apt/lists/* && \
    useradd --create-home --shell /bin/bash ais

WORKDIR /ais
COPY --from=builder /opt/venv /opt/venv
COPY --chown=ais:ais ais /ais/ais
COPY --chown=ais:ais gunicorn.conf.py /ais/
COPY --chown=ais:ais docker-build-files/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER ais
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/api/health-check || exit 1

ENTRYPOINT ["/entrypoint.sh"]
