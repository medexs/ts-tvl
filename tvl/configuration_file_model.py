from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml
from pydantic import BaseModel, Extra, StrictBool, StrictBytes
from typing_extensions import TypedDict

from .constants import (
    CERTIFICATE_SIZE,
    CHIP_ID_SIZE,
    DH_LEN,
    RISCV_FW_VERSION_SIZE,
    S_HI_PUB_NB_SLOTS,
    SPECT_FW_VERSION_SIZE,
)
from .targets.model.configuration_object_impl import ConfigurationObjectImplModel
from .targets.model.internal.ecc_keys import EccModel
from .targets.model.internal.mcounter import MCountersModel
from .targets.model.internal.mac_and_destroy import MacAndDestroyDataModel
from .targets.model.internal.pairing_keys import PairingKeysModel
from .targets.model.internal.user_data_partition import UserDataPartitionModel
from .typing_utils import FixedSizeBytes, RangedInt, SizedBytes, SizedList


class _BaseModel(BaseModel):
    class Config:
        extra = Extra.forbid
        frozen = True


class HostConfigurationModel(_BaseModel):
    s_h_priv: SizedList[FixedSizeBytes[DH_LEN], 0, S_HI_PUB_NB_SLOTS]
    s_h_pub: SizedList[FixedSizeBytes[DH_LEN], 0, S_HI_PUB_NB_SLOTS]
    s_t_pub: FixedSizeBytes[DH_LEN]
    pairing_key_index: RangedInt[0, S_HI_PUB_NB_SLOTS - 1]
    activate_encryption: Optional[StrictBool]
    debug_random_value: Optional[StrictBytes]


class ModelConfigurationModel(_BaseModel):
    s_t_priv: FixedSizeBytes[DH_LEN]
    s_t_pub: FixedSizeBytes[DH_LEN]
    # --- R-Memory Partitions ---
    r_config: Optional[ConfigurationObjectImplModel]
    r_ecc_keys: Optional[EccModel]
    r_user_data: Optional[UserDataPartitionModel]
    r_mcounters: Optional[MCountersModel]
    r_macandd_data: Optional[MacAndDestroyDataModel]
    # --- I-Memory Partitions ---
    i_config: Optional[ConfigurationObjectImplModel]
    i_pairing_keys: Optional[PairingKeysModel]
    # --- Others
    x509_certificate: Optional[SizedBytes[1, CERTIFICATE_SIZE]]
    chip_id: Optional[SizedBytes[1, CHIP_ID_SIZE]]
    riscv_fw_version: Optional[FixedSizeBytes[RISCV_FW_VERSION_SIZE]]
    spect_fw_version: Optional[FixedSizeBytes[SPECT_FW_VERSION_SIZE]]
    debug_random_value: Optional[StrictBytes]
    activate_encryption: Optional[StrictBool]
    init_byte: Optional[FixedSizeBytes[1]]
    busy_iter: Optional[List[StrictBool]]


class ConfigurationFileModel(_BaseModel):
    host: Optional[HostConfigurationModel]
    model: Optional[ModelConfigurationModel]


class ConfigurationDict(TypedDict):
    host: Dict[str, Any]
    model: Dict[str, Any]


def load_configuration_file(filename: Union[Path, str]) -> ConfigurationDict:
    with open(filename, "r") as fd:
        content = yaml.safe_load(fd)
    return {  # type: ignore
        **{"host": {}, "model": {}},
        **ConfigurationFileModel.parse_obj(content).dict(exclude_none=True),
    }
