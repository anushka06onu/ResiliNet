import { create } from 'zustand';

interface SystemState {
  systemStatus: string;
  version: string;
  activeConnections: number;
  currentTopology: any;
  wsConnected: boolean;
  setSystemStatus: (status: string, version: string, connections: number) => void;
  setTopology: (topo: any) => void;
  setWsConnected: (connected: boolean) => void;
}

export const useStore = create<SystemState>((set) => ({
  systemStatus: 'DISCONNECTED',
  version: 'Unknown',
  activeConnections: 0,
  currentTopology: null,
  wsConnected: false,
  setSystemStatus: (status, version, connections) => set({ systemStatus: status, version, activeConnections: connections }),
  setTopology: (topo) => set({ currentTopology: topo }),
  setWsConnected: (connected) => set({ wsConnected: connected }),
}));
