import { create } from 'zustand';

interface SystemState {
  systemStatus: string;
  version: string;
  activeConnections: number;
  currentTopology: any;
  setSystemStatus: (status: string, version: string, connections: number) => void;
  setTopology: (topo: any) => void;
}

export const useStore = create<SystemState>((set) => ({
  systemStatus: 'DISCONNECTED',
  version: 'Unknown',
  activeConnections: 0,
  currentTopology: null,
  setSystemStatus: (status, version, connections) => set({ systemStatus: status, version, activeConnections: connections }),
  setTopology: (topo) => set({ currentTopology: topo }),
}));
