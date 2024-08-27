import json
import os
from datetime import datetime
from pymodbus.client import ModbusTcpClient
import logging
import psycopg2
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
FORMAT = ('%(asctime)-15s %(threadName)-15s'
          ' %(levelname)-8s %(module)-15s:%(lineno)-8s %(message)s')
logging.basicConfig(format=FORMAT)
log = logging.getLogger()
log.setLevel(logging.INFO)

# Load configuration from config.json
with open('config.json', 'r') as config_file:
    config = json.load(config_file)

# Extract configuration values
modbus_to_key_map = config["modbus_to_key_map"]
device_id = config["device_id"]
asset_id = config["asset_id"]
HOST = os.getenv("MODBUS_HOST")
PORT = int(os.getenv("MODBUS_PORT"))
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# Connect to PostgreSQL
def connect_to_db():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        log.info("Connected to the database successfully")
        return conn
    except psycopg2.OperationalError as e:
        log.error(f"Database connection failed: {e}")
        return None

# Save data to PostgreSQL
def save_to_db(data):
    conn = None
    try:
        conn = connect_to_db()
        cur = conn.cursor()
        insert_query = """
            INSERT INTO modbus_data (timestamp, key, mode, scale, value, unit, device_id, asset_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        cur.executemany(insert_query, data)
        conn.commit()
        cur.close()
    except Exception as error:
        log.error(f"Error: {error}")
    finally:
        if conn is not None:
            conn.close()

def register_to_ascii(register_value):
    high_byte = (register_value >> 8) & 0xFF
    low_byte = register_value & 0xFF
    return chr(high_byte), chr(low_byte)

def register_to_signed_16_integer(register_value):
    if register_value > 0x7FFF:
        register_value -= 0x10000
    return register_value

def main():
    log.info("Connecting to Modbus server")
    client = ModbusTcpClient(HOST, PORT)
    assert client.connect()

    try:
        while True:
            now = datetime.now()
            data_to_save = []

            for address, details in modbus_to_key_map.items():
                if len(details) != 5:
                    log.error(f"Invalid entry for address {address}: {details}")
                    continue

                key, mode, scale, unit, type = details
                log.info(f"Reading register at address {address} for {key}")
                value = read_modbus_register(client, int(address), type, scale)
                if value is not None:
                    data_to_save.append((now, key, mode, scale, value, unit, device_id, asset_id))
                    log.info(f"{key}: {value} {unit}")

            # Save the data to PostgreSQL
            if data_to_save:
                save_to_db(data_to_save)

            # Wait for a specified interval before the next read (e.g., 60 seconds)
            time.sleep(60)

    except KeyboardInterrupt:
        log.info("Stopping program due to keyboard interrupt")

    finally:
        log.info("Closing Modbus connection")
        client.close()

def read_modbus_register(client, address, type, scale):
    try:
        if address >= 0 and address < 60:
            result = client.read_input_registers(address, count=1, unit=1)
            assert not result.isError()
        elif address >= 60 and address < 500:
            result = client.read_holding_registers(address, count=1, unit=1)
            assert not result.isError()
        else:
            result = client.read_input_registers(address, count=1, unit=1)
            assert not result.isError()

        if type == "ASCII":
            high_char, low_char = register_to_ascii(result.registers[0])
            decodingValue = high_char + low_char
        elif type == "boolean":
            decodingValue = "Enabled" if result.registers[0] != 0 else "Disabled"
        elif type == "-":
            decodingValue = result.registers[0] * scale if isinstance(scale, (int, float)) else result.registers[0]
        elif type == "U16":
            decodingValue = result.registers[0]
        elif type == "S16":
            decodingValue = register_to_signed_16_integer(result.registers[0])
        elif type == "hex":
            decodingValue = hex(result.registers[0])
        else:
            raise ValueError(f"Unsupported type: {type}")

        # Handle cases where decodingValue is 65535 or None
        if decodingValue == 65535 or decodingValue is None:
            decodingValue = 0

        return decodingValue

    except Exception as e:
        log.error(f"Error reading register at address {address}: {e}")
        return 0

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s - %(message)s')
    main()
