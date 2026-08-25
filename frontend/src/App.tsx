import { useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/layout/Layout';
import { useStore } from './store/useStore';
import NetworkOverview from './pages/NetworkOverview';
import DigitalTwin from './pages/DigitalTwin';
import FlowMonitor from './pages/FlowMonitor';
import Intelligence from './pages/Intelligence';
import RoutingDecisions from './pages/RoutingDecisions';
import ExperimentControl from './pages/ExperimentControl';
import Methodology from './pages/Methodology';
import SystemHealth from './pages/SystemHealth';

function App() {
  const { setSystemStatus, setWsConnected } = useStore();

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
        console.log("Telemetry Received:", data);
        // Handle telemetry (to be implemented in specific pages)
      } catch (e) {}
    };

    ws.onclose = () => {
      setWsConnected(false);
      setSystemStatus('DISCONNECTED', 'Unknown', 0);
    };

    return () => ws.close();
  }, [setSystemStatus, setWsConnected]);

  return (
    <Router>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<NetworkOverview />} />
          <Route path="twin" element={<DigitalTwin />} />
          <Route path="flows" element={<FlowMonitor />} />
          <Route path="intelligence" element={<Intelligence />} />
          <Route path="routing" element={<RoutingDecisions />} />
          <Route path="control" element={<ExperimentControl />} />
          <Route path="methodology" element={<Methodology />} />
          <Route path="health" element={<SystemHealth />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Router>
  );
}

export default App;
