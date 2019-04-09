# IG-NTC-BB #
A package for polling and parsing the registers of a [ComAp IG-NTC-BB Genset Controller](https://www.comap-control.com/products/detail/inteligen-ntc-basebox)
### Installation ###

Clone this repo and install using:

    pip install .

from the root directory of the repository.

### Usage ###

Currently, the only way to use this software is via a python shell. Before you can use this software, you need to obtain a GenConfig register map file. This is obtained using the ComAp Genconfig software and:

1) Connecting to an IG-NTC-BB controller,
2) Exporting the "Cfg Image" via File->Generate Cfg Image->Generate Cfg Image (Modbus Registers - used)...

which will create a `.txt` file. Finally, ***one must remove all of the "degree" symbols*** from any of the units in the file.

#### Python Shell ####
Generally, you will never do this, but to use the `ParseGenConfig` class:

    from igntcbb import ParseGenConfig
    genconfig_file = 'file_from_genconfig_export.txt'
    pgc = ParseGenConfig(genconfig_file)
    # now you have access to all of the registers and custom types via:
    registers = pgc.registers
    custom_types = pgc.custom_types

Instead, you will likely be wanting to use the `IGNTCModbusReadRegisters` class


    from igntcbb import IGNTCModbusReadRegisters
    genconfig_file = 'file_from_genconfig_export.txt'
    host = 'ip address of host'
    port = 502  # this is the default value
    igntc = IGNTCModbusReadRegisters(genconfig,host,port=port)
    # let's query 1 register from the "Info" group
    register = igntc.query_parameter('Info','SW version')
    # result is a "register" object. All information that we want is in a .params attribute:
    print(register.params)
    # specifically, you will be interested in
    print(register.params['value'])
    print(register.params['units'])
