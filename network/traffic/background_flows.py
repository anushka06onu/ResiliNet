#!/usr/bin/env python3
import time


def start_background_flow(net, src_name, dst_name, bw="10M", duration=60):
    """
    Simulate a large backup/download flow.
    Priority 0 (Best effort, can be delayed).
    """
    src = net.get(src_name)
    dst = net.get(dst_name)
    
    # Start TCP iperf server
    dst.cmd('iperf -s -p 5000 &')
    time.sleep(1)
    
    # Send TCP traffic (TCP will adapt, but we can set a target bandwidth limit)
    print(f"Starting Background Flow: {src_name} -> {dst_name} (Target: {bw}bps, {duration}s)")
    src.cmd(f'iperf -c {dst.IP()} -p 5000 -t {duration} &')
