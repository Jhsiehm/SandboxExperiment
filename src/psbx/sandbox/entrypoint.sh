#!/bin/sh
# Search sidecar only. Do not run the LLM in this process.
# libfaketime: https://github.com/wolfcw/libfaketime.git
set -eu
CUTOFF="${PSBX_FAKETIME:-2012-06-30 12:00:00}"
export FAKETIME="@${CUTOFF}"
export FAKETIME_NO_CACHE=1
export FAKETIME_DONT_FAKE_MONOTONIC=1
if [ -z "${LD_PRELOAD:-}" ]; then
  for lib in \
    /usr/lib/x86_64-linux-gnu/faketime/libfaketime.so.1 \
    /usr/lib/aarch64-linux-gnu/faketime/libfaketime.so.1 \
    /usr/lib/faketime/libfaketime.so.1
  do
    if [ -f "$lib" ]; then
      export LD_PRELOAD="$lib"
      break
    fi
  done
fi
if [ -z "${LD_PRELOAD:-}" ]; then
  echo "libfaketime .so not found" >&2
  exit 1
fi

PORT="${PSBX_SEARCH_PORT:-8766}"
if [ "${PSBX_LOCK_EGRESS:-1}" = "1" ]; then
  if ! command -v iptables >/dev/null 2>&1; then
    echo "iptables missing; cannot lock egress" >&2
    exit 1
  fi
  iptables -F
  iptables -P OUTPUT DROP
  iptables -P INPUT DROP
  iptables -A INPUT -i lo -j ACCEPT
  iptables -A OUTPUT -o lo -j ACCEPT
  iptables -A INPUT -p tcp --dport "$PORT" -j ACCEPT
  iptables -A OUTPUT -p tcp --sport "$PORT" -j ACCEPT
  if command -v ip6tables >/dev/null 2>&1; then
    ip6tables -F 2>/dev/null || true
    ip6tables -P OUTPUT DROP 2>/dev/null || true
    ip6tables -P INPUT DROP 2>/dev/null || true
  fi
fi

exec python -m psbx.sandbox.search_service
