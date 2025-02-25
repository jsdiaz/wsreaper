from bs4 import BeautifulSoup
import psutil
import requests
import re
import subprocess

debug = True

# Replace 'https://example.com' with your desired URL
url = 'http://localhost/server-status'

try:
    # Make a request to the webpage
    response = requests.get(url)
    
    # Parse the HTML content
    #soup = BeautifulSoup(response.text, 'html.parser')
    with open("server-status-multiple-old") as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
    
    # Look for all spans containing '(old gen)'
    matches = []
    for td in soup.find_all("td",text="yes (old gen)"):
        prev_sibling = td.find_previous_sibling("td")
        for text in prev_sibling.stripped_strings:
            matches.append(int(text))
        
    if debug and matches:
        print("Found matches!")
        print(matches)
    elif debug:
        print("No matches found.")

except requests.exceptions.RequestException:
    print("Failed to access the webpage.")

if matches:
    for match in matches:
        if psutil.pid_exists(match):
            print("a process with pid %d exists" % match)
        else:
            print("a process with pid %d does not exist" % match)
            exit(1)

        p = psutil.Process(match)
        for connection in p.connections(kind='inet'):
            if connection.status == psutil.CONN_ESTABLISHED:
                if connection.laddr.port == 443:
                    if debug:
                        print(connection)
                        print('remote address', connection.raddr.ip)
                        print('port', connection.raddr.port)
                    connectionIpPort = "[" + str(connection.raddr.ip) + "]:" + str(connection.raddr.port)
                    ssOutput = subprocess.run(['/usr/bin/ss', '-na', 'dst', connectionIpPort], capture_output=True, check=True)
                    if debug:
                        print(ssOutput)
