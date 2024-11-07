# Copyright 2023 TropicSquare
# SPDX-License-Identifier: Apache-2.0

import os
from typing import Any, Dict

import pytest

from tvl.api.l2_api import TsL2GetInfoRequest, TsL2GetInfoResponse
from tvl.constants import L2StatusEnum
from tvl.host.host import Host
from tvl.messages.l2_messages import L2Response

from ..utils import one_of, one_outside

_X509_CERTIFICATE = os.urandom(512)
_CHIP_ID = os.urandom(128)
_RISCV_FW_VERSION = os.urandom(4)
_SPECT_FW_VERSION = os.urandom(4)


@pytest.fixture()
def model_configuration(model_configuration: Dict[str, Any]):
    model_configuration.update(
        {
            "x509_certificate": _X509_CERTIFICATE,
            "chip_id": _CHIP_ID,
            "riscv_fw_version": _RISCV_FW_VERSION,
            "spect_fw_version": _SPECT_FW_VERSION,
        }
    )
    yield model_configuration


def _send_no_check(host: Host, object_id: int, block_index: int) -> L2Response:
    request = TsL2GetInfoRequest(object_id=object_id, block_index=block_index)
    return host.send_request(request)


def _send(host: Host, object_id: int, block_index: int) -> TsL2GetInfoResponse:
    response = _send_no_check(host, object_id, block_index)
    assert response.status.value == L2StatusEnum.REQ_OK
    assert isinstance(response, TsL2GetInfoResponse)
    return response


@pytest.mark.parametrize(
    "block_index, indices",
    [
        pytest.param(
            (b := TsL2GetInfoRequest.BlockIndexEnum.DATA_CHUNK_0_127),
            slice(0, 128),
            id=str(b),
        ),
        pytest.param(
            (b := TsL2GetInfoRequest.BlockIndexEnum.DATA_CHUNK_128_255),
            slice(128, 256),
            id=str(b),
        ),
        pytest.param(
            (b := TsL2GetInfoRequest.BlockIndexEnum.DATA_CHUNK_256_383),
            slice(256, 384),
            id=str(b),
        ),
        pytest.param(
            (b := TsL2GetInfoRequest.BlockIndexEnum.DATA_CHUNK_384_511),
            slice(384, 512),
            id=str(b),
        ),
    ],
)
def test_x509_certificate(host: Host, block_index: int, indices: slice):
    response = _send(
        host,
        TsL2GetInfoRequest.ObjectIdEnum.X509_CERTIFICATE,
        block_index,
    )
    assert response.object.to_bytes() == _X509_CERTIFICATE[indices]


@pytest.mark.parametrize("block_index", TsL2GetInfoRequest.BlockIndexEnum)
def test_chip_id(host: Host, block_index: int):
    response = _send(
        host,
        TsL2GetInfoRequest.ObjectIdEnum.CHIP_ID,
        block_index,
    )
    assert response.object.to_bytes() == _CHIP_ID


@pytest.mark.parametrize("block_index", TsL2GetInfoRequest.BlockIndexEnum)
def test_chip_riscv_fw_version(host: Host, block_index: int):
    response = _send(
        host,
        TsL2GetInfoRequest.ObjectIdEnum.RISCV_FW_VERSION,
        block_index,
    )
    assert response.object.to_bytes() == _RISCV_FW_VERSION


@pytest.mark.parametrize("block_index", TsL2GetInfoRequest.BlockIndexEnum)
def test_chip_spect_rom_id(host: Host, block_index: int):
    response = _send(
        host,
        TsL2GetInfoRequest.ObjectIdEnum.SPECT_FW_VERSION,
        block_index,
    )
    assert response.object.to_bytes() == _SPECT_FW_VERSION


def test_invalid_object_id(host: Host):
    response = _send_no_check(
        host=host,
        object_id=one_outside(TsL2GetInfoRequest.ObjectIdEnum),
        block_index=one_of(TsL2GetInfoRequest.BlockIndexEnum),
    )
    assert response.status.value == L2StatusEnum.GEN_ERR
    assert response.data_field_bytes == b""


@pytest.mark.parametrize(
    "object_id, expected_status",
    [
        pytest.param(
            (oid := TsL2GetInfoRequest.ObjectIdEnum.X509_CERTIFICATE),
            L2StatusEnum.GEN_ERR,
            id=str(oid),
        ),
        pytest.param(
            (oid := TsL2GetInfoRequest.ObjectIdEnum.CHIP_ID),
            L2StatusEnum.REQ_OK,
            id=str(oid),
        ),
        pytest.param(
            (oid := TsL2GetInfoRequest.ObjectIdEnum.RISCV_FW_VERSION),
            L2StatusEnum.REQ_OK,
            id=str(oid),
        ),
        pytest.param(
            (oid := TsL2GetInfoRequest.ObjectIdEnum.SPECT_FW_VERSION),
            L2StatusEnum.REQ_OK,
            id=str(oid),
        ),
    ],
)
def test_invalid_block_index(host: Host, object_id: int, expected_status: int):
    response = _send_no_check(
        host=host,
        object_id=object_id,
        block_index=one_outside(TsL2GetInfoRequest.BlockIndexEnum),
    )
    assert response.status.value == expected_status
