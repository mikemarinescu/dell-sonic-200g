########################################################################
# DellEMC
#
# Module contains the ext media drivers for QSFP56-DD modules
#
########################################################################
import syslog
import time

from .ext_media_utils import media_eeprom_address, read_eeprom_byte, media_summary, set_bits, \
    build_media_display_name, get_connector_name, extract_string_from_eeprom, \
    read_eeprom_multi_byte, parse_date_code, get_cmis_version, sfp_read_bytes, sfp_write_bytes, \
    DEFAULT_NO_DATA_VALUE, get_bit_set_count

from .ext_media_handler_base import media_static_info

QSFP56_DD_CMIS_1_LENGTH_ADDR = media_eeprom_address(offset=146)
QSFP56_DD_CMIS_3_LENGTH_ADDR = media_eeprom_address(offset=202)

QSFP56_DD_CMIS_3_MEDIA_TYPE_ENCODING_ADDR =  media_eeprom_address(offset=85)
QSFP56_DD_CMIS_3_DEFAULT_MODULE_MEDIA_INTERFACE_ADDR =  media_eeprom_address(offset=87)
QSFP56_DD_CMIS_3_DEFAULT_LANE_COUNT_ADDR =  media_eeprom_address(offset=88)
QSFP56_DD_CMIS_3_DEFAULT_LANE_ASSIGNMENT_ADDR = media_eeprom_address(offset=89)
QSFP56_DD_CMIS_3_MEDIA_INTERFACE_TECH_ADDR =  media_eeprom_address(offset=212)
QSFP56_DD_CMIS_3_FAR_END_COUNT_ADDR =  media_eeprom_address(offset=211)
QSFP56_DD_CMIS_3_CONNECTOR_ADDR = media_eeprom_address(offset=203)
QSFP56_DD_CMIS_3_MAX_POWER_CLASS_ADDR = media_eeprom_address(offset=200)
QSFP56_DD_CMIS_3_MAX_POWER_RAW_ADDR = media_eeprom_address(offset=201)

QSFP56_DD_CMIS_3_VENDOR_NAME_ADDR = media_eeprom_address(offset=129)
QSFP56_DD_CMIS_3_VENDOR_PART_NUM_ADDR = media_eeprom_address(offset=148)
QSFP56_DD_CMIS_3_VENDOR_REVISION_ADDR = media_eeprom_address(offset=164)
QSFP56_DD_CMIS_3_VENDOR_SERIAL_NUM_ADDR = media_eeprom_address(offset=166)
QSFP56_DD_CMIS_3_VENDOR_OUI_ADDR = media_eeprom_address(offset=145)
QSFP56_DD_CMIS_3_VENDOR_DATE_CODE_ADDR = media_eeprom_address(offset=182)
QSFP56_DD_CMIS_3_VENDOR_GEN_CODE_ADDR = media_eeprom_address(offset=245)
QSFP56_DD_CMIS_3_MEDIA_FEC_STATUS_ADDR = media_eeprom_address(offset=13)
QSFP56_DD_CMIS_3_SIG_INTEG_CTRL_AD_ADDR = media_eeprom_address(page=0x1, offset=162)
QSFP56_DD_CMIS_3_DATA_PATH_CTRL_ADDR = media_eeprom_address(page=0x10, offset=128)
QSFP56_DD_CMIS_3_LASER_CTRL_ADDR = media_eeprom_address(page=0x10, offset=130)
QSFP56_DD_CMIS_3_LINK_LENGTH_ADDR = media_eeprom_address(page=0x1, offset=132)

HIGH_POWER_MODULE_CTRL_ADDR = media_eeprom_address(offset=26)
QSFP56_DD_CMIS_3_MEDIA_FEC_IEEE_CTRL_ADDR = media_eeprom_address(page=0x10, offset=143)
QSFP56_DD_CMIS_3_MEDIA_FEC_CUST_CTRL_ADDR = media_eeprom_address(page=0x10, offset=178)
QSFP56_DD_CMIS_PAGE11_ADDR = media_eeprom_address(page=0x11, offset=128)
QSFP56_DD_RESET_MODULE_ADDR = media_eeprom_address(page=0x0, offset=26)
MEDIA_TYPE_ADDR = media_eeprom_address(offset=0x0)
CMIS_VER_ADDR = media_eeprom_address(offset=0x1)
CMIS_WAVELENGTH_ADDR = media_eeprom_address(offset=138)

QSFP_DD               = 0x18
MMF_MODULE            = 0x1
SMF_MODULE            = 0x2
BIDI_OPTICAL          = 0x1A
SET_FEC_MODE          = 0xFF
DEACTIVATE_DATA_PATH  = 0xFF
ACTIVATE_DATA_PATH    = 0x0
TURN_OFF_LASER        = 0xFF
TURN_ON_LASER         = 0x0
HIGH_POWER_MODE       = 0x0
MEDIA_FEC_MODE_IEEE   = 0x0
MEDIA_FEC_MODE_CUSTOM = 0x1
RESET_MODULE          = 0x10
SET_POWER_MODE        = 0x40
IEEE_4x100_SEQ = {145:0x30, 146:0x30, 147:0x34, 148:0x34, 149:0x38, 150:0x38, 151:0x3c, 152:0x3c}
CUSTOM_4x100_SEQ = {180:0x20, 181:0x20, 182:0x24, 183:0x24, 184:0x28, 185:0x28, 186:0x2c, 187:0x2c}
IEEE_1x400_SEQ = {145:0x10, 146:0x10, 147:0x10, 148:0x10, 149:0x10, 150:0x10, 151:0x10, 152:0x10}
SR4_2_GEN3_VERSION = 0x20
SR4_2_GEN3_1x400_BYPASS_SEQ = {86:0x11, 87:0x1A, 88:0x88, 89:0x01}
SR4_2_GEN3_4x100_CUSTOM_SEQ = {90:0x0D, 91:0x0B, 92:0x22, 93:0x55}
SR4_2_GEN3_4x100_BYPASS_SEQ = {94:0x0D, 95:0x1A, 96:0x22, 97:0x55}
RETRY_COUNT = 2

QSFP56_DD_CMIS_3_OPTICAL_MMF_TABLE = {
                                        0x0F: ('SR', 'FIBER', 16, None),
                                        0x10: ('SR', 'FIBER', 8, None),
                                        0x11: ('SR', 'FIBER', 4, None),
                                        0x1A: ('BIDI', 'FIBER', 8, None) # Special. Has name override to SR4.2
}
QSFP56_DD_CMIS_3_OPTICAL_SMF_TABLE = {
                                        0x1A: ('FR', 'FIBER', 8, None),
                                        0x1B: ('LR', 'FIBER', 8, None),
                                        0x42: ('ER', 'FIBER', 8, None),
                                        0x1C: ('DR', 'FIBER', 4, None),
                                        0x1D: ('FR', 'FIBER', 4, None),
                                        0x43: ('LR', 'FIBER', 4, None),
                                        0x1E: ('LR', 'FIBER', 4, None),
                                        0x3E: ('ZR', 'FIBER', 8, None)
}
QSFP56_DD_CMIS_3_PASSIVE_CU_TABLE = {
                                        0x01: ('CR', 'DAC', 8, None),
                                        0xBF: ('CR', 'E-LPBK', 8, None) # Effectively a DAC
}
# Active cable may be AOC or ACC. Need to check byte 212 (media interface technology)
QSFP56_DD_CMIS_3_ACTIVE_CABLE_TABLE = {
                                        0x01: ('SR', 'AOC', 8, 'BER:1e-12'),
                                        0x02: ('SR', 'AOC', 8, 'BER:5e-5'),
                                        0x03: ('SR', 'AOC', 8, 'BER:2.6e-4'),
                                        0x04: ('SR', 'AOC', 8, 'BER:1e-6'),
                                        0xBF: ('CR', 'E-LPBK', 8, None),
}

QSFP56_DD_CMIS_3_MEDIA_TYPE_TO_MODULE_TYPE_TABLE = {
                                        0x01: QSFP56_DD_CMIS_3_OPTICAL_MMF_TABLE,
                                        0x02: QSFP56_DD_CMIS_3_OPTICAL_SMF_TABLE,
                                        0x03: QSFP56_DD_CMIS_3_PASSIVE_CU_TABLE,
                                        0x04: QSFP56_DD_CMIS_3_ACTIVE_CABLE_TABLE
}

class qsfp56_dd(media_static_info):
    def cmis_ver_check(fn):
        def gn(self, eeprom):
            if get_cmis_version(eeprom) < 0x30:
                # Cannot proceed. Not supported
                return None
            return fn(self, eeprom)
        return gn

    def get_cable_length_detailed(self, eeprom):
        # CMIS Rev 2.x and below use QSFPx style
        if get_cmis_version(eeprom) < 0x30:
            return float(read_eeprom_byte(eeprom, QSFP56_DD_CMIS_1_LENGTH_ADDR))

        length_code = read_eeprom_byte(eeprom, QSFP56_DD_CMIS_3_LENGTH_ADDR)

        # Upper 2 bits is multiplier in powers of 10, starting from 0.1
        multiplier = float( (length_code & set_bits([6,7])) >> 6)
        multiplier = 0.1 * (10**multiplier)

        # Lower 6 bits is an integer scaling factor
        scale = length_code & set_bits([q for q in range(0,6)])

        return float(multiplier) * float(scale)

    # Get a summary of the media info
    @cmis_ver_check
    def _get_media_summary(self, eeprom):
        ms = media_summary()

        # Default
        ms.form_factor = self.get_form_factor(eeprom)
        ms.cable_length = self.get_cable_length_detailed(eeprom)
        ms.speed = 400*1000
        ms.lane_count = 8
        ms.breakout = '1x1'
        ms.cable_class = 'FIBER'

        module_type_encoding = read_eeprom_byte(eeprom, QSFP56_DD_CMIS_3_MEDIA_TYPE_ENCODING_ADDR)
        if module_type_encoding not in QSFP56_DD_CMIS_3_MEDIA_TYPE_TO_MODULE_TYPE_TABLE:
            return None

        module_type_table = QSFP56_DD_CMIS_3_MEDIA_TYPE_TO_MODULE_TYPE_TABLE[module_type_encoding]

        module_media_interface = read_eeprom_byte(eeprom, QSFP56_DD_CMIS_3_DEFAULT_MODULE_MEDIA_INTERFACE_ADDR)

        if module_media_interface not in module_type_table:
            return None
        ms.interface = module_type_table[module_media_interface][0]
        ms.cable_class = module_type_table[module_media_interface][1]
        ms.lane_count = module_type_table[module_media_interface][2] # Can be overriden
        if module_type_table[module_media_interface][3] is not None:
            ms.special_fields['fec_hint'] = module_type_table[module_media_interface][3]

        # Active cables can either be ACC or AOC. Need to check media interface tech
        if ms.cable_class is 'AOC':
            media_interface_tech = read_eeprom_byte(eeprom, QSFP56_DD_CMIS_3_MEDIA_INTERFACE_TECH_ADDR)
            if media_interface_tech in [0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F]:
                ms.cable_class = 'ACC'
                ms.interface = 'SR'

        # Check if standard field overrides
        # byte 88 gives media lanes per data path
        lanes_per_dp = self._get_lane_count(eeprom)
        # byte 89 gives number of datapaths
        no_of_dps = self._get_datapath_count(eeprom)
        ms.lane_count = no_of_dps * lanes_per_dp

        ms.breakout = self.get_cable_breakout(eeprom)

        syslog.syslog(syslog.LOG_DEBUG, "Init breakout {}".format(ms.breakout))

        # If no interface, discard defaults
        if ms.interface is None:
            return None
        return ms
    def get_media_interface(self, eeprom):
        if self.media_summary is None:
            # Summary builder could not find it
            return DEFAULT_NO_DATA_VALUE
        return self.media_summary.interface
    def get_cable_class(self, eeprom):
        if self.media_summary is None:
            # Summary builder could not find it
            return DEFAULT_NO_DATA_VALUE
        return self.media_summary.cable_class

    # Standard way, unless overridden by application code
    def _get_lane_count(self, eeprom):
        lane_count = read_eeprom_byte(eeprom, QSFP56_DD_CMIS_3_DEFAULT_LANE_COUNT_ADDR)
        # Only care about media lane count (lower 4 bits)
        lane_count = lane_count & 0x0F
        if lane_count > 0 and lane_count <= 8:
            return lane_count
        return None

    def _get_datapath_count(self, eeprom):
        lane_assignment = read_eeprom_byte(eeprom, QSFP56_DD_CMIS_3_DEFAULT_LANE_ASSIGNMENT_ADDR)
        dp_count = get_bit_set_count(lane_assignment)
        return dp_count

    def get_lane_count(self, eeprom):
        if self.media_summary is None:
            return DEFAULT_NO_DATA_VALUE
        return self.media_summary.lane_count

    def get_cable_breakout(self, eeprom):
        # Check for far-end (breakout)
        far_end_count = read_eeprom_byte(eeprom, QSFP56_DD_CMIS_3_FAR_END_COUNT_ADDR)
        # Lower 4 bits
        far_end_count = far_end_count & 0x1F
        # There are 26 different ways. Only care about 1x1, 1x2, 1x4, 1x8
        far_end_count_map = {0x00: '1x1',
                                0x01: '1x8',
                                0x02: '1x1',
                                0x03: '1x2',
                                0x0C: '1x4'}

        if far_end_count in far_end_count_map:
            return far_end_count_map[far_end_count]
        # Default
        return '1x1'
    def get_display_name(self, eeprom):
        display_name = build_media_display_name(self.media_summary)
        if display_name is not None:
            # Weird naming convention exception due to proprietary stuff
            if 'BIDI2' in display_name:
                sig_ctrl = sfp_read_bytes(self.sfp_obj, QSFP56_DD_CMIS_3_SIG_INTEG_CTRL_AD_ADDR, 1)[0]
                if (sig_ctrl & 0x20) != 0: #Staged Control Set 1 implemented on Page 10h
                    display_name = display_name.replace('BIDI2', 'SR4.2')
            if 'DR4' in display_name:
                link_length = sfp_read_bytes(self.sfp_obj, QSFP56_DD_CMIS_3_LINK_LENGTH_ADDR, 1)[0]
                multiplier = float( (link_length & 0xc0) >> 6)
                multiplier = 0.1 * (10**multiplier)
                base_len = int( (link_length & 0x3F) * multiplier)
                if base_len == 0x2:  #Extended DR4
                    display_name = display_name.replace('DR4', 'EDR4')
                elif base_len == 0xa:  #Longreach DR4
                    display_name = display_name.replace('DR4', 'LDR4')
        if display_name is not None:
            display_name=display_name.replace('BIDI8','SR4.2')
        return display_name
    def get_connector_type(self, eeprom):
        connector_code = read_eeprom_byte(eeprom, QSFP56_DD_CMIS_3_CONNECTOR_ADDR)
        return get_connector_name(connector_code)

    def get_power_rating_max(self, eeprom):
        power_max_code = (read_eeprom_byte(eeprom, QSFP56_DD_CMIS_3_MAX_POWER_CLASS_ADDR) >> 5) & 0x07
        power_old_method = 0.0
        if power_max_code < 0x07:
            # Hard-coded power values
            power_old_method = [1.5, 2.0, 2.5, 3.5, 4.0, 4.5, 5.0][power_max_code]
        # Alternatively, power is encoded as unsigned int in units of 0.25W
        return max(power_old_method, float(read_eeprom_byte(eeprom, QSFP56_DD_CMIS_3_MAX_POWER_RAW_ADDR)) * 0.25)

    def get_form_factor(self, eeprom):
        return 'QSFP56-DD'

    def get_vendor_name(self, eeprom):
        # 16 bytes
        return extract_string_from_eeprom(eeprom, QSFP56_DD_CMIS_3_VENDOR_NAME_ADDR, 16)

    def get_vendor_part_number(self, eeprom):
        # 16 bytes
        return extract_string_from_eeprom(eeprom, QSFP56_DD_CMIS_3_VENDOR_PART_NUM_ADDR, 16)

    def get_vendor_serial_number(self, eeprom):
        # 16 bytes
        return extract_string_from_eeprom(eeprom, QSFP56_DD_CMIS_3_VENDOR_SERIAL_NUM_ADDR, 16)

    def get_vendor_oui(self, eeprom):
        # 3 bytes, raw
        oui_bytes = read_eeprom_multi_byte(eeprom, QSFP56_DD_CMIS_3_VENDOR_OUI_ADDR, media_eeprom_address(offset=QSFP56_DD_CMIS_3_VENDOR_OUI_ADDR.offset+3))
        # Print OUI as hyphen seperated hex formatted bytes
        return '-'.join('{:02X}'.format(n) for n in oui_bytes)

    def get_vendor_revision(self, eeprom):
        # 2 bytes
        return extract_string_from_eeprom(eeprom, QSFP56_DD_CMIS_3_VENDOR_REVISION_ADDR, 2)

    def get_vendor_date_code(self, eeprom):
        # 8 bytes, strict formatting
        date_code = extract_string_from_eeprom(eeprom, QSFP56_DD_CMIS_3_VENDOR_DATE_CODE_ADDR, 8)
        return parse_date_code(date_code)

    def get_wavelength(self, eeprom):
        # 2 bytes
        if self.media_summary.cable_class in ['FIBER', 'AOC']:
            wavelength_bytes = read_eeprom_multi_byte(eeprom, CMIS_WAVELENGTH_ADDR,
                                               media_eeprom_address(offset=CMIS_WAVELENGTH_ADDR.offset+2))
            wavelength = (wavelength_bytes[0] << 8) | (wavelength_bytes[1]& 0xff)
            return round(wavelength/20, 2)

    def __init__(self, eeprom, sfp_obj):
        self.media_summary = self._get_media_summary(eeprom)
        self.sfp_obj = sfp_obj

def _media_fec_supported(sfp_obj):
    try:
        ## RAS Hack
        return True
        if sfp_read_bytes(sfp_obj, MEDIA_TYPE_ADDR, 1)[0] == QSFP_DD and \
            sfp_read_bytes(sfp_obj, CMIS_VER_ADDR, 1)[0] >= 3:
            encoding = sfp_read_bytes(sfp_obj, QSFP56_DD_CMIS_3_MEDIA_TYPE_ENCODING_ADDR, 1)[0]
            intf = sfp_read_bytes(sfp_obj, QSFP56_DD_CMIS_3_DEFAULT_MODULE_MEDIA_INTERFACE_ADDR, 1)[0]
            if encoding == MMF_MODULE and intf == BIDI_OPTICAL:
                sig_ctrl = sfp_read_bytes(sfp_obj, QSFP56_DD_CMIS_3_SIG_INTEG_CTRL_AD_ADDR, 1)[0]
                if (sig_ctrl & 0x20) != 0: #Staged Control Set 1 implemented on Page 10h
                    return True
    except TypeError:
        pass
    return False


def prepare_to_set_fec_mode(sfp_obj):
    """
    Prepare the media to program media FEC
    sfp_obj: Media obj to be prepared for
    """
    if _media_fec_supported(sfp_obj):
        try:
            sfp_write_bytes(sfp_obj, QSFP56_DD_RESET_MODULE_ADDR, [RESET_MODULE])
            sfp_write_bytes(sfp_obj, QSFP56_DD_RESET_MODULE_ADDR, [SET_POWER_MODE])
            syslog.syslog(syslog.LOG_NOTICE, "Preparation done to set media FEC mode on port {}"\
                .format(sfp_obj.port_index))
            return True
        except IOError:
            pass
    return False

def apply_GEN3_appsel_sequence(sfp_obj, seq):
    for key, value in seq.items():
        addr = media_eeprom_address(page=0x10, offset=key)
        sfp_write_bytes(sfp_obj, addr, [value])

def set_media_fec_mode_custom(sfp_obj, on_insertion, breakout_mode):
    set_media_fec_mode(sfp_obj, 'custom', on_insertion, breakout_mode)

def set_media_fec_mode(sfp_obj, mode, on_insertion, breakout_mode):
    """
    Set FEC mode on media
    sfp_boj : Media object on which FEC is set
    mode : FEC mode to be set on media
    on_insertion : True if FEC mode to be set on insertion
    """
    if not _media_fec_supported(sfp_obj):
        return None

    if mode == '':
        mode = 'ieee'

    fec_map = {0:'ieee', 1:'custom'}
    if mode not in ('ieee', 'custom'):
        syslog.syslog(syslog.LOG_ERR, "set_media_fec_mode FEC mode not supported on port {}"\
            .format(sfp_obj.port_index))
        return None

    if mode != 'ieee' and breakout_mode == '1x400':
        syslog.syslog(syslog.LOG_NOTICE, "set_media_fec_mode FEC mode not supported on port {} mode {} breakout {}"\
            .format(sfp_obj.port_index, mode, breakout_mode))
        return None

    sr_gen = sfp_read_bytes(sfp_obj, QSFP56_DD_CMIS_3_VENDOR_GEN_CODE_ADDR, 1)[0]
    if sr_gen & 0xF0 != SR4_2_GEN3_VERSION:
        syslog.syslog(syslog.LOG_DEBUG, "set media fec mode detected Gen2 on port {} "\
                    .format(sfp_obj.port_index))
        return _set_GEN2_media_fec_mode(sfp_obj, mode, on_insertion, breakout_mode, RETRY_COUNT)
    else:
        syslog.syslog(syslog.LOG_DEBUG, "set media fec mode detected Gen3 media on port {} "\
                    .format(sfp_obj.port_index))
        return _set_GEN3_media_fec_mode(sfp_obj, mode, on_insertion, breakout_mode, RETRY_COUNT)


def _set_GEN3_media_fec_mode(sfp_obj, mode, on_insertion, breakout_mode, retries=1):

    if retries < 0:
        syslog.syslog(syslog.LOG_ERR, "No more retries for setting media FEC")
        return None

#    if mode == 'ieee' and breakout_mode == '1x200':
 #      L_SEQ = 1x400_BYPASS_SEQ

    if mode == 'ieee' and breakout_mode == '1x400':
        SR4_2_GEN3_MODE_SEL_SEQ = SR4_2_GEN3_1x400_BYPASS_SEQ
    elif mode == 'custom' and breakout_mode == '4x100':
        SR4_2_GEN3_MODE_SEL_SEQ = SR4_2_GEN3_4x100_CUSTOM_SEQ
    elif mode == 'ieee' and breakout_mode == '4x100':
        SR4_2_GEN3_MODE_SEL_SEQ = SR4_2_GEN3_4x100_BYPASS_SEQ
    else:
        SR4_2_GEN3_MODE_SEL_SEQ = {}

    for key, value in SR4_2_GEN3_MODE_SEL_SEQ.items():
        addr = media_eeprom_address(page=0x0, offset=key)
        readval = sfp_read_bytes(sfp_obj, addr, 1)[0]
        if value != readval:
            syslog.syslog(syslog.LOG_ERR, "set_media_fec_mode reading {} IEEE SEQ {}:{}:{}"\
                    .format(breakout_mode, key, readval, value))
            syslog.syslog(syslog.LOG_ERR, "mode SEL is NOT correctly chosen")
            return None

    fec_map = {0:'ieee', 1:'custom'}
    ct_mode = None
    try:

        sfp_write_bytes(sfp_obj, QSFP56_DD_CMIS_3_DATA_PATH_CTRL_ADDR, [DEACTIVATE_DATA_PATH])
        sfp_write_bytes(sfp_obj, QSFP56_DD_CMIS_3_LASER_CTRL_ADDR, [TURN_OFF_LASER])

        # 1 Sec sleep - to deactivate the datapath
        time.sleep(1)

        sfp_write_bytes(sfp_obj, HIGH_POWER_MODULE_CTRL_ADDR, [HIGH_POWER_MODE])
        # 2 Sec sleep - to enable highpower mode using soft method
        time.sleep(2)

 
        if mode == 'ieee' and breakout_mode == '4x100':
            apply_GEN3_appsel_sequence(sfp_obj, IEEE_4x100_SEQ)
        elif mode == 'custom' and breakout_mode == '4x100':
            apply_GEN3_appsel_sequence(sfp_obj, CUSTOM_4x100_SEQ)
        elif mode == 'ieee' and breakout_mode == '1x400':
            apply_GEN3_appsel_sequence(sfp_obj, IEEE_1x400_SEQ)

        mode_addr = QSFP56_DD_CMIS_3_MEDIA_FEC_IEEE_CTRL_ADDR
# if mode == 'ieee'\
#                        else QSFP56_DD_CMIS_3_MEDIA_FEC_CUST_CTRL_ADDR
        sfp_write_bytes(sfp_obj, mode_addr, [SET_FEC_MODE])
        sfp_write_bytes(sfp_obj, QSFP56_DD_CMIS_3_DATA_PATH_CTRL_ADDR, [ACTIVATE_DATA_PATH])
        # 5s sleep - As per Hisense document page 9-10 LMQ8811B QSFP-DD SR4.2
        time.sleep(5)

        sfp_write_bytes(sfp_obj, QSFP56_DD_CMIS_3_LASER_CTRL_ADDR, [TURN_ON_LASER])
        time.sleep(2)

        # Verify if the mode switched, Check page 0x11, byte-128 to byte-131 for values 0x44 0x44 0x44 0x44
        addr = media_eeprom_address(page=0x11, offset=128)
        checkval = sfp_read_bytes(sfp_obj, addr, 4)
        syslog.syslog(syslog.LOG_DEBUG, "set_media_fec_mode reading {} modesel check {}:{} port {}"\
                .format(breakout_mode, key, checkval, sfp_obj.port_index))

        ct_mode = fec_map[sfp_read_bytes(sfp_obj, QSFP56_DD_CMIS_3_MEDIA_FEC_STATUS_ADDR, 1)[0]]
        if ct_mode != mode:
            syslog.syslog(syslog.LOG_NOTICE, "set_media_fec_mode Failed FEC mode {} on port {}"\
                        .format(mode, sfp_obj.port_index))
            ct_mode = _set_GEN3_media_fec_mode(sfp_obj, mode, on_insertion, breakout_mode, retries-1)
    except (TypeError, IOError):
        syslog.syslog(syslog.LOG_ERR, "set_media_fec_mode Failed FEC mode {} on port {} : Type or IO Error"\
                .format(mode, sfp_obj.port_index))
        return None
    return ct_mode


def _set_GEN2_media_fec_mode(sfp_obj, mode, on_insertion, breakout_mode, retries=1):

    if retries < 0:
        syslog.syslog(syslog.LOG_ERR, "No more retries for setting media FEC")
        return None
    ct_mode = None
    fec_map = {0:'ieee', 1:'custom'}
    try:
        sfp_write_bytes(sfp_obj, QSFP56_DD_CMIS_3_DATA_PATH_CTRL_ADDR, [DEACTIVATE_DATA_PATH])
        sfp_write_bytes(sfp_obj, QSFP56_DD_CMIS_3_LASER_CTRL_ADDR, [TURN_OFF_LASER])

        # 1 Sec sleep - to deactivate the datapath
        time.sleep(1)

        sfp_write_bytes(sfp_obj, HIGH_POWER_MODULE_CTRL_ADDR, [HIGH_POWER_MODE])

        # 2 Sec sleep - to enable highpower mode using soft method
        time.sleep(2)

        mode_addr = QSFP56_DD_CMIS_3_MEDIA_FEC_IEEE_CTRL_ADDR if mode == 'ieee'\
                        else QSFP56_DD_CMIS_3_MEDIA_FEC_CUST_CTRL_ADDR

        sfp_write_bytes(sfp_obj, mode_addr, [SET_FEC_MODE])
        sfp_write_bytes(sfp_obj, QSFP56_DD_CMIS_3_DATA_PATH_CTRL_ADDR, [ACTIVATE_DATA_PATH])
        time.sleep(5)
        sfp_write_bytes(sfp_obj, QSFP56_DD_CMIS_3_LASER_CTRL_ADDR, [TURN_ON_LASER])
        ct_mode = fec_map[sfp_read_bytes(sfp_obj, QSFP56_DD_CMIS_3_MEDIA_FEC_STATUS_ADDR, 1)[0]]
        if ct_mode != mode:
            syslog.syslog(syslog.LOG_ERR, "Failed to set media FEC mode {} on port {}, retry in progress"\
                    .format(mode, sfp_obj.port_index))

            ct_mode = _set_GEN2_media_fec_mode(sfp_obj, mode, on_insertion, breakout_mode, retries-1)
    except (TypeError, IOError):
        syslog.syslog(syslog.LOG_ERR, "set_media_fec_mode Failed FEC mode {} on port {} : Type or IO Error"\
                .format(mode, sfp_obj.port_index))
        return None

    return ct_mode

def get_media_fec_mode(sfp_obj):
    """
    Get FEC mode on media
    sfp_obj : Media object
    """
    if not _media_fec_supported(sfp_obj):
        return None
    fec_map = {0:'ieee', 1:'custom'}
    mode = None
    try:
       mode = fec_map[sfp_read_bytes(sfp_obj, QSFP56_DD_CMIS_3_MEDIA_FEC_STATUS_ADDR, 1)[0]]
    except TypeError:
       pass
    return mode

