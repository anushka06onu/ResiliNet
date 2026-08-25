#!/usr/bin/env python3
import time

def start_telemedicine_flow(net, src_name, dst_name, bw="3M"):
    """
    Simulate a telemedicine stream.
    Requires very low loss and latency.
    Priority 4.
    """
    src = net.get(src_name)
    dst = net.get(dst_name)
    
    # Start UDP iperf server
    dst.cmd('iperf -s -u -p 5004 &')
    time.sleep(1)
    
    # Send traffic
    print(f"Starting Critical Telemedicine Flow: {src_name} -> {dst_name} ({bw}bps)")
    src.cmd(f'iperf -c {dst.IP()} -u -p 5004 -b {bw} -t 60 &')
