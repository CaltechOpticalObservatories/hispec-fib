import yaml
from ..utils import *
from os import path

def normalize_key(key: str) -> str:
    return key.lower().replace(" ", "_").replace("-", "_")

class DeviceConfig:
    def __init__(self):
        parent_dir = path.dirname(path.abspath(__file__))
        self.file_path = path.join(parent_dir, 'device_config.yaml')
        self.config = None
        self.device_config = None
        self._normalized_parameters = {}
        self._normalized_states = {}

    def _load_yaml(self) -> None:
        with open(self.file_path, 'r', encoding='utf-8') as file:
            self.config = yaml.safe_load(file)

    def load(self, device_id: int) -> dict:
        self._load_yaml()
        device_config = self.config.get("devices", {}).get(device_id)
        if not device_config:
            raise ValueError(f"Device ID {device_id} not found.")

        self._validate_device_config(device_config)
        self.device_config = device_config

        # Create normalized lookup maps
        self._normalized_parameters = {
            normalize_key(k): v for k, v in self.device_config.get(SECTION_PARAMETERS, {}).items()
        }
        self._normalized_states = {
            normalize_key(k): v for k, v in self.device_config.get(SECTION_STATE_COMMANDS, {}).items()
        }
        self._normalized_tec = {
            normalize_key(k): v for k, v in self.device_config.get(SECTION_TEC_COMMANDS, {}).items()
        }
        return device_config

    def _validate_device_config(self, device_config: dict) -> None:
        required_sections = [SECTION_ERROR_CODES, SECTION_PARAMETERS, SECTION_STATE_COMMANDS]
        for section in required_sections:
            if section not in device_config:
                raise ValueError(f"Missing required section '{section}'.")

    def _get_section(self, section_name: str) -> dict:
        if not self.device_config:
            raise ValueError("Device configuration not loaded.")
        return self.device_config.get(section_name, {})

    @property
    def error_codes(self) -> dict:
        return self._get_section(SECTION_ERROR_CODES)

    @property
    def parameters(self) -> dict:
        return self._normalized_parameters

    @property
    def state_commands(self) -> dict:
        return self._normalized_states

    @property
    def tec_commands(self) -> dict:
        return self._get_section(SECTION_TEC_COMMANDS)

    @property
    def tec_state_commands(self) -> dict:
        return self._get_section(SECTION_TEC_STATE_COMMANDS)

    @property
    def device_info(self) -> dict:
        return self._get_section(SECTION_DEVICE_INFO)

    @property
    def system_commands(self) -> dict:
        return self._get_section(SECTION_SYSTEM_COMMANDS)

    def __repr__(self):
        config_snippet = str(self.config)[:100] + ("..." if len(str(self.config)) > 100 else "")
        return f"DeviceConfig(file_path={self.file_path}, config_snippet={config_snippet})"
