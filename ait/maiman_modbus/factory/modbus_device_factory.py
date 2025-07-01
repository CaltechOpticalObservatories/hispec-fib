# factory/modbus_device_factory.py

from ..device.modbus_device import ModbusDeviceModel
from ..communication import ModbusCommunication
from ..config import DeviceConfig
from ..device.modbus_device import ModbusDevice
from ..logger import Logger
from typing import Optional

class ModbusDeviceFactory:
    """
    Factory class for Modbus-based devices.
    Independent from UART implementation.
    """
    _instance = None

    @staticmethod
    def get_device(port: str = "COM6",
                   slave_address: int = 1,
                   timeout: float = 0.01,
                   logger: Optional[Logger] = None,
                   singleton: bool = False) -> ModbusDevice:
        if singleton and ModbusDeviceFactory._instance is not None:
            return  ModbusDeviceFactory._instance

        else:
            comm = ModbusCommunication(port=port, slave_address=slave_address)
            comm.connect()

            model = ModbusDeviceModel()
            config = DeviceConfig()

            # Get register and raw ID before creating the device
            register = model.get_register("device_id")
            raw_id = comm.receive_response(register)
            device_id = int(format(raw_id, 'X').zfill(4), 16)

            # Load config using this device ID
            config.load(device_id)

            device = ModbusDevice(port=port, slave_address=slave_address)
            device.comm = comm
            device.model = model
            device.config = config

        if singleton:
            ModbusDeviceFactory._instance = device

        return device