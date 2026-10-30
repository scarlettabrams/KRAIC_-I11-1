import serial
import serial.tools.list_ports

ports = serial.tools.list_ports.comports()

for port in ports:
    print(f"Serial Port: {port.serial_number}")
    print(f"Name: {port.name}")
    print(f"Description: {port.description}")
    print(f"hwid: {port.hwid}")
    print(f"vid: {port.vid}")
    print(f"pid: {port.pid}")
    print(f"location: {port.location}")
    print(f"Manufacturer: {port.manufacturer}")
    print(f"Product: {port.product}")
    print(f"Interface: {port.interface}")
    print(f"These are the results for {port.name}\n\n")
    print("-" * 50)
