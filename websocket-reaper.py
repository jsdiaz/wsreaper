#!/usr/bin/env python3

## websocket-reaper.py
## Author: J S Diaz
## Version: 0.3
## Date: 2025-02-26
## Description: This script is designed to kill stale WebSocket connections on an Apache server. The script fetches the server-status page, parses it to find Apache servers that are in graceful shutdown, and then terminates all connections that are ESTABLISHED and connected on https. It can run in different modes: kill mode to actually terminate connections, testing mode to simulate the process, and verbose mode for detailed logging.
## Requirements: Python 3, psutil, requests, BeautifulSoup4
## License: Apache License 2.0

## Usage: ./websocket-reaper.py [-h] [-k|-t] [-v] -u <url>
## Options:
## -d, --debug                          Run in debug/testing mode (inplies -v)
## -h, --help                           Show usage information and exit
## -k, --kill                           Run in kill mode
## -t <timeout>, --timeout <timeout>    Timeout in seconds (default 300s) for connections to be considered stale
## -u <url>, --url <url>                URL of the server-status page
## -v, --verbose                        Be verbose 
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
group.add_argument('-d', '--debug', action='store_true', help='Run in testing mode')
group.add_argument('-k', '--kill', action='store_true', help='Run in kill mode')
# add required argument url
parser.add_argument('-u', '--url', type=str, required=True, help='URL of the server-status page')
parser.add_argument('-t', '--timeout', type=int, default=300, help='Timeout in seconds for connections to be considered stale')
parser.add_argument('-v', '--verbose', action='store_true', help='Be verbose')
args = parser.parse_args()

# Define TESTING variable
TESTMODE = args.debug
KILLMODE = args.kill
VERBOSE = args.verbose
STATUSURL = args.url
threadTimeout = args.timeout

TESTING = False
if TESTMODE:
    TESTING = True
    VERBOSE = True
    logging.getLogger().handlers=[console_handler]
    logging.debug("Running in TESTING mode")
if KILLMODE:
    KILLPROCESS = True
    logging.debug("Running in KILL mode")
if VERBOSE:
    logging.getLogger().setLevel(logging.DEBUG)
    logging.debug("Running in VERBOSE mode")

def get_eligible_threads(url):
    serverPIDs = []
    serverStaleConnections = []
    requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
    response = requests.get(url, verify=False)
    if response.status_code != 200:
        raise ConnectionError(f"Unexpected HTTP response code: {response.status_code}")
    soup = BeautifulSoup(response.text, 'html.parser')

    try:
        if TESTING:
            for th in soup.find_all("th", text="accepting"):
                serverTable = th.find_parent("table")
                serverTableRows = serverTable.find_all("tr")[2:]
                for serverTableRow in serverTableRows:
                    if serverTableRow.find_all("td")[4].get_text(strip=True) == "yes":
                        for serverPID in serverTableRow.find_all("td")[1]:
                            serverPIDs.append(int(serverPID.text))
            logging.debug(f"Getting all active apache2 pids {serverPIDs} for testing")
            for serverPID in serverPIDs:
                logging.debug(f"Finding all threads under PID {serverPID} sending resposes to clients for longer than {threadTimeout} second(s)")
                for td in soup.find_all("td", text=str(serverPID)):
                    serverThreadTR = td.find_parent("tr")
                    if int(serverThreadTR.find_all("td")[5].get_text(strip=True)) >= threadTimeout and serverThreadTR.find_all("td")[3].get_text(strip=True) in ["W"]:
                        threadClient = serverThreadTR.find_all("td")[11].get_text(strip=True)
                        serverStaleConnections.append([serverPID, threadClient])
                        logging.debug(f"PID {serverPID} had been sending reply to client {threadClient} for longer than {threadTimeout}")

        else:
            logging.debug("Parsing server-status page and getting apache pids that are exiting")
            # find pids for all servers that are exiting
            for td in soup.find_all("td", text="yes (old gen)"):
                serverPIDs.append(int(td.find_previous_sibling('td').get_text(strip=True)))
            # find all threads under each pid that have been gracefully exiting for longer than threadTimeout seconds
            for serverPID in serverPIDs:
                logging.debug(f"Finding all threads under PID {serverPID} sending resposes to clients for longer than {threadTimeout} second(s)")
                for td in soup.find_all("td", text=str(serverPID)):
                    serverThreadTR = td.find_parent("tr")
                    if int(serverThreadTR.find_all("td")[5].get_text(strip=True)) >= threadTimeout and serverThreadTR.find_all("td")[3].get_text(strip=True) == "G":
                        serverStaleConnections.append([serverPID, serverThreadTR.find_all("td")[11].get_text(strip=True)])
                        logging.debug(f"PID {serverPID} has thread connected to {serverStaleConnections[1]} for longer than {threadTimeout}")

        if len(serverStaleConnections) == 0:
            logging.debug("No eligible connections found")
            return None
        else:
            logging.debug(f"Found {len(serverStaleConnections)} eiligible connections")
            return serverStaleConnections
    
    except ConnectionError as e:
        logging.error(f"Failed to fetch webpage data: {str(e)}")
        return None
    except Exception as e:
        logging.error(f"An error occured while parsing webpage data: {str(e)}")
        return None

def process_connection(serverPID,clientIP):
    try:
        # ensure valid process ID
        if not isinstance(serverPID, int) or serverPID <= 0:
            raise ValueError("Invalid Process ID")

        if not psutil.pid_exists(serverPID):
            raise ProcessLookupError(f"a process with pid {serverPID} does not exist")

        logging.debug(f"a process with pid {serverPID} exists")

        p = psutil.Process(serverPID)
        for connection in p.connections():
            if connection.status == psutil.CONN_ESTABLISHED and connection.laddr.port == 443 and connection.raddr.ip == "::ffff:" + clientIP:
                logging.debug(f"Found ESTABLISHED connection on port 443 for client {clientIP}")
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
        data = get_eligible_threads(STATUSURL)
        if not data:
            raise ValueError("No matching PIDs found")

        logging.debug(f"Found matching threads: {data}")
        
        for serverClient in data:
            # Assuming matches are captured as list of process IDs and client IPs
            try:
                ssResult = process_connection(serverClient[0],serverClient[1])
                if ssResult and KILLMODE:
                    logging.debug(f"Successfully terminated stale connections to PID {serverClient[0]}")
                elif KILLMODE:
                    logging.error(f"Failed to terminate stale connections to PID {serverClient[0]}")
            except ValueError as e:
                logging.error(f"Value error while processing PID {serverClient[0]} {str(e)}")
            except ProcessLookupError as e:
                logging.error(f"Process lookup error while processing PID {serverClient[0]}: {str(e)}")
            except subprocess.CalledProcessError as e:
                logging.error(f"Subprocess error while processing PID {serverClient[0]}: {str(e)}")
            except Exception as e:
                logging.error(f"Unexpected error while processing PID {serverClient[0]}: {str(e)}")
                
    except ValueError as e:
        logging.debug(f"{e}: exiting")
    except ConnectionError as e:
        logging.error("failed to fetch server-status")
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")

if __name__ == "__main__":
    main()
