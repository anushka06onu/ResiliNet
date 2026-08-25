#!/usr/bin/env python3

import subprocess
import time
import json
import csv
import os
from datetime import datetime

class OVSCollector:
    """
    Collects link telemetry from Open vSwitch using ovs-ofctl.
    """
    def __init__(self, output_dir='data_pipeline/data'):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.csv_file = os.path.join(self.output_dir, 'raw_link_telemetry.csv')
        self._init_csv()

    def _init_csv(self):
        if not os.path.exists(self.csv_file):
            with open(self.csv_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'switch_id', 'port_no', 'rx_packets', 
                    'tx_packets', 'rx_bytes', 'tx_bytes', 'rx_dropped', 'tx_dropped'
                ])

    def get_switches(self):
        """Get a list of all OVS bridges (switches)."""
        try:
            output = subprocess.check_output(['ovs-vsctl', 'list-br'], universal_newlines=True)
            return output.strip().split('\n')
        except FileNotFoundError:
            print("ovs-vsctl not found. Ensure Open vSwitch is installed.")
            return []
        except Exception as e:
            print(f"Error getting switches: {e}")
            return []

    def poll_switch(self, switch):
        """Poll port statistics for a single switch."""
        try:
            # Dump port statistics
            output = subprocess.check_output(['ovs-ofctl', 'dump-ports', switch], universal_newlines=True)
            lines = output.strip().split('\n')
            
            stats = []
            timestamp = datetime.now().isoformat()
            
            current_port = None
            port_data = {}
            
            for line in lines[1:]: # Skip the first line (header)
                line = line.strip()
                if line.startswith('port '):
                    if current_port is not None:
                        stats.append(port_data)
                    
                    # Parse port header
                    parts = line.split(':')
                    current_port = parts[0].split(' ')[1]
                    port_data = {
                        'timestamp': timestamp,
                        'switch_id': switch,
                        'port_no': current_port,
                        'rx_packets': 0, 'tx_packets': 0,
                        'rx_bytes': 0, 'tx_bytes': 0,
                        'rx_dropped': 0, 'tx_dropped': 0
                    }
                    
                    # Parse rx values
                    rx_part = parts[1] if len(parts) > 1 else ""
                    for pair in rx_part.split(','):
                        pair = pair.strip()
                        if '=' in pair:
                            k, v = pair.split('=')
                            if 'pkts' in k: port_data['rx_packets'] = v
                            if 'bytes' in k: port_data['rx_bytes'] = v
                            if 'drop' in k: port_data['rx_dropped'] = v
                            
                elif line.startswith('tx '):
                    # Parse tx values
                    for pair in line.split('tx ')[1].split(','):
                        pair = pair.strip()
                        if '=' in pair:
                            k, v = pair.split('=')
                            if 'pkts' in k: port_data['tx_packets'] = v
                            if 'bytes' in k: port_data['tx_bytes'] = v
                            if 'drop' in k: port_data['tx_dropped'] = v

            if current_port is not None:
                stats.append(port_data)
                
            return stats
            
        except Exception as e:
            print(f"Error polling switch {switch}: {e}")
            return []

    def save_stats(self, stats):
        with open(self.csv_file, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'timestamp', 'switch_id', 'port_no', 'rx_packets', 
                'tx_packets', 'rx_bytes', 'tx_bytes', 'rx_dropped', 'tx_dropped'
            ])
            for stat in stats:
                writer.writerow(stat)

    def start_polling(self, interval=5, max_iterations=0):
        """Poll telemetry every `interval` seconds."""
        switches = self.get_switches()
        if not switches or switches == ['']:
            print("No switches found. Are you running in Mininet?")
            return

        print(f"Starting telemetry collection on switches: {switches}")
        
        iterations = 0
        try:
            while True:
                if max_iterations > 0 and iterations >= max_iterations:
                    break
                
                all_stats = []
                for sw in switches:
                    stats = self.poll_switch(sw)
                    all_stats.extend(stats)
                
                self.save_stats(all_stats)
                print(f"[{datetime.now().time()}] Collected {len(all_stats)} port records.")
                
                iterations += 1
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nPolling stopped.")

if __name__ == '__main__':
    collector = OVSCollector()
    collector.start_polling(interval=5)
