#!/usr/bin/env python3
"""
Run test with explicit timeout control
"""

import sys
import subprocess
import time
from pathlib import Path

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

def run_test(test_file, timeout=300):
    """Run a test file with timeout"""
    project_root = Path(__file__).parent.parent
    test_path = project_root / "tests" / test_file
    
    if not test_path.exists():
        print(f"Test file not found: {test_path}")
        return
    
    print(f"Running {test_file} with {timeout}s timeout...")
    
    cmd = [
        r"C:\Users\hvksh\mcp-servers\venv312\Scripts\python.exe",
        str(test_path)
    ]
    
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(project_root)
        )
        
        output = []
        start_time = time.time()
        
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line:
                print(line.rstrip())
                output.append(line)
            
            # Check timeout
            if time.time() - start_time > timeout:
                proc.terminate()
                print(f"\n!!! Test timed out after {timeout}s !!!")
                break
        
        return_code = proc.poll()
        if return_code == 0:
            print(f"\nTest completed successfully")
        elif return_code is not None:
            print(f"\nTest failed with code {return_code}")
            
    except Exception as e:
        print(f"Error running test: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
        timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 300
        run_test(test_file, timeout)
    else:
        # Run quick regeneration test
        print("Running quick regeneration test...")
        run_test("debug_regeneration.py", 60)