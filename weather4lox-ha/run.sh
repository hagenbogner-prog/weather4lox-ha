#!/usr/bin/with-contenv bashio
set -e

bashio::log.info "Starting Weather4Lox HA test service"
exec python3 /server.py
