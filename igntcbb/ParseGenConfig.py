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
#   2021-09-14  Ashton Reimer
#               Updating documentation
#
#   Description: Provides a ParseGenConfig class that can read a GenConfig
#                file and creates an object with registers and custom
#                types that can be used with pymodbus to read and parse
#                the registers on an IG-NTC-BB controller.
#       
##########################################################################

class ParseGenConfig():
    """A class for polling and parsing the registers of a ComAp IG-NTC-BB
    Genset Controller via Modbus TCP.

    Attributes
    ==========
    filename : string
        The path to a text file containing register information. The text file
        is produced using ComAp's GenConfig software.
    registers : list
        A list of dictionaries, where each dictionary defines a register parsed
        from the genset config file. Each dictionary has the following keys:
        'register', 'comm_obj', 'name', 'units', 'datatype', 'points',
        'decimals', 'min', 'max', 'group'.
    custom_types : list
        A list of dictionaries, where each dictionary defines a custom type
        that was parsed from the genset config file. Each dictionary contains
        a type map, which maps register values to whatever the type requires.

    Examples
    ========
    ::

        genconfig_file = 'file_from_genconfig_export.txt'
        pgc = ParseGenConfig(genconfig_file)
        # now you have access to all of the registers and custom types via:
        registers = pgc.registers
        custom_types = pgc.custom_types

    """
    def __init__(self,filename):
        self.filename = filename

        # parse the genset register map text file
        registers, custom_types = self.parse()

        self.registers = registers
        self.custom_types = custom_types


    def parse(self):
        """Read and parse the genset register map file.

        Returns
        =======
            registers : list
                A list of dictionaries, where each dictionary defines a
                register parsed from the genset config file. Each dictionary
                has the following keys: 'register', 'comm_obj', 'name',
                'units', 'datatype', 'points', 'decimals', 'min', 'max',
                'group'.
            custom_types : list
                A list of dictionaries, where each dictionary defines a custom
                type that was parsed from the genset config file. Each
                dictionary contains a type map, which maps register values to
                whatever the type requires.

        """
        with open(self.filename,'r') as f:
            contents = f.readlines()

        # start by reading and parsing all of the registers and creating a
        # list of all these registers
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

        # some registers have min/max values that are defined by other
        # registers so find and clean that up
        registers = self.reparse_min_max_values(registers)

        # skip the Register      Protection #2     Protection #1   part of the
        # file for now, maybe support in future
        line_num += 10  # skip a few lines to jump past the header for the
                        # protection registers.

        # now search for the custom type definitions, search for '=======' and
        # check for the same on the second line after
        # for example, looking for the following:
        #
        # ======================================================================================
        # List# Types Meaning
        # ======================================================================================
        #
        # and trying to match to the equals signs

        searching_for_equals = True
        while searching_for_equals:
            line1 = contents[line_num].replace('\r','')[0:11]
            line2 = contents[line_num+2].replace('\r','')[0:11]

            if (line1 == '===========') and (line2 == '==========='):
                line_num += 2
                searching_for_equals = False

            line_num += 1


        # now start parsing the custom type using a helper function
        custom_types = dict()
        parsing_custom_types = True
        while parsing_custom_types:
            new_custom_type, new_line_num = self.find_and_parse_type(line_num, contents)
            line_num = new_line_num

            if new_custom_type is None:
                parsing_custom_types = False
            else:
                for key in new_custom_type.keys():
                    custom_types[key] = new_custom_type[key]

        return registers, custom_types


    def parse_register(self, line):
        """A helper function for parsing register parameters from a line of the
        genset register map file.

        Parameters
        ==========
        line : string
            A line of text from a genset register map file.

        Returns
        =======
            parsed_register : dict
                A dictionary with the following keys: 'register', 'comm_obj',
                'name', 'units', 'datatype', 'points', 'decimals', 'min',
                'max', 'group'.

        """
        # given a line like so (the content between the | and |):
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
        """A helper function for reparsing the min/max values for registers.
        Some of the registers min/max values depend on other registers. This
        function just uses the min or max value of the other register, but
        ideally, it should use the value of that register instead.

        Parameters
        ==========
        registers : list
            A list of dictionaries of parsed registers.

        Returns
        =======
        registers : dict
            A list of dictionaries of parsed registers.

        """
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
        """A helper function for reparsing the min/max values for registers.
        Some of the registers min/max values depend on other registers. This
        function just uses the min or max value of the other register, but
        ideally, it should use the value of that register instead.

        Parameters
        ==========
        line_num : integer

        contents : list

        registers : list
            A list of dictionaries of parsed registers.

        Returns
        =======
        registers : dict
            A list of dictionaries of parsed registers.

        """
        # search for this pattern
        # --------------------------------------------------------------------------------------
        # List#1
        #
        # Value  Name
        # --------------------------------------------------------------------------------------------
        #
        # and also "Bit  Name" instead of "Value Name"
        #
        # we could use regular expressions to match things, but the following
        # works just fine

        parsed_type = dict()
        valid_headers = ['Bit  Name','Value  Name']
        while True:
            # loop until we hit the end of the custom type definitions
            end_line = contents[line_num].replace('\r\n','')
            if end_line == 'Table# Types Meaning':
                return None, line_num

            # if not at the end, find the type name and value map
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

        # build a value map that maps register values to the custom type
        # defined values
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