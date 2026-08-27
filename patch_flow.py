import sys
import re

filename = "frontend/src/pages/FlowMonitor.tsx"
with open(filename, "r") as f:
    content = f.read()

# Replace mockFlows and add state/effect
new_imports = "import { useState, useEffect } from 'react';\nimport { Search, Filter } from 'lucide-react';\nimport { getFlows } from '../services/api';"
content = re.sub(r"import \{ Search, Filter \} from 'lucide-react';", new_imports, content)

# Remove mockFlows
content = re.sub(r"const mockFlows = \[\n(.*?)\n\];\n", "", content, flags=re.DOTALL)

# Add hooks
hooks = """const FlowMonitor = () => {
  const [flows, setFlows] = useState<any[]>([]);
  
  useEffect(() => {
    const fetchFlows = async () => {
      try {
        const data = await getFlows();
        setFlows(data);
      } catch (err) {
        console.error("Failed to fetch flows", err);
      }
    };
    fetchFlows();
    const interval = setInterval(fetchFlows, 3000);
    return () => clearInterval(interval);
  }, []);"""

content = content.replace("const FlowMonitor = () => {", hooks)

# Remove mock data badge
content = content.replace("""          <div className="bg-amber-900/30 text-amber-400 border border-amber-500/50 px-3 py-1.5 rounded flex items-center text-xs font-bold tracking-wider uppercase">
            MOCK DATA
          </div>""", "")

# Update mapping
mapping_old = """            {mockFlows.map((flow) => ("""
mapping_new = """            {flows.map((flow: any) => ("""
content = content.replace(mapping_old, mapping_new)

# Update fields
content = content.replace("flow.path", "flow.current_path ? flow.current_path.join(' → ') : 'Unknown'")
content = content.replace("{flow.latency}", "{flow.metrics?.latency_ms ? flow.metrics.latency_ms + 'ms' : 'Pending'}")
content = content.replace("{flow.loss}", "{flow.metrics?.loss_percent ? flow.metrics.loss_percent + '%' : 'Pending'}")
content = content.replace("flow.sla", "flow.sla_status")
content = content.replace("parseInt(flow.risk)", "parseInt(flow.risk || '0')")
content = content.replace("flow.risk", "flow.risk || '0%'")

with open(filename, "w") as f:
    f.write(content)
