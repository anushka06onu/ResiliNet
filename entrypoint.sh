#!/bin/bash
set -e

# Start Open vSwitch
service openvswitch-switch start

# Execute CMD
exec "$@"
