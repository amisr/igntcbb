#!/usr/bin/env python

##########################################################################
#
#   Parse a GenConfig .txt register map of a ComAp IG-NTC-BB genset
#   controller
#
#   2018-09-17  Ashton Reimer
#               Initial implementation
#   2018-09-26  Ashton Reimer
#               Operations ready version
#
#   Description: Provides a ParseGenConfig class that can read a GenConfig
#                file and creates an object with registers and custom
#                types that can be used with pymodbus to read and parse
#                the registers on an IG-NTC-BB controller.
#       
##########################################################################

class ParseGenConfig():
    def __init__(self,filename):
        self.filename = filename

        registers, custom_types = self.parse()

        self.registers = registers
        self.custom_types = custom_types

    def parse(self):

        with open(self.filename,'r') as f:
            contents = f.readlines()


        # Start by reading and parsing all of the registers
        line_num = 2 # skip the registers header
        registers = list()
        while True:
            line = contents[line_num].replace('\r','')
            if line == '\n':
                break

            parsed_register = self.parse_register(line)

            if parsed_register is None:
                parsing_custom_types = False
            else:
                registers.append(parsed_register)

            line_num += 1

        # Some registers have min/max values that are defined by other registers so find and clean that up
        registers = self.reparse_min_max_values(registers)

        # Skip the Register      Protection #2     Protection #1   part of the file for now. Maybe support in future
        line_num += 10  # skip a few lines to jump past the header for the protection registers.

        # Now search for the custom type definitions. Search for '=======' and check for the same on the second line after
        # For example, looking for the following:
        #
        # ======================================================================================
        # List# Types Meaning
        # ======================================================================================
        #
        # And trying to match to the equals signs

        searching_for_equals = True
        while searching_for_equals:
            line1 = contents[line_num].replace('\r','')[0:11]
            line2 = contents[line_num+2].replace('\r','')[0:11]

            if (line1 == '===========') and (line2 == '==========='):
                line_num += 2
                searching_for_equals = False

            line_num += 1


        # Now start parsing the custom types. Use a helper function
        custom_types = dict()
        parsing_custom_types = True
        while parsing_custom_types:
            # look for the next custom type definition
            new_custom_type, new_line_num = self.find_and_parse_type(line_num, contents)
            line_num = new_line_num

            if new_custom_type is None:
                parsing_custom_types = False
            else:
                for key in new_custom_type.keys():
                    custom_types[key] = new_custom_type[key]

        return registers, custom_types


    def parse_register(self, line):
        # Expecting lines like (between the ||):
        #  Register(s)      Com.Obj. Name           Dim  Type       Len Dec   Min    Max Group
        # |40003            8235     BIN                 Binary#1    2   -      -      - Bin inputs CU |
        #  ^               ^        ^              ^    ^          ^   ^  ^      ^      ^
        #  1               17       26             41   46         57  61 64     71     78

        # get values for each field and strip all whitespace
        register  = line[:17].strip()
        comm_obj  = line[17:26].strip()
        name      = line[26:41].strip()
        units     = line[41:46].strip()
        datatype  = line[46:57].strip()
        points    = line[57:61].strip()
        decimals  = line[61:64].strip()
        min_val   = line[64:71].strip()
        max_val   = line[71:78].strip()
        group     = line[78:].strip()

        # convert to expected type/format
        register  = int(register[:5])
        comm_obj  = int(comm_obj)
        if units == '-':
            units = ''
        if '#' in datatype:
            datatype  = datatype.replace('#','').lower()
        points    = int(points)
        if decimals == '-':
            decimals = None
        else:
            decimals = int(decimals)
        if min_val == '-':
            min_val = None
        if max_val == '-':
            max_val = None

        parsed_register = {'register':register,
                           'comm_obj':comm_obj,
                           'name':name,
                           'units':units,
                           'datatype':datatype,
                           'points':points,
                           'decimals':decimals,
                           'min':min_val,
                           'max':max_val,
                           'group':group,
                          }

        return parsed_register

    def reparse_min_max_values(self, registers):
        comm_objs = [x['comm_obj'] for x in registers]

        for register in registers:
            # do maxes
            if not register['max'] is None:
                if '*' in register['max']:
                    comm_2_find = int(register['max'].replace('*',''))
                    try:
                        ind = comm_objs.index(comm_2_find)
                        register['max'] = registers[ind]['max']
                    except ValueError:
                        register['max'] = None
            # do mins
            if not register['min'] is None:
                if '*' in register['min']:
                    comm_2_find = int(register['min'].replace('*',''))
                    try:
                        ind = comm_objs.index(comm_2_find)
                        register['min'] = registers[ind]['min']
                    except ValueError:
                        register['min'] = None

        # Now convert all min/max into integers
        for register in registers:
            if not (register['min'] is None):
                register['min'] = int(register['min'])
            if not (register['max'] is None):
                register['max'] = int(register['max'])

        return registers


    def find_and_parse_type(self, line_num, contents):
        # search for this pattern
        # --------------------------------------------------------------------------------------
        # List#1

        # Value  Name
        # --------------------------------------------------------------------------------------------
        #
        # and also "Bit  Name" instead of "Value Name"
        #
        # Could use regular expressions to match things, for now just loop.

        parsed_type = dict()
        valid_headers = ['Bit  Name','Value  Name']
        while True:
            # check for end of custom type definitions
            end_line = contents[line_num].replace('\r\n','')
            if end_line == 'Table# Types Meaning':
                return None, line_num

            # if not, find the type name and value map
            line1 = contents[line_num].replace('\r','')[0:11]
            line2 = contents[line_num+3].replace('\r\n','')
            line3 = contents[line_num+4].replace('\r','')[0:11]

            if (line1 == '-----------') and (line2 in valid_headers) and (line3 == '-----------'):
                start_parsing_line_num = line_num + 5
                type_name = contents[line_num+1].replace('\r\n','')
                type_name = type_name.replace('#','').lower()
                break

            line_num += 1

        # There's a different number of spaces for binary bit/name lines
        if 'binary' in type_name:
            line_split_ind = 4
        else:
            line_split_ind = 6

        # ending lines aren't always consistent, but are one of these
        end_parse_match = ['\r\n','--------------------------------------------------------------------------------------\r\n']

        line_num = start_parsing_line_num
        value_map = dict()
        while True:
            line = contents[line_num]
            if line in end_parse_match:
                break

            line = line.replace('\r\n','')
            value = int(line[0:line_split_ind].strip())
            name = line[line_split_ind:].strip()
            value_map[value] = name

            line_num += 1

        parsed_type[type_name] = value_map

        return parsed_type, line_num


if __name__ == '__main__':
    from pprint import pprint
    from datetime import datetime
    st = datetime.now()
    genconfig_file = 'test/example_registers.txt'
    pgc = ParseGenConfig(genconfig_file)
    registers, custom_types = pgc.registers, pgc.custom_types
    et = datetime.now()
    pprint(registers)
    pprint(custom_types)

    print((et-st).total_seconds())