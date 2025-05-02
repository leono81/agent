import subprocess
import sys
import os
import shutil

def run_streamlit():
    """Runs the Streamlit application by invoking the streamlit.web.cli module."""
    project_root = os.path.dirname(os.path.abspath(__file__))
    app_script = os.path.join(project_root, "orchestrator_app.py")

    if not os.path.exists(app_script):
        print(f"Error: Cannot find orchestrator_app.py at {app_script}")
        sys.exit(1)

    print(f"Starting Streamlit for {app_script} via module streamlit.web.cli...")
    print("-" * 20)

    python_executable = sys.executable
    # Construct command to run the cli module directly
    command = [python_executable, "-m", "streamlit.web.cli", "run", app_script]

    try:
        print(f"Executing command: {' '.join(command)}")
        process = subprocess.run(
            command,
            check=True,
            cwd=project_root
        )
    except subprocess.CalledProcessError as e:
        print(f"Streamlit process failed with error code {e.returncode}")
        if e.stderr:
            print(f"Stderr:\n{e.stderr}")
    except FileNotFoundError:
        # This error now specifically means the python executable wasn't found, which is unlikely
        print(f"Error: Command failed. Could not find Python executable '{python_executable}'.")
    except ModuleNotFoundError:
        # Catch if streamlit.web.cli itself cannot be found by the python interpreter
        print(f"Error: Python executable '{python_executable}' could not find the 'streamlit.web.cli' module.")
        print("Ensure Streamlit is correctly installed in the environment.")
    except Exception as e:
        print(f"An unexpected error occurred while running Streamlit: {e}")

if __name__ == "__main__":
    run_streamlit() 