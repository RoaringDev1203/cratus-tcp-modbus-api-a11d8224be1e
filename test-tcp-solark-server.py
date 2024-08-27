# test-tcp-solark-server.py

from pymodbus.server import StartTcpServer
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSparseDataBlock
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext

from pymodbus.client import ModbusSerialClient

from FileTable import FileTable

import logging
FORMAT = ('%(asctime)-15s %(threadName)-15s'
		  ' %(levelname)-8s %(module)-15s:%(lineno)-8s %(message)s')
logging.basicConfig(format=FORMAT)
_logger = logging.getLogger()

_logger.setLevel(logging.DEBUG)


TCP_HOST = "127.0.0.1"  # Standard loopback interface address (localhost)
TCP_PORT = 5020  # TCP port to listen on for Modbus commands

RTU_PORT_NAME = '/dev/ttyUSB0'
SOLARK_MODBUS_SLAVE_ID = 0x01

# ToDo: make a SolArk-specific subclass of ExtendedSparseDataBlock
# SolArk register address space map (from Section 5 of https://docs.google.com/document/d/1aIg44J2IYcBw5pRLY9feluqrQJlwBs51tIyS_aTyJFk/edit )
# 	0 - 59 register addresses are readable register types, 0x 03 function code. 
# 	60 - 499 register address is readable and writable register type, 0x10 function code. 
# 	500 - 2000 register address is readable register type, 0x 03 function code. [ToDo? is 2000 actually included?]
SOLARK_READ_ONLY_LO_MIN = 0
SOLARK_READ_ONLY_LO_MAX = 59
SOLARK_READ_WRITE_MIN = 60
SOLARK_READ_WRITE_MAX = 499
SOLARK_READ_ONLY_HI_MIN = 500
SOLARK_READ_ONLY_HI_MAX = 2000

def countFromMinMax(minAddr, maxAddr):
	return maxAddr - minAddr + 1

# ToDo? what do we need to add  for Section "5.4. 0 3 Deye battery read-only area"?  SolArk doc is unclear, particularly this statement:
# "By analogy, the SN+22 and data registers of 8 registers=30 registers are the second battery pack  information. Subsequent packs follow the same rule"
# It starts at 10000 and the last address in the doc is 10069, but are there more copies of this pattern for "subsequent packs"?
# Putting this in for now... <shrug>
SOLARK_DEYE_BATTERY_MIN = 10000
SOLARK_DEYE_BATTERY_MAX = 10069

# Virtual register address space -- presumably someday these will support more complex software-defined functionality 
VIRTUAL_REGISTER_MIN = 30000
VIRTUAL_REGISTER_MAX = 32000

def isVirtualRegisterAddress(addr):
	return VIRTUAL_REGISTER_MIN <= addr <= VIRTUAL_REGISTER_MAX

def isHoldingRegisterAddress(addr):
	return SOLARK_READ_WRITE_MIN <= addr <= SOLARK_READ_WRITE_MAX

def isInputRegisterAddress(addr):
	return (not isHoldingRegisterAddress(addr)) and (not isVirtualRegisterAddress(addr))

class ExtendedSparseDataBlock(ModbusSparseDataBlock):
	"""A datablock that implements registers in memory, and extends the operations.
	"""

	rtu_client = None

	def __init__(self, values_map, rtu_client):
		"""Initialize."""
		super().__init__(values_map)
		# set up serial Modbus RTU 
		self.rtu_client = rtu_client

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		return

	def setValues(self, address, value):
		"""Set the requested values of the datastore."""
		txt = f">> Entering Extended setValues with address {address}, value {value}"
		_logger.debug(txt)
		# if real rtu and not virtual register address then write to it else write cache
		if (self.rtu_client and not isVirtualRegisterAddress(address)):
			self.rtu_client.write_registers(
				# address=address, 
				# value=value,
				# slave=SOLARK_MODBUS_SLAVE_ID
				address,
				[value],
				SOLARK_MODBUS_SLAVE_ID
				)
		else:
			super().setValues(address, value)
		txt = f"<< Returning from Extended setValues with address {address}, value {value}"
		_logger.debug(txt)
		return 

	def setVirtualValues(self, address, value):
		if (isVirtualRegisterAddress(address)):
			txt = f"Returning from Extended setValues with Virtual address {address}, value {value}"
			_logger.debug(txt)
		
	def getValues(self, address, count=1):
		"""Return the requested values from the datastore."""
		txt = f">> Entering Extended getValues with address {address}, count {count}"
		_logger.debug(txt)
		# if real rtu and not virtual register address then read from it, else read from cache
		if (self.rtu_client and not isVirtualRegisterAddress(address)):
			# ToDo: verify if we should use read_input_registers -- read_holding_registers seems to work fine with the SolArk
#			result = self.rtu_client.read_input_registers(address, count)
			response = self.rtu_client.read_holding_registers(
				address=address, 
				count=count,
				slave=SOLARK_MODBUS_SLAVE_ID
			)
			result = response.registers
		else:
			result = super().getValues(address, count=count)
		txt = f"<< Returning from Extended getValues with address {address}, count {count} with result {result}"
		_logger.debug(txt)
		return result

	def validate(self, address, count=1):
		"""Check to see if the request is in range."""
		result = super().validate(address, count=count)
		txt = f"Returning from Extended validate with address {address}, count {count}, giving result {result}"
		_logger.debug(txt)
		# result = True
		return result


class MappedExtendedDataBlock(ExtendedSparseDataBlock):
	"""An ExtendedSparseDataBlock that implements simple address mapping based on a FileTable
	"""

	file_table = None

	def map_address(self, address):
		component = address//1000
		if (1 == component):	#ie SolArk
			return self.file_table.get_cell(address, "Component Address")
		else:
			return f"No component for address {address}"

	def __init__(self, values_map, rtu_client, file_table):
		"""Initialize."""
		super().__init__(values_map, rtu_client)
		# set up file table
		self.file_table = file_table

	def getValues(self, address, count=1):
		"""Return the requested values from the datastore, mapping the address."""
		return super().getValues(self.map_address(address), count=count)

	def setValues(self, address, value):
		"""Set the requested value, mapping the address."""
		return super().setValues(self.map_address(address), value)

	def validate(self, address, count=1):
		"""Check to see if the requested address is in range."""
		return super().validate(self.map_address(address), count=count)


# create a connected RTU client
def makeRTU(portName):
	txt = f">> Entering makeRTU with port name {portName}"
	_logger.debug(txt)
	client = None
	if (portName):
		client = ModbusSerialClient(
			port=portName,
			method='rtu',
			baudrate=9600,
			stopbits=1,
			bytesize=8,
			parity='N')
		assert client.connect()
	txt = f"<< Exiting Extended init_rtu with RTU client {client}"
	_logger.debug(txt)
	return client


CSV_PATH = "points.csv"

def run_server(rtu_port_name=RTU_PORT_NAME, file_path=CSV_PATH):
	# ToDo put all this in a try block
	rtu_client = makeRTU(rtu_port_name)

	file_table = FileTable()
	file_table.ingest_csv(file_path, "API Address")

	# SolArk does not support any single-bit access, so intentionally not defining anything for "discrete inputs" (aka di) and "coils" (aka co)
	
	# initializing read-only "input registers" (aka ir) with their address
	# solark_ir = ExtendedSparseDataBlock(
	solark_ir = MappedExtendedDataBlock(
										{	SOLARK_READ_ONLY_LO_MIN: 	[x + SOLARK_READ_ONLY_LO_MIN
																			for x in range(countFromMinMax(SOLARK_READ_ONLY_LO_MIN, SOLARK_READ_ONLY_LO_MAX))],
											SOLARK_READ_ONLY_HI_MIN:	[x + SOLARK_READ_ONLY_HI_MIN
																			for x in range(countFromMinMax(SOLARK_READ_ONLY_HI_MIN, SOLARK_READ_ONLY_HI_MAX))] },
										rtu_client,
										file_table
										)

	# initializing read-write "holding registers" (aka hr) with 0's
	# solark_hr = ExtendedSparseDataBlock(
	solark_hr = MappedExtendedDataBlock(
										{	SOLARK_READ_WRITE_MIN:		[0] * countFromMinMax(SOLARK_READ_WRITE_MIN, SOLARK_READ_WRITE_MAX),
											SOLARK_DEYE_BATTERY_MIN:	[0] * countFromMinMax(SOLARK_DEYE_BATTERY_MIN, SOLARK_DEYE_BATTERY_MAX),
											VIRTUAL_REGISTER_MIN:		[0] * countFromMinMax(VIRTUAL_REGISTER_MIN, VIRTUAL_REGISTER_MAX) },
										rtu_client,
										file_table
										)

	store = ModbusSlaveContext(
		ir=solark_ir,
		hr=solark_hr, 
		zero_mode=True)

	context = ModbusServerContext(slaves=store, single=True)
	server = StartTcpServer(context=context, address=(TCP_HOST, TCP_PORT))

	rtu_client.close()	# ToDo: strengthen this


if __name__ == "__main__":
	run_server()
