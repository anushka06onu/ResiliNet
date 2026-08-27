filename = "frontend/src/pages/ExperimentControl.tsx"
with open(filename, "r") as f:
    content = f.read()

import re
# Fix duplicate useState imports
content = re.sub(r"import \{ useState \} from 'react';\nimport \{ useState, useEffect \} from 'react';", "import { useState, useEffect } from 'react';", content)

# Fix unused res
content = content.replace("const res = await startExperiment({", "await startExperiment({")

with open(filename, "w") as f:
    f.write(content)
