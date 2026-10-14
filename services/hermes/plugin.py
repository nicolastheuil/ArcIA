"""
ArcIA Tokenmaxing Plugin for Hermes Agent
Compresses shell outputs (e.g. git log) and large JSON data (>8KB) to optimize context window.
"""
import os
import json
import subprocess
from typing import Any, Dict

MAX_JSON_BYTES = 8192

def compress_shell_output(command: str, output: str) -> str:
    """Uses RTK if available, or collapses verbose git log output."""
    if not output:
        return output
    
    # Check if rtk binary is available
    if os.path.exists("/usr/local/bin/rtk"):
        try:
            proc = subprocess.run(
                ["/usr/local/bin/rtk", "compress"],
                input=output.encode("utf-8"),
                capture_output=True,
                timeout=5
            )
            if proc.returncode == 0 and proc.stdout:
                return proc.stdout.decode("utf-8")
        except Exception:
            pass

    # Fallback compression for git log
    if "git log" in command and len(output.splitlines()) > 50:
        lines = output.splitlines()
        head = lines[:30]
        tail = lines[-10:]
        return "\n".join(head) + f"\n\n[... {len(lines) - 40} lines truncated by ArcIA Tokenmaxing ...]\n\n" + "\n".join(tail)

    return output

def compress_large_json(raw_text: str) -> str:
    """Collapses large JSON objects exceeding 8KB."""
    if len(raw_text.encode("utf-8")) <= MAX_JSON_BYTES:
        return raw_text
    
    try:
        data = json.loads(raw_text)
        if isinstance(data, list) and len(data) > 20:
            sample = data[:10]
            summary = {
                "_arcia_tokenmaxing": f"List truncated: showing 10 of {len(data)} items",
                "sample": sample,
                "total_items": len(data)
            }
            return json.dumps(summary, indent=2)
        elif isinstance(data, dict):
            # Keep top-level keys, summarize large nested structures
            truncated = {}
            for k, v in data.items():
                if isinstance(v, (dict, list)) and len(str(v)) > 1024:
                    truncated[k] = f"[Truncated container: {type(v).__name__} with size {len(v)}]"
                else:
                    truncated[k] = v
            truncated["_arcia_tokenmaxing"] = "Large JSON keys pruned to stay within context budget"
            return json.dumps(truncated, indent=2)
    except Exception:
        pass

    return raw_text

def on_tool_result(tool_name: str, command: str, result: str) -> str:
    """Hermes hook called on tool execution result."""
    if tool_name in ["terminal", "bash", "exec"]:
        return compress_shell_output(command, result)
    if tool_name in ["read_file", "fetch_url", "http"]:
        return compress_large_json(result)
    return result
