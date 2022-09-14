import logging
import shlex
import subprocess
import re


logger = logging.getLogger(__name__)


# registered modules are imported and used in the core
registered_modules = {}


def dict_getter(d, *args, **kwargs):
    if not d:
        return None
    out = {}
    for arg in args:
        out[arg] = d.get(arg, None)
    for key, val in kwargs.items():
        out[val] = d.get(key, None)
    return out


def run_shell(command_string, raise_exception=False):
    # convenience function for running arguments with shell=True
    # these arguments can be formatted as a single string as long as the syntax is exactly the same as on the cli
    # the system shell will default to /bin/sh for these commands
    try:
        command = shlex.split(command_string)
        cmd = subprocess.run(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return cmd.returncode, cmd.stdout.decode().strip("\n")
    except Exception as e:
        logger.error(f"Error running command ({command_string}) ({e})")
        if raise_exception is False:
            return None, None
        raise


def register_module(*args, **kwargs):

    """
    Register a module to be used with the Core
    """

    def wrapper(clazz):
        # register the module
        registered_modules[clazz.name] = clazz
        return clazz

    return wrapper


class CommandParser:

    def __init__(self, data):
        self._data = data or ""
        self.data = []

    @staticmethod
    def execute(command):
        _, data = run_shell(command)
        return CommandParser(data)

    def split(self, string_split):
        return [CommandParser(data) for data in self._data.split(string_split)]

    def contains(self, regex):
        return re.search(regex, self._data, re.MULTILINE) is not None

    @staticmethod
    def _listify(item):
        return item if isinstance(item, list) else list(item) if isinstance(item, tuple) else [item]

    @staticmethod
    def _dict_getter(d, *keys):
        return [d.get(key) for key in keys]

    def filter(self, lambda_filter=None, **value_filters):
        if lambda_filter is not None:
            self.data = list(filter(lambda_filter, self.data))
        if value_filters:
            keys = list(value_filters.keys())
            filter_values = self._dict_getter(value_filters, *keys)
            self.data = list(filter(lambda x: self._dict_getter(x, *keys) == filter_values, self.data))
        return self

    def list(self, regex, *keys):
        lst = re.findall(regex, self._data or "", re.MULTILINE)
        self.data = [dict(zip(keys, self._listify(listitem))) for listitem in lst]
        return self

    def dict(self, regex, *keys):
        match = re.match(regex, self._data or "", re.MULTILINE)
        if match:
            d = match.groupdict()
            self.data = [{
                key: d.get(key) for key in keys
            }] if keys else [d]
        return self

    def get(self, regex, key=0, default=None):
        match = re.search(regex, self._data, re.MULTILINE)
        return match.group(key).strip() if match else default

    def all(self):
        return self.data

    def first(self):
        return self.data[0] if self.data else {}

    def values(self, *keys):
        return [[item.get(key) for key in keys] for item in self.data]


class Module:

    # the name of the module for referencing
    name = "module"

    # the event key to send incoming events from the websocket to
    # set to None to ignore events
    event_keys = []

    def __init__(self, core, queue):
        # reference to the core application
        self.core = core

        # the queue is where data that will be sent over the websocket is queued up
        # modules should put any data that needs to be sent into this queue
        self.queue = queue
        self.running = False

    def startup(self):
        """
        Startup the module
        :return: None
        """
        self.running = True

    def shutdown(self):
        """
        Shutdown and cleanup this module
        :return: None
        """
        self.running = False

    def event(self, ev):
        """
        Process an incoming event
        :param ev: Object for this module to process
        :return: None
        """
        pass
