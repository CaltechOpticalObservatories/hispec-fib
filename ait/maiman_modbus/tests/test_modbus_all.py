
import os
import sys
import time
from datetime import datetime

# Setup environment
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(parent_dir)

from device import ModbusDevice
from logger import Logger

def test_all_required_modbus_steps():
    logger = Logger("modbus_documented_steps_test_log.txt")

    # 1. Initialization
    device = ModbusDevice(port="COM6", slave_address=1)

    try:
        device.comm.connect()

        # 2. Read basic parameters
        print("Current:", device.get_current())
        print("Voltage:", device.get_voltage_measured())
        print("TEC Temp:", device.get_tec_temperature_measured())
        print("PCB Temp:", device.get_pcb_temperature_measured())

        # 3. Write parameters
        device.set_current(500.0)
        device.set_frequency(100.0)
        device.set_duration(5.0)

        # 4. Read back to confirm
        print("Set Current:", device.get_current())
        print("Set Frequency:", device.get_frequency())
        print("Set Duration:", device.get_duration())

        # 5. State control
        state_before = device.get_raw_status("state_of_device")
        print("State before start:", hex(state_before))
        device.start_device()
        time.sleep(2)
        state_after = device.get_raw_status("state_of_device")
        print("State after start:", hex(state_after))
        device.stop_device()
        time.sleep(1)

        # 6. State status validation
        print("Operation started:", device.is_operation_started())

        # 7. Serial number and ID
        print("Device ID:", device.get_device_id())
        print("Serial Number:", device.get_serial_number())

        # 8. Extended values
        print("Max Current Limit:", device.get_current_max_limit())
        print("Protection Threshold:", device.get_current_protection_threshold())

        # 9. TEC related values
        print("TEC Voltage:", device.get_tec_voltage())
        print("TEC Current:", device.get_tec_current_measured())
        print("TEC Temperature Value:", device.get_tec_temperature_value())

    except Exception as e:
        print("❌ Test failed:", e)
    finally:
        device.comm.disconnect()

if __name__ == "__main__":
    test_all_required_modbus_steps()