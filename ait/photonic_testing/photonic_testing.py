import atexit
import time
from dataclasses import dataclass
import astropy.units as u
from threading import Timer, Thread
import numpy as np
from dask.array import remainder

from .maiman_modbus.factory import ModbusDeviceFactory
from .maiman_modbus.utils import utils as mainman_const

@dataclass
class LaserProperties:
    name: str
    model_number: str
    nominal_current: float  #the "full power current" may be<= max_current, used for computing percentage of drive
    max_current: float
    dne_current: float
    threshold_current: float
    efficiency: float
    wavelength: float
    test_monitor_current: float
    operating_temp_range: tuple[float, float] = None
    operating_temp: float = None
    thermisistor: float = None
    isolation: float = None
    tec_max_current: float = None
    tec_pid: tuple = None
    test_monitor_current: float = None
    ntc_t_coefficient: float = None
    dlambda_dT: float = None
    dlambda_dA: float = None


@dataclass
class LaserMonitorData:
    data: np.recarray
    cadence_hz: float
    duration_s: float
    start_time_s: float
    _count: int = 0
    _thread: Thread | None = None

    def get_data(self) -> np.recarray:
        """Return data collected so far. Do not mutate the returned data."""
        return self.data[:self._count]

#NB the pot that sets the OCP on the Maiman driver is https://www.digikey.com/en/products/detail/bourns-inc/3224W-1-203E/225661
#with a 100ppm/degC coeff. the driver is 0-250 mA over the range of the pot.
# thermal envelope has domain of -15 to 30 C or so. At pot extrema it sets the Maiman to 0 and 331mA.
# So 45*100e-6*331 is max OCP drift or 1.48 mA so set pot 1.5mA below allowable diode DNE current.

TEC_PID_DEFAULT = (100, 1000, 0)
TEC_PID_DFB = (20, 1000, 1000)

#Driver limited to +15-40 deg tec control range
LASER_1028 = LaserProperties(name="1028", model_number="FLPD-1028-50-DFB-BTF",
                             threshold_current=14.5 * u.mA,
                             nominal_current=250 * u.mA,
                             max_current=250 * u.mA,
                             dne_current=275 * u.mA,  # 110% per V. Mazo Frankfurt laser
                             tec_max_current=1.2 * u.A,
                             tec_pid=TEC_PID_DFB,

                             wavelength=1028.01 * u.nm,
                             test_monitor_current=23.3 * u.uA, # @43.8mA optical power
                             efficiency=0.185 * u.mW / u.mA,

                             dlambda_dA=0.015 * u.nm / u.mA,
                             dlambda_dT=0.12 * u.nm / u.deg_C,

                             operating_temp_range=(15 * u.deg_C, 40* u.deg_C),
                             operating_temp=25 * u.deg_C,
                             thermisistor=10 * u.kOhm,
                             isolation=30 * u.dB,
                             ntc_t_coefficient=-.044 / u.C)

LASER_2330 = LaserProperties(name="2330", model_number="FLPD-2330-03-DFB-BTF",
                             threshold_current=24.9 * u.mA,
                             nominal_current=120.0 * u.mA,
                             max_current=120 * u.mA,
                             dne_current=135 * u.mA, # ~110% per V. Mazo Frankfurt laser
                             tec_max_current=1.2 * u.A,
                             tec_pid=TEC_PID_DFB,

                             wavelength=2329.81 * u.nm,  # may have been at 40 deg C!!!
                             test_monitor_current=None,
                             efficiency=0.031 * u.mW / u.mA,

                             dlambda_dA=0.015 * u.nm / u.mA,
                             dlambda_dT=0.12 * u.nm / u.deg_C,

                             operating_temp_range=(15 * u.deg_C, 40 * u.deg_C),
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
                             dlambda_dT=0.08*u.nm/u.deg_C,

                             operating_temp_range=(15 * u.deg_C, 40 * u.deg_C),  # loosely, DS specifies case temp of -5-60
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
                             dlambda_dT=0.08*u.nm/u.deg_C,

                             operating_temp_range=(15 * u.deg_C, 40 * u.deg_C),  # loosely, DS specifies case temp of -5-60
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
                             dlambda_dT=0.08*u.nm/u.deg_C,

                             operating_temp_range=(15 * u.deg_C, 40 * u.deg_C), # loosely, DS specifies case temp of -5-60
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
        self.device.enable_interlock()
        ocp_ma = self.device.get_current_protection_threshold()
        dne_ma = self.laser_properties.dne_current.value
        if ocp_ma > dne_ma:
            self.device.enable_interlock()
            self.device.set_current(0)
            self.device.stop_device()
            self.device.stop_tec()
            raise RuntimeError(f"Current DRV OCP ({ocp_ma} mA) potentiometer is too "
                               f"high for laser {self.name} (DNE {dne_ma} mA). Unsafe to continue")

        self.device.set_tec_current_limit(self.laser_properties.tec_max_current.to(u.A).value)
        self.device.set_current_max(self.laser_properties.max_current.to(u.mA).value)
        self.device.set_tec_pid(*self.laser_properties.tec_pid)

    def startup(self):
        self.program_drive_limits()
        self.device.set_current(0)
        self.device.disable_interlock()
        self.device.set_tec_temperature(self.device.get_tec_temperature_measured())
        self.device.start_tec()
        self.device.start_device()

    def shutdown(self):
        self.device.set_current(0)
        self.device.stop_device()
        self.device.stop_tec()
        self.device.enable_interlock()

    @property
    def nominal_optical_power(self):
        return (self.device.get_current()*u.mA-self.laser_properties.threshold_current)*self.laser_properties.efficiency

    @property
    def nominal_wavelength(self):
        current = self.device.get_current()
        if current==0:
            return self.laser_properties.wavelength.to(u.nm)

        delta_i =  (current*u.mA-self.laser_properties.nominal_current)
        delta_t = (self.device.get_tec_temperature_measured()*u.deg_C - self.laser_properties.operating_temp)
        shift = delta_t*self.laser_properties.dlambda_dT + delta_i*self.laser_properties.dlambda_dA
        return (self.laser_properties.wavelength+shift).to(u.nm)

    def tune_wavelength(self, desired_brightness:float, wavelength:u.Quantity, use_current=True, use_temp=True,
                        maximum_power_shift=np.inf, autooff=3*3600, apply=False):
        """
        Tune with temp then with power unless modality disallowed

        """
        if desired_brightness<0:
            raise ValueError(f"Desired brightness must be [0-1]")

        if desired_brightness==0:
            self.device.set_current(0)
            self.device.stop_device()
            return None

        if not self.ready_to_operate():
            raise RuntimeError("Laser not ready to operate, try calling disable_interlock_and_cool() or status()")


        current_range = self.laser_properties.nominal_current - self.laser_properties.threshold_current
        desiredI = min(self.laser_properties.threshold_current+current_range * desired_brightness, self.laser_properties.max_current)

        initial_l = (desiredI - self.laser_properties.nominal_current)*self.laser_properties.dlambda_dA + self.laser_properties.wavelength

        # Tune with T
        dl = wavelength-initial_l
        dt = dl/self.laser_properties.dlambda_dT
        desiredT= self.laser_properties.operating_temp+dt
        minT, maxT = min(self.laser_properties.operating_temp_range), max(self.laser_properties.operating_temp_range)
        newT = np.round(max(min(maxT, desiredT), minT), 2)

        currentT=self.device.get_tec_temperature_measured()*u.deg_C

        if use_temp:
            dl_fromT = self.laser_properties.dlambda_dT * (newT-self.laser_properties.operating_temp)
        else:
            dl_fromT = 0 *u.nm
            newT = self.laser_properties.operating_temp


        # Then fine tune with I
        dl_remain = dl - dl_fromT

        dI = dl_remain/self.laser_properties.dlambda_dA
        dI_allowed = maximum_power_shift*current_range
        if abs(dI)>dI_allowed:
            dI = np.sign(dI)*dI_allowed

        newI = round(max(min(desiredI+dI, self.laser_properties.max_current), self.laser_properties.threshold_current),1)

        if use_current:
            dl_fromI = (newI-self.laser_properties.nominal_current)*self.laser_properties.dlambda_dA
        else:
            dl_fromI = 0 *u.nm
            newI = desiredI

        if apply:
            self.device.set_tec_temperature(newT.to_value(u.deg_C))
            self.device.set_current(newI.to_value(u.mA))
            self.auto_off(autooff)

        lI_err = .01*newI* self.laser_properties.dlambda_dA
        lT_err = .01*newT*self.laser_properties.dlambda_dT

        print(f'Requested tuning {self.laser_properties.wavelength:.3f} to {wavelength:.3f} at'
              f' {desired_brightness*100:.1f}±{maximum_power_shift*100:.2f}% flux.\n'
              f'    TEC Temp: {newT} (current {currentT}), resulting dl from nominal {dl_fromT:.3f}.\n'
              f'    Drive current: {desiredI}->{newI}, resulting dl {dl_fromI:.3f}.\n'
              f'    Optical Power: {(newI-self.laser_properties.threshold_current)*self.laser_properties.efficiency:.2f}\n'
              f'    Laser power difference from request: {(newI-desiredI)*self.laser_properties.efficiency:.2f}\n'
              f'    Wavelength difference from request: {(wavelength - (initial_l+dl_fromI+dl_fromT)).to("nm"):.3f}\n'
              f'    Note drive accuracy: {np.sqrt(lT_err**2 + lI_err**2):.3f}')

        return self.nominal_wavelength

    def monitor_diode(self, duration_s: float, cadence_hz: float = 100.0) -> LaserMonitorData:
        """
        Monitor TEC temp/voltage/current, PCB temp, and laser diode current/voltage.

        Data fields (units):
            t_s, tec_temp_c, tec_voltage_v, tec_current_a, board_temp_c,
            diode_current_ma, diode_voltage_v
        """
        if duration_s <= 0:
            raise ValueError("duration_s must be > 0")
        if cadence_hz <= 0:
            raise ValueError("cadence_hz must be > 0")

        period_s = 1.0 / cadence_hz
        num_samples = max(1, int(np.ceil(duration_s * cadence_hz)))
        dtype = [
            ("t_s", "f8"),
            ("tec_temp_c", "f4"),
            ("tec_voltage_v", "f4"),
            ("tec_current_a", "f4"),
            ("diode_current_ma", "f4"),
            ("diode_voltage_v", "f4"),
        ]
        data = np.zeros(num_samples, dtype=dtype).view(np.recarray)
        monitor = LaserMonitorData(
            data=data,
            cadence_hz=cadence_hz,
            duration_s=duration_s,
            start_time_s=time.time(),
        )

        def _run():
            device = self.device
            device.comm.connect()
            start = time.perf_counter()
            for i in range(num_samples):
                now = time.perf_counter()
                data[i] = (
                    now - start,
                    device.get_tec_temperature_measured(),
                    device.get_tec_voltage(),
                    device.get_tec_current_measured(),
                    device.get_current_measured(),
                    device.get_voltage_measured(),
                )
                monitor._count = i + 1
                next_time = start + (i + 1) * period_s
                sleep_s = next_time - time.perf_counter()
                if sleep_s > 0:
                    time.sleep(sleep_s)

        thread = Thread(target=_run, daemon=True)
        monitor._thread = thread
        thread.start()
        return monitor

    def tune_and_monitor(self, desired_brightness: float, wavelength: u.Quantity, duration_s: float,
                         cadence_hz: float = 100.0, **tune_kwargs) -> LaserMonitorData:
        """Tune wavelength (applying settings) then start monitoring and return the monitor object."""
        apply = tune_kwargs.pop("apply", True)
        self.tune_wavelength(desired_brightness, wavelength, apply=apply, **tune_kwargs)
        return self.monitor_diode(duration_s=duration_s, cadence_hz=cadence_hz)

    @staticmethod
    def compute_power_and_wavelength(laser_properties: LaserProperties, tec_temp_c, diode_current_ma):
        """Compute optical power and wavelength from TEC temp and diode current arrays."""
        tec_temp = np.asarray(tec_temp_c) * u.deg_C
        diode_current = np.asarray(diode_current_ma) * u.mA

        power = (diode_current - laser_properties.threshold_current) * laser_properties.efficiency
        delta_i = diode_current - laser_properties.nominal_current
        delta_t = tec_temp - laser_properties.operating_temp
        wavelength = (laser_properties.wavelength + delta_t * laser_properties.dlambda_dT +
                      delta_i * laser_properties.dlambda_dA)

        return power.to(u.mW), wavelength.to(u.nm)

    def auto_off(self, autooff):

        if self._autooff_timer is not None:
            self._autooff_timer.cancel()

        if autooff > 0:
            def autooff_callback():
                print(f"Autooff timer expired after {autooff}, turning off laser current {self.name}.")
                self.device.set_current(0)
            self._autooff_timer = Timer(int(autooff), autooff_callback)
            self._autooff_timer.daemon = True
            self._autooff_timer.start()

    def set_current_as_percent(self, x:float, autooff=3*3600):
        if x<0:
            raise ValueError(f"Desired brightness must be [0-1]")

        if x==0:
            self.device.set_current(0)
            self.device.stop_device()

        if not self.ready_to_operate():
            raise RuntimeError("Laser not ready to operate, try calling disable_interlock_and_cool() or status()")

        device = self.device
        x = max(min(x,1), 0)
        device.comm.connect()
        range = self.laser_properties.nominal_current - self.laser_properties.threshold_current
        current = (range*x + self.laser_properties.threshold_current)
        print(f"Setting current to {x if x==0 else current}... ")
        device.set_current(x if x==0 else current.to('mA').value)
        self.auto_off(autooff)
        self.device.start_device()

        print(f"  done. Estimated output {self.nominal_optical_power:.2f} @ {self.nominal_wavelength:.3f}.")
        self.status(verbose=False)

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

    def status(self, verbose=True):
        device = self.device

        print(f"Laser Name: '{self.laser_properties.name}'")
        if verbose:
            print("Device ID:", device.get_device_id())
            print("Serial Number:", device.get_serial_number())
        print("Operation started:", device.is_operation_started())
        if verbose:
            print(" Raw State:", hex(device.get_raw_status("state_of_device")))
            print(" Current Set Internal:", device.is_current_set_internal())
            print(" Enable Internal:", device.is_enable_internal())
            print(" External NTC Denied:", device.is_external_ntc_denied())
            print(" Interlock Denied:", device.is_interlock_denied())
            print(" Interlock State:", hex(device.get_raw_status("lock_status")))
            print(" Interlock:", device.is_lockstate_interlock())
            print(" External NTC Interlock:", device.is_lockstate_external_ntc_interlock())
        print("Voltage:", device.get_voltage_measured())
        print(f"Current (min-max): {device.get_current():.2f} ({device.get_current_min():.2f}-{device.get_current_max():.2f})")


        if verbose:
            print("Protection Threshold:", device.get_current_protection_threshold())
            print("Driver Max Current:", device.get_current_max_limit())
        print("Current Set Calibration:", device.get_current_set_calibration())

        if verbose:
            print("Frequency:", device.get_frequency())
            print("Duration:", device.get_duration())

        print("TEC Started:", device.is_tec_started())
        print(" TEC Temperature Setpoint:", device.get_tec_temperature_value())
        print(" TEC Temperature:", device.get_tec_temperature_measured())
        print(" TEC Voltage:", device.get_tec_voltage())
        print(" TEC Current Limit:", device.get_tec_current_limit())
        print(" TEC Current:", device.get_tec_current_measured())
        print(" TEC Error:", device.is_lockstate_tec_error())
        print(" TEC Self-heat:", device.is_lockstate_tec_selfheat())
        if verbose:
            print(" TEC PID:", device.get_tec_pid())
            print(" TEC NTC Coefficient:", device.get_ntc_b25_100_coefficient())
            print(" TEC Raw State:", hex(device.get_raw_status("tec_state")))
            print(" TEC Set Internal:", device.is_tec_set_external())
            print(" TEC Enable Internal:", device.is_tec_enable_external())


        print("LD Overcurrent:", device.is_lockstate_lo_overcurrent())
        print("LD Overheat:", device.is_lockstate_lo_overheat())

