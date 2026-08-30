#!/usr/bin/with-contenv bashio
set -e

bashio::log.info "Starting Weather4Lox HA 0.3.5 service"
exec python3 /server_035.py
