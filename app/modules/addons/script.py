#!/usr/bin/env python3
import logging
import os
import pty
import select
import subprocess
import sys
import shlex
import time
from datetime import datetime
from threading import Thread
from modules.util import register_module, Module, run_shell

logger = logging.getLogger(__name__)


class Script:

    # maximum bytes output from the script execution
    # anything over this will be discarded
    max_output_length = 10_000

    # max execution time of a script before it times out
    max_execution_time = 300

    def __init__(self, language: str, script_path: str, arguments=None):
        self.executable = self._resolve_executable(language)
        logger.debug(f"Resolved executable for language [{language}] to [{self.executable}]")
        self.path = script_path
        self.arguments = arguments

    def execute(self, arguments: str=None) -> dict:
        """
        Execute the temp file script with the specified arguments
        Resolving the language to an executable on the machine
        """
        if not os.path.isfile(self.path):
            raise ScriptDoesntExist(self.path)

        args = [self.executable, self.path] if self.executable else [self.path]

        # add the parsed argument string as an arguments list
        arguments = arguments if arguments is not None else self.arguments
        if arguments:
            args += shlex.split(arguments)

        return_code = None
        result_string = None
        result_output = None

        # record the script start time
        time_start = datetime.utcnow()

        try:

            logger.info(f"Executing script [{' '.join(args)}]")

            # execute the command, capturing stdout and stderr in a single output
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )

            proc.wait(timeout=self.max_execution_time)

            return_code = proc.returncode
            result_output = proc.stdout.read(self.max_output_length)
            result_string = "Script executed successfully" if return_code == 0 else "Script errored out"

        except subprocess.TimeoutExpired:
            logger.warning(f"Script execution timed out [{' '.join(args)}] after {self.max_execution_time} seconds")
            result_output = f"Script timed out after {self.max_execution_time} seconds"

        except Exception:
            logger.exception(f"Script execution resulted in error [{' '.join(args)}]")
            result_output = f"Unknown error executing script"

        finally:
            time_end = datetime.utcnow()

        duration = (time_end - time_start).total_seconds()
        logger.info(f"Script execution took {duration} seconds")

        return dict(
            exit_code=return_code,
            result_message=result_string,
            output=result_output,
            date_started=time_start.isoformat(),
            date_completed=time_end.isoformat()
        )

    def _resolve_executable(self, language):
        """
        Determine the executable to use for the specified language
        """
        if not language:
            return None
        _, which = run_shell(f"which {language}")

        if language.lower() == "bash":
            return self._first_file(which, "/bin/bash", default="/bin/sh")

        if language.lower() == "python":
            return self._first_file(which, "/usr/bin/python3", "/usr/bin/python")

        return which or None

    def _first_file(self, *files, default=None):
        """
        Return the first file that exists
        """
        for fil in files:
            if os.path.isfile(fil):
                return fil
        return default


@register_module()
class ScriptManager(Module):

    name = "script"
    event_keys = ["script"]

    def __init__(self, core, queue):
        super().__init__(core, queue)
        self.main_thread = None
        self.script_queue = []
        self.scripts = {}

    def startup(self):
        super().startup()
        self.main_thread = Thread(target=self._events_loop)
        self.main_thread.start()

    def shutdown(self):
        super().shutdown()

        self.main_thread.join()
        self.main_thread = None

    def event(self, ev):
        # dict format
        _type = ev.get("type")
        _data = ev.get("data")

        if _type == "queuescript":
            # queue up a new script
            self.queue_script(_data)

        elif _type == "cancelscript":
            # cancel a queued script
            self.cancel_script(_data)

    def queue_script(self, uuid):

        if uuid in self.script_queue:
            logger.info("Duplicate script uuid received, ignoring")
            return False

        language, arguments, script_path = self.core.get_script(uuid)

        if not script_path:
            logger.warning(f"Could not load script with uuid {uuid}, this will be skipped")
            return False

        script = Script(language, script_path, arguments=arguments)
        self.scripts[uuid] = script
        self.script_queue.append(uuid)

        return True

    def cancel_script(self, uuid):
        if uuid in self.script_queue:
            # remove the script from the execution queue
            self.script_queue.remove(uuid)
            self.scripts.pop(uuid, None)

        if uuid:
            self.queue.put({
                "type": "script",
                "data": {
                    "type": "scriptcancel",
                    "data": {
                        "uuid": uuid
                    }
                }
            })

    def _events_loop(self):
        logger.debug(f"Running main loop")
        while self.running:
            if not len(self.script_queue) > 0:
                time.sleep(1)
                continue

            script_uuid = self.script_queue.pop(0)
            script = self.scripts.pop(script_uuid)

            self.queue.put({
                "type": "script",
                "data": {
                    "type": "scriptstart",
                    "data": {
                        "uuid": script_uuid
                    }
                }
            })

            result = script.execute()

            self.queue.put({
                "type": "script",
                "data": {
                    "type": "scriptend",
                    "data": {
                        "uuid": script_uuid,
                        "result": result
                    }
                }
            })

        logger.debug("Exit main loop")


class ScriptDoesntExist(Exception):
    def __init__(self, path):
        super().__init__(f"Script at [{path}] cannot be found")


class ScriptNotQueued(Exception):
    def __init__(self, uuid):
        super().__init__(f"Script {uuid} is not queued")


if __name__ == "__main__":
    import json
    logger.setLevel(logging.DEBUG)
    script = Script("bash", "/home/dan/Desktop/test.sh")
    result = script.execute("one two 'argument three'")
    print(json.dumps(result, indent=True))
