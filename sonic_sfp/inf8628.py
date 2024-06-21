#----------------------------------------------------------------------------
# QSFP-DD 8X Transceiver (QSFP Double Density)
#----------------------------------------------------------------------------

from __future__ import print_function

try:
    from .sff8024 import type_of_transceiver    # Dot module supports both Python 2 and Python 3 using explicit relative import methods
    from .sff8024 import type_abbrv_name    # Dot module supports both Python 2 and Python 3 using explicit relative import methods
    from .sff8024 import type_of_media_interface
    from .sff8024 import power_class_of_transceiver
    from .sffbase import sffbase    # Dot module supports both Python 2 and Python 3 using explicit relative import methods
    from .qsfp_dd import qsfp_dd_InterfaceId
    from .qsfp_dd import qsfp_dd_Dom
except ImportError as e:
    raise ImportError ("%s - required module not found" % e)

class inf8628InterfaceId(sffbase):

    def decode_application_advertisement(self, eeprom_data, offset, size):
        ret = {}
        tbl = self.qsfp_dd.parse_media_type(eeprom_data, offset)
        if tbl is None:
            return
        app = 1
        hid = int(eeprom_data[1 + offset], 16)
        while (app <= 8) and (hid != 0) and (hid != 0xff):
            (ht, mt) = self.qsfp_dd.parse_application(tbl, eeprom_data[1 + offset], eeprom_data[2 + offset])
            ret[app] = { 'host_if': ht, 'media_if': mt }
            app += 1
            offset += 4
            hid = int(eeprom_data[1 + offset], 16)
        return str(ret)

    def decode_cable_assembly_length(self, eeprom_data, offset, size):
        return self.qsfp_dd.decode_cable_len(eeprom_data, offset, size)

    def decode_fiber_length_smf(self, eeprom_data, offset, size):
        mult_dict = { 0: 0.1, 1: 1, 2: 0, 3: 0 }
        byte = int(eeprom_data[offset], 16)
        mult = (byte >> 6) & 0x03
        base = byte & 0x3f
        len = base * mult_dict[mult]
        return len

    def decode_upper_memory_type(self, eeprom_data, offset, size):
        val = int(eeprom_data[offset], 16)
        return "Flat" if val & 0x80 else "Paged"

    def decode_implemented_memory_pages(self, eeprom_data, offset, size):
        ret = []
        val = int(eeprom_data[offset], 16)
        if (val & 0x40) > 0:
            ret.append('Versatile Diagnostic Monitoring')
        if (val & 0x20) > 0:
            ret.append('Diagnostic Pages Implemented')
        if (val & 0x04) > 0:
            ret.append('Page 03h Implemented')
        bank = val & 0x03
        if (bank == 0):
            ret.append('Bank 0 Implemented')
        elif (bank == 1):
            ret.append('Bank 0,1 Implemented')
        elif (bank == 2):
            ret.append('Bank 0,1,2,3 Implemented')
        return str(ret)

    def decode_revision_compliance(self, eeprom_data, offset, size):
        return '%c.%c' % (eeprom_data[offset][0], eeprom_data[offset][1])

    def decode_power_class(self, eeprom_data, offset, size):
        val = (int(eeprom_data[offset], 16) >> 5) & 0x07
        raw = "{0:0{1}x}".format(val, 2)
        return power_class_of_transceiver[raw]

    def decode_module_state(self, eeprom_data, offset, size):
        module_state_byte = eeprom_data[offset]
        module_state = int(module_state_byte, 16) & 14
        if module_state == 2:
            return 'Low Power State'
        elif module_state == 4:
            return 'Power Up State'
        elif module_state == 6:
            return 'Ready State'
        elif module_state == 8:
            return 'Power Down State'
        elif module_state == 10:
            return 'Fault State'
        return 'Unknown State %s' % module_state

    def decode_type_abbrv_name(self, eeprom_data, offset, size):
        """
        Routine to decode Module abbreviation name by reading EEPROM contents
        """
        media_type = int(eeprom_data[offset], 16)
        ret_val = 'Unknown'  # SFF-8024 type_abbrv_name[0] dict value
        if media_type == 0x1e:
            # CMIS Compliant media. Check for QSFP56 type and return
            # QSFP56 as Module Type
            qsfp56_eeprom_identifiers = [
                (0x01, 0x0F, 0x0E, 0x44, 0x01),  #200G QSFP56 SR4
		(0x02, 0x0F, 0x18, 0x44, 0x01)   #200G QSFP56 FR4
                ]

            byte85 = int(eeprom_data[85], 16)
            byte86 = int(eeprom_data[86], 16)
            byte87 = int(eeprom_data[87], 16)
            byte88 = int(eeprom_data[88], 16)
            byte89 = int(eeprom_data[89], 16)
            eeprom_data = (byte85, byte86, byte87, byte88, byte89)
            if eeprom_data in qsfp56_eeprom_identifiers:
                ret_val = 'QSFP56'
        else:
            ret_val = type_abbrv_name[str(eeprom_data[offset])]
        return ret_val

    version = '1.0'

    interface_id = {
            'Identifier':
                {'offset': 128,
                 'size': 1,
                 'type': 'enum',
                 'decode': type_of_transceiver},
            'type_abbrv_name':
                {'offset': 128,
                 'size':1,
                 'type' : 'func',
                 'decode' : {'func': decode_type_abbrv_name}},
            'Revision Compliance':
                {'offset': 1,
                 'type': 'func',
                 'decode': {'func': decode_revision_compliance}},
            'Upper Memory Type':
                {'offset':2,
                 'size':1,
                 'type' : 'func',
                 'decode': {'func': decode_upper_memory_type}},
            'Module State':
                {'offset': 3,
                 'type': 'func',
                 'decode': {'func': decode_module_state}},
            'Interrupt Asserted':
                {'offset': 3,
                 'bit': 0,
                 'type': 'bitvalue'},
            'Media Type':
                {'offset': 85,
                 'size': 1,
                 'type': 'enum',
                 'decode': type_of_media_interface},
            'Application Advertisement':
                {'offset': 85,
                 'type': 'func',
                 'decode': {'func': decode_application_advertisement}},
            'Vendor Name':
                {'offset': 129,
                 'size': 16,
                 'type': 'str'},
            'Vendor OUI':
                {'offset': 145,
                 'size'  : 3,
                 'type'  : 'hex'},
            'Vendor Part Number':
                {'offset': 148,
                 'size': 16,
                 'type': 'str'},
            'Vendor Revision':
                {'offset': 164,
                 'size': 2,
                 'type': 'str'},
            'Vendor Serial Number':
                {'offset': 166,
                 'size': 16,
                 'type': 'str'},
            'Vendor Date Code(YYYY-MM-DD Lot)':
                {'offset': 182,
                 'size'  : 8,
                 'type'  : 'date'},
            'Power Class':
                {'offset': 200,
                 'type': 'func',
                 'decode': {'func': decode_power_class}},
            'Length Cable Assembly(m)':
                {'offset': 202,
                 'type': 'func',
                 'decode': {'func': decode_cable_assembly_length}},
            'Length SMF(km)':
                {'offset': (132 & 0x7f) | 256,
                 'type': 'func',
                 'decode': {'func': decode_fiber_length_smf}},
            'Length OM5(2m)':
                {'offset': (133 & 0x7f) | 256,
                 'size': 1,
                 'type': 'int'},
            'Length OM4(2m)':
                {'offset': (134 & 0x7f) | 256,
                 'size': 1,
                 'type': 'int'},
            'Length OM3(2m)':
                {'offset': (135 & 0x7f) | 256,
                 'size': 1,
                 'type': 'int'},
            'Length OM2(m)':
                {'offset': (136 & 0x7f) | 256,
                 'size': 1,
                 'type': 'int'}
            }

    sfp_type = {
        'type':
            {'offset': 0,
             'size': 1,
             'type': 'enum',
             'decode': type_of_transceiver}
        }

    sfp_type_abbrv_name = {
        'type_abbrv_name':
            {'offset': 0,
             'size': 1,
             'type': 'enum',
             'decode': type_abbrv_name}
        }

    vendor_name = {
        'Vendor Name':
            {'offset': 0,
             'size': 16,
             'type': 'str'}
        }

    vendor_pn = {
        'Vendor PN':
            {'offset': 0,
             'size': 16,
             'type': 'str'}
        }

    vendor_rev = {
        'Vendor Rev':
            {'offset': 0,
             'size': 2,
             'type': 'str'}
        }

    vendor_sn = {
        'Vendor SN':
            {'offset': 0,
             'size': 16,
             'type': 'str'}
        }

    impl_mem_pages = {
        'Implemented Memory Pages':
            {'offset': 0,
             'type': 'func',
             'decode': {'func': decode_implemented_memory_pages}},
        }

    module_state = {
        'Module State':
            {'offset': 0,
             'type': 'func',
             'decode': {'func': decode_module_state}},
        }

    def __init__(self, eeprom_raw_data=None):
        self.qsfp_dd = qsfp_dd_InterfaceId()
        self.interface_data = None
        start_pos = 0

        if eeprom_raw_data is not None:
            self.interface_data = sffbase.parse(self,
                            self.interface_id,
                            eeprom_raw_data,
                            start_pos)

    def parse(self, eeprom_raw_data, start_pos):
        return sffbase.parse(self, self.interface_id, eeprom_raw_data, start_pos)

    def parse_sfp_type(self, type_raw_data, start_pos):
        return sffbase.parse(self, self.sfp_type, type_raw_data, start_pos)

    def parse_sfp_type_abbrv_name(self, type_raw_data, start_pos):
        return sffbase.parse(self, self.sfp_type_abbrv_name, type_raw_data, start_pos)

    def parse_vendor_name(self, name_raw_data, start_pos):
        return sffbase.parse(self, self.vendor_name, name_raw_data, start_pos)

    def parse_vendor_rev(self, rev_raw_data, start_pos):
        return sffbase.parse(self, self.vendor_rev, rev_raw_data, start_pos)

    def parse_vendor_pn(self, pn_raw_data, start_pos):
        return sffbase.parse(self, self.vendor_pn, pn_raw_data, start_pos)

    def parse_vendor_sn(self, sn_raw_data, start_pos):
        return sffbase.parse(self, self.vendor_sn, sn_raw_data, start_pos)

    def parse_implemented_memory_pages(self, raw_data, start_pos):
        return sffbase.parse(self, self.impl_mem_pages, raw_data, start_pos)

    def parse_module_state(self, sn_raw_data, start_pos):
        return sffbase.parse(self, self.module_state, sn_raw_data, start_pos)

    def dump_pretty(self):
        if self.interface_data is None:
            print('Object not initialized, nothing to print')
            return
        sffbase.dump_pretty(self, self.interface_data)

    def get_calibration_type(self):
        return self.calibration_type

    def get_data(self):
        return self.interface_data

    def get_data_pretty(self):
        return sffbase.get_data_pretty(self, self.interface_data)

class inf8628Dom(sffbase):

    version = '1.0'

    def calc_temperature(self, eeprom_data, offset, size):
        return self.qsfp_dd.calc_temperature(eeprom_data, offset, size)

    def calc_voltage(self, eeprom_data, offset, size):
        return self.qsfp_dd.calc_voltage(eeprom_data, offset, size)

    def calc_bias(self, eeprom_data, offset, size):
        return self.qsfp_dd.calc_bias(eeprom_data, offset, size)

    def calc_power(self, eeprom_data, offset, size):
        return self.qsfp_dd.calc_rx_power(eeprom_data, offset, size)

    dom_id = {
            'Temperature':
                {'offset': 14,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_temperature}},
            'Vcc':
                {'offset': 16,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_voltage}},
            'TX1Power':
                {'offset': (154 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_power}},
            'TX2Power':
                {'offset': (156 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_power}},
            'TX3Power':
                {'offset': (158 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_power}},
            'TX4Power':
                {'offset': (160 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_power}},
            'TX5Power':
                {'offset': (162 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_power}},
            'TX6Power':
                {'offset': (164 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_power}},
            'TX7Power':
                {'offset': (166 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_power}},
            'TX8Power':
                {'offset': (168 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_power}},
            'TX1Bias':
                {'offset': (170 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_bias}},
            'TX2Bias':
                {'offset': (172 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_bias}},
            'TX3Bias':
                {'offset': (174 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_bias}},
            'TX4Bias':
                {'offset': (176 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_bias}},
            'TX5Bias':
                {'offset': (178 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_bias}},
            'TX6Bias':
                {'offset': (180 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_bias}},
            'TX7Bias':
                {'offset': (182 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_bias}},
            'TX8Bias':
                {'offset': (184 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_bias}},
            'RX1Power':
                {'offset': (186 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_power}},
            'RX2Power':
                {'offset': (188 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_power}},
            'RX3Power':
                {'offset': (190 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_power}},
            'RX4Power':
                {'offset': (192 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_power}},
            'RX5Power':
                {'offset': (194 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_power}},
            'RX6Power':
                {'offset': (196 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_power}},
            'RX7Power':
                {'offset': (198 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_power}},
            'RX8Power':
                {'offset': (200 & 0x7f) + 0x900,
                 'size': 2,
                 'type': 'func',
                 'decode': {'func': calc_power}},
    }

    dom_module_threshold_values = {
        'TempHighAlarm':
             {'offset':0,
              'size':2,
              'type': 'func',
              'decode': { 'func':calc_temperature}},
        'TempLowAlarm':
             {'offset':2,
              'size':2,
              'type': 'func',
              'decode': { 'func':calc_temperature}},
        'TempHighWarning':
              {'offset':4,
              'size':2,
              'type': 'func',
              'decode': { 'func':calc_temperature}},
        'TempLowWarning':
             {'offset':6,
              'size':2,
              'type': 'func',
              'decode': { 'func':calc_temperature}},
        'VccHighAlarm':
             {'offset':8,
              'size':2,
              'type': 'func',
              'decode': { 'func':calc_voltage}},
        'VccLowAlarm':
             {'offset':10,
              'size':2,
              'type': 'func',
              'decode': { 'func':calc_voltage}},
        'VccHighWarning':
             {'offset':12,
              'size':2,
              'type': 'func',
              'decode': { 'func':calc_voltage}},
        'VccLowWarning':
             {'offset':14,
              'size':2,
              'type': 'func',
              'decode': { 'func':calc_voltage}}}

    dom_channel_threshold_values = {
        'TxPowerHighAlarm':
             {'offset':0,
              'size':2,
              'type': 'func',
              'decode': { 'func':calc_power}},
        'TxPowerLowAlarm':
             {'offset':2,
              'size':2,
              'type': 'func',
              'decode': { 'func':calc_power}},
        'TxPowerHighWarning':
             {'offset':4,
              'size':2,
              'type': 'func',
              'decode': { 'func':calc_power}},
        'TxPowerLowWarning':
             {'offset':6,
              'size':2,
              'type': 'func',
              'decode': { 'func':calc_power}},
        'TxBiasHighAlarm':
             {'offset':8,
              'size':2,
              'type': 'func',
              'decode': { 'func':calc_bias}},
        'TxBiasLowAlarm':
             {'offset':10,
              'size':2,
              'type': 'func',
              'decode': { 'func':calc_bias}},
        'TxBiasHighWarning':
             {'offset':12,
              'size':2,
              'type': 'func',
              'decode': { 'func':calc_bias}},
        'TxBiasLowWarning':
             {'offset':14,
              'size':2,
              'type': 'func',
              'decode': { 'func':calc_bias}},
        'RxPowerHighAlarm':
             {'offset':16,
              'size':2,
              'type': 'func',
              'decode': { 'func':calc_power}},
        'RxPowerLowAlarm':
             {'offset':18,
              'size':2,
              'type': 'func',
              'decode': { 'func':calc_power}},
        'RxPowerHighWarning':
             {'offset':20,
              'size':2,
              'type': 'func',
              'decode': { 'func':calc_power}},
        'RxPowerLowWarning':
             {'offset':22,
              'size':2,
              'type': 'func',
              'decode': { 'func':calc_power}}}

    dom_threshold_map = {
        'ModuleThresholdValues':
             {'offset': 0,
              'size': 48,
              'type': 'nested',
              'decode': dom_module_threshold_values},
        'ChannelThresholdValues':
             {'offset': 48,
              'size': 24,
              'type': 'nested',
              'decode': dom_channel_threshold_values}}

    def __init__(self, eeprom_raw_data=None):
        self.qsfp_dd = qsfp_dd_Dom()
        if eeprom_raw_data is not None:
            self.dom_data = sffbase.parse(self,
                                          self.dom_id,
                                          eeprom_raw_data,
                                          0)

    def get_data_pretty(self):
        return sffbase.get_data_pretty(self, self.dom_data)

    def parse_module_threshold_values(self, eeprom_raw_data, start_pos):
        return sffbase.parse(self, self.dom_module_threshold_values, eeprom_raw_data,
                    start_pos)

    def parse_channel_threshold_values(self, eeprom_raw_data, start_pos):
        return sffbase.parse(self, self.dom_channel_threshold_values, eeprom_raw_data,
                    start_pos)

class inf8628Diag(sffbase):

    version = '1.0'

    def calc_ber(self, eeprom_data, offset, size):
        ret = "0"
        msb = int(eeprom_data[offset + 0], 16)
        lsb = int(eeprom_data[offset + 1], 16)
        exp = (msb >> 3)
        msa = ((msb & 0x7) << 8) | lsb
        if msa == 0:
            ret = "0"
        elif msa >= 1000:
            ret = "{0}E{1:+}".format(msa / 1000.0, exp - 21)
        elif msa >= 100:
            ret = "{0}E{1:+}".format(msa / 100.0, exp - 22)
        elif msa >= 10:
            ret = "{0}E{1:+}".format(msa / 10.0, exp - 23)
        else:
            ret = "{0}E{1:+}".format(msa, exp - 24)
        return ret

    def calc_snr(self, eeprom_data, offset, size):
        lsb = int(eeprom_data[offset + 0], 16)
        msb = int(eeprom_data[offset + 1], 16)
        val = ((msb << 8) | lsb)
        return "0" if val == 0 else "{0:.1f}".format(val / 256.0)

    def decode_loopback_capabilities(self, eeprom_data, offset, size):
        caps = []
        byte = int(eeprom_data[offset], 16)
        if byte & 0x40:
            caps.append('Simultaneous Host and Media Side Loopback')
        if byte & 0x20:
            caps.append('Per-lane Media Side Loopback')
        if byte & 0x10:
            caps.append('Per-lane Host Side Loopback')
        if byte & 0x08:
            caps.append('Host Side Input Loopback')
        if byte & 0x04:
            caps.append('Host Side Output Loopback')
        if byte & 0x02:
            caps.append('Media Side Input Loopback')
        if byte & 0x01:
            caps.append('Media Side Output Loopback')
        return str(caps)

    def decode_general_pattern_capabilities(self, eeprom_data, offset, size):
        caps = []
        byte = int(eeprom_data[offset], 16)
        gate = (byte >> 6) & 0x03
        if gate == 1:
            caps.append('Gating <= 2 ms')
        elif gate == 2:
            caps.append('Gating <= 20 ms')
        elif gate == 3:
            caps.append('Gating > 20 ms')
        if byte & 0x20:
            caps.append('Latched Error Information')
        if byte & 0x10:
            caps.append('Real-time BER Error Count')
        if byte & 0x08:
            caps.append('Per-lane Gating Timer')
        if byte & 0x04:
            caps.append('Auto Restart')
        return str(caps)

    def decode_pattern_types(self, eeprom_data, offset, size):
        caps = []
        word = (int(eeprom_data[offset + 1], 16) << 8) | int(eeprom_data[offset], 16)
        if word & 0x0001:
            caps.append('PRBS-31Q')
        if word & 0x0002:
            caps.append('PRBS-31')
        if word & 0x0004:
            caps.append('PRBS-23Q')
        if word & 0x0008:
            caps.append('PRBS-23')
        if word & 0x0010:
            caps.append('PRBS-15Q')
        if word & 0x0020:
            caps.append('PRBS-15')
        if word & 0x0040:
            caps.append('PRBS-13Q')
        if word & 0x0080:
            caps.append('PRBS-13')
        if word & 0x0100:
            caps.append('PRBS-9Q')
        if word & 0x0200:
            caps.append('PRBS-9')
        if word & 0x0400:
            caps.append('PRBS-7Q')
        if word & 0x0800:
            caps.append('PRBS-7')
        if word & 0x1000:
            caps.append('SSPRQ')
        if word & 0x2000:
            caps.append('Reserved')
        if word & 0x4000:
            caps.append('Custom')
        if word & 0x8000:
            caps.append('User Pattern')
        return str(caps)

    def decode_reporting_capabilities(self, eeprom_data, offset, size):
        caps = []
        byte = int(eeprom_data[offset], 16)
        if byte & 0x80:
            caps.append('Media side FEC')
        if byte & 0x40:
            caps.append('Host side FEC')
        if byte & 0x20:
            caps.append('Media side SNR measurement')
        if byte & 0x10:
            caps.append('Host side SNR measurement')
        if byte & 0x08:
            caps.append('Media side input peak detector')
        if byte & 0x04:
            caps.append('Host side input peak detector')
        if byte & 0x02:
            caps.append('BER Error Count/Total Bits')
        if byte & 0x01:
            caps.append('BER register')
        return str(caps)

    diag_id = {
            'Loopback Capabilities':
                {'offset': 0,
                 'type': 'func',
                 'decode': {'func': decode_loopback_capabilities}},
            'General Pattern Capabilities':
                {'offset': 1,
                 'type': 'func',
                 'decode': {'func': decode_general_pattern_capabilities}},
            'Reporting Capabilities':
                {'offset': 2,
                 'type': 'func',
                 'decode': {'func': decode_reporting_capabilities}},
            'Pattern Generator Capabilities - Host':
                {'offset': 4,
                 'type': 'func',
                 'decode': {'func': decode_pattern_types}},
            'Pattern Generator Capabilities - Media':
                {'offset': 6,
                 'type': 'func',
                 'decode': {'func': decode_pattern_types}},
            'Pattern Checker Capabilities - Host':
                {'offset': 8,
                 'type': 'func',
                 'decode': {'func': decode_pattern_types}},
            'Pattern Checker Capabilities - Media':
                {'offset': 10,
                 'type': 'func',
                 'decode': {'func': decode_pattern_types}},
    }

    ber_id = {
        'BER1':
            {'offset': 0,
             'type': 'func',
             'decode': {'func': calc_ber}},
        'BER2':
            {'offset': 2,
             'type': 'func',
             'decode': {'func': calc_ber}},
        'BER3':
            {'offset': 4,
             'type': 'func',
             'decode': {'func': calc_ber}},
        'BER4':
            {'offset': 6,
             'type': 'func',
             'decode': {'func': calc_ber}},
        'BER5':
            {'offset': 8,
             'type': 'func',
             'decode': {'func': calc_ber}},
        'BER6':
            {'offset': 10,
             'type': 'func',
             'decode': {'func': calc_ber}},
        'BER7':
            {'offset': 12,
             'type': 'func',
             'decode': {'func': calc_ber}},
        'BER8':
            {'offset': 14,
             'type': 'func',
             'decode': {'func': calc_ber}},
    }

    snr_id = {
        'SNR1':
            {'offset': 0,
             'type': 'func',
             'decode': {'func': calc_snr}},
        'SNR2':
            {'offset': 2,
             'type': 'func',
             'decode': {'func': calc_snr}},
        'SNR3':
            {'offset': 4,
             'type': 'func',
             'decode': {'func': calc_snr}},
        'SNR4':
            {'offset': 6,
             'type': 'func',
             'decode': {'func': calc_snr}},
        'SNR5':
            {'offset': 8,
             'type': 'func',
             'decode': {'func': calc_snr}},
        'SNR6':
            {'offset': 10,
             'type': 'func',
             'decode': {'func': calc_snr}},
        'SNR7':
            {'offset': 12,
             'type': 'func',
             'decode': {'func': calc_snr}},
        'SNR8':
            {'offset': 14,
             'type': 'func',
             'decode': {'func': calc_snr}},
    }

    def __init__(self, eeprom_raw_data=None):
        if eeprom_raw_data is not None:
            self.diag_data = sffbase.parse(self,
                                           self.diag_id,
                                           eeprom_raw_data,
                                           0)

    def get_data_pretty(self):
        return sffbase.get_data_pretty(self, self.diag_data)

    def parse_ber(self, raw_data, start_pos):
        return sffbase.parse(self, self.ber_id, raw_data, start_pos)

    def parse_snr(self, raw_data, start_pos):
        return sffbase.parse(self, self.snr_id, raw_data, start_pos)
