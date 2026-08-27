filename = "frontend/src/pages/RoutingDecisions.tsx"
with open(filename, "r") as f:
    lines = f.readlines()

# find where "           </div>" is (around 113) and "{/* Info Panel */}" is (around 135)
start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if "</div>" in line and "            </div>" in line: # It's a bit fuzzy
        pass
    if "          </div>" in line and "{decisions.map" not in "".join(lines[max(0,i-10):i]):
        pass
    if "{/* Info Panel */}" in line:
        end_idx = i

for i, line in enumerate(lines):
    if "          </div>" in line and "            ))} " not in line and i < end_idx and "          <h3 className=\"text-slate-300 font-medium mb-4\">Controller Logic</h3>" not in lines[i+1:end_idx]:
        pass

# Actually let's just use string replacement on the file content

with open(filename, "r") as f:
    content = f.read()

import re
# Remove the old remaining static block
content = re.sub(r"            </div>\n\n            <div className=\"bg-slate-800/30 border border-slate-700/50 p-4 rounded-lg\">.*?</div>\n          </div>\n        </div>\n", "        </div>\n", content, flags=re.DOTALL)

with open(filename, "w") as f:
    f.write(content)
