import os, sys
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(parent_dir)

from ..communication import ModbusCommunication
from .modbus_device_model import ModbusDeviceModel, modbus_get, modbus_set
from ..config import DeviceConfig
from ..utils import (
    STATE_OF_DEVICE_COMMAND,
    STATE_OF_TEC_COMMAND,
    STATE_OF_INTERLOCK_COMMAND,
    OPERATION_STATE_STARTED,
    CURRENT_SET_INTERNAL,
    ENABLE_INTERNAL,
    EXTERNAL_NTC_INTERLOCK_DENIED,
    INTERLOCK_DENIED,
    TEC_OPERATION_STATE_STARTED,
    TEC_SET_INTERNAL,
    TEC_ENABLE_INTERNAL,
    LOCK_STATE_INTERLOCK,
    LOCK_STATE_LD_OVERCURRENT,
    LOCK_STATE_LD_OVERHEAT,
    LOCK_STATE_EXTERNAL_NTC_INTERLOCK,
    LOCK_STATE_TEC_ERROR,
    LOCK_STATE_TEC_SELFHEAT,
    MODBUS_START_COMMAND_VALUE,
    MODBUS_STOP_COMMAND_VALUE,
    MODBUS_START_TEC_COMMAND_VALUE,
    MODBUS_STOP_TEC_COMMAND_VALUE,
    MODBUS_DISABLE_INTERLOCK_COMMAND_VALUE,
    MODBUS_ENABLE_INTERLOCK_COMMAND_VALUE,
    DEFAULT_PORT,
    DEFAULT_SLAVE_ADDRESS,
    REGISTER_DEVICE_ID,
    REGISTER_CURRENT,
    REGISTER_CURRENT_MIN,
    REGISTER_CURRENT_MAX,
    REGISTER_FREQUENCY,
    REGISTER_DURATION,
    REGISTER_VOLTAGE_MEASURED,
    REGISTER_CURRENT_MEASURED,
    REGISTER_CURRENT_MAX_LIMIT,
    REGISTER_CURRENT_PROTECTION_THRESHOLD,
    REGISTER_CURRENT_SET_CALIBRATION,

    REGISTER_TEC_TEMPERATURE_MEASURED,
    REGISTER_TEC_TEMPERATURE_VALUE,

    REGISTER_PCB_TEMPERATURE_MEASURED,
    REGISTER_TEC_CURRENT_MEASURED,
    REGISTER_TEC_VOLTAGE,
    REGISTER_TEC_CURRENT,
    REGISTER_NTC_COEFFICIENT,
    REGISTER_SERIAL_NUMBER,
    REGISTER_TEC_TEMPERATURE,
    REGISTER_TEC_P_COEFFICIENT,
    REGISTER_TEC_I_COEFFICIENT,
    REGISTER_TEC_D_COEFFICIENT,
    REGISTER_TEC_CURRENT_LIMIT,
    REGISTER_VOLTAGE
    )

class ModbusDevice:
    def __init__(self, port=DEFAULT_PORT, slave_address=DEFAULT_SLAVE_ADDRESS):
        self.comm = ModbusCommunication(port, slave_address)
        self.model = ModbusDeviceModel()

        self.comm.connect()
        device_id = self.get_device_id()
        print(f"🆔 Found device ID: {device_id}")

        self.config = DeviceConfig()
        self.config.load(device_id)
        print("📦 Loaded device configuration.")

    def get_device_id(self) -> str:
        register = self.model.get_register(REGISTER_DEVICE_ID)
        raw_id = self.comm.receive_response(register)
        print(f"Raw ID from register: {hex(raw_id)}")
        return int(format(raw_id, 'X').zfill(4), 16)

    def get_divider(self, param_name: str) -> float:
        return self.config.parameters.get(param_name, {}).get("divider", 1)

    def get_units(self, param_name: str) -> str:
        return self.config.parameters.get(param_name, {}).get("units", "")

    def to_signed(self, raw: int) -> int:
        return raw - 0x10000 if raw >= 0x8000 else raw

    def to_signed_16bit(self, val):
        return val - 0x10000 if val >= 0x8000 else val

    @modbus_get(REGISTER_TEC_TEMPERATURE_MEASURED)
    def get_tec_temperature_measured(self, raw):
        raw = self.to_signed(raw)
        divider = self.config.tec_commands.get(REGISTER_TEC_TEMPERATURE, {}).get("divider", 1)
        return raw / divider

    @modbus_get(REGISTER_PCB_TEMPERATURE_MEASURED)
    def get_pcb_temperature_measured(self, raw):
        raw_signed = self.to_signed_16bit(raw)
        print(f"Raw PCB temperature (signed): {raw_signed}")
        divider = self.get_divider(REGISTER_PCB_TEMPERATURE_MEASURED)
        return raw_signed / divider

    @modbus_get(REGISTER_TEC_TEMPERATURE_VALUE)
    def get_tec_temperature_value(self, raw):
        raw = self.to_signed(raw)
        divider =  self.config.tec_commands.get(REGISTER_TEC_TEMPERATURE, {}).get("divider", 1)
        return raw / divider

    @modbus_get(REGISTER_FREQUENCY)
    def get_frequency(self, raw):
        divider = self.get_divider(REGISTER_FREQUENCY)
        return raw / divider

    @modbus_set(REGISTER_FREQUENCY)
    def set_frequency(self, value):
        divider = self.get_divider(REGISTER_FREQUENCY)
        return int(value * divider)

    @modbus_set(REGISTER_TEC_CURRENT_LIMIT)
    def set_frequency(self, value):
        divider =  self.config.tec_commands.get(REGISTER_TEC_CURRENT, {}).get("divider", 1)
        return int(value * divider)

    @modbus_get(REGISTER_DURATION)
    def get_duration(self, raw):
        divider = self.get_divider(REGISTER_DURATION)
        return raw / divider

    @modbus_set(REGISTER_DURATION)
    def set_duration(self, value):
        divider = self.get_divider(REGISTER_DURATION)
        return int(value * divider)

    @modbus_get(REGISTER_CURRENT)
    def get_current(self, raw):
        divider = self.get_divider(REGISTER_CURRENT)
        return raw / divider

    @modbus_set(REGISTER_CURRENT)
    def set_current(self, value):
        divider = self.get_divider(REGISTER_CURRENT)
        return int(value * divider)

    @modbus_get(REGISTER_CURRENT_MEASURED)
    def get_current_measured(self, raw):
        divider = self.config.parameters.get(REGISTER_CURRENT, {}).get("divider_measured", 1)
        return raw / divider

    @modbus_get(REGISTER_VOLTAGE_MEASURED)
    def get_voltage_measured(self, raw):
        divider = self.get_divider(REGISTER_VOLTAGE)
        return raw / divider

    @modbus_get(REGISTER_CURRENT_MAX_LIMIT)
    def get_current_max_limit(self, raw):
        divider = self.get_divider(REGISTER_CURRENT)
        return raw / divider

    @modbus_get(REGISTER_CURRENT_MAX)
    def get_current_max(self, raw):
        divider = self.get_divider(REGISTER_CURRENT)
        return raw / divider

    @modbus_set(REGISTER_CURRENT_MAX)
    def set_current_max(self, raw):
        divider = self.get_divider(REGISTER_CURRENT)
        return int(raw * divider)

    @modbus_get(REGISTER_CURRENT_MIN)
    def get_current_min(self, raw):
        divider = self.get_divider(REGISTER_CURRENT)
        return raw / divider

    @modbus_get(REGISTER_CURRENT_PROTECTION_THRESHOLD)
    def get_current_protection_threshold(self, raw):
        divider = self.get_divider(REGISTER_CURRENT)
        return raw / divider

    @modbus_get(REGISTER_CURRENT_SET_CALIBRATION)
    def get_current_set_calibration(self, raw):
        divider = self.get_divider(REGISTER_CURRENT_SET_CALIBRATION)
        return raw / divider

    @modbus_get(REGISTER_NTC_COEFFICIENT)
    def get_ntc_b25_100_coefficient(self, raw):
        divider = self.get_divider(REGISTER_NTC_COEFFICIENT)
        return raw / divider

    @modbus_get(REGISTER_TEC_CURRENT_LIMIT)
    def get_tec_current_limit(self, raw):
        divider =  self.config.tec_commands.get(REGISTER_TEC_CURRENT, {}).get("divider", 1)
        return raw / divider

    @modbus_set(REGISTER_TEC_CURRENT_LIMIT)
    def set_tec_current_limit(self, raw):
        divider =  self.config.tec_commands.get(REGISTER_TEC_CURRENT, {}).get("divider", 1)
        return int(raw * divider)

    @modbus_get(REGISTER_TEC_CURRENT_MEASURED)
    def get_tec_current_measured(self, raw):
        divider =  self.config.tec_commands.get(REGISTER_TEC_CURRENT, {}).get("divider", 1)
        return raw / divider

    @modbus_set(REGISTER_TEC_TEMPERATURE_VALUE)
    def set_tec_temperature(self, value):
        divider =  self.config.tec_commands.get(REGISTER_TEC_TEMPERATURE, {}).get("divider", 1)
        return int(value * divider)

    @modbus_get(REGISTER_TEC_VOLTAGE)
    def get_tec_voltage(self, raw):
        divider =  self.config.tec_commands.get(REGISTER_TEC_VOLTAGE, {}).get("divider", 1)
        return raw / divider

    def set_tec_pid(self, raw_p, raw_i, raw_d):
        self.comm.send_command(self.model.get_register(REGISTER_TEC_P_COEFFICIENT), raw_p)
        self.comm.send_command(self.model.get_register(REGISTER_TEC_I_COEFFICIENT), raw_i)
        self.comm.send_command(self.model.get_register(REGISTER_TEC_D_COEFFICIENT), raw_d)

    def get_tec_pid(self):
        raw_p = self.comm.receive_response(self.model.get_register(REGISTER_TEC_P_COEFFICIENT))
        raw_i = self.comm.receive_response(self.model.get_register(REGISTER_TEC_I_COEFFICIENT))
        raw_d = self.comm.receive_response(self.model.get_register(REGISTER_TEC_D_COEFFICIENT))
        return raw_p, raw_i, raw_d

    @modbus_get(REGISTER_SERIAL_NUMBER)
    def get_serial_number(self, raw):
        return raw 

    def get_raw_status(self, state_name: str, verbose=False) -> int:
        register = self.model.get_register(state_name)
        try:
            status = self.comm.receive_response(register)
            if verbose:
                print(f"Raw status for '{state_name}': {status:04X}")
            return status
        except Exception as e:
            print(f"Error reading raw status for {state_name}: {e}")
            return 0

    def is_bit_set(self, state_name: str, bit_mask: int) -> bool:
        bitmask = self.get_raw_status(state_name)
        return bool(bitmask & bit_mask)

    def is_operation_started(self) -> bool:
        return self.is_bit_set(STATE_OF_DEVICE_COMMAND, int(OPERATION_STATE_STARTED, 16))

    def is_current_set_internal(self) -> bool:
        return self.is_bit_set(STATE_OF_DEVICE_COMMAND, int(CURRENT_SET_INTERNAL, 16))

    def is_enable_internal(self) -> bool:
        return self.is_bit_set(STATE_OF_DEVICE_COMMAND, int(ENABLE_INTERNAL, 16))

    def is_external_ntc_denied(self) -> bool:
        return self.is_bit_set(STATE_OF_DEVICE_COMMAND, int(EXTERNAL_NTC_INTERLOCK_DENIED, 16))

    def is_interlock_denied(self) -> bool:
        return self.is_bit_set(STATE_OF_DEVICE_COMMAND, int(INTERLOCK_DENIED, 16))

    def disable_interlock(self):
        command = self.model.get_register(STATE_OF_DEVICE_COMMAND)
        self.comm.send_command(command, MODBUS_DISABLE_INTERLOCK_COMMAND_VALUE)

    def enable_interlock(self):
        command = self.model.get_register(STATE_OF_DEVICE_COMMAND)
        self.comm.send_command(command, MODBUS_ENABLE_INTERLOCK_COMMAND_VALUE)

    def start_device(self):
        command = self.model.get_register(STATE_OF_DEVICE_COMMAND)
        self.comm.send_command(command, MODBUS_START_COMMAND_VALUE)

    def stop_device(self):
        command = self.model.get_register(STATE_OF_DEVICE_COMMAND)
        self.comm.send_command(command, MODBUS_STOP_COMMAND_VALUE)

    def start_tec(self):
        command = self.model.get_register(STATE_OF_TEC_COMMAND)
        self.comm.send_command(command, MODBUS_START_TEC_COMMAND_VALUE)

    def stop_tec(self):
        command = self.model.get_register(STATE_OF_TEC_COMMAND)
        self.comm.send_command(command, MODBUS_STOP_TEC_COMMAND_VALUE)

    def is_tec_started(self) -> bool:
        return self.is_bit_set(STATE_OF_TEC_COMMAND, int(TEC_OPERATION_STATE_STARTED, 16))

    def is_tec_set_external(self) -> bool:
        return self.is_bit_set(STATE_OF_TEC_COMMAND, int(TEC_SET_INTERNAL, 16))

    def is_tec_enable_external(self) -> bool:
        return self.is_bit_set(STATE_OF_TEC_COMMAND, int(TEC_ENABLE_INTERNAL, 16))

    def is_lockstate_interlock(self) -> bool:
        return self.is_bit_set(STATE_OF_INTERLOCK_COMMAND, int(LOCK_STATE_INTERLOCK, 16))

    def is_lockstate_lo_overcurrent(self) -> bool:
        return self.is_bit_set(STATE_OF_INTERLOCK_COMMAND, int(LOCK_STATE_LD_OVERCURRENT, 16))

    def is_lockstate_lo_overheat(self) -> bool:
        return self.is_bit_set(STATE_OF_INTERLOCK_COMMAND, int(LOCK_STATE_LD_OVERHEAT, 16))

    def is_lockstate_external_ntc_interlock(self) -> bool:
        return self.is_bit_set(STATE_OF_INTERLOCK_COMMAND, int(LOCK_STATE_EXTERNAL_NTC_INTERLOCK, 16))

    def is_lockstate_tec_error(self) -> bool:
        return self.is_bit_set(STATE_OF_INTERLOCK_COMMAND, int(LOCK_STATE_TEC_ERROR, 16))

    def is_lockstate_tec_selfheat(self) -> bool:
        return self.is_bit_set(STATE_OF_INTERLOCK_COMMAND, int(LOCK_STATE_TEC_SELFHEAT, 16))

