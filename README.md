# dpdk-telemetry-exporter
A small DPDK telemetry exporter

![dpdk-telemetry-exporter](/dte_grafana_screenshot.png?raw=true "Grafana screenshot of DPDK exported metrics from Prometheus")

## Run in docker

The recommended way when running locally. Remember to mount the dpdk run dir as a volume and add extra options to the command line, e.g.:
```bash
$ docker run --rm --name exporter -p 8000:8000 -v /var/run/dpdk/:/var/run/dpdk/ nfvri/dpdk-telemetry-exporter:0.1 dpdkTelemetryExporter -vvv -T 5
```

## Run as sidecar

To run as a sidecar, add the exporter container to your Deployment/Statefulset/Daemonset definition with mount access to the dpdk run directory (usually `/var/run/dpdk`) as follows:
```yaml
apiVersion: apps/v1
kind: Deployment
...
spec:
  template:
    spec:
      containers:
      - name: telemetry-exporter
        imagePullPolicy: Always
        image: nfvri/dpdk-telemetry-exporter:0.1
        command: ["dpdkTelemetryExporter"]
        args: ["-vvv"]
        volumeMounts:
           - mountPath: /var/run/dpdk/
             name: dpdkrun-volume
        resources:
          requests:
            memory: "1Gi"
            cpu: "1000m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        ports:
          - containerPort: 8000
...
```

Then assuming you have a Prometheus-operator deployment, use a `Service` and `ServiceMonitor` to specify a target to the exporter (be careful to match the appropriate labels/namespaces for your case):

```yaml
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: dpdk-deployment-monitor
  namespace: monitoring
  labels:
    app: dpdk
    release: k8s-prom
spec:
  endpoints:
  - port: metrics
    path: /
    interval: "5s"
    scrapeTimeout: "5s"
  namespaceSelector:
    matchNames:
      - dpdk
  selector:
    matchLabels:
      app: dpdk

---
apiVersion: v1
kind: Service
metadata:
  name: dpdk-deployment-svc
  namespace: dpdk
  labels:
    app: dpdk
spec:
  ports:
  - name: metrics
    port: 8000
    protocol: TCP
  selector:
    app: dpdk
```

