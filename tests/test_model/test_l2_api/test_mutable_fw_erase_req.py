# Copyright 2023 TropicSquare
# SPDX-License-Identifier: Apache-2.0

import os

from tvl.api.l2_api import TsL2MutableFwEraseReqRequest, TsL2MutableFwEraseReqResponse
from tvl.constants import L2StatusEnum
from tvl.host.host import Host


def test_mutable_fw_erase_req(host: Host):
    response = host.send_request(TsL2MutableFwEraseReqRequest(bank_id=os.urandom(1)))
    assert isinstance(response, TsL2MutableFwEraseReqResponse)
    assert response.status.value == L2StatusEnum.REQ_OK
