#!/bin/bash
# Remote dev entrypoint: tuned for rootless Docker bind-mounts where the
# container "root" maps to an unprivileged host UID.  Unlike the default
# entrypoint, this one never drops to a hard-coded `hermes` user when chown
# fails — that branch is the cause of /opt/data permission denied loops
# under rootless Docker.
set -e

HERMES_HOME="${HERMES_HOME:-/opt/data}"
INSTALL_DIR="/opt/hermes"

mkdir -p "$HERMES_HOME"

# --- Privilege handling ---
# Two execution modes are supported:
#
#   rootful Docker  -> container UID 0 == real root.  We optionally remap
#                      the bundled `hermes` user to HERMES_UID/HERMES_GID,
#                      chown the volume, then `gosu hermes` so the agent
#                      runs unprivileged.
#
#   rootless Docker -> container UID 0 maps to a non-zero host UID.  We
#                      MUST stay as container root: the bind mount is
#                      owned by that host UID and any chown -> gosu drop
#                      would push files into the unmapped subuid range
#                      and break host-side visibility.
#
# Detect rootless via /proc/self/uid_map: rootful starts with `0 0`,
# rootless starts with `0 <non-zero host UID>`.
is_rootless_user_namespace() {
    [ -r /proc/self/uid_map ] || return 1
    awk 'NR==1 { exit ($2 == 0 ? 1 : 0) }' /proc/self/uid_map
}

if [ "$(id -u)" = "0" ]; then
    if is_rootless_user_namespace; then
        echo "[entrypoint.remote.dev] rootless user namespace detected; staying as container root"
    else
        if [ -n "${HERMES_UID:-}" ] && [ "$HERMES_UID" != "$(id -u hermes)" ]; then
            usermod -u "$HERMES_UID" hermes 2>/dev/null || true
        fi
        if [ -n "${HERMES_GID:-}" ] && [ "$HERMES_GID" != "$(id -g hermes)" ]; then
            groupmod -o -g "$HERMES_GID" hermes 2>/dev/null || true
        fi

        if chown -R hermes:hermes "$HERMES_HOME" 2>/dev/null; then
            actual_hermes_uid="$(id -u hermes)"
            xdg_runtime="/run/user/${actual_hermes_uid}"
            mkdir -p "$xdg_runtime"
            chown hermes:hermes "$xdg_runtime" 2>/dev/null || true
            chmod 700 "$xdg_runtime" 2>/dev/null || true
            echo "[entrypoint.remote.dev] rootful Docker; dropping to hermes user"
            exec gosu hermes "$0" "$@"
        fi

        echo "[entrypoint.remote.dev] WARN: chown $HERMES_HOME failed under rootful Docker"
        echo "[entrypoint.remote.dev] continuing as container root"
    fi
fi

# --- Running as the final UID from here (hermes, host user, or container root) ---

current_uid="$(id -u)"

# Probe writability before touching anything else; fail fast with a hint.
if ! touch "$HERMES_HOME/.write-probe" 2>/dev/null; then
    echo "[entrypoint.remote.dev] ERROR: $HERMES_HOME is not writable by uid=$current_uid gid=$(id -g)" >&2
    echo "[entrypoint.remote.dev] On the host, run: sudo chown -R \$(id -u):\$(id -g) ~/.hermes" >&2
    exit 1
fi
rm -f "$HERMES_HOME/.write-probe"

# Route per-user paths that subprocesses (git, ssh, gh, npm, Chromium,
# Playwright) expect to be writable.  TMPDIR is intentionally left alone so
# agent-browser keeps using the container's tmpfs /tmp for short-lived
# Unix domain sockets — much faster than the bind-mounted volume.
export HOME="$HERMES_HOME/home"
export XDG_CACHE_HOME="$HERMES_HOME/cache"
export XDG_CONFIG_HOME="$HERMES_HOME/config"
export XDG_DATA_HOME="$HERMES_HOME/data"
export XDG_STATE_HOME="$HERMES_HOME/state"
export XDG_RUNTIME_DIR="$HERMES_HOME/runtime/$current_uid"

mkdir -p \
    "$HERMES_HOME"/{cron,sessions,logs,hooks,memories,skills,skins,plans,workspace,home,cache,config,data,state} \
    "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR" 2>/dev/null || true

# Skills are shared between the dashboard TUI and gateway/API service.  Older
# agent-created SKILL.md files may be 0600, so make the tree readable/traversable
# across same-volume containers without making ordinary files executable.
chmod -R u+rwX,go+rX "$HERMES_HOME/skills" 2>/dev/null || \
    echo "[entrypoint.remote.dev] WARN: could not normalize skill permissions"

# Activate the prebuilt venv (it lives under INSTALL_DIR, owned by the
# image build user; we only need read+exec, which is granted via the
# `chmod -R a+rX` in Dockerfile.dev).
source "${INSTALL_DIR}/.venv/bin/activate"

if [ ! -f "$HERMES_HOME/.env" ] && [ -f "$INSTALL_DIR/.env.example" ]; then
    cp "$INSTALL_DIR/.env.example" "$HERMES_HOME/.env"
fi

if [ ! -f "$HERMES_HOME/config.yaml" ] && [ -f "$INSTALL_DIR/cli-config.yaml.example" ]; then
    cp "$INSTALL_DIR/cli-config.yaml.example" "$HERMES_HOME/config.yaml"
fi

if [ ! -f "$HERMES_HOME/SOUL.md" ] && [ -f "$INSTALL_DIR/docker/SOUL.md" ]; then
    cp "$INSTALL_DIR/docker/SOUL.md" "$HERMES_HOME/SOUL.md"
fi

if [ -d "$INSTALL_DIR/skills" ] && [ -f "$INSTALL_DIR/tools/skills_sync.py" ]; then
    python3 "$INSTALL_DIR/tools/skills_sync.py" || \
        echo "[entrypoint.remote.dev] skills_sync.py failed; continuing"
fi

# Same dispatch contract as docker/entrypoint.sh: run a bare command if it
# resolves on PATH, otherwise treat args as a hermes subcommand.
if [ $# -gt 0 ] && command -v "$1" >/dev/null 2>&1; then
    exec "$@"
fi
exec hermes "$@"
