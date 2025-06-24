import yaml
from functools import wraps
import importlib.resources


class ModbusDeviceModel:
    def __init__(self, yaml_path=None):
        if yaml_path is None:
            yaml_path = str(importlib.resources.files('maiman_modbus.config').joinpath('modbus_config.yaml'))
        with open(yaml_path, "r") as file:
            self.register_map = yaml.safe_load(file)["modbus_registers"]

    def get_register(self, name: str) -> int:
        return self.register_map.get(name)


def modbus_get(parameter_name):
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            register = self.model.get_register(parameter_name)
            raw = self.comm.receive_response(register)
            return func(self, raw, *args, **kwargs)
        return wrapper
    return decorator

def modbus_set(parameter_name):
    def decorator(func):
        @wraps(func)
        def wrapper(self, value, *args, **kwargs):
            register = self.model.get_register(parameter_name)
            raw = func(self, value, *args, **kwargs)
            self.comm.send_command(register, raw)
        return wrapper
    return decorator