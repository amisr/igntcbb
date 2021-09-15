#!/usr/bin/env python

##########################################################################
#
#   Read registers on a IG-NTC-BB genset controller
#
#   2018-09-17  Ashton Reimer
#               Initial implementation (based on Todd's shark200 code)
#   2018-09-26  Ashton Reimer
#               Ops ready version
#   2021-09-15  Ashton Reimer
#               Fixed decoding bug
#               Improved 'List#' type decoding
#               Disable validation for 'List#' types
#
#   Description:
#       The read code works in 2 steps: 1) parse a GenConfig file to 
#       determine list of available registers to query, 2) decode
#       the registers using the parsed register mapping
#
##########################################################################

from pymodbus.client.sync import ModbusTcpClient as ModbusClient
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian

import math
import time

from .ParseGenConfig import ParseGenConfig


# For documentation, see IGS-NT-Communication-Guide-11-2017.pdf
# Modbus TCP (page 90):
#    Packet is 6 byte header + Modbus RTU payload = RTU encapsulated in TCP packet, CRC not used.
#    Function Codes:
#        - 3 (Read Multiple Registers)
#        - 6 (Write Single Registers)
#        - 10 (Command)
#        - 16 (Write Multiple Registers)
# Connection timeout is set to 15 seconds
#
# From page 14 of PI_MBUS_300.pdf:
#     The modbus payload is device address + function code + 8-bit data bytes + CRC
#                              (8 bits)        (8 bits)        (N x 8 bits)     (16 bits)
#
# Get the list of registers used and their mapping by following instructions
# on page 98. In summary, use GenConfig software to get mapping.

_TCP_ACCESS = 46339-40000-1

# a class for handling decoding registers
class Register():
    def __init__(self,register,points,description,units,datatype,scaler=None,
                 format=None,value=None,min=None,max=None,typemap=None):

        self.params = {'register':register,
                       'address':register-40000-1,
                       'points':points,
                       'desc':description,
                       'units':units,
                       'datatype':datatype,
                       'value':None,
                       'min':min,
                       'max':max,
                       'scaler':scaler,
                       'format':format,
                      }
        self.typemap = typemap

    def decode(self,data):
        # initialize a decoder
        decoder  = BinaryPayloadDecoder.fromRegisters(data,byteorder=Endian.Big)
        datatype = self.params['datatype']
        length   = self.params['points']

        # use a datatype mapping? If statements are good for now...
        if datatype == 'Integer' and length == 1:
            value = decoder.decode_16bit_int()
        if datatype == 'Integer' and length == 2:
            value = decoder.decode_16bit_int()
        if datatype == 'Integer' and length == 4:
            value = decoder.decode_32bit_int()
        if datatype == 'Unsigned' and length == 1:
            value = decoder.decode_16bit_uint()
        if datatype == 'Unsigned' and length == 2:
            value = decoder.decode_16bit_uint()
        if datatype == 'Unsigned' and length == 4:
            value = decoder.decode_32bit_uint()
        if datatype == 'String0':
            value = decoder.decode_string(length*2) # need 2 because registers are 16 bit but data type is 8 bit
            value = value.strip('\x00')
        if datatype == 'Char':
            value = decoder.decode_string(8)
            value = value.strip('\x00')
        if datatype == 'Binary':
            value = decoder.decode_bits()
        if datatype in ['Time', 'Date']:
            value = [hex(x)[2:].zfill(6) for x in data]

        # Now parse custom types
        if not self.typemap is None:
            decoded = decoder.decode_16bit_uint()

            if 'binary' in datatype:
                binary = bin(decoded)[2:].zfill(16)  # pad in front with 0s to make sure we have 16 bits

                lines = list()
                num_bits = len(self.typemap)
                for i in range(num_bits):
                    lines.append('%s: %s' % (self.typemap[i],binary[-1-i]))
                self.params['value'] = ', '.join(lines)

            if 'list' in datatype:
                key = decoded
                self.params['value'] = '%s: %s' % (key, self.typemap[key])
        else:
            self.params['value'] = value

        if not self.params['scaler'] is None:
            self.params['value'] = self.params['value'] * self.params['scaler']

    # validate the value of the register using min and max values
    def validate(self):
        if self.params['value'] is None:
            return None

        # hack for "List#" datatypes, we don't actually want
        # to validate them
        datatype = self.params['datatype']
        if 'list' in datatype:
            return True

        # for all others, check the min/max values
        if not self.params['min'] is None:
            if self.params['value'] < self.params['min']:
                return False
        if not self.params['max'] is None:
            if self.params['value'] > self.params['max']:
                return False
        return True

    def __str__(self):
        # use the formatter from self.params['format'] for values.
        msg = '%s %s' % (str(self.params['value']),self.params['units'])
        msg = msg.strip('\x00')
        
        return msg


# a class that provides telemetry reading capabilities
class IGNTCModbusReadRegisters(ParseGenConfig):
    def __init__(self,genconfig_file,host,port=502):

        # first parse the genconfig file so we know what registers are
        # available how to parse them.
        ParseGenConfig.__init__(self,genconfig_file)
        register_list = self.registers
        parsed_custom_types = self.custom_types

        custom_types = parsed_custom_types.keys()
        self.registers = dict()
        for parsed_register in register_list:
            register = parsed_register['register']
            comm_obj = parsed_register['comm_obj']
            name     = parsed_register['name']
            units    = parsed_register['units']
            datatype = parsed_register['datatype']
            points   = parsed_register['points']
            decimals = parsed_register['decimals']
            min_val  = parsed_register['min']
            max_val  = parsed_register['max']
            group    = parsed_register['group']

            if decimals is None:
                scalar = None
            else:
                scalar   = 10**(-decimals)

            if not scalar is None:
                if not min_val is None:
                    min_val *= scalar
                if not max_val is None:
                    max_val *= scalar

            typemap = parsed_custom_types.get(datatype,None)

            if not group in self.registers.keys():
                self.registers[group] = list()

            new_reg = Register(register,points,name,units,datatype,
                               scaler=scalar,format=None,value=None,
                               min=min_val,max=max_val,typemap=typemap)

            self.registers[group].append(new_reg)

        self.groups = sorted(self.registers.keys())
        self.register_list = register_list
        self.num_registers = len(register_list)

        self.host = host
        self.port = port

        self.client = ModbusClient(self.host,port=self.port)


    # Read ALL the registers. Only really intended for testing purposes. This will take awhile to run...
    def query_all_parameters(self):

        # read the generator name. Need to read 8 registers:
        # 43001-43008 ( 8) 8637     Gen-set name        String0    16   -      -      - Comms settings
        print("Reading %s registers..." % (self.num_registers))
        print("Reading by group:")
        for group in self.groups:
            print("\n%s\n---------------" % (group))
            group_registers = self.registers[group]
            for register in group_registers:
                data = self.read_registers(self.client,register.params['address'],register.params['points'])
                if data is None:
                    print('!!! Problem reading: %s' % register.params['desc'])
                    continue
                register.decode(data)
                print(' -> %s: %s' % (register.params['desc'],register))


    def query_parameter(self,group,param,verbose=False):

        # find the parameter in the registers in the specified group
        group_registers = self.registers[group]
        param_names = [x.params['desc'] for x in group_registers]
        try:
            ind = param_names.index(param)
        except ValueError:
            if verbose:
                print("Parameter '%s' not found in group '%s'" % (param,group))
            return None

        register = group_registers[ind]

            # read the generator name. Need to read 8 registers:
            # 43001-43008 ( 8) 8637     Gen-set name        String0    16   -      -      - Comms settings

        self.client.connect()            
        data = self.read_registers(self.client,register.params['address'],register.params['points'])
        if data is None:
            if verbose:
                print('!!! Problem reading: %s' % register.params['desc'])
            return None
        
        register.decode(data)
        if verbose:
            print(' -> %s: %s' % (register.params['desc'],register))
        
        self.client.close()

        return register


    def read_registers(self,client,addr,num_registers,max_num_tries=50,verbose=False):
        # client: A pymodbus TCP client (must be connected)
        # addr: register name - 40000 - 1. Get register name from GenConfig
        # num_registers: The number of registers to read from

        unit  = 1

        # jump in to a loop where we ensure the socket is open before attempting
        # to read anything
        num_tries = 1
        client.connect()
        while not client.is_socket_open():
            if num_tries >= max_num_tries:
                if verbose:
                    print("! FAILED TO CONNECT AFTER TRYING %s TIMES !" % (num_tries))
                return None
            time.sleep(0.01)
            client.connect()
            num_tries += 1

        # need to write an access code for TCP access
        data = client.write_register(_TCP_ACCESS,0,unit=unit)
        data = client.read_holding_registers(addr,count=num_registers,unit=unit)

        client.close()

        if data.isError():
            return None
        else:
            return data.registers

