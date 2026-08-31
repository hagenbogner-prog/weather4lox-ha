#!/usr/bin/with-contenv bashio
set -e

bashio::log.info "Starting Weather4Lox HA 0.3.7 service"
exec python3 /live_data.py
