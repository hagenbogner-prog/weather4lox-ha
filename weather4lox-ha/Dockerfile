FROM ghcr.io/home-assistant/base:latest

ARG BUILD_VERSION
ARG BUILD_ARCH

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

RUN apk add --no-cache python3

COPY run.sh /run.sh
COPY server.py /server.py
COPY server_035.py /server_035.py
COPY live_data.py /live_data.py
COPY json_compat.py /json_compat.py
COPY bootstrap.py /bootstrap.py
RUN chmod a+x /run.sh

CMD ["/run.sh"]
