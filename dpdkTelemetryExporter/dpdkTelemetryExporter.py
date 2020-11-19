#! /usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright(c) 2020 Intel Corporation
# Copyright(c) 2020 Intracom Telecom S.A.

import schedule
import json
import logging
import argparse
from prometheus_client import start_http_server, Counter, Gauge, Histogram
import pathos.pools as pp
import socket
import os
import time
import glob

logging.basicConfig()
_log = logging.getLogger('DPDKTelemetryExporter')

# global vars
BUFFER_SIZE = 200000

V1_METRICS_REQ = "{\"action\":0,\"command\":\"ports_all_stat_values\",\"data\":null}"
V1_API_REG = "{\"action\":1,\"command\":\"clients\",\"data\":{\"client_path\":\""
V1_API_UNREG = "{\"action\":2,\"command\":\"clients\",\"data\":{\"client_path\":\""
V1_GLOBAL_METRICS_REQ = "{\"action\":0,\"command\":\"global_stat_values\",\"data\":null}"
V1_DEFAULT_FP = "{0}/default_client".format(os.environ.get('DPDK_RUN_DIR', '/var/run/dpdk/'))


class V1Socket:

    def __init__(self):
        self.send_fd = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.recv_fd = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.client_fd = None

    def __del__(self):
        try:
            self.send_fd.close()
            self.recv_fd.close()
            self.client_fd.close()
        except:
            print("Error - Sockets could not be closed")

            
class V1Client:

    def __init__(self):  # Creates a client instance
        self.socket = V1Socket()
        self.socket_path = None
        self.unregistered = 0

    def __del__(self):
        try:
            if self.unregistered == 0:
                self.unregister()
        except:
            print("Error - Client could not be destroyed")

    def setSocketpath(self, socket_path):
        self.socket_path = socket_path

    def register(self):  # Connects a client to DPDK-instance
        if os.path.exists(V1_DEFAULT_FP):
            os.unlink(V1_DEFAULT_FP)
        try:
            self.socket.recv_fd.bind(V1_DEFAULT_FP)
        except socket.error as msg:
            print ("Error - Socket binding error: " + str(msg) + "\n")
        self.socket.recv_fd.settimeout(2)
        self.socket.send_fd.connect(self.socket_path)
        JSON = (V1_API_REG + V1_DEFAULT_FP + "\"}}")
        self.socket.send_fd.sendall(JSON.encode())

        self.socket.recv_fd.listen(1)
        self.socket.client_fd = self.socket.recv_fd.accept()[0]

    def unregister(self):  # Unregister a given client
        self.socket.client_fd.send((V1_API_UNREG + V1_DEFAULT_FP + "\"}}").encode())
        self.socket.client_fd.close()

    def requestMetrics(self):  # Requests metrics for given client
        self.socket.client_fd.send(V1_METRICS_REQ.encode())
        data = self.socket.client_fd.recv(BUFFER_SIZE).decode()
        _log.debug("Response: {0}".format(data))
        return data

    def requestGlobalMetrics(self):  # Requests global metrics for given client
        self.socket.client_fd.send(V1_GLOBAL_METRICS_REQ.encode())
        data = self.socket.client_fd.recv(BUFFER_SIZE).decode()
        _log.debug("Response: {0}".format(data))
        return data
        
    def handle_socket(self):
        """ Connect to socket and handle user input """
        
        results = []
        
        globalMetrics = json.loads(self.requestGlobalMetrics())
        
        if '200' in globalMetrics['status_code']:
            for port in globalMetrics['data']:
                results.append(port)
                    
        metrics = json.loads(self.requestMetrics())
        
        if '200' in metrics['status_code']:
            for port in metrics['data']:
                results.append(port)
                
        return results

            
class V2Client:

    def __init__(self):  # Creates a client instance
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.socket_path = None
            
    def setSocketpath(self, socket_path):  # Gets arguments from Command-Line and assigns to instance of client
        self.socket_path = socket_path
        
    def read_socket(self, sock, buf_len, echo=True):
        """ Read data from socket and return it in JSON format """
        reply = sock.recv(buf_len).decode()
        try:
            ret = json.loads(reply)
        except json.JSONDecodeError:
            print("Error in reply: ", reply)
            sock.close()
            raise
        if echo:
            print(json.dumps(ret))
        return ret

    def handle_socket(self):
        """ Connect to socket and handle user input """
        print("Connecting to " + self.socket_path)
        try:
            self.socket.connect(self.socket_path)
        except OSError:
            print("Error connecting to " + self.socket_path)
            self.socket.close()
            return
        json_reply = self.read_socket(self.socket, 1024)
        output_buf_len = json_reply["max_output_len"]
    
        # get list of commands for readline completion
        self.socket.send("/".encode())
        CMDS = self.read_socket(self.socket, output_buf_len, False)["/"]
    
        # Send all commands to gather metrics
        for cmd in  CMDS:
            if cmd.startswith('/'):
                self.socket.send(cmd.encode())
                self.read_socket(self.socket, output_buf_len)
        self.socket.close()


class DPDKTelemetryExporter():
    
    def __init__(self, args):
        self.args = args
        self.threads = args.threads
        self.timeout = args.timeout
        
        self.verbose = args.verbose
        if self.verbose >= 3:
            _log.setLevel(logging.DEBUG)
        elif self.verbose == 2:
            _log.setLevel(logging.INFO)
        elif self.verbose == 1:
            _log.setLevel(logging.ERROR)
        else:
            _log.setLevel(logging.CRITICAL)
            
        # # Set metrics to expose
        
        # Gauges
        self.dpdkexporter_busy_percent = Gauge('dpdk_telemetry_busy_percent', '', ['socket', 'port', 'aggregate'])
        self.dpdkexporter_idle_status = Gauge('dpdk_telemetry_idle_status', '', ['socket', 'type', 'direction', 'port', 'aggregate'])
        
        # Counter
        self.dpdkexporter_polls = Counter('dpdk_telemetry_exporter_polls_total', '', ['socket', 'type', 'port', 'aggregate'])
        self.dpdkexporter_packets = Counter('dpdk_telemetry_packets_total', '', ['socket', 'type', 'direction', 'priority', 'port', 'aggregate'])
        self.dpdkexporter_bytes = Counter('dpdk_telemetry_bytes_total', '', ['socket', 'type', 'direction', 'port', 'aggregate'], unit='bytes')
        self.dpdkexporter_errors = Counter('dpdk_telemetry_errors_total', '', ['socket', 'type', 'direction', 'port', 'aggregate'])
        self.dpdkexporter_idle_count = Counter('dpdk_telemetry_idle_total', '', ['socket', 'type', 'direction', 'port', 'aggregate'])
        
        # Histogram
        self.buckets = (64, 128, 256, 512, 1024, 1522, float("inf"))
        self.dpdkexporter_packets_size = Histogram('dpdk_telemetry_packets_size', '', ['socket', 'direction', 'port', 'aggregate'],
                                                   buckets=self.buckets)
        
        self.p = pp.ProcessPool(int(self.threads))
    
    def loadDPDKv1Sockets(self):
        v1sockets = []
        
        # Path to sockets for processes run as a root user
        for f in glob.glob('/var/run/dpdk/rte/telemetry'):
            v1sockets.append(f)
        # Path to sockets for processes run as a regular user
        for f in glob.glob('{0}/rte/telemetry'.format(os.environ.get('DPDK_RUN_DIR', '/tmp'))):
            v1sockets.append(f)
        
        _log.debug("v1sockets: {0}".format(v1sockets))
        
        return v1sockets
    
    def loadDPDKv2Sockets(self):
        v2sockets = []
        
        # Path to sockets for processes run as a root user
        for f in glob.glob('/var/run/dpdk/*/dpdk_telemetry.v2'):
            v2sockets.append(f)
        # Path to sockets for processes run as a regular user
        for f in glob.glob('{0}/*/dpdk_telemetry.v2'.format(os.environ.get('DPDK_RUN_DIR', '/tmp'))):
            v2sockets.append(f)
        
        _log.debug("v2sockets: {0}".format(v2sockets))
        
        return v2sockets
    
    def getSingleV1SocketStats(self, socket_path):
        # Get status from requests     
        client = V1Client()
        client.setSocketpath(socket_path)
        client.register()
        results = client.handle_socket()
        
        return { 'socket_path': socket_path, 'results': results }
    
    def getSingleV2SocketStats(self, socket_path):
        # Get status from requests     
        client = V2Client()
        client.setSocketpath(socket_path)
        client.handle_socket()
        
        return []

    def chunks(self, l, n):
        # Yield successive n-sized chunks from l.
        for i in range(0, len(l), n):
            yield l[i:i + n]

    def refreshMetricsV1(self, results):
        socket_path = results['socket_path']
        for result in results['results']:
            globalMetric = 0
            port = int(result['port'])
            # Telemetry V1 uses max C uint for global metrics, i.e.  4294967295
            if port >= 4294967295: 
                globalMetric = 1
            
            if 'stats' in result:
                # Manually reset histogram
                for direction in ['rx', 'tx']:
                    self.dpdkexporter_packets_size.labels(socket=socket_path, port=port, aggregate=globalMetric, direction=direction
                                                    )._sum.set(0)
                    for i, bucket in enumerate(self.buckets):
                        self.dpdkexporter_packets_size.labels(socket=socket_path, port=port, aggregate=globalMetric, direction=direction
                                                    )._buckets[i].set(0)
            
                for metric in result['stats']:
                    if 'poll' in metric['name']:
                        self.dpdkexporter_polls.labels(socket=socket_path, type=metric['name'].replace('_poll', ''), port=port, aggregate=globalMetric
                                                       )._value.set(float(metric['value']))
                    if 'busy_percent' in metric['name']:
                        self.dpdkexporter_busy_percent.labels(socket=socket_path, port=port, aggregate=globalMetric).set(float(metric['value']))
                    if 'idle_status' in metric['name']:
                        components = metric['name'].replace('_idle_status', '').split('_')
                        self.dpdkexporter_idle_status.labels(socket=socket_path, port=port, aggregate=globalMetric, direction=components[0], type='_'.join(components[1:])
                                                             ).set(float(metric['value']))
                    if 'idle_count' in metric['name']:
                        components = metric['name'].replace('_idle_count', '').split('_')
                        self.dpdkexporter_idle_count.labels(socket=socket_path, port=port, aggregate=globalMetric, direction=components[0], type='_'.join(components[1:])
                                                            )._value.set(float(metric['value']))
                                                            
                    if 'packets' in metric['name'] and 'size' not in metric['name']:
                        
                        # Get components with no packets
                        components = metric['name'].replace('_packets', '').split('_')
                        
                        priority = ""
                        if 'priority' in metric['name']:
                            # Get priority as str but ensure it is an int representation
                            priority = str(int(metric['name'].split('priority')[1].split('_')[0]))
                            
                            # Get components with no priority and packets
                            components = metric['name'].replace('_packets', '').replace('_priority{0}'.format(priority), '').split('_')
                        
                        self.dpdkexporter_packets.labels(socket=socket_path, port=port, aggregate=globalMetric, priority=priority, direction=components[0], type='_'.join(components[1:])
                                                            )._value.set(float(metric['value']))
                                                            
                    if 'packets' in metric['name'] and 'size' in metric['name']:
                        
                        # Get components with no packets
                        components = metric['name'].replace('_packets', '').replace('_size', '').split('_')
                        
                        # Get bucket as last in 'to'+1 or inf
                        if components[-1] == 'max':
                            bucket = float("inf")
                        elif int(components[-1]) == 64 or int(components[-1]) == 1522 :
                            bucket = int(components[-1])
                        else:
                            bucket = int(components[-1]) + 1
                            
                        _log.debug(bucket)
                        
                        # Find bucket index
                        index = self.buckets.index(bucket)
                        
                        # Add to histogram
                        self.dpdkexporter_packets_size.labels(socket=socket_path, port=port, aggregate=globalMetric, direction=components[0]
                                                            )._sum.inc(float(metric['value']))
                                                            
                        self.dpdkexporter_packets_size.labels(socket=socket_path, port=port, aggregate=globalMetric, direction=components[0]
                                                    )._buckets[index].set(float(metric['value']))
                    
                    if 'bytes' in metric['name']:
                        components = metric['name'].replace('_bytes', '').split('_')
                        self.dpdkexporter_bytes.labels(socket=socket_path, port=port, aggregate=globalMetric, direction=components[0], type='_'.join(components[1:])
                                                            )._value.set(float(metric['value']))
                                                    
                    if 'errors' in metric['name']:
                        components = metric['name'].replace('_errors', '').split('_')
                        self.dpdkexporter_errors.labels(socket=socket_path, port=port, aggregate=globalMetric, direction=components[0], type='_'.join(components[1:])
                                                            )._value.set(float(metric['value']))
                                                            
                    # Add malformed dpdk dropped packets for correlation
                    if 'dropped' in metric['name'] and 'packets' not in metric['name']:
                        components = metric['name'].split('_')
                        self.dpdkexporter_packets.labels(socket=socket_path, port=port, aggregate=globalMetric, priority=priority, direction=components[0],
                                                         type='_'.join(components[1:]))._value.set(float(metric['value']))

    def getDPDKStats(self):
        
        v1_socket_list = self.loadDPDKv1Sockets()
        _log.debug(v1_socket_list)
        
        v2_socket_list = self.loadDPDKv2Sockets()
        _log.debug(v2_socket_list)
        
        resultListV1 = []
        resultListV2 = []
        
        # Run in parallel 
        resultListV1.extend(self.p.map(self.getSingleV1SocketStats, v1_socket_list))
        
        resultListV2.extend(self.p.map(self.getSingleV2SocketStats, v2_socket_list))
        
        _log.debug(resultListV1)
        _log.debug(resultListV2)
        
        for result in resultListV1:
            self.refreshMetricsV1(result)
        
    def run(self):
        # Start up the server to expose the metrics.
        start_http_server(8000)
        
        schedule.every(int(self.timeout)).seconds.do(self.getDPDKStats)
        while True:
            schedule.run_pending()
            time.sleep(1)
            
        self.p.close()


def parser():
    parser = argparse.ArgumentParser(prog='DPDKTelemetryExporter')
    parser.add_argument('-t', dest="threads", default='8', help='DPDKTelemetryExporter parallel threads (default: 8)')
    parser.add_argument('-T', '--timeout', action='store', default=5, help='The update interval in seconds (default 5)')
    parser.add_argument(
        '-v',
        '--verbose',
        action='count',
        default=2,
        help='Set output verbosity (default: -vv = INFO)')
    return parser.parse_args()


def main():
    args = parser()
    dte = DPDKTelemetryExporter(args)
    dte.run()


if __name__ == '__main__':
    main()

