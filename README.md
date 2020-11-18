# dpdk-telemetry-exporter
A small DPDK telemetry exporter

## Run in docker

The recommended way when running locally. Remember to mount the dpdk run dir as a volume and add extra options to the command line, e.g.:
```bash
$ docker run --rm --name exporter -p 8000:8000 -v /var/run/dpdk/:/var/run/dpdk/ docker.pkg.github.com/nfvri/dpdk-telemetry-exporter/dpdk-telemetry-exporter:0.1 dpdkTelemetryExporter -vvv -T 5
```
