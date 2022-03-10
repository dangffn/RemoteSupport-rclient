#!/usr/bin/env python3
import logging
import os
import pty
import select
import subprocess
import sys
from threading import Thread
from modules.util import register_module, Module


logger = logging.getLogger(__name__)


class Shell:

    def __init__(self):
        self.i_r, self.i_w = os.pipe()
        self.o_r, self.o_w = os.pipe()
        self.running = False

    def close(self):
        # close the pipes
        self.running = False

    def run(self):

        self.running = True

        command = '/bin/bash'

        os.environ.setdefault("TERM", "xterm")

        master_fd, slave_fd = pty.openpty()

        try:

            # ws.sock.setblocking(False)

            p = subprocess.Popen(
                command,
                preexec_fn=os.setsid,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                universal_newlines=True
            )

            while p.poll() is None:
                if not self.running:
                    break

                rl = [master_fd, self.i_r]
                r, w, e = select.select(rl, [], [], 1)
                if self.i_r in r:
                    x = os.read(self.i_r, 10240)
                    if len(x) == 0:
                        break
                    os.write(master_fd, x)
                if master_fd in r:
                    o = os.read(master_fd, 10240)
                    if o:
                        os.write(self.o_w, o)

        except Exception as e:
            logger.exception(f"Exception raised in terminal ({e})")

        finally:

            for fd in [self.i_w, self.i_r, self.o_w, self.o_r]:
                try:
                    os.close(fd)
                except OSError:
                    pass

            logger.debug("Shell closed")


@register_module()
class ShellManager(Module):

    name = "terminal"
    event_keys = ["td", "terminal"]

    def __init__(self, core, queue):
        super().__init__(core, queue)
        self.shells = {}
        self.read_fd_index = {}
        self.read_fds = []
        self.threads = {}
        self.main_thread = None

    def startup(self):
        super().startup()
        self.main_thread = Thread(target=self._events_loop)
        self.main_thread.start()

    def shutdown(self):
        super().shutdown()
        for shell in self.shells.values():
            # terminate each shell
            shell.close()

        for thread in self.threads.values():
            thread.join()

        self.main_thread.join()

    def event(self, ev):
        # shortened str format
        if isinstance(ev, str):
            _id, _data = ev.split(":", 1)
            self.term_data(int(_id), _data)
            return

        # dict format
        _type = ev.get("type")
        _data = ev.get("data")
        if _type == "data":
            _id = _data.get("id")
            _data = _data.get("data")
            self.term_data(_id, _data)

        elif _type == "newterminal":
            self.new()

        elif _type == "closeterminal":
            _id = _data.get("id")
            self.close(_id)

    def term_data(self, _id, data):
        if _id is not None and data is not None:
            if _id not in self.shells:
                raise ShellDoesntExist(_id)

            os.write(self.shells[_id].i_w, data.encode())

    def _events_loop(self):
        logger.debug(f"Running main loop")
        while self.running:
            try:
                rl, wl, el = select.select([*self.read_fds], [], [], 1)
                for r in rl:
                    _id = self.read_fd_index.get(r, None)
                    if _id is not None:
                        self.queue.put(":".join(["td", str(_id), os.read(r, 10240).decode()]))
            except OSError:
                pass
        logger.debug("Exit main loop")

    def new(self):
        _id = max(self.shells.keys()) + 1 if self.shells else 0
        logger.debug(f"Created new shell with id %s", _id)
        th = Thread(target=self._run, args=(_id, ))
        self.threads[_id] = th
        th.start()
        return _id

    def close(self, _id):
        logger.debug(f"Closing shell with id {_id}")
        if _id not in self.shells:
            raise ShellDoesntExist(_id)
        self.shells[_id].close()

    def _run(self, _id):

        shell = Shell()

        # set up tracking for this shell
        logger.debug(f"Setting shell id {_id} to {shell}")
        self.shells[_id] = shell
        self.read_fd_index[shell.o_r] = _id
        self.read_fds.append(shell.o_r)

        self.queue.put({
            "type": "terminal",
            "data": {
                "type": "startterminal",
                "data": {
                    "id": _id
                }
            }
        })

        # run the shell
        shell.run()

        self.queue.put({
            "type": "terminal",
            "data": {
                "type": "stopterminal",
                "data": {
                    "id": _id
                }
            }
        })

        logger.debug(f"Removing shell id {_id}")
        self.read_fds.remove(shell.o_r)
        del self.shells[_id]
        del self.read_fd_index[shell.o_r]


class ShellDoesntExist(Exception):
    def __init__(self, idx):
        super().__init__(f"Shell {idx} does not exist")


if __name__ == "__main__":
    pass
