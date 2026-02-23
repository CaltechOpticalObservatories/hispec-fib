import atexit
from dataclasses import dataclass
import astropy.units as u
from threading import Timer

from .maiman_modbus.factory import ModbusDeviceFactory
from .maiman_modbus.utils import utils as mainman_const

@dataclass
class LaserProperties:
    name: str
    model_number: str
    nominal_current: float
    max_current: float
    dne_current: float
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
    dlambda_dT: float = None
    dlambda_dA: float = None

#NB the pot that sets the OCP on the Maiman driver is https://www.digikey.com/en/products/detail/bourns-inc/3224W-1-203E/225661
#with a 100ppm/degC coeff. the driver is 0-250 mA over the range of the pot.
# thermal envelope has domain of -15 to 30 C or so. At pot extrema it sets the Maiman to 0 and 331mA.
# So 45*100e-6*331 is max OCP drift or 1.48 mA so set pot 1.5mA below allowable diode DNE current.

TEC_PID_DEFAULT = (100, 1000, 0)
TEC_PID_DFB = (20, 1000, 1000)


LASER_1028 = LaserProperties(name="1028", model_number="FLPD-1028-50-DFB-BTF",
                             threshold_current=14.5 * u.mA,
                             nominal_current=230 * u.mA,
                             max_current=240 * u.mA,
                             dne_current=250 * u.mA,
                             tec_max_current=1.2 * u.A,
                             tec_pid=TEC_PID_DFB,

                             wavelength=1028.01 * u.nm,
                             test_monitor_current=23.3 * u.uA,
                             efficiency=0.185 * u.mW / u.mA,

                             dlambda_dA=0.015 * u.nm / u.mA,
                             dlambda_dT=0.12 * u.nm / u.K,

                             operating_temp=25 * u.deg_C,
                             thermisistor=10 * u.kOhm,
                             isolation=30 * u.dB,
                             ntc_t_coefficient=-.044 / u.C)

LASER_2330 = LaserProperties(name="2330", model_number="FLPD-2330-03-DFB-BTF",
                             threshold_current=24.9 * u.mA,
                             nominal_current=114.2 * u.mA,  # calculated fromm test report for 3mA optical power
                             max_current=120 * u.mA,
                             dne_current=135 * u.mA,
                             tec_max_current=1.2 * u.A,
                             tec_pid=TEC_PID_DFB,

                             wavelength=2329.81 * u.nm,
                             test_monitor_current=None,
                             efficiency=0.031 * u.mW / u.mA,

                             dlambda_dA=0.015 * u.nm / u.mA,
                             dlambda_dT=0.12 * u.nm / u.K,

                             operating_temp=25 * u.deg_C,
                             thermisistor=10 * u.kOhm,
                             isolation=30 * u.dB,
                             ntc_t_coefficient=-.044 / u.C)

LASER_1270 = LaserProperties(name="1270", model_number="1270LD-1-0-0",
                             threshold_current=8 * u.mA,
                             nominal_current=60 * u.mA,
                             max_current=60 * u.mA,
                             dne_current=70 * u.mA,
                             tec_max_current=1 * u.A,
                             tec_pid=TEC_PID_DEFAULT,

                             wavelength=1270 * u.nm,
                             test_monitor_current=None,
                             efficiency=.166 * u.mW / u.mA,
                             dlambda_dA=0.003*u.nm/u.mA,
                             dlambda_dT=0.08*u.nm/u.K,

                             operating_temp=25 * u.deg_C,
                             thermisistor=10 * u.kOhm,
                             isolation=25 * u.dB,
                             ntc_t_coefficient=None)

LASER_1430 = LaserProperties(name="1430", model_number="1430LD-1-0-0",
                             threshold_current=8 * u.mA,
                             nominal_current=60 * u.mA,
                             max_current=60 * u.mA,
                             dne_current=70 * u.mA,
                             tec_max_current=1 * u.A,
                             tec_pid=TEC_PID_DEFAULT,

                             wavelength=1430 * u.nm,
                             test_monitor_current=None,
                             efficiency=.166 * u.mW / u.mA,
                             dlambda_dA=0.003*u.nm/u.mA,
                             dlambda_dT=0.08*u.nm/u.K,

                             operating_temp=25 * u.deg_C,
                             thermisistor=10 * u.kOhm,
                             isolation=25 * u.dB,
                             ntc_t_coefficient=None)

LASER_1510 = LaserProperties(name="1510", model_number="15100LD-1-0-0",
                             threshold_current=8 * u.mA,
                             nominal_current=60 * u.mA,
                             max_current=60 * u.mA,
                             dne_current=70 * u.mA,
                             tec_max_current=1 * u.A,
                             tec_pid=TEC_PID_DEFAULT,

                             wavelength=1430 * u.nm,
                             test_monitor_current=None,
                             efficiency=.166 * u.mW / u.mA,
                             dlambda_dA=0.003*u.nm/u.mA,
                             dlambda_dT=0.08*u.nm/u.K,

                             operating_temp=25 * u.deg_C,
                             thermisistor=10 * u.kOhm,
                             isolation=25 * u.dB,
                             ntc_t_coefficient=None)


LASER_PROPERTIES = {"1028": LASER_1028,
                    "1270": LASER_1270,
                    "yj1430": LASER_1430,
                    "hk1430": LASER_1430,
                    "1510": LASER_1510,
                    "2330": LASER_2330}

LASER_DRIVER_SERIALS = {"1028": 8229,
                   "1270": 8228,
                   "yj1430": 8222,
                   "hk1430": 8227,
                   "1510": 8225,
                   "2330": 8226}

class Laser:
    def __init__(self, name: str, address: int = 1, MODBUS_PORT: str = "COM6", register_atexit=True):
        self.name = name
        try:
            self.laser_properties = LASER_PROPERTIES[name]
        except KeyError:
            raise ValueError(f"Unknown laser {name}")
        assert self.laser_properties.nominal_current<=self.laser_properties.max_current, 'Nominal current must be <= than max_current'
        assert self.laser_properties.max_current<self.laser_properties.dne_current, 'Max current must be < than DNE_current'
        self.device = ModbusDeviceFactory.get_device(MODBUS_PORT, slave_address=address)
        assert self.device.get_serial_number() == LASER_DRIVER_SERIALS[name], 'BAD BUS CONFIG, do not continue'
        if register_atexit:
            atexit.register(self.shutdown)
        self._autooff_timer : Timer = None

    def program_drive_limits(self):
        print(f"Programming limits for {self.name}, Maiman driver: S/N {self.device.get_serial_number()}...")
        ocp_ma = self.device.get_current_protection_threshold()
        dne_ma = self.laser_properties.dne_current.value
        if ocp_ma > dne_ma:
            raise RuntimeError(f"Current DRV OCP ({ocp_ma} mA) potentiometer is too "
                               f"high for laser {self.name} (DNE {dne_ma} mA)")
        self.device.set_tec_current_limit(self.laser_properties.tec_max_current.to(u.A).value)
        self.device.set_current_max(self.laser_properties.max_current.to(u.mA).value)
        self.device.set_tec_pid(*self.laser_properties.tec_pid)

    def startup(self):
        self.device.comm.connect()
        self.device.enable_interlock()
        self.program_drive_limits()
        self.device.set_current(0)
        self.device.disable_interlock()
        self.device.start_tec()
        self.device.start_device()

    def shutdown(self):
        self.device.comm.connect()
        self.device.set_current(0)
        self.device.stop_device()
        self.device.stop_tec()
        self.device.enable_interlock()

    @property
    def nominal_optical_power(self):
        return (self.device.get_current()*u.mA-self.laser_properties.threshold_current)*self.laser_properties.efficiency

    @property
    def nominal_wavelength(self):
        delta_i =  (self.device.get_current()*u.mA-self.laser_properties.nominal_current)
        delta_t = (self.device.get_tec_temperature_measured()*u.deg_C - self.laser_properties.operating_temp).value*u.K
        shift = delta_t*self.laser_properties.dlambda_dT + delta_i*self.laser_properties.dlambda_dA
        return (self.laser_properties.wavelength+shift).to(u.nm)

    def set_current_as_percent(self, x:float, autooff=3*3600):
        if not self.ready_to_operate():
            raise RuntimeError("Laser not ready to operate, try calling disable_interlock_and_cool() or status()")

        device = self.device
        x = max(min(x,1), 0)
        device.comm.connect()
        range = self.laser_properties.nominal_current - self.laser_properties.threshold_current
        current = (range*x + self.laser_properties.threshold_current)
        print(f"Setting current to {x if x==0 else current} ")
        device.set_current(x if x==0 else current.to('mA').value)
        set_current = device.get_current()
        print(f"...current: {set_current} mA, output power: {self.nominal_optical_power}, "
              f"wavelength: {self.nominal_wavelength} (temp = {self.device.get_tec_temperature_measured()} C)")


        if self._autooff_timer is not None:
            self._autooff_timer.cancel()

        if autooff > 0:
            def autooff_callback():
                print(f"Autooff timer expired after {autooff}, shutting down {self.name}.")
                self.shutdown()
            self._autooff_timer = Timer(int(autooff), autooff_callback)
            self._autooff_timer.daemon = True
            self._autooff_timer.start()

        return set_current

    def ready_to_operate(self):
        """Determines readiness by checking device status flags"""
        interlock_bitmask = (int(mainman_const.LOCK_STATE_LD_OVERCURRENT, 16) |int(mainman_const.LOCK_STATE_LD_OVERHEAT, 16) |
                             int(mainman_const.LOCK_STATE_EXTERNAL_NTC_INTERLOCK, 16) | int(mainman_const.LOCK_STATE_TEC_ERROR, 16))

        state = self.device.get_raw_status("state_of_device")
        device_started = bool(state & (int(mainman_const.OPERATION_STATE_STARTED, 16) | int(mainman_const.INTERLOCK_DENIED, 16)))


        interlocked = bool(self.device.get_raw_status("lock_status") & interlock_bitmask)
        tec_running = self.device.is_tec_started()
        print(f"tec_running: {tec_running}, interlocked: {interlocked}, started: {device_started}")
        return device_started and tec_running and not interlocked

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
        print("Protection Threshold:", device.get_current_protection_threshold())
        print("Driver Max Current:", device.get_current_max_limit())
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
