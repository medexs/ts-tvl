# Structure of the TASSIC Verification Library

Three main components are defined in the TVL:
- targets: interfaces to the TROPIC01 implementations
- `Host`: abstraction of the Host MCU, providing utilities to communicate with a target
- messages: classes for modelling the data exchanged with the targets.

## Targets
The TVL provides a set of classes to communicate with the different implementations
of TROPIC01, referred to as targets, namely:

- `Tropic01Model`: the reference model, written in Python

More on TROPIC01 targets [here](./targets/README.md).

## Host
The `Host` class intends to provide a user-friendly way to communicate with a
target. It abstracts the low-level communication details, thus allowing the user
to focus on the content of the messages sent to the target.

More on TROPIC01 host [here](./host/README.md).

## Messages
The messages exchanged between the host and the target are implemented as Python
classes. These classes are defined based on the API (see above).
They abstract the way the messages are created an perform several low-level
operations.

More on messages [here](./messages/README.md).

## How to use

1. instantiate and configure a TROPIC01 target
2. instantiate the `Host` and link to the target
3. create a request or a command
4. send the request or command to the target via the `Host` instance
5. repeat steps 3. and 4.

## A basic example: issue a GetInfo request

This example can also be found in
[`examples/example_01_get_info_request.py`](../examples/example_01_get_info_request.py)

```python
from tvl.api.l2_api import TsL2GetInfoRequest
from tvl.host.host import Host
from tvl.logging import setup_logging
from tvl.targets.model.tropic01_model import Tropic01Model

# Configure logging
setup_logging()

# Instantiate the target (in this case, `Tropic01Model`)
model = Tropic01Model()

# Instantiate the `Host`
host = Host(target=model)

# Create a message (in this case `TsL2GetInfoRequest`)
request = TsL2GetInfoRequest(object_id=1, block_index=0)
print(request)
# > TsL2GetInfoRequest<(id=AUTO, length=AUTO, object_id=01, block_index=00, crc=AUTO)

# Send the request and then receive the response
response = host.send_request(request)

print(response)
# > TsL2GetInfoReqResponse<(status=01, length=07, object=[63, 68, 69, 70, 5f, 69, 64], crc=f253)
```

More examples in the [`examples`](../examples/) directory.
