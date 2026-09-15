#!/bin/sh
# Search sidecar only. Do not run the LLM in this process.
# libfaketime: https://github.com/wolfcw/libfaketime.git
set -eu
CUTOFF="${PSBX_FAKETIME:-2012-06-30 12:00:00}"
# An absolute timestamp freezes libfaketime. Prefixing it with "@" would
# start the clock there and let it advance with real container uptime.
export FAKETIME="${CUTOFF}"
export FAKETIME_NO_CACHE=1
export FAKETIME_DONT_FAKE_MONOTONIC=1
FAKETIME_LIB="${LD_PRELOAD:-}"
if [ -z "${FAKETIME_LIB}" ]; then
  for lib in \
    /usr/lib/x86_64-linux-gnu/faketime/libfaketime.so.1 \
    /usr/lib/aarch64-linux-gnu/faketime/libfaketime.so.1 \
    /usr/lib/faketime/libfaketime.so.1
  do
    if [ -f "$lib" ]; then
      FAKETIME_LIB="$lib"
      break
    fi
  done
fi
if [ -z "${FAKETIME_LIB}" ]; then
  echo "libfaketime .so not found" >&2
  exit 1
fi
# Do not preload libfaketime into the root entrypoint or setpriv. Loading it
# only after the UID switch keeps its internal state owned by the psbx user.
unset LD_PRELOAD

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

# NET_ADMIN configures the firewall; SETUID/SETGID perform this one-way
# identity switch. Changing away from UID 0 clears the service's effective
# capabilities, and no-new-privs prevents it from acquiring them again.
exec setpriv --reuid=psbx --regid=psbx --init-groups --no-new-privs \
  env LD_PRELOAD="${FAKETIME_LIB}" python -m psbx.sandbox.search_service
