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
COPY bootstrap.py /bootstrap.py
COPY providers.py /providers.py
COPY ha_entities.py /ha_entities.py
COPY loxone_format2.py /loxone_format2.py
COPY protocol /protocol

RUN chmod a+x /run.sh

CMD ["/run.sh"]
