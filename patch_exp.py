import sys
import re

filename = "frontend/src/pages/ExperimentControl.tsx"
with open(filename, "r") as f:
    content = f.read()

# Add imports and state
new_imports = "import { useState, useEffect } from 'react';\nimport { Play, Square, Pause, Settings, RefreshCw, FastForward } from 'lucide-react';\nimport { startExperiment, stopExperiment, getExperiments } from '../services/api';"
content = re.sub(r"import \{ Play, Square, Pause, Settings, RefreshCw, FastForward \} from 'lucide-react';", new_imports, content)

hooks = """const ExperimentControl = () => {
  const [status, setStatus] = useState('Stopped');
  const [scenario, setScenario] = useState('normal');
  const [policy, setPolicy] = useState('predictive');
  const [currentExpId, setCurrentExpId] = useState<string | null>(null);

  useEffect(() => {
    const checkStatus = async () => {
      try {
        const exps = await getExperiments();
        const running = exps.find((e: any) => e.status === 'running');
        if (running) {
          setStatus('Running');
          setCurrentExpId(running.id);
        } else {
          setStatus('Stopped');
          setCurrentExpId(null);
        }
      } catch (err) {
        console.error("Failed to fetch experiments", err);
      }
    };
    checkStatus();
    const interval = setInterval(checkStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleCommand = async (command: string) => {
    try {
      if (command === 'start') {
        setStatus('Starting...');
        const res = await startExperiment({
          scenario,
          policy,
          duration: 60,
          seed: 42
        });
        setCurrentExpId(`exp_${policy}_${scenario}_ui`);
        setStatus('Running');
      } else if (command === 'stop') {
        setStatus('Stopping...');
        if (currentExpId) {
          await stopExperiment(currentExpId);
        }
        setStatus('Stopped');
        setCurrentExpId(null);
      }
    } catch (err) {
      console.error(`Command ${command} failed`, err);
      setStatus('Error');
    }
  };
"""

content = content.replace("""const ExperimentControl = () => {
  const [status, setStatus] = useState('Stopped');

  const handleCommand = async (command: string) => {
    setStatus(command === 'start' ? 'Running' : command === 'pause' ? 'Paused' : 'Stopped');
    // Simulated API call for the frontend
    console.log(`Sent ${command} to Mininet backend`);
  };""", hooks)

# Update Selects
scenario_select = """              <select 
                value={scenario}
                onChange={(e) => setScenario(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-white outline-none focus:border-emerald-500"
              >
                <option value="normal">Normal Operations</option>
                <option value="gradual_congestion">Gradual Congestion</option>
                <option value="sudden_surge">Sudden Burst (Flash Crowd)</option>
              </select>"""
content = re.sub(r"<select className=\"w-full bg-slate-800 border border-slate-700 rounded p-2 text-white outline-none focus:border-emerald-500\">\s*<option>High Background Contention</option>\s*<option>Sudden Burst \(Flash Crowd\)</option>\s*<option>Normal Operations</option>\s*</select>", scenario_select, content)


policy_select = """            <div className="mt-4">
              <label className="block mb-1 text-slate-400">Routing Policy</label>
              <select 
                value={policy}
                onChange={(e) => setPolicy(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-white outline-none focus:border-emerald-500"
              >
                <option value="static">Static (No Rerouting)</option>
                <option value="reactive">Reactive (Post-Violation)</option>
                <option value="predictive">Predictive (ML Proactive)</option>
              </select>
            </div>"""

content = content.replace("""            <div>
              <label className="block mb-1 text-slate-400">Topology</label>""", policy_select + "\n            <div>\n              <label className=\"block mb-1 text-slate-400\">Topology</label>")


with open(filename, "w") as f:
    f.write(content)
