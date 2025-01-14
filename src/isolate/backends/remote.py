from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, ClassVar, Dict, Optional

import grpc

from isolate.backends import (
    BaseEnvironment,
    BasicCallable,
    CallResultType,
    EnvironmentConnection,
)
from isolate.backends.common import sha256_digest_of
from isolate.backends.settings import DEFAULT_SETTINGS, IsolateSettings
from isolate.server import interface
from isolate.server.definitions import (
    BoundFunction,
    EnvironmentDefinition,
    IsolateStub,
)


@dataclass
class IsolateServer(BaseEnvironment[EnvironmentDefinition]):
    BACKEND_NAME: ClassVar[str] = "isolate-server"

    host: str
    target_environment_kind: str
    target_environment_config: Dict[str, Any]

    @classmethod
    def from_config(
        cls,
        config: Dict[str, Any],
        settings: IsolateSettings = DEFAULT_SETTINGS,
    ) -> BaseEnvironment:
        environment = cls(**config)
        environment.apply_settings(settings)

        return environment

    @property
    def key(self) -> str:
        return sha256_digest_of(
            self.host,
            self.target_environment_kind,
            json.dumps(self.target_environment_config),
        )

    def create(self) -> EnvironmentDefinition:
        return EnvironmentDefinition(
            kind=self.target_environment_kind,
            configuration=interface.to_struct(self.target_environment_config),
        )

    def open_connection(
        self, connection_key: EnvironmentDefinition
    ) -> IsolateServerConnection:
        return IsolateServerConnection(self, self.host, connection_key)


@dataclass
class IsolateServerConnection(EnvironmentConnection):
    host: str
    definition: EnvironmentDefinition
    _channel: Optional[grpc.Channel] = None

    def _acquire_channel(self) -> None:
        self._channel = grpc.insecure_channel(self.host)

    def _release_channel(self) -> None:
        if self._channel:
            self._channel.close()
            self._channel = None

    def __exit__(self, *args: Any) -> None:
        self._release_channel()

    def run(
        self,
        executable: BasicCallable,
        *args: Any,
        **kwargs: Any,
    ) -> CallResultType:
        if self._channel is None:
            self._acquire_channel()

        stub = IsolateStub(self._channel)
        request = BoundFunction(
            function=interface.to_serialized_object(
                executable,
                method=self.environment.settings.serialization_method,
                was_it_raised=False,
            ),
            environment=self.definition,
        )

        return_value = []
        for result in stub.Run(request):
            for raw_log in result.logs:
                log = interface.from_grpc(raw_log)
                self.log(log.message, level=log.level, source=log.source)

            if result.is_complete:
                return_value.append(interface.from_grpc(result.result))

        if len(return_value) == 0:
            raise RuntimeError(
                "No result object was received from the server"
                " (it never set is_complete to True)."
            )
        elif len(return_value) > 1:
            raise RuntimeError(
                "Multiple result objects were received from the server"
                " (it set is_complete to True multiple times)."
            )
        else:
            return return_value[0]
