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
  const { setSystemStatus } = useStore();

  useEffect(() => {
    // Establish WebSocket Connection
    const ws = new WebSocket('ws://localhost:8000/api/v1/stream');
    
    ws.onopen = () => {
      // Fetch system status via REST on connect
      fetch('http://localhost:8000/api/v1/system/status')
        .then(r => r.json())
        .then(data => setSystemStatus(data.status, data.version, data.active_connections))
        .catch(() => setSystemStatus('LIVE LAB', '1.1.0', 1));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log("Telemetry Received:", data);
        // Handle telemetry (to be implemented in specific pages)
      } catch (e) {}
    };

    ws.onclose = () => {
      setSystemStatus('DISCONNECTED', 'Unknown', 0);
    };

    return () => ws.close();
  }, [setSystemStatus]);

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
