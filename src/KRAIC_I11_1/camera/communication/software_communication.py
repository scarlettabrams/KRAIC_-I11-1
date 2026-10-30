import logging
import threading
import time

import serial
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ConnectionException, ModbusException, ModbusIOException

from KRAIC_I11_1.camera.helper.helper import (
    load_json,
)


class PyConnection:
    """Generic Serial Connection Class for Lab Equipment using Pyserial"""

    def __init__(self, device_type, conn_settings, timeout=1):
        """Initialise all the attributes"""

        connection = load_json(conn_settings)

        self.device_type = device_type
        self.timeout = timeout
        self.lock = threading.Lock()

        self.config = connection["CONNECTION_SETTINGS"].get(device_type)
        if not self.config:
            raise ValueError(
                "No connection configuration settings found for device type: "
                f"'{device_type}'."
            )

        self.method = self.config.get("comm_method")
        if not self.method:
            raise ValueError(
                f"Communication protocol not specified for: '{device_type}'."
            )

        try:
            if self.method == "serial":
                self._init_serial()
            elif self.method == "modbus":
                self._init_modbus()
            else:
                raise ValueError(f"Unsupported communication method: {self.method}")
            time.sleep(self.config.get("startup_delay", 2))
        except (
            serial.SerialException,
            ConnectionException,
            ModbusIOException,
            ModbusException,
        ) as e:
            logging.warning(f"[{self.device_type}] Connection attempt failed: {e}")
            time.sleep(1)
            raise ConnectionError(
                f"Failed to establish {self.method} connection"
            ) from e

    def _init_serial(self):
        """Initialize PySerial connection"""
        self.ser_s = serial.Serial(
            port=self.config.get("port", None),
            baudrate=self.config.get("baudrate", 9600),
            timeout=self.timeout,
            bytesize=getattr(serial, self.config.get("bytesize", "EIGHTBITS")),
            parity=getattr(serial, self.config.get("parity", "PARITY_NONE")),
            stopbits=getattr(serial, self.config.get("stopbits", "STOPBITS_ONE")),
            xonxoff=self.config.get("xonxoff", False),
        )

    def _init_modbus(self):
        """Initialize Modbus RTU connection via pymodbus"""
        self.ser_m = ModbusSerialClient(
            port=self.config.get("port", None),
            baudrate=self.config.get("baudrate", 9600),
            stopbits=self.config.get("stopbits", 1),
            bytesize=self.config.get("bytesize", 8),
            parity=self.config.get("parity", "N"),
            timeout=self.config.get("timeout", 1),
            # remove 'method' parameter as it's invalid in pymodbus 3.x
        )

        if not self.ser_m.connect():
            raise ConnectionException(
                f"Unable to connect to Modbus device on port {self.config.get('port')}"
            )

    def __enter__(self):
        """Support use with 'with' statement"""
        if self.method == "serial":
            if not self.ser_s.is_open:
                self.ser_s.open()
        elif self.method == "modbus":
            if not self.ser_m.connected:
                self.ser_m.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensure proper cleanup"""
        if self.method == "serial" and getattr(self, "ser_s", None):
            if self.ser_s.is_open:
                self.ser_s.close()
                logging.info(f"[{self.device_type}] Serial connection closed.")
        elif self.method == "modbus" and getattr(self, "ser_m", None):
            if self.ser_m.connected:
                self.ser_m.close()
                logging.info(f"[{self.device_type}] Modbus connection closed.")

    def send_serial(self, command, number="0"):
        """Send a command to a serial device"""
        if self.method != "serial":
            raise RuntimeError("send_serial() only valid for serial devices.")
        if not self.ser_s.is_open:
            raise ConnectionError("Serial port is not open.")

        try:
            with self.lock:
                self.ser_s.reset_input_buffer()
                self.ser_s.write((command + "\r\n").encode())

                response = self.ser_s.readline().decode(errors="ignore").strip()
            return response
        except serial.SerialException as e:
            logging.error(f"[{self.device_type}] Serial write failed: {e}")
            return None
        except Exception as e:
            logging.error(f"[{self.device_type}] Unexpected error: {e}")
            return None

    def read_holding_registers(self, address, count, slave):
        """Read registers from Modbus slave"""
        if self.method != "modbus":
            raise RuntimeError(
                "read_holding_registers() only valid for Modbus devices."
            )
        if not self.ser_m.connected:
            self.ser_m.connect()

        try:
            with self.lock:
                # slave ID as 3rd positional argument (no unit= keyword)

                response = self.ser_m.read_holding_registers(
                    address=address, count=count, device_id=slave
                )
                if response.isError():
                    raise ModbusException(
                        f"Modbus error reading from slave {slave} at address {address}"
                    )
            return response
        except (ConnectionException, ModbusIOException, ModbusException) as e:
            logging.error(f"[{self.device_type}] Modbus read failed: {e}")
            return None

    def write_register(self, address, value, slave):
        """Write a holding register on Modbus slave"""
        if self.method != "modbus":
            raise RuntimeError("write_register() only valid for Modbus devices.")
        if not self.ser_m.connected:
            self.ser_m.connect()

        try:
            with self.lock:
                # slave ID as 3rd positional argument (no unit= keyword)
                response = self.ser_m.write_register(
                    address=address, value=value, device_id=slave
                )
                if response.isError():
                    raise ModbusException(
                        f"Modbus error writing to slave {slave} at address {address}"
                    )
            return response
        except (ConnectionException, ModbusIOException, ModbusException) as e:
            logging.error(f"[{self.device_type}] Modbus write failed: {e}")
            return None
