#!/usr/bin/env python3

## websocket-reaper.py
## Author: J S Diaz
## Version: 0.2
## Date: 2025-02-26
## Description: This script is designed to kill stale WebSocket connections on an Apache server. The script fetches the server-status page, parses it to find Apache servers that are in graceful shutdown, and then terminates all connections that are ESTABLISHED and connected on https. It can run in different modes: kill mode to actually terminate connections, testing mode to simulate the process, and verbose mode for detailed logging.
## Requirements: Python 3, psutil, requests, BeautifulSoup4
## License: Apache License 2.0

## Usage: ./websocket-reaper.py [-h] [-k|-t] [-v] -u <url>
## Options:
## -h, --help               Show usage information and exit
## -k, --kill               Run in kill mode
## -t, --testing            Run in testing mode (inplies -v)
## -u <url>, --url <url>    URL of the server-status page
## -v, --verbose            Be verbose 
## Example: ./websocket-reaper.py -u http://localhost/server-status -t

import logging, logging.handlers
from bs4 import BeautifulSoup
import os
import psutil
import requests
import re
import subprocess
import argparse

# Configure Logging
formatter = logging.Formatter('Apache WSReaper: %(asctime)s - %(levelname)s - %(message)s')

# Log to console
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# Log to syslog
syslog_handler = logging.handlers.SysLogHandler(address='/dev/log')
syslog_handler.setFormatter(formatter)

# Configure root logger
logging.basicConfig(level=logging.WARN, handlers=[console_handler, syslog_handler])

# Parse command line arguments
parser = argparse.ArgumentParser(description='WebSocket Reaper')
group = parser.add_mutually_exclusive_group()
group.add_argument('-k', '--kill', action='store_true', help='Run in kill mode')
group.add_argument('-t', '--testing', action='store_true', help='Run in testing mode')
# add required argument url
parser.add_argument('-u', '--url', type=str, required=True, help='URL of the server-status page')
parser.add_argument('-v', '--verbose', action='store_true', help='Be verbose')
args = parser.parse_args()

# Define TESTING variable
TESTMODE = args.testing
KILLMODE = args.kill
VERBOSE = args.verbose
STATUSURL = args.url
TESTING = False
if TESTMODE:
    TESTING = True
    VERBOSE = True
    logging.debug("Running in TESTING mode")
if KILLMODE:
    KILLPROCESS = True
    logging.debug("Running in KILL mode")
if VERBOSE:
    logging.getLogger().setLevel(logging.DEBUG)
    logging.debug("Running in VERBOSE mode")

def fetch_webpage_data(url):
    serverPIDs = []

    try:
        if TESTING:
            logging.debug("Getting a two first apache2 pids for testing")
            processList = []
            for process in psutil.process_iter(['pid', 'name']):
                if process.info['name'] == 'apache2':
                    processList.append(process.info['pid'])
            # get last two pids
            serverPIDs = processList[-2:]

        else:
            requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
            response = requests.get(url, verify=False)
            if response.status_code != 200:
                raise ConnectionError(f"Unexpected HTTP response code: {response.status_code}")
            soup = BeautifulSoup(response.text, 'html.parser')
    
            # Find all td elements containing 'yes (old gen)'
            logging.debug("Parsing server-status page and getting apache pids that are exiting")
            for td in soup.find_all("td", text="yes (old gen)"):
                serverPIDs.append(int(td.find_previous_sibling('td').get_text(strip=True)))
                
        return serverPIDs
    
    except ConnectionError as e:
        logging.error(f"Failed to fetch webpage data: {str(e)}")
        return None
    except Exception as e:
        logging.error(f"An error occured while parsing webpage data: {str(e)}")
        return None

def process_connection(serverPID):
    try:
        # ensure valid process ID
        if not isinstance(serverPID, int) or serverPID <= 0:
            raise ValueError("Invalid Process ID")

        if not psutil.pid_exists(serverPID):
            raise ProcessLookupError(f"a process with pid {serverPID} does not exist")

        logging.debug(f"a process with pid {serverPID} exists")

        p = psutil.Process(serverPID)
        for connection in p.connections():
            if connection.status == psutil.CONN_ESTABLISHED and connection.laddr.port == 443:
                remote_addr = f'[{connection.raddr.ip}]:{connection.raddr.port}'

                if KILLMODE:
                    logging.debug(f"Terminating connection to {remote_addr}")
                    # kill the network connections via ss
                    try:
                        ss_output = subprocess.run(
                            ['/usr/bin/ss', '-K', 'dst', remote_addr],
                            capture_output=True, 
                            check=True,
                            text=True
                        )
                        logging.debug(f"ss terminated connection to {remote_addr}")
                    except subprocess.CalledProcessError as e:
                        logging.error(f"ss failed to terminate connection to {remote_addr}")     
                    except Exception as e:
                        logging.error(f"Unexpected error while terminating connection to {remote_addr}: {str(e)}")
                else:
                    logging.debug(f"Would terminate connection to {remote_addr}")
            else:
                logging.debug(f"PID {serverPID} has no ESTABLISHED connections on port 443")
                return False

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
    try:
        data = fetch_webpage_data(STATUSURL)
        if not data:
            raise ValueError("No matching PIDs found")

        logging.debug(f"Found matching PIDS: {data}")
        
        for serverPID in data:
            # Assuming matches are captured as process IDs
            try:
                ssResult = process_connection(serverPID)
                if ssResult and KILLMODE:
                    logging.debug(f"Successfully terminated stale connections to PID {serverPID}")
                elif KILLMODE:
                    logging.error(f"Failed to terminate stale connections to PID {serverPID}")
            except ValueError as e:
                logging.error(f"Value error while processing PID {serverPID}: {str(e)}")
            except ProcessLookupError as e:
                logging.error(f"Process lookup error while processing PID {serverPID}: {str(e)}")
            except subprocess.CalledProcessError as e:
                logging.error(f"Subprocess error while processing PID {serverPID}: {str(e)}")
            except Exception as e:
                logging.error(f"Unexpected error while processing PID {serverPID}: {str(e)}")
                
    except ValueError as e:
        logging.debug(f"{e}: exiting")
    except ConnectionError as e:
        logging.error("failed to fetch server-status")
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")

if __name__ == "__main__":
    main()
