# Weather4Lox HA — test add-on

Experimental diagnostic build for Home Assistant OS.

## Installation

Add the GitHub repository to Home Assistant's add-on/app repository list:

`https://github.com/hagenbogner-prog/weather4lox-ha`

Install **Weather4Lox HA** and start it.

## First tests

From another device on the LAN:

```bash
curl http://192.168.178.158:6066/health
```

Expected:

```text
lox-weather-ha-test: OK
```

Then inspect the data:

```bash
curl http://192.168.178.158:6066/raw
```

Finally simulate a Loxone request:

```bash
curl "http://192.168.178.158:6066/forecast/?user=loxone_TEST&coord=10.681,48.56&asl=450&format=2&new_api=1"
```

## DNS test

```bash
nslookup weather.loxone.com
```

It should resolve to the Home Assistant IP.

## Logging

Open the add-on log in Home Assistant. Every request is logged, including the query parameters sent by the Miniserver. The test build also logs the Home Assistant weather snapshot and response size.

## Important

This is a compatibility test build, not a production Weather4Lox replacement yet. Forecast mapping and exact Gen-1 response compatibility still need to be verified against the real Miniserver and the original Weather4Lox implementation.
