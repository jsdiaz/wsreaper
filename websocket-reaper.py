import logging
from bs4 import BeautifulSoup
import psutil
import requests
import re
import subprocess

# Configure Logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def fetch_webpage_data(url):
    try:
        response = requests.get(url)
        if response.status_code != 200:
            raise ConnectionError(f"Unexpected HTTP response code: {response.status_code}")
        soup = BeautifulSoup(response.text, 'html.parser')
# for testing with captured output
#        with open("server-status-multiple-old") as f:
#            soup = BeautifulSoup(f.read(), 'html.parser')

        # Find all td elements containing 'yes (old gen)'
        serverPIDs = []
        for td in soup.find_all("td", text="yes (old gen)"):
            prev_sibling = td.find_previous_sibling('td')
            for txt in prev_sibling.stripped_strings:
                serverPIDs.append(int(txt))
                
        return serverPIDs
    
    except ConnectionError as e:
        logging.error(f"Failed to fetch webpage data: {str(e)}")
        return None

def process_connection(serverPID):
    try:
        # ensure valid process ID
        if not isinstance(serverPID, int) or serverPID <= 0:
            raise ValueError("Invalid Process ID")

        if psutil.pid_exists(serverPID):
            logging.debug(f"a process with pid {serverPID} exists")
        else:
            raise ProcessLookupError(f"a process with pid {serverPID} does not exist")

        p = psutil.Process(serverPID)
        for connection in p.connections():
            if connection.status == psutil.CONN_ESTABLISHED and connection.laddr.port == 443:
                remote_addr = f'[{connection.raddr.ip}]:{connection.raddr.port}'
                # call ss
                try:
                    ss_output = subprocess.run(
                        ['/usr/bin/ss', '-na', 'dst', remote_addr],
                        capture_output=True, 
                        check=True,
                        text=True
                    )
                    logging.debug(f"ss terminated connection to {remote_addr}")
        
                except Exception as e:
                    logging.error(f"ss failed to terminate connection to {remote_addr}")
                    
        return True
        
    except ValueError as e:
        logging.error(f"PID Value Error: {str(e)}")
        return False
    except ProcessLookupError as e:
        logging.error(f"PID Lookup Error: {str(e)}")
        return False
    except Exception as e:
        logging.error(f"Connection processing failed: {str(e)}")
        return False

def main():
    url = 'http://localhost/server-status'

    try:
        data = fetch_webpage_data(url)
        if data:
            logging.debug(f"Found matching PIDS: {data}")
        if not data:
            raise ValueError("No matching PIDs found")
        
        for serverPID in data:
            # Assuming matches are captured as process IDs
            try:
                ssResult = process_connection(serverPID)
                if ssResult:
                    logging.debug(f"Successfully terminated stale connections to PID {serverPID}")
                
            except Exception as e:
                logging.error(f"Failed to terminate stale connections to PID {serverPID}")
                
    except ValueError as e:
        logging.debug(f"{e}: exiting")
    except ConnectionError as e:
        logging.error("failed to fetch server-status")
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")

if __name__ == "__main__":
    main()
