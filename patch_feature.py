import sys

filename = "data_pipeline/feature_engineering.py"
with open(filename, "r") as f:
    content = f.read()

patch = """
        # Append new raw metrics
        entry = {
            "timestamp": timestamp,
            "metrics": raw_metrics
        }
        history.append(entry)

        # Global Trim: Trim history for ALL links by time window
        cutoff_time = timestamp - timedelta(seconds=self.window_seconds)
        expired_links = []
        for l_id, l_hist in self.link_history.items():
            pruned = [h for h in l_hist if h["timestamp"] >= cutoff_time]
            if len(pruned) == 0:
                expired_links.append(l_id)
            else:
                self.link_history[l_id] = pruned
                
        for l_id in expired_links:
            del self.link_history[l_id]
            
        if link_id not in self.link_history:
            return {"status": "INSUFFICIENT_DATA"}
            
        history = self.link_history[link_id]

        # Calculate features over the window
"""

content = content.replace(
"""        # Append new raw metrics
        entry = {
            "timestamp": timestamp,
            "metrics": raw_metrics
        }
        history.append(entry)

        # Trim history by time window
        cutoff_time = timestamp - timedelta(seconds=self.window_seconds)
        pruned_history = [h for h in history if h["timestamp"] >= cutoff_time]
        
        if len(pruned_history) == 0:
            if link_id in self.link_history:
                del self.link_history[link_id]
            return {"status": "INSUFFICIENT_DATA"}
            
        self.link_history[link_id] = pruned_history
        history = self.link_history[link_id]

        # Calculate features over the window""", patch)

with open(filename, "w") as f:
    f.write(content)
