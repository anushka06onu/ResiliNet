#!/usr/bin/env python3

import xml.etree.ElementTree as ET
from mininet.topo import Topo

class SNDlibTopo(Topo):
    """
    Topology builder that parses an SNDlib XML file.
    
    Expected format: SNDlib native XML format.
    https://sndlib.put.poznan.pl/
    """
    def __init__(self, xml_file, **opts):
        self.xml_file = xml_file
        super(SNDlibTopo, self).__init__(**opts)

    def build(self):
        try:
            tree = ET.parse(self.xml_file)
            root = tree.getroot()
            
            # Namespace handling for SNDlib XML
            ns = {'sndlib': 'http://sndlib.zib.de/network'}
            
            # 1. Extract nodes (Switches)
            network_nodes = root.find('.//sndlib:nodes', ns)
            if network_nodes is None:
                # Try without namespace if parsing fails
                network_nodes = root.find('.//nodes')
                ns = {}
            
            node_map = {}
            if network_nodes is not None:
                for node in network_nodes.findall('sndlib:node' if ns else 'node', ns):
                    node_id = node.get('id')
                    # Mininet switch names must be alphanumeric and often short
                    clean_id = ''.join(e for e in node_id if e.isalnum())
                    self.addSwitch(clean_id)
                    node_map[node_id] = clean_id
                    
                    # Add a default host to each switch to represent local traffic aggregation
                    host_id = f"h_{clean_id}"
                    self.addHost(host_id)
                    self.addLink(host_id, clean_id, bw=1000, delay='1ms')

            # 2. Extract links
            network_links = root.find('.//sndlib:links', ns)
            if network_links is not None:
                for link in network_links.findall('sndlib:link' if ns else 'link', ns):
                    source = link.find('sndlib:source' if ns else 'source', ns).text
                    target = link.find('sndlib:target' if ns else 'target', ns).text
                    
                    # Optional: extract capacity or routing cost if available
                    # For ResiliNet, we enforce standard backbone metrics if not provided
                    
                    if source in node_map and target in node_map:
                        s1 = node_map[source]
                        s2 = node_map[target]
                        self.addLink(s1, s2, bw=10000, delay='5ms')
                        
        except Exception as e:
            print(f"Failed to parse SNDlib XML: {e}")

if __name__ == '__main__':
    print("SNDlib Adapter loaded. Use this class within a Mininet script to load .xml topologies.")
