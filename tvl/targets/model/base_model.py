# Copyright 2023 TropicSquare
# SPDX-License-Identifier: Apache-2.0

import functools
import logging
from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Type,
    TypeVar,
    Union,
    overload,
)

from typing_extensions import Self

from ...constants import CHUNK_SIZE, ENCRYPTION_TAG_LEN, S_HI_PUB_NB_SLOTS, L2StatusEnum
from ...crypto.encrypted_session import TropicEncryptedSession
from ...logging_utils import Labeller
from ...messages.exceptions import NoValidSubclassError, SubclassNotFoundError
from ...messages.l2_messages import L2Request, L2Response
from ...messages.l3_messages import L3Command, L3Result
from ...random_number_generator import RandomNumberGenerator
from ...utils import chunked
from .configuration_object_impl import ConfigurationObjectImpl
from .exceptions import L2ProcessingError, L3ProcessingErrorUnauthorized
from .internal.command_buffer import CommandBuffer
from .internal.ecc_keys import EccKeys
from .internal.mac_and_destroy import MacAndDestroyData
from .internal.mcounter import MCounters
from .internal.pairing_keys import PairingKeys
from .internal.spi_fsm import SpiFsm
from .internal.user_data_partition import UserDataPartition
from .meta_model import MetaModel, base


def split_data(data: bytes, *, chunk_size: int = CHUNK_SIZE) -> Iterator[bytes]:
    yield from (bytes(chunk) for chunk in chunked(data, chunk_size))


class SupportsFromDict(Protocol):
    @classmethod
    def from_dict(cls, __mapping: Mapping[Any, Any], /) -> Self:
        ...


T = TypeVar("T")

D = TypeVar("D", bound=SupportsFromDict)


class BaseModel(metaclass=MetaModel):
    """
    Functional model of the TROPIC01 chip for functional verification
    """

    def __init__(
        self,
        *,
        r_config: Optional[ConfigurationObjectImpl] = None,
        r_ecc_keys: Optional[EccKeys] = None,
        r_user_data: Optional[UserDataPartition] = None,
        r_mcounters: Optional[MCounters] = None,
        r_macandd_data: Optional[MacAndDestroyData] = None,
        i_config: Optional[ConfigurationObjectImpl] = None,
        i_pairing_keys: Optional[PairingKeys] = None,
        s_t_priv: Optional[bytes] = None,
        s_t_pub: Optional[bytes] = None,
        x509_certificate: bytes = b"x509_certificate",
        chip_id: bytes = b"chip_id",
        riscv_fw_version: bytes = b"riscv_fw_version",
        spect_fw_version: bytes = b"spect_fw_version",
        serial_code: bytes = b"\x00\x01\x02\x03",
        activate_encryption: bool = True,
        debug_random_value: Optional[bytes] = None,
        init_byte: bytes = b"\x00",
        busy_iter: Optional[Sequence[bool]] = None,
        split_data_fn: Callable[[bytes], Iterator[bytes]] = split_data,
        logger: Optional[logging.Logger] = None,
    ):
        """Initialize the model.

        Args:
            r_config (ConfigurationObjectImpl, optional): reversible
                configuration object. Defaults to None.
            r_ecc_keys (Ecc, optional): ecc key partition. Defaults to None.
            r_user_data (UserDataPartition, optional): user-data partition.
                Defaults to None.
            r_mcounters (MCounters, optional): monotonic counters partition.
                Defaults to None.
            r_macandd_data (MacAndDestroyData, optional): Mac-and-Destroy
                data slots. Defaults to None.
            i_config (ConfigurationObjectImpl, optional): irreversible
                configuration object. Defaults to None.
            i_pairing_keys (PairingKeys, optional): pairing key partition.
                Defaults to None.
            s_t_priv (bytes, optional): TROPIC01 static private key.
                Defaults to None.
            s_t_pub (bytes, optional): TROPIC01 static public key.
                Defaults to None.
            x509_certificate (bytes, optional): TropicSquare x509 certificate.
                Defaults to b"x509_certificate".
            chip_id (bytes, optional): ID of the chip. Defaults to b"chip_id".
            riscv_fw_version (bytes, optional): version of the FW.
                Defaults to b"riscv_fw_version".
            spect_fw_version (bytes, optional): version of the SPECT.
                Defaults to b"spect_fw_version".
            serial_code (bytes, optional): chip's serial code.
                Defaults to b"serial_code".
            activate_encryption (bool, optional): enable encrypted L3 layer.
                Defaults to True.
            debug_random_value (bytes, optional): TRNG2 initial random value.
                Defaults to None.
            init_byte (bytes): byte sent behind the chip status byte upon
                reception of a request. Defaults to b"\x00".
            busy_iter (Sequence[bool], optional): sequence managing the
                frequency model returns the BUSY status code.
                Defaults to None.
        """

        def __factory(value: Optional[T], default: Callable[[], T]) -> T:
            if value is not None:
                return value
            return default()

        # --- R-Memory Partitions ---

        self.r_config = __factory(r_config, ConfigurationObjectImpl)
        """Reversible chip configuration"""
        self.r_ecc_keys = __factory(r_ecc_keys, EccKeys)
        """Keys for Elliptic Curve Cryptography (ECDSA/EdDSA) algorithms"""
        self.r_user_data = __factory(r_user_data, UserDataPartition)
        """General purpose storage for user data"""
        self.r_mcounters = __factory(r_mcounters, MCounters)
        """Data for Monotonic Counters"""
        self.r_macandd_data = __factory(r_macandd_data, MacAndDestroyData)
        """Mac and Destroy infrastructure"""

        # --- I-Memory Partitions ---

        self.i_config = __factory(i_config, ConfigurationObjectImpl)
        """Irreversible chip configuration."""
        self.i_pairing_keys = __factory(i_pairing_keys, PairingKeys)
        """The Host's X25519 public key used by TROPIC01 during a handshake"""
        self.s_t_priv = s_t_priv
        """The TROPIC01 X25519 private key"""
        self.s_t_pub = s_t_pub
        """The TROPIC01 X25519 public key"""

        self.x509_certificate = x509_certificate
        """The X.509 certificate signed by Tropic Square"""
        self.chip_id = chip_id
        self.riscv_fw_version = riscv_fw_version
        self.spect_fw_version = spect_fw_version
        self.serial_code = serial_code

        # --- Others ---
        self.activate_encryption = activate_encryption
        """Encrypt L3-layer messages"""

        if debug_random_value is not None and len(debug_random_value) != 4:
            raise ValueError("debug_random_value has to be 4 byte long.")

        self.trng2 = RandomNumberGenerator(debug_random_value)
        """Random number generator"""

        # Actual configuration object update
        self._config: Optional[ConfigurationObjectImpl] = None
        # Create an empty encrypted session state.
        self.session = TropicEncryptedSession(random_source=self.trng2)
        # pairing key currently used by the session
        self.pairing_key_slot: int = -1

        # command buffer
        self.command_buffer = CommandBuffer()

        # L1 layer finite-state machine
        self.spi_fsm = SpiFsm(init_byte, busy_iter, self.process_input)

        self.split_data_fn = split_data_fn

        # logging settings
        if logger is None:
            logger = logging.getLogger(self.__class__.__name__.lower())
        self.set_logger(logger)

    def set_logger(self, logger: logging.Logger) -> Self:
        self.logger = Labeller(logger, "base")
        self.uap_logger = Labeller(logger, "uap")
        self.spi_fsm.set_logger(Labeller(logger, "spi"))
        return self

    def __enter__(self) -> Self:
        """Instance can be used as a context manager"""
        return self

    def __exit__(self, *args: Any) -> None:
        """Instance can be used as a context manager"""
        pass

    def to_dict(self) -> Dict[str, Any]:
        """Dump the configuration of the model to a dict.

        Returns:
            the configuration dumped as a dict
        """
        return dict(
            r_config=self.r_config.to_dict(),
            r_ecc_keys=self.r_ecc_keys.to_dict(),
            r_user_data=self.r_user_data.to_dict(),
            r_mcounters=self.r_mcounters.to_dict(),
            r_macandd_data=self.r_macandd_data.to_dict(),
            i_config=self.i_config.to_dict(),
            i_pairing_keys=self.i_pairing_keys.to_dict(),
            s_t_priv=self.s_t_priv,
            s_t_pub=self.s_t_pub,
            x509_certificate=self.x509_certificate,
            chip_id=self.chip_id,
            riscv_fw_version=self.riscv_fw_version,
            spect_fw_version=self.spect_fw_version,
            serial_code=self.serial_code,
            activate_encryption=self.activate_encryption,
            debug_random_value=self.trng2.debug_random_value,
            init_byte=self.spi_fsm.init_byte,
            busy_iter=self.spi_fsm.busy_iter,
        )

    @classmethod
    def from_dict(cls, __mapping: Mapping[str, Any], /) -> Self:
        """Create a new model from a configuration dict.

        Args:
            __mapping (Mapping[str, Any]): the configuration of the model

        Returns:
            a new model
        """

        def __d(n: str, t: Type[D]) -> Dict[str, Optional[D]]:
            if (cfg := __mapping.get(n)) is None:
                return {}
            return {n: t.from_dict(cfg)}

        def __s(n: str) -> Dict[str, Any]:
            if (v := __mapping.get(n)) is None:
                return {}
            return {n: v}

        return cls(
            **__d("r_config", ConfigurationObjectImpl),
            **__d("r_ecc_keys", EccKeys),
            **__d("r_user_data", UserDataPartition),
            **__d("r_mcounters", MCounters),
            **__d("r_macandd_data", MacAndDestroyData),
            **__d("i_config", ConfigurationObjectImpl),
            **__d("i_pairing_keys", PairingKeys),
            **__s("s_t_priv"),
            **__s("s_t_pub"),
            **__s("x509_certificate"),
            **__s("chip_id"),
            **__s("riscv_fw_version"),
            **__s("spect_fw_version"),
            **__s("serial_code"),
            **__s("activate_encryption"),
            **__s("debug_random_value"),
            **__s("init_byte"),
            **__s("busy_iter"),
        )

    def wait(self, usecs: int) -> None:
        """Wait for the model

        Args:
            usecs (int): waiting time in microseconds
        """
        pass

    def spi_drive_csn_low(self) -> None:
        """Drive the Chip Select signal to LOW"""
        self.spi_fsm.spi_drive_csn_low()

    def spi_drive_csn_high(self) -> None:
        """Drive the Chip Select signal to HIGH"""
        self.spi_fsm.spi_drive_csn_high()

    @overload
    def spi_send(self, data: List[int]) -> List[int]:
        ...

    @overload
    def spi_send(self, data: bytes) -> bytes:
        ...

    def spi_send(self, data: Union[List[int], bytes]) -> Union[List[int], bytes]:
        """Send data through the SPI bus in half-duplex mode.

        Args:
            data (Union[List[int], bytes]): data to send

        Returns:
            the response of the TROPIC01.
        """
        return self._spi_send(data)

    @functools.singledispatchmethod
    def _spi_send(self, data: Any) -> Any:
        raise TypeError(f"{type(data)} not supported")

    @_spi_send.register(list)
    def _(self, data: List[int]) -> List[int]:
        return list(self._spi_send(bytes(data)))

    @_spi_send.register
    def _(self, data: bytes) -> bytes:
        return self.spi_fsm.process_spi_data(data)

    def process_input(self, data: bytes) -> Union[bytes, List[bytes]]:
        """Process the received L2 request - should be overridden by the API.

        Args:
            request (Request): received request

        Raises:
            NotImplementedError: API should be implemented

        Returns:
            the response computed from the request
        """
        responses = self._process_input(data)

        if not isinstance(responses, list):
            self.logger.info(f"Returning L2 response: {responses}")
            return responses.to_bytes()

        self.logger.info(
            f"Returning L2 responses: {[str(response) for response in responses]}"
        )
        return [response.to_bytes() for response in responses]

    def _process_input(self, data: bytes) -> Union[L2Response, List[L2Response]]:
        self.logger.debug(f"Parsing raw L2 request {data}.")
        request = L2Request.with_length(len(data)).from_bytes(data)

        self.logger.info(f"Checking checksum of {request}")
        if not request.has_valid_crc():
            self.logger.debug("Checksum is incorrect.")
            return L2Response(status=L2StatusEnum.CRC_ERR)
        self.logger.debug("Checksum is correct.")

        self.logger.debug("Parsing L2 request.")
        try:
            request = L2Request.instantiate_subclass(request.id.value, data)
        except SubclassNotFoundError as exc:
            self.logger.debug(exc)
            return L2Response(status=L2StatusEnum.UNKNOWN_REQ)
        except NoValidSubclassError as exc:
            self.logger.debug(exc)
            return L2Response(status=L2StatusEnum.CRC_ERR)

        self.logger.info(f"Processing L2 request {request}")
        try:
            return self.process_l2_request(request)
        except L2ProcessingError as exc:
            return L2Response(status=exc.status)

    @base("l2_api")
    def process_l2_request(
        self, request: L2Request
    ) -> Union[L2Response, List[L2Response]]:
        """Process the L2 request.

        Args:
            request (L2Request): the received L2 request

        Raises:
            NotImplementedError: unknown request

        Returns:
            the response(s) after processing
        """
        raise NotImplementedError(f"{type(request)} not supported")

    @base("l3_api")
    def process_l3_command(self, command: L3Command) -> L3Result:
        """Process the L3 command.

        Args:
            command (L3Command): the received L3 command

        Raises:
            NotImplementedError: unknown command

        Returns:
            the result after processing
        """
        raise NotImplementedError(f"{type(command)} not supported")

    def power_on(self) -> None:
        self.logger.info("Switching the model on.")

    def power_off(self) -> None:
        self.logger.info("Switching the model off.")
        self._process_power_off()

    def _process_power_off(self) -> None:
        self.invalidate_session()
        self.command_buffer.reset()
        self.spi_fsm.reset()
        self._config = None

    @property
    def config(self) -> ConfigurationObjectImpl:
        """Compute the configuration from the irreversible and reversible
          configuration objects.

        Returns:
            the logical AND between the irreversible and reversible
                configuration objects
        """
        if self._config is None:
            self.logger.debug(
                "Updating configuration for the first time after power on."
            )
            self._config = self.i_config & self.r_config
        return self._config

    def check_access_privileges(self, name: str, value: int) -> None:
        """Check the current pairing key access privileges

        Args:
            name (str): name of the configuration field
            value (int): value of the configuration field

        Raises:
            FailError: TROPIC01 is not paired yet
            UnauthorizedError: the current pairing key does not have sufficient
                privileges to access the feature guarded by the register.
        """
        name = name.upper()
        self.uap_logger.info(f"Checking access privileges for {name}.")
        if not self.activate_encryption:
            self.uap_logger.debug("Encryption deactivated, bypassing check.")
            return
        self.uap_logger.debug(f"Pairing key slot #{self.pairing_key_slot}")
        self.uap_logger.debug(f"Configuration field: {value:#b}")
        if not 0 <= self.pairing_key_slot < S_HI_PUB_NB_SLOTS:
            raise RuntimeError("Chip not paired yet.")
        if not value & 2**self.pairing_key_slot:
            raise L3ProcessingErrorUnauthorized(
                f"Pairing key slot #{self.pairing_key_slot} "
                f"does not have access to {name}."
            )
        self.uap_logger.debug(
            f"Pairing key slot #{self.pairing_key_slot} has access to {name}."
        )

    def invalidate_session(self) -> None:
        """Invalidate the secure channel session"""
        self.logger.debug("Invalidating secure channel session.")
        self.session.reset()
        self.pairing_key_slot = -1
        self.logger.debug("Done.")

    def encrypt_result(self, result: bytes) -> bytes:
        """Encrypt the raw result to be sent.

        Args:
            result (bytes): raw result to encrypt

        Returns:
            the encrypted raw result
        """
        if self.activate_encryption:
            return self.session.encrypt_response(result)
        return result + b"\x00" * ENCRYPTION_TAG_LEN

    def decrypt_command(self, command: bytes) -> Optional[bytes]:
        """Decrypt the received raw command.

        Args:
            command (bytes): raw command to decrypt

        Returns:
            the decrypted raw command
        """
        if self.activate_encryption:
            return self.session.decrypt_command(command)
        return command[:-ENCRYPTION_TAG_LEN]
