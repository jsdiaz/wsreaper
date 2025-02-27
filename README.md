# Apache Websocket Reaper

Python3 script that kills established socket connections in gracefully shutting down apache 2.4 mpm-event proxy servers.

## Description

This script is designed to kill stale WebSocket connections on an Apache 2.4 server functioning as a reverse proxy. It is intended as a brute-force workaround to Apache bug 65180 (https://bz.apache.org/bugzilla/show_bug.cgi?id=65180). The script is intended to run at intervals in cron. It forcefully kills connections that do not exit, avoiding server exhaustion once servers with WebSocket connections, that are shutting down, fill all available server slots. This issue is fixed in Apache 2.5 by adding a ProxyWebsocketIdleTimeout directive that sets the maximum amount of time to wait for data on the WebSocket tunnel (https://httpd.apache.org/docs/trunk/mod/mod_proxy_wstunnel.html#proxywebsocketidletimeout).

The script fetches the server-status page, parses it to find Apache servers that are in graceful shutdown. It then terminates all connections that are ESTABLISHED and connected on https. It can run in different modes: kill mode to actually terminate connections, testing mode to simulate the process, and verbose mode for detailed logging.

## Getting Started

### Dependencies

* Python 3
* BeautifulSoup4
* psutil
* requests
* subprocess

### Installing

* Download the script from the github repo.
* Install Python3 and required Python libraries (see dependencies).
* Make the script executable (`chmod 750 websocket-reaper.py`)
* Change the ownership to root (`chown root:root websocket-reaper.py`)
* Copy the script into /usr/local/sbin (or your preferred location where the script will be run from).

### Executing program

In order for the script to be able to kill established connections, it will need elevated privileges, eg as root. Anything that you download and run with elevated privs on your machine should be throughly inspected. Please inspect this code prior to running it with elevated privs.

* This script should be run as root.
* Run the script in test mode (`-d`) and inspect output.
* Set up the script to run at the desired interval in cron.


#### Usage
./websocket-reaper.py -u <url> [-h] [-d|-k] [-v] [-t TIMEOUT]


#### Options
-d, --debug                         Run in debug/testing mode (inplies -v)  
-h, --help                          Show usage information and exit  
-k, --kill                          Run in kill mode  
-t <timeout>, --timeout <timeout>   Timeout in seconds (default 300) for connections to be considered stale  
-u <url>, --url <url>               URL of the server-status page  
-v, --verbose                       Be verbose  


#### Example
```
./websocket-reaper.py -u http://localhost/server-status -d
```

## Help

If you experience odd behavior, try running the script in testing mode (include `-d`).

## Authors

Contributors names and contact info

@[jsdiaz](https://github.com/jsdiaz)

## Version History

* 0.3
    * Added timeout checking
    * Added per client validation
    * Improved debug mode
* 0.2
    * Added command line options
    * Improved error handling
    * Various optimizations
    * See [commit change]() or See [release history]()
* 0.1
    * Initial Release

## License

This project is licensed under the Apache License 2.0 License - see the LICENSE.md file for details

## Acknowledgments
Inspired by the need for my Apache server to not die a horrible, slow death from exhaustion.
