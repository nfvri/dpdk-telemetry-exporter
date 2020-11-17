FROM debian:stable

MAINTAINER angelouev@intracom-telecom.com
LABEL Vendor="Intracom Telecom S.A."
LABEL Description="DPDK Telemetry exporter image"

RUN apt-get update && apt-get install -y python3 python3-pip && apt clean

COPY ./ /opt/dpdkTelemetryExporter

WORKDIR /opt/dpdkTelemetryExporter

RUN python3 setup.py install

CMD ["/bin/bash","-c","while true; do echo debug; sleep 10;done"]
