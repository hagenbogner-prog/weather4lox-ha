#!/usr/bin/with-contenv bashio
set -e

bashio::log.info "Starting Weather4Lox HA 0.4.2 service"
exec python3 /bootstrap.py
