#!/usr/bin/env python3
import time


def start_video_flow(net, src_name, dst_name, bw="2M", duration=60):
    """
    Simulate an online class / video conference.
    Priority 3.
    """
    src = net.get(src_name)
    dst = net.get(dst_name)
    
    # Start UDP iperf server
    dst.cmd('iperf -s -u -p 5003 &')
    time.sleep(1)
    
    # Send traffic
    print(f"Starting High Priority Video Flow: {src_name} -> {dst_name} ({bw}bps, {duration}s)")
    src.cmd(f'iperf -c {dst.IP()} -u -p 5003 -b {bw} -t {duration} &')
