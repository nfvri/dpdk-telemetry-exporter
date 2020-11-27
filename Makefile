#NS = your docker namespace

# For public repo
export REPO = ghcr.io/nfvri

export VERSION ?= 0.1

export NAME = dpdk-telemetry-exporter

.PHONY: build-dpdk-telemetry-exporter push-dpdk-telemetry-exporter rm-dpdk-telemetry-exporter

default: build

build-dpdk-telemetry-exporter:
	docker build -t $(REPO)/$(NAME):$(VERSION) .

push-dpdk-telemetry-exporter:
	# For public repo
	echo $(REPO_PAT) | base64 -d | docker login ghcr.io -u $(USERNAME) --password-stdin
	docker push $(REPO)/$(NAME):$(VERSION)

clean-dpdk-telemetry-exporter: 
	docker rmi -f $(REPO)/$(NAME):$(VERSION)

release-dpdk-telemetry-exporter: build-dpdk-telemetry-exporter push-dpdk-telemetry-exporter

release: release-dpdk-telemetry-exporter

build: build-dpdk-telemetry-exporter

clean: clean-dpdk-telemetry-exporter
