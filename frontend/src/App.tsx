import { Suspense, lazy, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/layout/Layout';
import { useStore } from './store/useStore';

const NetworkOverview = lazy(() => import('./pages/NetworkOverview'));
const DigitalTwin = lazy(() => import('./pages/DigitalTwin'));
const FlowMonitor = lazy(() => import('./pages/FlowMonitor'));
const Intelligence = lazy(() => import('./pages/Intelligence'));
const RoutingDecisions = lazy(() => import('./pages/RoutingDecisions'));
const ExperimentControl = lazy(() => import('./pages/ExperimentControl'));
const Methodology = lazy(() => import('./pages/Methodology'));
const SystemHealth = lazy(() => import('./pages/SystemHealth'));

// Fallback for lazy loading
const Loader = () => (
  <div className="flex h-full w-full items-center justify-center bg-slate-950">
    <div className="text-emerald-500 animate-pulse">Loading View...</div>
  </div>
);

function App() {
  const { setSystemStatus, setWsConnected, updateTelemetry, checkDataModeExpiry } = useStore();

  useEffect(() => {
    const WS_BASE = import.meta.env.VITE_WS_BASE_URL ?? 'ws://localhost:8000/api/v1/stream';
    const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1';
    
    // Establish WebSocket Connection
    const ws = new WebSocket(WS_BASE);
    
    ws.onopen = () => {
      setWsConnected(true);
      // Fetch system status via REST on connect
      fetch(`${API_BASE}/system/status`)
        .then(r => r.json())
        .then(data => setSystemStatus(data.status, data.version, data.active_connections))
        .catch(() => setSystemStatus('DEMO DATA', 'Frontend Demo', 0));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        updateTelemetry(data);
      } catch {}
    };

    ws.onclose = () => {
      setWsConnected(false);
      setSystemStatus('DISCONNECTED', 'Unknown', 0);
    };

    const intervalId = setInterval(() => {
      checkDataModeExpiry();
    }, 2000);

    return () => {
      ws.close();
      clearInterval(intervalId);
    };
  }, [setSystemStatus, setWsConnected, updateTelemetry, checkDataModeExpiry]);

  return (
    <Router>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Suspense fallback={<Loader />}><NetworkOverview /></Suspense>} />
          <Route path="twin" element={<Suspense fallback={<Loader />}><DigitalTwin /></Suspense>} />
          <Route path="flows" element={<Suspense fallback={<Loader />}><FlowMonitor /></Suspense>} />
          <Route path="intelligence" element={<Suspense fallback={<Loader />}><Intelligence /></Suspense>} />
          <Route path="routing" element={<Suspense fallback={<Loader />}><RoutingDecisions /></Suspense>} />
          <Route path="control" element={<Suspense fallback={<Loader />}><ExperimentControl /></Suspense>} />
          <Route path="methodology" element={<Suspense fallback={<Loader />}><Methodology /></Suspense>} />
          <Route path="health" element={<Suspense fallback={<Loader />}><SystemHealth /></Suspense>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Router>
  );
}

export default App;
