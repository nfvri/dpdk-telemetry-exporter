#!/usr/bin/env python

import os.path

from setuptools import setup, find_packages

yapsi_path = os.path.join('dpdkTelemetryExporter', 'modules')
yapsy_files = [(d, [os.path.join(d, f) for f in files if f.endswith('.yapsy-plugin')]) for d, folders, files in os.walk(yapsi_path)]
assets_path = os.path.join('dpdkTelemetryExporter', 'assets')
assets_files = [(d, [os.path.join(d, f) for f in files if f.endswith('.tar.gz')]) for d, folders, files in os.walk(assets_path)]

setup(name='dpdkTelemetryExporter',
      version='0.1',
      description='DPDK Telemetry exporter',
      packages=find_packages(),
      install_requires=[
        'argparse',
        'requests',
        'prometheus_client',
        'pathos',
        'schedule'
      ],
    entry_points={'console_scripts': ['dpdkTelemetryExporter=dpdkTelemetryExporter.dpdkTelemetryExporter:main']},
    zip_safe=False,
    data_files=yapsy_files + assets_files
)

