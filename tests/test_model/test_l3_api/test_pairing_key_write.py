# Copyright 2023 TropicSquare
# SPDX-License-Identifier: Apache-2.0

import os
from typing import Any, Dict

import pytest

from tvl.api.l3_api import TsL3PairingKeyWriteCommand
from tvl.constants import L3ResultFieldEnum
from tvl.host.host import Host
from tvl.targets.model.internal.pairing_keys import BLANK_VALUE, INVALID_VALUE, KEY_SIZE
from tvl.targets.model.tropic01_model import Tropic01Model

from ..utils import sample_from, sample_outside

KEY_SLOTS = sample_from((lst := TsL3PairingKeyWriteCommand.SlotEnum), k=4)
SECURE_CHANNEL_KEY_IDX, SET_KEY_IDX, BLANK_KEY_IDX, INVALID_KEY_IDX = KEY_SLOTS

SET_KEY = os.urandom(KEY_SIZE)


def _i(__bytes: bytes, /) -> int:
    return int.from_bytes(__bytes, byteorder="big")


def _b(__int: int, /) -> bytes:
    return __int.to_bytes(KEY_SIZE, byteorder="big")


@pytest.fixture()
def configuration(configuration: Dict[str, Any]):
    # set the secure channel key to another index
    configuration["host"]["pairing_key_index"] = SECURE_CHANNEL_KEY_IDX
    configuration["model"]["i_pairing_keys"] = {
        SECURE_CHANNEL_KEY_IDX: {"value": configuration["host"]["s_h_pub"]},
        SET_KEY_IDX: {"value": SET_KEY},
        BLANK_KEY_IDX: {"value": BLANK_VALUE},
        INVALID_KEY_IDX: {"value": INVALID_VALUE},
    }
    yield configuration


@pytest.mark.parametrize(
    "slot, value, expected_new_value, result_field",
    [
        pytest.param(
            BLANK_KEY_IDX,
            (v_ := os.urandom(KEY_SIZE)),
            v_,
            L3ResultFieldEnum.OK,
            id="blank_slot",
        ),
        pytest.param(
            SET_KEY_IDX,
            (v_ := os.urandom(KEY_SIZE)),
            _b(_i(SET_KEY) & _i(v_)),
            L3ResultFieldEnum.OK,
            id="already_set_slot",
        ),
        pytest.param(
            INVALID_KEY_IDX,
            (v_ := os.urandom(KEY_SIZE)),
            INVALID_VALUE,
            L3ResultFieldEnum.FAIL,
            id="invalid_slot",
        ),
    ],
)
def test_write_key(
    host: Host,
    model: Tropic01Model,
    slot: int,
    value: bytes,
    expected_new_value: bytes,
    result_field: int,
):
    command = TsL3PairingKeyWriteCommand(
        slot=slot,
        s_hipub=value,
    )
    result = host.send_command(command)

    assert result.result.value == result_field
    assert model.i_pairing_keys[slot].read() == expected_new_value


@pytest.mark.parametrize(
    "slot", sample_outside(TsL3PairingKeyWriteCommand.SlotEnum, 1, k=10)
)
def test_write_out_of_range_key_slot(host: Host, slot: int):
    command = TsL3PairingKeyWriteCommand(
        slot=slot,
        s_hipub=os.urandom(KEY_SIZE),
    )
    result = host.send_command(command)

    assert result.result.value == L3ResultFieldEnum.UNAUTHORIZED
