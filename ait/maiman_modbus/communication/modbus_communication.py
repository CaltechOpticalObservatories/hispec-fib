import minimalmodbus
import serial

class ModbusCommunication:
    """Handles MODBUS RTU communication for devices over RS-485."""

    def __init__(self, port: str, slave_address: int = 100, baudrate: int = 115200, timeout: float = 1.0):
        self.instrument = minimalmodbus.Instrument(port, slave_address)
        self.instrument.serial.baudrate = baudrate
        self.instrument.serial.bytesize = 8
        self.instrument.serial.parity = serial.PARITY_NONE
        self.instrument.serial.stopbits = 1
        self.instrument.serial.timeout = timeout
        self.instrument.mode = minimalmodbus.MODE_RTU
        self.connected = False

    def connect(self):
        """Open the serial connection."""
        if not self.instrument.serial.is_open:
            try:
                self.instrument.serial.open()
                self.connected = True
            except serial.SerialException as e:
                raise ConnectionError(f"Failed to connect: {e}")

    def is_connected(self) -> bool:
        """Check if the serial port is open."""
        return self.instrument.serial.is_open

    def disconnect(self):
        """Close the serial connection."""
        if self.instrument.serial.is_open:
            self.instrument.serial.close()
            self.connected = False

    def send_command(self, register: int, value: int):
        """Write a single value to a register."""
        try:
            self.instrument.write_register(register, value)
        except Exception as e:
            raise IOError(f"MODBUS write error: {e}")

    def receive_response(self, register: int, signed: bool = False) -> int | None:
        """Read a single value from a register."""
        try:
            return self.instrument.read_register(register, signed=signed)
        except Exception as e:
            raise IOError(f"MODBUS read error: {e}")

    def send_multiple_registers(self, register: int, values: list[int]):
        """Write multiple values to consecutive registers."""
        try:
            self.instrument.write_registers(register, values)
        except Exception as e:
            raise IOError(f"MODBUS multi-write error: {e}")

    def receive_multiple_registers(self, register: int, count: int, signed: bool = False) -> list[int]:
        """Read multiple consecutive registers."""
        try:
            return self.instrument.read_registers(register, count, signed=signed)
        except Exception as e:
            raise IOError(f"MODBUS multi-read error: {e}")

    def flush_input(self):
        """Flush input buffer."""
        if self.instrument.serial.is_open:
            self.instrument.serial.reset_input_buffer()

    def flush_output(self):
        """Flush output buffer."""
        if self.instrument.serial.is_open:
            self.instrument.serial.reset_output_buffer()

if __name__ == "__main__":
    port_name = "COM6"     
    slave_address = 1       
    modbus = ModbusCommunication(port=port_name, slave_address=2)

    try:
        modbus.connect()
        print("Connection successful!")

        # Test: Read register (e.g., TEC temperature register)
        temp_register = 0x0075
        raw_value = modbus.receive_response(temp_register)
        temperature = raw_value / 100
        print(f"Temperature: {temperature:.2f} °C")

        # Test: Write register (e.g., current limit)
        current_limit_register = 0x0007
        value_to_write = int(10.0 * 10)
        modbus.send_command(current_limit_register, value_to_write)
        print(f"Set current limit to {value_to_write / 10} A")

        # Verify write
        read_back = modbus.receive_response(current_limit_register) / 10
        print(f"Current Limit Read Back: {read_back:.1f} A")

    except Exception as e:
        print(f"Modbus test failed: {e}")

    finally:
        modbus.disconnect()
        print("Disconnected.")
