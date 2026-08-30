ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM ${BUILD_FROM}

RUN apk add --no-cache python3

COPY run.sh /run.sh
COPY server.py /server.py
RUN chmod a+x /run.sh

CMD ["/run.sh"]
