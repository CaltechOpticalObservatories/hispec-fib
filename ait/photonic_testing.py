import atexit
from dataclasses import dataclass
import astropy.units as u

from maiman_modbus.factory import ModbusDeviceFactory


@dataclass
class LaserProperties:
    name: str
    model_number: str
    max_current: float
    threshold_current: float
    efficiency: float
    wavelength: float
    test_monitor_current: float
    operating_temp: float = None
    thermisistor: float = None
    isolation: float = None
    tec_max_current: float = None
    tec_pid: tuple = None
    test_monitor_current: float = None
    ntc_t_coefficient: float = None


TEC_PID_DEFAULT = (100, 1000, 0)
TEC_PID_DFB = (20, 1000, 1000)


LASER_1028 = LaserProperties(name="1028", model_number="FLPD-1028-50-DFB-BTF",
                             threshold_current=14.5 * u.mA,
                             max_current=250 * u.mA,
                             tec_max_current=1.2 * u.A,
                             tec_pid=TEC_PID_DFB,

                             wavelength=1028.01 * u.nm,
                             test_monitor_current=23.3 * u.uA,
                             efficiency=0.185 * u.mW / u.mA,
                             # bias_current = 250*u.mA,
                             # bias_voltage = 1.667 * u.V,

                             operating_temp=25 * u.C,
                             thermisistor=10 * u.kOhm,
                             isolation=30 * u.dB,
                             ntc_t_coefficient=-.044 / u.C)

LASER_2330 = LaserProperties(name="2330", model_number="FLPD-2330-03-DFB-BTF",
                             threshold_current=24.9 * u.mA,
                             max_current=120 * u.mA,
                             tec_max_current=1.2 * u.A,
                             tec_pid=TEC_PID_DFB,

                             wavelength=2329.81 * u.nm,
                             test_monitor_current=None,
                             efficiency=0.031 * u.mW / u.mA,
                             # bias_current = 120*u.mA,
                             # bias_voltage = 3.105 * u.V,

                             operating_temp=25 * u.C,
                             thermisistor=10 * u.kOhm,
                             isolation=30 * u.dB,
                             ntc_t_coefficient=-.044 / u.C)

LASER_1270 = LaserProperties(name="1270", model_number="1270LD-1-0-0",
                             threshold_current=8 * u.mA,
                             max_current=70 * u.mA,
                             tec_max_current=1 * u.A,
                             tec_pid=TEC_PID_DEFAULT,

                             wavelength=1270 * u.nm,
                             test_monitor_current=None,
                             efficiency=.166 * u.mW / u.mA,
                             # dlambda_dA=0.003*u.nm/u.mA,
                             # dlambda_dT=0.08*u.nm/u.K,

                             operating_temp=25 * u.C,
                             thermisistor=10 * u.kOhm,
                             isolation=25 * u.dB,
                             ntc_t_coefficient=None)

LASER_1430 = LaserProperties(name="1430", model_number="1430LD-1-0-0",
                             threshold_current=8 * u.mA,
                             max_current=70 * u.mA,
                             tec_max_current=1 * u.A,
                             tec_pid=TEC_PID_DEFAULT,

                             wavelength=1430 * u.nm,
                             test_monitor_current=None,
                             efficiency=.166 * u.mW / u.mA,
                             # dlambda_dA=0.003*u.nm/u.mA,
                             # dlambda_dT=0.08*u.nm/u.K,

                             operating_temp=25 * u.C,
                             thermisistor=10 * u.kOhm,
                             isolation=25 * u.dB,
                             ntc_t_coefficient=None)

LASER_1510 = LaserProperties(name="1510", model_number="15100LD-1-0-0",
                             threshold_current=8 * u.mA,
                             max_current=70 * u.mA,
                             tec_max_current=1 * u.A,
                             tec_pid=TEC_PID_DEFAULT,

                             wavelength=1430 * u.nm,
                             test_monitor_current=None,
                             efficiency=.166 * u.mW / u.mA,
                             # dlambda_dA=0.003*u.nm/u.mA,
                             # dlambda_dT=0.08*u.nm/u.K,

                             operating_temp=25 * u.C,
                             thermisistor=10 * u.kOhm,
                             isolation=25 * u.dB,
                             ntc_t_coefficient=None)


LASER_PROPERTIES = {"1028": LASER_1028,
                    "1270": LASER_1270,
                    "yj1430": LASER_1430,
                    "hk1430": LASER_1430,
                    "1510": LASER_1510,
                    "2330": LASER_2330}

class Laser:
    def __init__(self, name: str, address: int = 1, MODBUS_PORT: str = "COM6"):
        self.name = name
        self.laser_properties = LASER_PROPERTIES[name]
        self.device = ModbusDeviceFactory.get_device(MODBUS_PORT, slave_address=address)
        atexit.register(self.device.stop_device)

    def program_drive_limits(self):
        drive = self.device
        drive.comm.connect()
        print(f"Programming Limits for Maiman (S/N: {drive.get_serial_number()})...")
        drive.set_tec_current_limit(self.laser_properties.tec_max_current.to(u.A).value)
        drive.set_current_max(self.laser_properties.max_current.to(u.mA).value)
        drive.set_tec_pid(*self.laser_properties.tec_pid)

    def disable_interlock_and_cool(self):
        self.program_drive_limits()
        self.device.set_current(0)
        self.device.disable_interlock()
        self.device.start_tec()
        self.device.start_device()

    def shutdown(self):
        self.device.set_current(0)
        self.device.stop_device()
        self.device.stop_tec()

    def set_current_as_percent(self, x:float, enforce_limits=True):
        if enforce_limits:
            self.program_drive_limits()
        device = self.device
        x = max(min(x,1), 0)
        device.comm.connect()
        range = self.laser_properties.max_current - self.laser_properties.threshold_current
        current = (range*x + self.laser_properties.threshold_current)
        print(f"Setting current to {x if x==0 else current} ")
        device.set_current(x if x==0 else current.to('mA').value)

    def status(self):
        device = self.device
        device.comm.connect()

        print("Laser Properties Name:", self.laser_properties.name)
        print("Device ID:", device.get_device_id())
        print("Serial Number:", device.get_serial_number())
        print("State:", hex(device.get_raw_status("state_of_device")))
        print(" Operation started:", device.is_operation_started())
        print(" Current Set Internal:", device.is_current_set_internal())
        print(" Enable Internal:", device.is_enable_internal())
        print(" External NTC Denied:", device.is_external_ntc_denied())
        print(" Interlock Denied:", device.is_interlock_denied())

        print("Current:", device.get_current())
        print("Current Min:", device.get_current_min())
        print("Current Max:", device.get_current_max())
        print("Max Current Limit:", device.get_current_max_limit())
        print("Protection Threshold:", device.get_current_protection_threshold())
        print("Voltage:", device.get_voltage_measured())

        print("Frequency:", device.get_frequency())
        print("Duration:", device.get_duration())
        print("PCB Temp:", device.get_pcb_temperature_measured())

        print("Current Set Calibration:", device.get_current_set_calibration())

        print("TEC PID:", device.get_tec_pid())
        print("TEC Voltage:", device.get_tec_voltage())
        print("TEC Current Limit:", device.get_tec_current_limit())
        print("TEC Current:", device.get_tec_current_measured())
        print("TEC Temperature Setpoint:", device.get_tec_temperature_value())
        print("TEC Temperature:", device.get_tec_temperature_measured())
        print("TEC NTC Coefficient:", device.get_ntc_b25_100_coefficient())
        print("TEC State:", hex(device.get_raw_status("tec_state")))
        print(" TEC started:", device.is_tec_started())
        print(" TEC Set Internal:", device.is_tec_set_external())
        print(" TEC Enable Internal:", device.is_tec_enable_external())

        print("Interlock State:", hex(device.get_raw_status("lock_status")))
        print(" Interlock:", device.is_lockstate_interlock())
        print(" LD Overcurrent:", device.is_lockstate_lo_overcurrent())
        print(" LD Overheat:", device.is_lockstate_lo_overheat())
        print(" External NTC Interlock:", device.is_lockstate_external_ntc_interlock())
        print(" TEC Error:", device.is_lockstate_tec_error())
        print(" TEC Self-heat:", device.is_lockstate_tec_selfheat())
