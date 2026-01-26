import subprocess
import re
import sys
from typing import Callable, List, Optional
import datetime

class ProcessMonitor:
    """
    Monitors a subprocess, parsing its output for progress updates.
    Target format: 
        Header: || Sorting Phase-II ||
        Progress: [PB Info 2025-Dec-25 01:40:35] 32.4
    """

    PROGRESS_PATTERN = re.compile(r"\[PB Info .+?\]\s+(\d+\.\d+)")
    
    HEADER_PATTERN = re.compile(r"^\[PB Info .+?\] \|\|\s+(.+?)\s+\|\|$")

    # Phase I format: [PB Info ...] # 10  0  1 ... pool:  1 168396395 bases/GPU/minute: 950938482.0
    # Group 1: Bases processed (integer), Group 2: Rate (float)
    PHASE_I_PATTERN = re.compile(r"pool:\s+\d+\s+(\d+)\s+bases/GPU/minute:\s+([\d\.]+)")

    def __init__(self, callback: Optional[Callable[[str, dict], None]] = None, total_input_size: Optional[int] = None):
        """
        Args:
            callback: Function(phase: str, info: dict)
                      info can contain {"progress": 10.5} or {"processed_bases": 12345, "rate": 99.9}
            total_input_size: Optional total bases count. If provided, Phase I will report "progress" % based on processed_bases.
        """
        self.callback = callback
        self.total_input_size = total_input_size
        self.current_phase = "Initializing"

    def run_command(self, command: List[str]):
        """
        Executes the command and monitors stdout/stderr for progress.
        Blocks until command completes.
        
        Args:
            command: List of command arguments.
        """
        print(f"[{datetime.datetime.now()}] Starting command: {' '.join(command)}")
        
        # Popen with universal_newlines=True (text mode) and buffering=1 (line buffered)
        with subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # Merge stderr into stdout to capture everything
            text=True,
            bufsize=1
        ) as process:
            
            # Read line by line
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                
                # Check for Header (Phase Change)
                header_match = self.HEADER_PATTERN.search(line)
                if header_match:
                    content = header_match.group(1).strip()
                    if not any(x in content for x in ["Version", "Time:", "Program:"]):
                        self.current_phase = content

                # Check for Phase I pattern
                p1_match = self.PHASE_I_PATTERN.search(line)
                if p1_match:
                        bases = int(p1_match.group(1))
                        rate = float(p1_match.group(2))
                        
                        info_payload = {"processed_bases": bases, "rate": rate}
                        
                        if self.total_input_size and self.total_input_size > 0:
                            percent = (bases / self.total_input_size) * 100.0
                            percent = min(100.0, max(0.0, percent)) # Clamp
                            info_payload["progress"] = float(f"{percent:.1f}")
                            
                        if self.callback:
                            self.callback(self.current_phase, info_payload)
                    # Skip standard progress check if Phase I matched? 
                    # Usually they don't overlap.
                
                else:
                    # Check for standard progress pattern (Percentage)
                    match = self.PROGRESS_PATTERN.search(line)
                    if match:
                        try:
                            # Avoid matching the rate "32.4" if it appears in a Phase I line context?
                            # Phase I line: "... 950938482.0" -> regex `(\d+\.\d+)` would match "950938482.0"
                            # But valid progress line starts with `[PB Info ...] 32.4`.
                            # Phase I line has `# 10 ...` between Info and number.
                            # My PROGRESS_PATTERN is `r"\[PB Info .+?\]\s+(\d+\.\d+)"`.
                            # It expects [PB Info ...] directly followed by number.
                            # Phase I line: [PB Info ...] # 10 ...
                            # So `#` breaks the `\s+` match? `\s+` matches space. `#` is not space.
                            # So PROGRESS_PATTERN should NOT match Phase I lines.
                            progress = float(match.group(1))
                            if self.callback:
                                self.callback(self.current_phase, {"progress": progress})
                        except ValueError:
                            pass
                
                print(f"[CMD] {line}")

        ret_code = process.wait()
        if ret_code != 0:
            raise subprocess.CalledProcessError(ret_code, command)
            
        print(f"[{datetime.datetime.now()}] Command finished successfully.")

def run_with_logging(command: List[str], sample_id: str, db_callback=None, total_input_size: Optional[int] = None):
    """
    Helper to run a command and report to a simulated DB callback.
    """
    def _cb(phase, info):
        # Format msg based on info
        if "progress" in info:
            msg = f"{info['progress']}%"
            if "processed_bases" in info:
                 msg += f" ({info['processed_bases']}/{total_input_size})"
        elif "processed_bases" in info:
            msg = f"{info['processed_bases']} bases (Rate: {info['rate']})"
        else:
            msg = str(info)
            
        print(f" -> Reporting progress for {sample_id} [{phase}]: {msg}")
        if db_callback:
            # We standardize the DB callback to receive (id, phase, info_dict)
            db_callback(sample_id, phase, info)
            
    monitor = ProcessMonitor(callback=_cb, total_input_size=total_input_size)
    monitor.run_command(command)
