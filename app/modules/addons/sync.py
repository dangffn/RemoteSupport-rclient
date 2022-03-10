#!/usr/bin/env python3
import logging
import os
import sys
import netifaces
import re
from threading import Thread
from modules.util import register_module, Module, dict_getter, run_shell, CommandParser


"""
df command
 df --total -T -x tmpfs -x devtmpfs -x squashfs -x overlay

hdparm command
 hdparm -I /dev/sda
"""


# test.py: aW1wb3J0IHN1YnByb2Nlc3MKaW1wb3J0IGxvZ2dpbmcKaW1wb3J0IHJlCgpsb2dnZXIgPSBsb2dnaW5nLmdldExvZ2dlcihfX25hbWVfXykKCmNsYXNzIFN0b3JhZ2U6CgogICAgZGVmIF9faW5pdF9fKHNlbGYpOgogICAgICAgIHNlbGYuX3JhdyA9IHJ1bl9zaGVsbCgiZmRpc2sgLWwgLS1ieXRlcyIpCiAgICAgICAgc2VsZi5kaXNrcyA9IHNlbGYuX3NlYXJjaF9kaXNrcyhzZWxmLl9yYXcpCgogICAgZGVmIF9zZWFyY2hfZGlza3Moc2VsZiwgZGF0YSk6CiAgICAgICAgcmV0dXJuIHJlLmZpbmRhbGwocidEaXNrICg/UDxkaXNrPihcL1suX1wtQS1aYS16MC05XSspKyk6Lio/KD9QPHNpemU+XGQrKSBieXRlcycsIGRhdGEpCgogICAgZGVmIHRvX2RpY3Qoc2VsZik6CiAgICAgICAgcmV0dXJuIHt9CgpjbGFzcyBEcml2ZToKCiAgICBkZWYgX19pbml0X18oc2VsZiwgbmFtZSk6CiAgICAgICAgc2VsZi5uYW1lID0gbmFtZQogICAgICAgIHNlbGYuX3JldHZhbCwgc2VsZi5fcmF3ID0gcnVuX3NoZWxsKGYiaGRwYXJtIC1JIHtzZWxmLm5hbWV9Iikgb3IgIiIKCiAgICBkZWYgc2VhcmNoKHNlbGYsIHJlZ2V4LCBncm91cCk6CiAgICAgICAgdHJ5OgogICAgICAgICAgICByZXR1cm4gcmUuc2VhcmNoKHJlZ2V4LCBzZWxmLl9yYXcpLmdyb3VwKGdyb3VwKS5zdHJpcCgpCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICAgICAgcmV0dXJuIE5vbmUKCiAgICBAcHJvcGVydHkKICAgIGRlZiBtb2RlbChzZWxmKToKICAgICAgICByZXR1cm4gc2VsZi5zZWFyY2gocidNb2RlbCBOdW1iZXI6XHMrKD9QPG1vZGVsPi4qKVxuJywgIm1vZGVsIikKCiAgICBAcHJvcGVydHkKICAgIGRlZiBzZXJpYWxfbnVtYmVyKHNlbGYpOgogICAgICAgIHJldHVybiBzZWxmLnNlYXJjaChyJ1NlcmlhbCBOdW1iZXI6XHMrKD9QPHNlcmlhbD4uKilcbicsICJzZXJpYWwiKQoKICAgIEBwcm9wZXJ0eQogICAgZGVmIGZvcm1fZmFjdG9yKHNlbGYpOgogICAgICAgIHJldHVybiBzZWxmLnNlYXJjaChyJ0Zvcm0gRmFjdG9yOlxzKyg/UDxmb3JtX2ZhY3Rvcj4uKilcbicsICJmb3JtX2ZhY3RvciIpCgogICAgQHByb3BlcnR5CiAgICBkZWYgcm90YXRpb25fcmF0ZShzZWxmKToKICAgICAgICByZXR1cm4gc2VsZi5zZWFyY2gocidOb21pbmFsIE1lZGlhIFJvdGF0aW9uIFJhdGU6XHMrKD9QPHJvdGF0aW9uX3JhdGU+LiopXG4nLCAicm90YXRpb25fcmF0ZSIpCgogICAgZGVmIHRvX2RpY3Qoc2VsZik6CiAgICAgICAgZmllbGRzID0gWyJtb2RlbCIsICJzZXJpYWxfbnVtYmVyIiwgImZvcm1fZmFjdG9yIiwgInJvdGF0aW9uX3JhdGUiXQogICAgICAgIHJldHVybiB7YXR0cjogZ2V0YXR0cihzZWxmLCBhdHRyLCBOb25lKSBmb3IgYXR0ciBpbiBmaWVsZHN9CgoKCmRlZiBydW5fc2hlbGwoY29tbWFuZF9zdHJpbmcsIHJhaXNlX2V4Y2VwdGlvbj1GYWxzZSk6CiAgICAjIGNvbnZlbmllbmNlIGZ1bmN0aW9uIGZvciBydW5uaW5nIGFyZ3VtZW50cyB3aXRoIHNoZWxsPVRydWUKICAgICMgdGhlc2UgYXJndW1lbnRzIGNhbiBiZSBmb3JtYXR0ZWQgYXMgYSBzaW5nbGUgc3RyaW5nIGFzIGxvbmcgYXMgdGhlIHN5bnRheCBpcyBleGFjdGx5IHRoZSBzYW1lIGFzIG9uIHRoZSBjbGkKICAgICMgdGhlIHN5c3RlbSBzaGVsbCB3aWxsIGRlZmF1bHQgdG8gL2Jpbi9zaCBmb3IgdGhlc2UgY29tbWFuZHMKICAgIHRyeToKICAgICAgICAjIGJlIGNhcmVmdWwgd2hlbiBydW5uaW5nIHdpdGggc2hlbGw9VHJ1ZQogICAgICAgICMgcG90ZW50aWFsIHNlY3VyaXR5IHZ1bG5lcmFiaWxpdHkgaWYgdGhlcmUgYXJlIHVzZXIgZGVmaW5lZCBzdHJpbmdzIGludGVycHJldGVkIGhlcmUKICAgICAgICBjbWQgPSBzdWJwcm9jZXNzLnJ1bihjb21tYW5kX3N0cmluZywgY2FwdHVyZV9vdXRwdXQ9VHJ1ZSwgc2hlbGw9VHJ1ZSkKICAgICAgICBpZiBjbWQucmV0dXJuY29kZSA9PSAwIGFuZCBjbWQuc3Rkb3V0IGlzIG5vdCBOb25lOgogICAgICAgICAgICB2YWx1ZSA9IGNtZC5zdGRvdXQuZGVjb2RlKCJ1dGY4Iikuc3RyaXAoIlxuIikKICAgICAgICAgICAgcmV0dXJuIGNtZC5yZXR1cm5jb2RlLCB2YWx1ZSBvciBOb25lCiAgICAgICAgcmV0dXJuIE5vbmUsIE5vbmUKICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToKICAgICAgICBsb2dnZXIuZXJyb3IoZiJFcnJvciBydW5uaW5nIGNvbW1hbmQgKHtjb21tYW5kX3N0cmluZ30pICh7ZX0pIikKICAgICAgICBpZiByYWlzZV9leGNlcHRpb24gaXMgRmFsc2U6CiAgICAgICAgICAgIHJldHVybiBOb25lLCBOb25lCiAgICAgICAgcmFpc2UKCgppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOgogICAgaW1wb3J0IGpzb24KICAgICNwcmludChEcml2ZSgiL2Rldi9zZGEiKS5fcmF3KQogICAgcHJpbnQoanNvbi5kdW1wcyhEcml2ZSgiL2Rldi9zZGEiKS50b19kaWN0KCksIGluZGVudD1UcnVlKSkK


logger = logging.getLogger(__name__)


class Storage:

    def __init__(self):
        self.disks = self._search_disks()

    def _search_disks(self):
        regex = r'^Device.+?Sectors.+?Size.+?Type$'
        regex_name_size = r'(?:^|\n)Disk (?P<disk>(?:\/[._\-A-Za-z0-9]+)+):.+?(?P<total_size>\d+) bytes'

        parser = CommandParser.execute("fdisk -l --bytes")
        parsers = parser.split("\n\n\n")
        disks = []
        for p in parsers:
            if p.contains(regex):
                d = p.dict(regex_name_size, "disk", "total_size").first()
                if d:
                    disks.append(Disk(d.get("disk"), d.get("total_size")))
        return disks

    def to_dict(self):
        return {
            "disks": [d.to_dict() for d in self.disks]
        }


class Volume:

    def __init__(self, name, type, total_blocks, used_blocks, available_blocks, mount_point, block_size=512):
        self.name = name
        self._data = dict(
            name=name,
            type=type,
            total_blocks=total_blocks,
            used_blocks=used_blocks,
            available_blocks=available_blocks,
            mount_point=mount_point
        )
        self.block_size = block_size

    def _to_bytes(self, key):
        try:
            return int(self._data.get(key)) * self.block_size
        except (ValueError, TypeError):
            return None

    @property
    def total_size(self):
        return self._to_bytes("total_blocks")

    @property
    def used_space(self):
        return self._to_bytes("used_blocks")

    @property
    def available_space(self):
        return self._to_bytes("available_blocks")

    @property
    def type(self):
        return self._data.get("type")

    @property
    def mount_point(self):
        return self._data.get("mount_point")

    def to_dict(self):
        fields = ["name", "type", "total_size", "used_space", "available_space", "mount_point"]
        return {f: getattr(self, f, None) for f in fields}


class Disk:

    def __init__(self, name, total_size):
        self.name = name
        try:
            self.total_size = int(total_size)
        except (TypeError, ValueError):
            self.total_size = None
        self.volumes = self._search_volumes(self.name)
        self.info_parser = CommandParser.execute(f"hdparm -I {self.name}")

    def _search_volumes(self, name):
        regex = r'^(?P<name>(?:\/[._\-A-Za-z0-9]+)+)\s+(?P<type>[^ ]+)\s+(?P<total_blocks>[^ ]+)\s+(?P<used_blocks>[^ ]+)\s+(?P<available_blocks>[^ ]+)\s+(?P<mount_point>.+?)$'
        df_command = f"df -x tmpfs -x devtmpfs -x squashfs -x overlay -x debugfs -B 512 --output=source,fstype,size,used,avail,target {self.name}*"

        parser = CommandParser.execute(df_command)

        volumes = []
        for volume in parser.list(regex, "name", "type", "total_blocks", "used_blocks", "available_blocks", "mount_point").all():
            volumes.append(Volume(**volume))
        return volumes

    def search(self, regex, group):
        return self.info_parser.get(regex, key=group)

    @property
    def model(self):
        return self.search(r'Model Number:\s+(?P<model>.*)\n', "model")

    @property
    def serial_number(self):
        return self.search(r'Serial Number:\s+(?P<serial>.*)\n', "serial")

    @property
    def form_factor(self):
        return self.search(r'Form Factor:\s+(?P<form_factor>.*)\n', "form_factor")

    @property
    def rotation_rate(self):
        try:
            return int(self.search(r'Nominal Media Rotation Rate:\s+(?P<rotation_rate>.*)\n', "rotation_rate"))
        except (TypeError, ValueError):
            return None

    def to_dict(self):
        fields = ["name", "model", "serial_number", "form_factor", "rotation_rate", "total_size"]
        output = {
            attr: getattr(self, attr, None) for attr in fields
        }
        return { **output, "volumes": [p.to_dict() for p in self.volumes] }


class Network:

    def __init__(self):
        self.gateways = {i[1]: i[0] for i in netifaces.gateways().get(netifaces.AF_INET)}
        default_gateway = netifaces.gateways().get("default").get(netifaces.AF_INET)
        self.default_interface = default_gateway[1] if default_gateway else None
        self.default_gateway = default_gateway[0] if default_gateway else None
        self.interfaces = [Interface(i) for i in netifaces.interfaces()]

    def to_dict(self):
        return {
            "interfaces": [i.to_dict(
                default=i.name == self.default_interface,
                gateway=self.gateways.get(i.name)
            ) for i in self.interfaces],
            "default_gateway": self.default_gateway
        }


class Interface:

    def __init__(self, name):
        self.name = name
        self.obj = netifaces.ifaddresses(name)

    @property
    def ipv4_addresses(self):
        return list(map(
            lambda addr: dict_getter(
                addr, 
                'broadcast',
                'netmask',
                addr='address'
            ),
            self.obj.get(netifaces.AF_INET, [])
        ))

    @property
    def mac_address(self):
        macs = self.obj.get(netifaces.AF_LINK, [])
        if macs:
            return macs[0].get('addr')
        return None

    def to_dict(self, **extra):
        return {
            "name": self.name,
            "ipv4_addresses": self.ipv4_addresses,
            "mac_address": self.mac_address,
            **extra
        }


@register_module()
class SystemSync(Module):

    name = "sync"
    event_keys = ["sync"]

    def __init__(self, core, queue):
        super().__init__(core, queue)
        self._thread = Thread(target=self._run)

    def startup(self):
        super().startup()
        self._thread.start()

    def shutdown(self):
        super().shutdown()
        self._thread.join()

    def event(self, ev):
        pass

    def _system_info(self):
        if self.core and self.core.info:
            return self.core.info.to_dict()
        return None

    def _network(self):
        return Network().to_dict()

    def _storage(self):
        return Storage().to_dict()

    def _run(self):
        logger.debug("Starting system info sync")
        self.queue.put({
            "type": "sync",
            "data": {
                "system": self._system_info(),
                "network": self._network(),
                "storage": self._storage(),
            }
        })
        logger.debug("Finished with system info sync")


if __name__ == "__main__":
    pass
