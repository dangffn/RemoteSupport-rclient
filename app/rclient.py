#!/usr/bin/env python3
import argparse
import base64
import json
import logging
import os
import re
import ssl
import sys
import tempfile
from multiprocessing import Queue
from queue import Empty
from threading import Thread

import requests
import websocket
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5
from websocket import create_connection

from modules import registered_modules
from modules.util import run_shell

"""
Linux dependencies
    - dmidecode
    - lsb-release
    - hdparm

TODO: implement machine-id checking when provisioning, useful for
  re-establishing association with an existing device after software reinstall
  https://man7.org/linux/man-pages/man5/machine-id.5.html
"""



logging.basicConfig(
    format="[%(asctime)s] (%(levelname)s) <%(name)s.%(funcName)s:%(lineno)d> —-> %(message)s",
    level=logging.DEBUG
)

logger = logging.getLogger(__name__)


def to_camel_case(snake_case):
    s = snake_case.split("_")
    return s[0] + "".join([w.capitalize() for w in s[1:]])


class Config:
    base_dir = os.environ.get("REMOTE_SUPPORT_HOME", "/usr/local/remotesupport")
    config_dir = os.path.join(base_dir, "config")
    config_file = os.path.join(config_dir, "config.json")
    private_key_file = os.path.join(config_dir, "private.key")
    base_url = os.environ.get("REMOTE_SUPPORT_BASE_URL", "https://ssh.danbuntu.com")
    ws_endpoint = base_url.replace("http", "ws")

    def __init__(self):
        self._loaded = False
        self._data = {}

    def get(self, key, default=None):
        if not self._loaded:
            self.load()
        return self._data.get(key, default)

    def clear(self, *keys):
        for key in keys:
            if key in self._data:
                del self._data[key]
        self.save()

    def set(self, **kwargs):
        self._data.update(kwargs)
        self.save()

    def save(self):
        Utils.save_file(self.config_file, json.dumps(self._data, indent=True))

    def load(self):
        self._data = Utils.load_json_file(self.config_file)
        self._loaded = True


class Info:

    fields = [
        "hostname", "manufacturer", "model", "ram", "cpu", "operating_system",
        "operating_system_version", "operating_system_codename", "serial_number"
    ]

    def _dictify(self, item):

        if isinstance(item, dict):
            # dictionary
            for key, value in item.items():
                item[key] = self._dictify(value)

        elif isinstance(item, list):
            # recurse through each element
            item = [self._dictify(element) for element in item]

        return item

    def to_dict(self):
        output = {}
        for field in self.fields:
            output.update({field: self._dictify(getattr(self, field, None))})

        return output

    # @property
    # def network_interfaces(self):
    #     primary_int = self.primary_int
    #     if primary_int is not None:
    #         if_addresses = netifaces.ifaddresses(primary_int).get(netifaces.AF_LINK)
    #         if len(if_addresses) > 0:
    #             return if_addresses[0].get("addr")
    #     return None

    @property
    def hostname(self):
        _retval, hostname = run_shell("hostname", raise_exception=False)
        return hostname

    @property
    def manufacturer(self):
        _retval, mfg = run_shell("dmidecode -s system-manufacturer", raise_exception=False)
        return mfg

    @property
    def model(self):
        _retval, model = run_shell("dmidecode -s system-product-name", raise_exception=False)
        if model is None:
            _retval, model = run_shell("cat /proc/cpuinfo 2> /dev/null | grep Model | cut -f2 -d':' | xargs", raise_exception=False)
        # TODO: check the output of /proc/cpuinfo if this is None
        return model

    @property
    def ram(self):
        _retval, output = run_shell("free -h", raise_exception=False)
        if output:
            match = re.search(r'Mem:\s+(?P<ram>[^\s]+)', output)
            if match:
                return match.group("ram")
        return None

    @property
    def cpu(self):
        _retval, output = run_shell("lscpu", raise_exception=False)
        if output:
            match = re.search(r'Model name:\s+(?P<cpu>.*)', output)
            if match:
                return match.group("cpu")
        return None

    @property
    def operating_system(self):
        _retval, os_name = run_shell("lsb_release -si", raise_exception=False)
        return os_name

    @property
    def operating_system_version(self):
        _retval, os_version = run_shell("lsb_release -sr", raise_exception=False)
        return os_version

    @property
    def operating_system_codename(self):
        _retval, codename = run_shell("lsb_release -sc", raise_exception=False)
        return codename

    @property
    def serial_number(self):
        _retval, pc_serial = run_shell("dmidecode -s system-serial-number", raise_exception=False)
        if pc_serial is None:
            _retval, pc_serial = run_shell("cat /proc/cpuinfo 2> /dev/null | grep Serial | cut -f2 -d':' | xargs")
        return pc_serial


class Utils:

    @classmethod
    def read_file(cls, filename, default=None):
        if os.path.isfile(filename):
            logger.debug(f"Loading file {filename}")
            try:
                with open(filename, "r") as infile:
                    return infile.read()
            except Exception as e:
                logger.exception(f"Error reading file {filename}")
        else:
            logger.debug(f"Tried to load file {filename} but it doesn't exist")
        return default

    @classmethod
    def load_json_file(cls, filename):
        if os.path.isfile(filename):
            try:
                return json.loads(cls.read_file(filename))
            except Exception as e:
                logger.exception(f"Error converting json {filename}")
        return {}

    @classmethod
    def save_file(cls, filename, data, mode="w"):
        try:
            logger.debug(f"Saving file {filename}")
            folder = os.path.dirname(filename)
            if not os.path.isdir(folder):
                os.makedirs(folder)
            with open(filename, mode) as outfile:
                outfile.write(data)
        except Exception as e:
            logger.exception(f"Error saving to file {filename}")

    @classmethod
    def load_private_key(cls, filename):
        try:
            data = cls.read_file(filename)
            if data:
                return RSA.importKey(data)
        except Exception as e:
            logger.exception(f"Error loading private key {filename}")
        return None

    @classmethod
    def generate_key(cls):
        logger.info("Generating private key")
        key = RSA.generate(1024)
        Utils.save_file(Config.private_key_file, key.exportKey("PEM"), mode="wb")
        os.chmod(Config.private_key_file, 0o600)  # RW permissions for owner only
        return key

    @classmethod
    def get_signature(cls, data, private_key):
        digest = SHA256.new(data.encode("utf-8"))
        signer = PKCS1_v1_5.new(private_key)
        return base64.b64encode(signer.sign(digest)).decode("utf-8")

    @classmethod
    def verify_signature(cls, data, signature, public_key):
        digest = SHA256.new(data.encode("utf-8"))
        verifier = PKCS1_v1_5.new(public_key)
        return verifier.verify(digest, signature)


class API:

    class DeviceContract:
        def __init__(self, data):
            data = data or {}
            self.uuid = data.get("uuid")

    class ScriptQueueContract:
        def __init__(self, data):
            self.data = data or {}
            self.uuid = data.get("uuid")
            self.script_language = API._dict_path(self.data, "script", "language")
            self.script_arguments = API._dict_path(self.data, "script", "arguments")
            self.script_name = API._dict_path(self.data, "script", "name")
            self.script_description = API._dict_path(self.data, "script", "description")

        @property
        def code(self):
            code_base64 = API._dict_path(self.data, "script", "codeBase64")
            try:
                return base64.b64decode(code_base64)
            except Exception as e:
                logger.error("Failed to decode base64 from script queue result")
            return None

    url = f"{Config.base_url}/graphql"

    def __init__(self):
        self.headers = None

    def authenticate(self, device_id, signature):
        if device_id and signature:
            self.headers = self.auth_headers(device_id, signature)
        else:
            self.headers = None

    @classmethod
    def auth_headers(cls, device_id, signature):
        return {
            "Support-Device-Id": device_id,
            "Support-Device-Sig": signature,
        }

    @staticmethod
    def _dict_path(d, *path, default=None):
        for p in path:
            d = d.get(p, {})
        return d or default

    def _query(self, query, variables):
        logger.debug(f"Query {self.url}")
        response = requests.post(self.url, json={'query': query, 'variables': variables}, headers=self.headers)

        logger.debug(f"Response code [{response.status_code}] from {self.url}")

        if response.status_code == 200:
            return response.json()

        else:
            raise Exception(f"Error with the request [{response.status_code}] ({response.reason})")

    def _get_error_list(self, error_response):
        if error_response:
            error_lists = list(map(lambda d: d.get("messages"), error_response))
            return [item for sublist in error_lists for item in sublist]
        return None

    def new_device(self, public_key, workgroup_uuid, **device_info) -> DeviceContract:

        query = """
            mutation NewDevice(
              $publicKey: String!, 
              $workgroupUuid: String!,
              $model: String,
              $hostname: String,
              $manufacturer: String
            ) {
              support {
                newDevice(input: {
                  publicKey: $publicKey,
                  workgroup: $workgroupUuid,
                  model: $model,
                  hostname: $hostname,
                  manufacturer: $manufacturer,
                }) {
                  uuid
                  errors {
                    field
                    messages
                  }
                }
              }
            }
        """

        device_info = {to_camel_case(key): val for key, val in device_info.items()}

        data = self._query(query=query, variables={
            "publicKey": public_key,
            "workgroupUuid": workgroup_uuid,
            **device_info
        })

        new_device = self._dict_path(data, "data", "support", "newDevice", default={})
        errors = self._get_error_list(new_device.get("errors"))
        if errors is not None:
            raise Exception(f"Errors received from new_device mutation ({', '.join(errors)})")

        return API.DeviceContract(new_device)

    def get_script(self, script_uuid) -> ScriptQueueContract:

        query = """
            query Script($uuid: String!) {
              support {
                scriptQueue(uuid: $uuid) {
                  uuid
                  script {
                    dateCreated
                    lastUpdated
                    name
                    description
                    language
                    codeBase64
                  }
                  __typename
                }
              }
            }
        """

        data = self._query(
            query=query,
            variables={
                "uuid": script_uuid,
            }
        )

        script_data = self._dict_path(data, "data", "support", "scriptQueue")

        return API.ScriptQueueContract(script_data) if script_data else None


class Core:

    websocket_url = f"{Config.ws_endpoint}/ws/deviceconnect/"

    def __init__(self):
        self.private_key = Utils.load_private_key(Config.private_key_file) or Utils.generate_key()
        self.config = Config()
        self.api = API()
        self.websocket = None
        self.queue = Queue()
        self.send_thread = None
        self.running = False
        self.info = Info()

        self.modules = {}
        self.event_keys = {}
        for name, clz in registered_modules.items():
            module = clz(self, self.queue)
            self.modules[name] = module
            if module.event_keys:
                for event_key in clz.event_keys:
                    self.event_keys[event_key] = module

    def __enter__(self):
        self.running = True

        try:
            self.connect()
        except ConnectionError:
            sys.exit(1)

        self.send_thread = Thread(target=self._send_loop)
        self.send_thread.start()

        for module in self.modules.values():
            logger.debug(f"Starting module {module.name}")
            module.startup()

        logger.info(f"Core startup complete")

        return self.websocket

    def __exit__(self, exc_type, exc_val, exc_tb):

        for module in self.modules.values():
            logger.debug(f"Stopping module {module.name}")
            module.shutdown()

        self.running = False

        self.send_thread.join()
        self.queue.close()
        self.disconnect()

        logger.info(f"Core shutdown complete")

    def get_handler(self, event_key):
        return self.event_keys.get(event_key)

    def _send_loop(self):
        logger.debug("Starting core send loop")
        while self.running:
            try:
                event = self.queue.get(True, 1)
                _msg = json.dumps(event)
                logger.debug(f"Websocket send [{_msg}]")
                self.websocket.send(_msg)
            except (OSError, EOFError) as e:
                logger.error(f"Error reading from queue ({e})")
                break
            except Empty:
                pass

        self.running = False
        logger.debug("Stopped core send loop")

    @property
    def public_key(self):
        if self.private_key:
            return self.private_key.publickey()
        return None

    def provision(self, workgroup_uuid, **device_info):
        if self.public_key is None:
            logger.warning("Could not provision, missing public key")
            return False

        logger.info(f"Sending provision request")

        try:
            public_key = self.public_key.exportKey("PEM").decode("utf-8")
            device = self.api.new_device(
                public_key,
                workgroup_uuid,
                **device_info
            )
            self.config.set(
                device_id=device.uuid,
                workgroup_uuid=workgroup_uuid
            )
            return True

        except Exception as e:
            error_message = f"Error sending new_device request ({e})"
            logger.exception(error_message)
            raise ConnectionError(error_message)

    def connect(self):
        workgroup_uuid = self.config.get("workgroup_uuid")
        device_id = self.config.get("device_id")
        if not workgroup_uuid or not self.private_key or not device_id:
            error_msg = "Could not connect because missing one of private_key / workgroup_uuid / device_id"
            logger.critical(error_msg)
            raise ConnectionError(error_msg)

        signature = Utils.get_signature(device_id, self.private_key)

        try:
            logger.info(f"Connecting websocket {self.websocket_url}")
            self.websocket = create_connection(
                self.websocket_url,
                header=API.auth_headers(device_id, signature),
                sslopt={
                    "cert_reqs": ssl.CERT_NONE
                }
            )
        except Exception as e:
            error_message = f"Failed to create websocket connection ({e})"
            logger.critical(error_message)
            raise ConnectionError(error_message)

    def disconnect(self):
        logger.info(f"Disconnecting websocket {self.websocket_url}")
        if self.websocket:
            self.websocket.close()
            self.websocket = None

    def get_script(self, uuid):
        """
        Get a script from the API
        Decode and save the script content to a temporary file
        Return the language, arguments, temporary file path
        """

        device_id = self.config.get("device_id")
        if not self.private_key or not device_id:
            error_msg = "Could not connect because missing one of private_key / device_id"
            logger.critical(error_msg)
            raise ConnectionError(error_msg)

        signature = Utils.get_signature(device_id, self.private_key)

        self.api.authenticate(device_id, signature)

        language = arguments = script_path = None

        try:
            script = self.api.get_script(uuid)

            if script:

                logger.info(f"Downloaded script [{script.script_name}] --> {uuid} from the API")

                # create the temp file and do not delete on close
                temp_file = tempfile.NamedTemporaryFile("wb", delete=False)
                temp_file.write(script.code or b'')
                temp_file.close()
                logger.info(f"Created temporary file for script [{script.script_name}] --> {temp_file.name}")

                language = script.script_language
                arguments = script.script_arguments
                script_path = temp_file.name

        except Exception:
            logger.exception(f"Failed to get script {uuid}")

        return language, arguments, script_path


class AlreadyProvisionedException(Exception):
    pass


def main():
    parser = argparse.ArgumentParser(description="Core client connection program for the Remote Support app")
    parser.add_argument("--workgroup", "-w", type=str, help="The workgroup ID to join this device to")
    parser.add_argument("--provision-only", action="store_true", help="Provision the system and exit")
    parser.add_argument("--log-level", choices=[
        "debug", "info", "warning", "error", "critical"
    ], default="info")

    args = parser.parse_args()

    # set the log level
    logger.setLevel(getattr(logging, args.log_level.upper()))

    core = Core()

    provisioned = all([core.config.get("device_id"), core.private_key])
    if args.workgroup and args.workgroup != core.config.get("workgroup_uuid"):
        # workgroup is changing
        provisioned = core.provision(args.workgroup, **core.info.to_dict()) is True

    if args.provision_only is True:
        sys.exit(0 if provisioned else 1)

    with core as ws:

        while core.running:
            try:

                # receive message from websocket
                logger.debug(f"Waiting for messages")

                data = ws.recv()

                if data:
                    logger.debug(f"Websocket receive [{data}]")
                else:
                    logger.warning("Websocket received empty data")
                    continue


                msg = json.loads(data)

                # terminal event str
                if type(msg) == str:
                    _type, _data = msg.split(":", 1)

                    handler = core.get_handler(_type)
                    if handler:
                        logger.debug(f"Handling message with handler {handler.name}")
                        handler.event(_data)
                        continue

                # terminal event dict
                elif type(msg) == dict:
                    _type = msg.get("type")
                    _data = msg.get("data")

                    handler = core.get_handler(_type)
                    if handler:
                        logger.debug(f"Handling message with handler {handler.name}")
                        handler.event(_data)
                        continue

                # unknown event
                logger.info(f"Unhandled message from client {msg}")

            except websocket.WebSocketConnectionClosedException as e:
                logger.error(f"Websocket closed unexpectedly ({e})")
                break

            except (InterruptedError, KeyboardInterrupt):
                logger.info("Interrupt received")
                break

            except Exception as e:
                logger.exception(f"Exception raised receiving websocket message")


if __name__ == "__main__":
    main()
