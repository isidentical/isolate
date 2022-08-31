# A Python native two-way bridge implementation between the controller
# process and the agent process(es).
#
#    controller       both       children
# /--------------\ /--------\ /------------\
# object -> dill -> socket -> dill -> object

from __future__ import annotations

import base64
from contextlib import closing
from functools import partial
from multiprocessing.connection import Client, ConnectionWrapper, Listener
from typing import Union

import dill

dill_wrapper = partial(ConnectionWrapper, dumps=dill.dumps, loads=dill.loads)


class _DillListener(Listener):
    def accept(self) -> ConnectionWrapper:
        return closing(dill_wrapper(super().accept()))


def controller_connection() -> _DillListener:
    # The controller here assumes that there will be at most one
    # client. This restriction might change in the future as an
    # optimization.
    return _DillListener()


def child_connection(address: str) -> ConnectionWrapper:
    return closing(dill_wrapper(Client(address)))


def encode_service_address(address: Union[bytes, str]) -> str:
    if isinstance(address, bytes):
        address = address.decode()

    return base64.b64encode(address.encode()).decode("utf-8")


def decode_service_address(address: str) -> str:
    return base64.b64decode(address).decode("utf-8")
