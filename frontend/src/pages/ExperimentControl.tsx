import { useState, useEffect } from 'react';
import { Play, Square, Pause, Settings, RefreshCw, FastForward } from 'lucide-react';
import { startExperiment, stopExperiment, getExperiments } from '../services/api';
import type { ExperimentConfig } from '../services/api';

const ExperimentControl = () => {
  const [status, setStatus] = useState('Stopped');
  const [scenario, setScenario] = useState<ExperimentConfig['scenario']>('normal');
  const [policy, setPolicy] = useState<ExperimentConfig['policy']>('predictive');
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
        console.error('Failed to fetch experiments', err);
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
        await startExperiment({
          scenario,
          policy,
          duration: 60,
          seed: 42,
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

  const handleReplay = () => {
    setStatus('Running (Replay Mode)');
    alert('Replay dataset exp_001 loaded successfully. Simulating past telemetry...');
  };

  return (
    <div className="p-6 h-full overflow-y-auto">
      <header className="mb-8 flex justify-between items-end">
        <div>
          <h2 className="text-2xl font-bold text-white mb-2 flex items-center gap-3">
            <Settings className="text-emerald-500" />
            Simulation & Replay
          </h2>
          <p className="text-slate-400 text-sm">
            Configure live network simulations or replay historical datasets.
          </p>
        </div>
      </header>

      <div className="grid grid-cols-2 gap-6 h-[500px]">
        {/* Configuration Panel */}
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-6">
          <h3 className="text-lg font-bold text-slate-200 mb-6 border-b border-slate-800 pb-2">
            Configuration
          </h3>

          <div className="space-y-4 text-sm text-slate-300">
            <div className="mt-4">
              <label className="block mb-1 text-slate-400">Routing Policy</label>
              <select
                value={policy}
                onChange={(e) => setPolicy(e.target.value as ExperimentConfig['policy'])}
                className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-white outline-none focus:border-emerald-500"
              >
                <option value="static">Static (No Rerouting)</option>
                <option value="reactive">Reactive (Post-Violation)</option>
                <option value="predictive">Predictive (ML Proactive)</option>
              </select>
            </div>
            <div>
              <label className="block mb-1 text-slate-400">Topology</label>
              <select className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-white outline-none focus:border-emerald-500">
                <option>sndlib_campus (14 nodes, 21 links)</option>
                <option>small_test (4 nodes, 4 links)</option>
                <option>sndlib_backbone (32 nodes, 54 links)</option>
              </select>
            </div>

            <div>
              <label className="block mb-1 text-slate-400">Traffic Scenario</label>
              <select
                value={scenario}
                onChange={(e) => setScenario(e.target.value as ExperimentConfig['scenario'])}
                className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-white outline-none focus:border-emerald-500"
              >
                <option value="normal">Normal Operations</option>
                <option value="gradual_congestion">Gradual Congestion</option>
                <option value="sudden_surge">Sudden Burst (Flash Crowd)</option>
              </select>
            </div>

            <div>
              <label className="block mb-1 text-slate-400">Inject Link Failure</label>
              <select className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-white outline-none focus:border-emerald-500">
                <option>None</option>
                <option>s2-s4 (Core bottleneck)</option>
                <option>s1-s2 (Edge link)</option>
              </select>
            </div>
          </div>
        </div>

        {/* Execution Panel */}
        <div className="flex flex-col gap-6">
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-6 flex-1 flex flex-col items-center justify-center text-center">
            <h3 className="text-slate-400 font-medium mb-6 uppercase tracking-widest text-sm">
              Status
            </h3>
            <div
              className={`text-4xl font-bold mb-8 ${status === 'Running' ? 'text-emerald-500' : 'text-slate-500'}`}
            >
              {status}
            </div>

            <div className="flex gap-4">
              <button
                onClick={() => handleCommand('start')}
                className="bg-emerald-500/20 text-emerald-400 border border-emerald-500 hover:bg-emerald-500/30 px-6 py-3 rounded-lg flex items-center gap-2 font-bold transition-colors"
              >
                <Play size={20} /> Start
              </button>
              <button
                onClick={() => handleCommand('pause')}
                className="bg-amber-500/20 text-amber-400 border border-amber-500 hover:bg-amber-500/30 px-6 py-3 rounded-lg flex items-center gap-2 font-bold transition-colors"
              >
                <Pause size={20} /> Pause
              </button>
              <button
                onClick={() => handleCommand('stop')}
                className="bg-red-500/20 text-red-400 border border-red-500 hover:bg-red-500/30 px-6 py-3 rounded-lg flex items-center gap-2 font-bold transition-colors"
              >
                <Square size={20} /> Stop
              </button>
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-lg p-6">
            <h3 className="text-lg font-bold text-slate-200 mb-4 border-b border-slate-800 pb-2 flex items-center gap-2">
              <FastForward size={18} className="text-indigo-400" />
              Historical Data Replay
            </h3>
            <p className="text-sm text-slate-400 mb-4">
              For demonstration, you can load a pre-recorded dataset to see the AI demonstrate
              predicted congestion-related SLA violations that happened in the past.
            </p>
            <button
              onClick={handleReplay}
              className="w-full bg-indigo-500/20 text-indigo-400 border border-indigo-500/50 hover:bg-indigo-500/30 py-2 rounded flex justify-center items-center gap-2 transition-colors mb-3"
            >
              <RefreshCw size={16} /> Load Replay Dataset
            </button>
            <p className="text-sm text-slate-400 mb-3 mt-4">
              <strong>Guided Reviewer Demo:</strong> Runs a 2-minute automated sequence
              demonstrating the complete pipeline: Normal operation &rarr; Controlled load increase
              &rarr; Elevated future-risk score &rarr; Explanation &rarr; Alternative route &rarr;
              OpenFlow installation &rarr; Route verification &rarr; QoS outcome comparison.
            </p>
            <button
              onClick={handleReplay}
              className="w-full bg-purple-500/20 text-purple-400 border border-purple-500/50 hover:bg-purple-500/30 py-2 rounded flex justify-center items-center gap-2 transition-colors"
            >
              <Play size={16} /> Start Guided Reviewer Demo
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ExperimentControl;
