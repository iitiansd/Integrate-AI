import requests
import subprocess
import signal
import os
import uvicorn
from fastapi import FastAPI, HTTPException
import time
import threading

from health_check.connections_counter import read_counter, initialize_counter_file
from health_check.common import get_streamlit_url

app = FastAPI()

STREAMLIT_URL = get_streamlit_url()


@app.get('/livez')
def get_livez():
    return {'status': 'ok'}


@app.get('/readyz')
def get_readyz():
    try:
        r = requests.get(STREAMLIT_URL)
        if r.status_code == 200:
            return {"status": True}
        else:
            return {"status": False, "code": r.status_code}
    except Exception as e:
        return {"status": False, "error": str(e)}


@app.get("/openConnections")
def open_connections():
    """
    API endpoint to retrieve the global count of open connections.
    """
    count = read_counter()
    print(f"Current open connections: {count}")
    return {"open_connections": count}


@app.get("/shutdown")
def shutdown():
    try:
        # Find all Streamlit processes
        output = subprocess.check_output(["pgrep", "-f", "streamlit run"])
        pids = output.decode().strip().split("\n")

        if not pids:
            raise HTTPException(status_code=404, detail="No Streamlit process found.")

        for pid in pids:
            os.kill(int(pid), signal.SIGTERM)
            print(f"✅ Sent SIGTERM to Streamlit process with PID {pid}")

        # Delay shutdown of FastAPI to give response time
        def delayed_self_shutdown():
            time.sleep(1)
            print("💀 Shutting down the FastAPI shutdown server itself...")
            os.kill(os.getpid(), signal.SIGTERM)

        threading.Thread(target=delayed_self_shutdown, daemon=True).start()

        return {
            "status": "shutting down",
            "streamlit_pids": pids,
            "message": "FastAPI will shut down shortly."
        }

    except subprocess.CalledProcessError:
        raise HTTPException(status_code=404, detail="Streamlit process not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to shutdown Streamlit: {str(e)}")


if _name_ == "_main_":
    initialize_counter_file()
    uvicorn.run(app, host="0.0.0.0", port=8000)