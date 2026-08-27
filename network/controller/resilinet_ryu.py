import os
import time

import requests
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.lib import hub
from ryu.lib.packet import ether_types, ethernet, packet
from ryu.ofproto import ofproto_v1_3

API_ENDPOINT = os.environ.get("RESILINET_API_URL", "http://host.docker.internal:8000/api/v1/telemetry/ingest")

class ResiliNetRyuController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.datapaths = {}
        self.monitor_thread = hub.spawn(self._monitor)
        
        # State tracking for diff calculations
        self.port_stats = {} # {dpid: {port_no: {rx_bytes: X, tx_bytes: Y, rx_dropped: Z, tx_dropped: W, tx_packets: P, timestamp: T}}}
        self.latency_stats = {} # {dpid: latency_ms}

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        self.datapaths[datapath.id] = datapath

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return
        dst = eth.dst
        src = eth.src

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, 1, match, actions, msg.buffer_id)
                return
            else:
                self.add_flow(datapath, 1, match, actions)
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)

    def _monitor(self):
        while True:
            for dp in self.datapaths.values():
                self._request_stats(dp)
            hub.sleep(2) # Polling interval

    def _request_stats(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        # Active latency probing
        echo_req = parser.OFPEchoRequest(datapath, data=str(time.time()).encode('utf-8'))
        datapath.send_msg(echo_req)
        
        req = parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(req)
        
    @set_ev_cls(ofp_event.EventOFPEchoReply, [MAIN_DISPATCHER, CONFIG_DISPATCHER])
    def _echo_reply_handler(self, ev):
        try:
            timestamp = float(ev.msg.data.decode('utf-8'))
            rtt_ms = (time.time() - timestamp) * 1000
            self.latency_stats[ev.msg.datapath.id] = rtt_ms
        except Exception:
            pass

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        msg = ev.msg
        dpid = msg.datapath.id
        current_time = time.time()
        
        if dpid not in self.port_stats:
            self.port_stats[dpid] = {}

        for stat in msg.body:
            port_no = stat.port_no
            # Ignore local ports (usually > 0xffffff00)
            if port_no > 0xffffff00:
                continue

            prev = self.port_stats[dpid].get(port_no, None)
            
            # Save current state
            self.port_stats[dpid][port_no] = {
                'rx_bytes': stat.rx_bytes,
                'tx_bytes': stat.tx_bytes,
                'rx_dropped': stat.rx_dropped,
                'tx_dropped': stat.tx_dropped,
                'tx_packets': stat.tx_packets,
                'timestamp': current_time
            }

            if prev:
                dt = current_time - prev['timestamp']
                if dt > 0:
                    rx_rate = (stat.rx_bytes - prev['rx_bytes']) / dt
                    tx_rate = (stat.tx_bytes - prev['tx_bytes']) / dt
                    
                    d_tx_dropped = stat.tx_dropped - prev['tx_dropped']
                    d_tx_packets = stat.tx_packets - prev['tx_packets']
                    
                    loss_rate = d_tx_dropped / (d_tx_packets + d_tx_dropped) if (d_tx_packets + d_tx_dropped) > 0 else 0.0

                    # Convert to bps
                    rx_bps = rx_rate * 8
                    tx_bps = tx_rate * 8
                    
                    # Estimate utilization based on 10Mbps link (small_test.py)
                    capacity_bps = 10_000_000 
                    utilization = max(rx_bps, tx_bps) / capacity_bps
                    
                    latency = self.latency_stats.get(dpid, None)
                    
                    # Send telemetry to API with consistent ML features
                    telemetry = {
                        "switch_id": f"s{dpid}",
                        "port_no": str(port_no),
                        "features": {
                            "utilization": min(utilization, 1.0),
                            "loss_mean_30s": loss_rate,
                            "tx_dropped_max": d_tx_dropped,
                            "control_plane_rtt_ms": latency,
                            "rx_bytes_slope": rx_rate,
                            "tx_bytes_rate": tx_rate
                        }
                    }
                    
                    # Send async via hub to avoid blocking Ryu
                    hub.spawn(self._send_telemetry, telemetry)

    def _send_telemetry(self, telemetry):
        try:
            response = requests.post(API_ENDPOINT, json=telemetry, timeout=1)
            if response.status_code >= 400:
                print(f"API Error {response.status_code}: {response.text}")
        except Exception as e:
            print(f"API Connection Error: {e}")
