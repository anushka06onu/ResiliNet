import { create } from 'zustand';

interface SystemState {
  systemStatus: string;
  version: string;
  activeConnections: number;
  currentTopology: any;
  wsConnected: boolean;
  latestTelemetry: any;
  telemetryHistory: any[];
  linkStates: Record<string, any>;
  dataMode: string;
  setSystemStatus: (status: string, version: string, connections: number) => void;
  setTopology: (topo: any) => void;
  setWsConnected: (connected: boolean) => void;
  updateTelemetry: (event: any) => void;
  checkDataModeExpiry: () => void;
}

export const useStore = create<SystemState>((set) => ({
  systemStatus: 'DISCONNECTED',
  version: 'Unknown',
  activeConnections: 0,
  currentTopology: null,
  wsConnected: false,
  latestTelemetry: null,
  telemetryHistory: [],
  linkStates: {},
  dataMode: 'DISCONNECTED',
  setSystemStatus: (status, version, connections) =>
    set({ systemStatus: status, version, activeConnections: connections, dataMode: status }),
  setTopology: (topo) => set({ currentTopology: topo }),
  setWsConnected: (connected) => set({ wsConnected: connected }),
  updateTelemetry: (event) =>
    set((state) => {
      const { link_id, utilization, loss_rate, predicted_risk, latency_ms } = event.payload || {};

      // Update link state
      const newLinkStates = { ...state.linkStates };
      if (link_id) {
        newLinkStates[link_id] = {
          utilization,
          loss_rate,
          predicted_risk,
          latency_ms,
          timestamp: event.timestamp,
        };
      }

      // Keep last 100 events in history
      const newHistory = [event, ...state.telemetryHistory].slice(0, 100);

      return {
        latestTelemetry: event,
        telemetryHistory: newHistory,
        linkStates: newLinkStates,
        dataMode: event.mode || state.dataMode,
      };
    }),
  checkDataModeExpiry: () =>
    set((state) => {
      if ((state.dataMode === 'LIVE' || state.dataMode === 'LIVE LAB') && state.latestTelemetry) {
        const timestamp = new Date(state.latestTelemetry.timestamp).getTime();
        const age = Date.now() - timestamp;
        if (age > 10000) {
          return { dataMode: 'STALE', systemStatus: 'STALE' };
        }
      }
      return state;
    }),
}));
