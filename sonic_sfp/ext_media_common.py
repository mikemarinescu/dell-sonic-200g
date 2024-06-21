########################################################################
# DellEMC
#
# Module contains common classes and functions for other components
# of the extended media functionality
#
########################################################################

from .ext_media_utils import read_eeprom_byte, media_eeprom_address, get_cmis_version
from . import ext_media_handler_sfp as ext_media_handler_sfp
from . import ext_media_handler_sfp_plus as ext_media_handler_sfp_plus
from . import ext_media_handler_sfp28 as ext_media_handler_sfp28
from . import ext_media_handler_sfp56_dd as ext_media_handler_sfp56_dd
from . import ext_media_handler_qsfp_plus as ext_media_handler_qsfp_plus
from . import ext_media_handler_qsfp28 as ext_media_handler_qsfp28
from . import ext_media_handler_qsfp_dd as ext_media_handler_qsfp_dd
from . import ext_media_handler_qsfp28_dd as ext_media_handler_qsfp28_dd
from . import ext_media_handler_qsfp56 as ext_media_handler_qsfp56
from . import ext_media_handler_qsfp56_dd as ext_media_handler_qsfp56_dd
from . import ext_media_handler_qsfp56_depop as ext_media_handler_qsfp56_depop


"""
The following functions are used to determine the form-factor 
This is needed so we can know which driver module to proceed with
"""

def is_sfp(eeprom):
    # SFP if Byte 0 = 0x03 and Byte 12 in range (0x0 - 0x15)
    if  read_eeprom_byte(eeprom, media_eeprom_address(offset=0)) == 0x03 and \
            read_eeprom_byte(eeprom, media_eeprom_address(offset=12)) in range(0x0, 0x16):
        return True
    return False

def is_sfp28(eeprom):
    # SFP28 if Byte 0 = 0x03 and Byte 12 = 0xFF
    # and bit rate is  between 25G and 28G : Byte 66 in range (0x67 - 0x70)
    # Byte 36 is used to determine media type
    sfp28_module_identifier = [0x01, 0x02, 0x03, 0x04, 0x08, 0x0B, 0x0C, 0x0D, 0x18, 0x19, 0x38]
    byte66 = read_eeprom_byte(eeprom, media_eeprom_address(offset=66))
    byte36 = read_eeprom_byte(eeprom, media_eeprom_address(offset=36))
    if read_eeprom_byte(eeprom, media_eeprom_address(offset=0)) == 0x03 and \
            read_eeprom_byte(eeprom, media_eeprom_address(offset=12)) == 0xFF and \
            (byte66 in range(0x67, 0x71) or \
            ((byte66 == 0x00) and (byte36 in sfp28_module_identifier))):
        return True
    return False

def is_sfp_plus(eeprom):
    # SFP+ if Byte 0 = 0x03 and Byte 12 in range (0x16 - 0x8C)
    if read_eeprom_byte(eeprom, media_eeprom_address(offset=0)) == 0x03 and \
            read_eeprom_byte(eeprom, media_eeprom_address(offset=12)) in range(0x16, 0x8D):
        return True
    return False

def is_qsfp_plus(eeprom):
    if read_eeprom_byte(eeprom, media_eeprom_address(offset=0)) not in [0x0C, 0x0D]:
        return False
    return True

def is_qsfp28(eeprom):
    if is_qsfp56_depop(eeprom):
        return False
    else:
        if read_eeprom_byte(eeprom, media_eeprom_address(offset=0)) != 0x11:
            return False
        return True

def is_qsfp_dd(eeprom):
    qsfp_dd_eeprom_identifiers = [
        (0x04, 0x11, 0xFF), #80G QDD to 8x10G SFP+ AOC breakout
        (0x04, 0x88, 0x11), #80G QDD
        (0x07, 0x44, 0x11), #80G QSFP-DD to 2x40G QSFP+ AOC
        ]
    if read_eeprom_byte(eeprom, media_eeprom_address(offset=0)) != 0x18:
        return False
    byte86 = read_eeprom_byte(eeprom, media_eeprom_address(offset=86))
    byte88 = read_eeprom_byte(eeprom, media_eeprom_address(offset=88))
    byte89 = read_eeprom_byte(eeprom, media_eeprom_address(offset=89))
    eeprom_data = (byte86, byte88, byte89)

    if get_cmis_version(eeprom) >= 0x30:
        if eeprom_data in qsfp_dd_eeprom_identifiers:
            return True
    return False

def is_qsfp28_dd(eeprom):
    if read_eeprom_byte(eeprom, media_eeprom_address(offset=0)) != 0x18:
        return False
    qsfp28_dd_eeprom_identifiers = [
        (0x0B, 0x88, 0x01), #200G Q28DD AOC
        (0x1A, 0x88, 0x01), #200G Q28DD DAC
        (0x0B, 0x44, 0x11), #200G Q28DD to 2x100G QSFP28 AOC breakout
        (0x1A, 0x44, 0x11), #200G Q28DD to 2x100G QSFP28 DAC, breakout cable
        (0x05, 0x11, 0xFF), #200G Q28DD to 8x25G SFP28 AOC breakout
        (0x14, 0x11, 0xFF), #200G Q28DD to 8x25G SFP28 DAC, breakout cable
        (0x15, 0x11, 0xFF), #200G Q28DD to 8x25G SFP28 DAC, breakout cable
        (0x16, 0x11, 0xFF)  #200G Q28DD to 8x25G SFP28 DAC, breakout cable
        ]
    byte86 = read_eeprom_byte(eeprom, media_eeprom_address(offset=86))
    byte88 = read_eeprom_byte(eeprom, media_eeprom_address(offset=88))
    byte89 = read_eeprom_byte(eeprom, media_eeprom_address(offset=89))
    eeprom_data = (byte86, byte88, byte89)

    if get_cmis_version(eeprom) >= 0x30:
        if eeprom_data in qsfp28_dd_eeprom_identifiers:
            return True
    return False

def is_qsfp56_dd(eeprom):
    if read_eeprom_byte(eeprom, media_eeprom_address(offset=0)) != 0x18:
        return False
    return not is_qsfp28_dd(eeprom)

def is_qsfp56(eeprom):
    if read_eeprom_byte(eeprom, media_eeprom_address(offset=0)) != 0x1E or \
        get_cmis_version(eeprom) not in [0x40, 0x50]:
        return False

    # All CMIS compliant modules have Identifier as 0x1E. To find if the module
    # is a 200G QSFP56 type, check 85-89 byte content for the following pattern
    qsfp56_eeprom_identifiers = [
                (0x01, 0x0F, 0x0E, 0x44, 0x01),  #200G QSFP56 SR4
                (0x02, 0x0F, 0x18, 0x44, 0x01)   #200G QSFP56 FR4
        ]

    byte85 = read_eeprom_byte(eeprom, media_eeprom_address(offset=85))
    byte86 = read_eeprom_byte(eeprom, media_eeprom_address(offset=86))
    byte87 = read_eeprom_byte(eeprom, media_eeprom_address(offset=87))
    byte88 = read_eeprom_byte(eeprom, media_eeprom_address(offset=88))
    byte89 = read_eeprom_byte(eeprom, media_eeprom_address(offset=89))
    eeprom_data = (byte85, byte86, byte87, byte88, byte89)

    if eeprom_data in qsfp56_eeprom_identifiers:
        return True
    return False

def is_sfp56_dd(eeprom):
    if read_eeprom_byte(eeprom, media_eeprom_address(offset=0)) != 0x1A:
        return False
    return True

def is_qsfp56_depop(eeprom):
    byte192 = read_eeprom_byte(eeprom, media_eeprom_address(offset=192))
    byte113 = read_eeprom_byte(eeprom, media_eeprom_address(offset=113))
    if read_eeprom_byte(eeprom, media_eeprom_address(offset=0)) == 0x11 and \
       (((byte192 == 0x40) and (byte113 == 0x2c)) or ((byte192 == 0x40) and (byte113 == 0x0c))):
        return True
    return False

"""
Maps the handler to the name, and form factor driver module
"""
form_factor_handler_to_ff_info = {is_sfp:   ('SFP', ext_media_handler_sfp),
                            is_sfp_plus:    ('SFP+', ext_media_handler_sfp_plus),
                            is_sfp28:       ('SFP28', ext_media_handler_sfp28),
                            is_sfp56_dd:    ('SFP56-DD', ext_media_handler_sfp56_dd),
                            is_qsfp_plus:   ('QSFP+', ext_media_handler_qsfp_plus),
                            is_qsfp28:      ('QSFP28', ext_media_handler_qsfp28),
                            is_qsfp_dd:     ('QSFP-DD', ext_media_handler_qsfp_dd),
                            is_qsfp28_dd:   ('QSFP28-DD', ext_media_handler_qsfp28_dd),
                            is_qsfp56:      ('QSFP56', ext_media_handler_qsfp56),
                            is_qsfp56_dd:   ('QSFP56-DD', ext_media_handler_qsfp56_dd),
                            is_qsfp56_depop:('QSFP56-DEPOP', ext_media_handler_qsfp56_depop)
                            }

"""
Returns the form factor name and handler functions
"""
def get_form_factor_info(eeprom_bytes):
    for func in form_factor_handler_to_ff_info:
        if func(eeprom_bytes):
            return form_factor_handler_to_ff_info[func]
    return (None, None)

def qsfp28_enable_media_power(eeprom_path, media_power):
    """ Enable media power on QSFP28 """
    ext_media_handler_qsfp28.enable_media_power(eeprom_path, media_power)

def qsfp28_select_rate(sfp_obj, rate):
    """ Select rate on QSFP28 """
    return ext_media_handler_qsfp28.select_rate(sfp_obj, rate)

def qsfp28_dd_select_rate(sfp_obj, rate):
    """ Select rate on QSFP28 DD"""
    return ext_media_handler_qsfp28_dd.select_rate(sfp_obj, rate)

def qsfp56_dd_prep_to_set_fec_mode(sfp_obj):
    """ Prepare to set FEC mode on QSFP56 DD """
    return ext_media_handler_qsfp56_dd.prepare_to_set_fec_mode(sfp_obj)

def qsfp56_dd_set_media_fec_mode(sfp_obj, mode, on_insertion, breakout_mode):
    """ Set FEC Mode on QSFP56 DD """
    return ext_media_handler_qsfp56_dd.set_media_fec_mode(sfp_obj, mode,
                                                          on_insertion, breakout_mode)

def qsfp56_dd_get_media_fec_mode(sfp_obj):
    """ Get FEC Mode on QSFP56 DD """
    return ext_media_handler_qsfp56_dd.get_media_fec_mode(sfp_obj)

def qsfp28_dd_media_lockdown_set(sfp_obj, status):
    """ media lockdown set """
    return ext_media_handler_qsfp28_dd.media_lockdown_set(sfp_obj, status)
