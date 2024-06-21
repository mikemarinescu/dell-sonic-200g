#
# sfp_standard.py
#
# Abstract base class for implementing a platform-specific class with which
# to interact with a SFP module in SONiC
#

from __future__ import print_function

try:
    import abc
    import sys
    import time
    import syslog

    from datetime import datetime
    from multiprocessing import Lock
    from .sfp_base import SfpBase
    from .sonic_sfp.sff8024 import connector_dict
    from .sonic_sfp.sff8436 import sff8436InterfaceId
    from .sonic_sfp.sff8436 import sff8436Dom
    from .sonic_sfp.sff8472 import sff8472InterfaceId
    from .sonic_sfp.sff8472 import sff8472Dom
    from .sonic_sfp.inf8628 import inf8628InterfaceId
    from .sonic_sfp.inf8628 import inf8628Dom
    from .sonic_sfp.inf8628 import inf8628Diag
    from .sonic_sfp.mis2 import mis2InterfaceId
    from .sonic_sfp.mis2 import mis2Dom
    from .sonic_sfp.mis2 import mis2Diag
except ImportError as ex:
    raise ImportError (str(ex) + "- required module not found")

sfp_cable_length_types = [
    'LengthSMFkm-UnitsOfKm', 'LengthSMF(UnitsOf100m)', 'Length50um(UnitsOf10m)',
    'Length62.5um(UnitsOfm)', 'LengthCable(UnitsOfm)', 'LengthOM3(UnitsOf10m)'
]

qsfp_cable_length_types = [
    'Length(km)', 'Length OM3(2m)', 'Length OM2(m)', 'Length OM1(m)',
    'Length Cable Assembly(m)'
]

cmis_cable_length_types = [
    'Length Cable Assembly(m)', 'Length SMF(km)', 'Length OM5(2m)',
    'Length OM4(2m)', 'Length OM3(2m)', 'Length OM2(m)'
]

mis_cable_length_types = [
    'Length Cable Assembly(m)', 'Length SMF(km)', 'Length OM5(2m)',
    'Length OM4(2m)', 'Length OM3(2m)', 'Length OM2(m)'
]
XCVR_EEPROM_TYPE_UNKNOWN = 0
XCVR_EEPROM_TYPE_SFP     = 1
XCVR_EEPROM_TYPE_QSFP    = 2
XCVR_EEPROM_TYPE_QSFPDD  = 3
XCVR_EEPROM_TYPE_SFPDD   = 4
XCVR_EEPROM_TYPE_QSFP56  = 5
XCVR_EEPROM_TYPE_OSFP    = XCVR_EEPROM_TYPE_QSFPDD

SFF8024_TYPE_SFP                 = ['03']
SFF8024_TYPE_QSFP                = ['0c','0d','11']
SFF8024_TYPE_QSFPDD              = ['18','19']
SFF8024_TYPE_QSFP_CMIS_COMPLIANT = ['1e']      # Follows CMIS Spec (v3.0 or higher)
SFF8024_TYPE_SFPDD               = ['1a']

SFF8472_CONNECTOR_ADDR           = 2
SFF8472_ENHANCED_OPTS_ADDR       = 93
SFF8472_ENHANCED_OPTS_RX_LOS     = 0x10
SFF8472_ENHANCED_OPTS_TX_FAULT   = 0x20
SFF8472_ENHANCED_OPTS_TX_DISABLE = 0x40
SFF8472_ENHANCED_OPTS_MASK       = 0x70
SFF8472_DOM_ADDR                 = (0 | 0x100)
SFF8472_DOM_THRES_ADDR           = SFF8472_DOM_ADDR
SFF8472_DOM_TEMP_WARM_HI_ADDR    = (4 | 0x100)
SFF8472_DOM_TEMP_WARM_LO_ADDR    = (6 | 0x100)
SFF8472_DOM_VOLT_WARM_HI_ADDR    = (12 | 0x100)
SFF8472_DOM_VOLT_WARM_LO_ADDR    = (14 | 0x100)
SFF8472_DOM_TXPWR_WARM_HI_ADDR   = (28 | 0x100)
SFF8472_DOM_TXPWR_WARM_LO_ADDR   = (30 | 0x100)
SFF8472_DOM_RXPWR_WARM_HI_ADDR   = (36 | 0x100)
SFF8472_DOM_RXPWR_WARM_LO_ADDR   = (38 | 0x100)
SFF8472_DOM_TEMP_ADDR            = (96 | 0x100)
SFF8472_DOM_VOLT_ADDR            = (98 | 0x100)
SFF8472_DOM_CHAN_MON_ADDR        = (100 | 0x100)
SFF8472_DOM_TXPWR_ADDR           = (102 | 0x100)
SFF8472_DOM_RXPWR_ADDR           = (104 | 0x100)
SFF8472_DOM_STCR_ADDR            = (110 | 0x100)
SFF8472_DOM_STCR_TX_DISABLE      = 0x80
SFF8472_DOM_STCR_TX_FAULT        = 0x04
SFF8472_DOM_STCR_RX_LOS          = 0x02
SFF8472_DOM_STCR_NOT_READY       = 0x01
SFF8472_CC_BASE                  = 63
SFF8472_CC_BASE_START            = 0

# QSFP+/QSFP28
SFF8636_CONNECTOR_ADDR           = 130
SFF8636_PWR_CTRL_ADDR            = 93
SFF8636_MOD_STATE_ADDR           = 2
SFF8636_MOD_STATE_NOT_READY      = 0x01
SFF8636_DOM_TEMP_ADDR            = 22
SFF8636_DOM_TEMP_WARM_HI_ADDR    = (132 & 0x7f) | 0x200
SFF8636_DOM_TEMP_WARM_LO_ADDR    = (134 & 0x7f) | 0x200
SFF8636_DOM_VOLT_ADDR            = 26
SFF8636_DOM_VOLT_WARM_HI_ADDR    = (148 & 0x7f) | 0x200
SFF8636_DOM_VOLT_WARM_LO_ADDR    = (150 & 0x7f) | 0x200
SFF8636_DOM_RXPWR_ADDR           = 34
SFF8636_DOM_RXPWR_WARM_HI_ADDR   = (180 & 0x7f) | 0x200
SFF8636_DOM_RXPWR_WARM_LO_ADDR   = (182 & 0x7f) | 0x200
SFF8636_DOM_TXPWR_ADDR           = 50
SFF8636_DOM_TXPWR_WARM_HI_ADDR   = (196 & 0x7f) | 0x200
SFF8636_DOM_TXPWR_WARM_LO_ADDR   = (198 & 0x7f) | 0x200
SFF8636_DOM_CHAN_MON_ADDR        = 34
SFF8636_DOM_TYPE_ADDR            = 220
SFF8636_DOM_THRES_ADDR           = 512
SFF8636_DOM_THRES_MODULE_OFFSET  = 0
SFF8636_DOM_THRES_CHANNEL_OFFSET = 48
SFF8636_CC_BASE                  = 191
SFF8636_CC_BASE_START            = 129

# CMIS 4.0/5.0 specs have similar EEPROM bit offsets
# QSFP-DD/QSFP56
CMIS_CONNECTOR_ADDR             = 203
CMIS_IMPL_MEM_PAGES_ADDR        = ((142 & 0x7f) | 0x100)
CMIS_PAGE_SIZE                  = 128
CMIS_PAGE_ADDR_00h              = ((0 + 1) << 7)
CMIS_PAGE_ADDR_01h              = ((1 + 1) << 7)
CMIS_PAGE_ADDR_02h              = ((2 + 1) << 7)
CMIS_PAGE_ADDR_10h              = ((16 + 1) << 7)
CMIS_PAGE_ADDR_11h              = ((17 + 1) << 7)
CMIS_DOM_THRES_ADDR             = CMIS_PAGE_ADDR_02h
CMIS_DOM_THRES_MODULE_OFFSET    = 0
CMIS_DOM_THRES_CHANNEL_OFFSET   = 48
CMIS_CHECKSUM                   = 222
CMIS_CHECKSUM_START             = 129

MOD_FLAGS_ADDR                   = 3
MOD_POWER_ADDR                   = 26
MOD_STATE_MASK                   = 0x7
MOD_STATE_READY                  = 3

# MIS2 (SFP-DD)
MIS2_IMPL_MEM_PAGES_ADDR        = ((142 & 0x7f) | 0x100)
MIS2_PAGE_SIZE                  = 128
MIS2_PAGE_ADDR_00h              = ((0 + 1) << 7)
MIS2_PAGE_ADDR_01h              = ((1 + 1) << 7)
MIS2_PAGE_ADDR_02h              = ((2 + 1) << 7)
MIS2_DOM_THRES_ADDR             = MIS2_PAGE_ADDR_01h
MIS2_DOM_THRES_MODULE_OFFSET    = 49
MIS2_DOM_THRES_CHANNEL_OFFSET   = 81

SFP_EEPROM_MANDATORY_FIELD_OFFSET_LIMIT = 256

class SfpStandard(SfpBase):
    """
    Abstract base class for interfacing with a SFP module
    """

    __metaclass__ = abc.ABCMeta

    CMIS_IDS = [0x18, 0x19]
    CMIS_REG_REV = 1
    CMIS_REG_MOD_CTRL = 26
    CMIS_REG_ID = 128

    CMIS_MOD_CTRL_SW_RESET = 0x08
    CMIS_MOD_CTRL_FORCE_LP = 0x10

    MIS_REG_REV = 1

    PORT_TYPE_NONE = 0
    PORT_TYPE_SFP = 1
    PORT_TYPE_QSFP = 2
    PORT_TYPE_QSFPDD = 3
    PORT_TYPE_SFPDD = 4

    def __init__(self):
        SfpBase.__init__(self)
        self.eeprom_lock = Lock()
        self.eeprom_cache = None

    @abc.abstractproperty
    def port_index(self):
        pass

    @abc.abstractproperty
    def port_type(self):
        pass

    @abc.abstractproperty
    def eeprom_path(self):
        pass

    # Read out any bytes from any offset
    def __read_eeprom(self, offset, num_bytes):
        """
        read eeprom specfic bytes beginning from a random offset with size as num_bytes

        Args:
             offset :
                     Integer, the offset from which the read transaction will start
             num_bytes:
                     Integer, the number of bytes to be read

        Returns:
            bytearray, if raw sequence of bytes are read correctly from the offset of size num_bytes
            None, if the read_eeprom fails
        """
        buf = None
        eeprom_raw = []
        sysfs_sfp_i2c_client_eeprom_path = self.eeprom_path

        if not self.get_presence():
            return None

        # Read retry logic to handle EEPROM read failures
        retry_expiry = 4  # Counter to retry for 1 second
        retry_interval = 0.25  # Delay between retries in seconds

        retry_count = 0

        sysfsfile_eeprom = None

        while retry_count < retry_expiry:
            try:
                if not sysfsfile_eeprom:
                    # Open the file only if it's not already open
                    sysfsfile_eeprom = open(sysfs_sfp_i2c_client_eeprom_path, "rb", 0)
                sysfsfile_eeprom.seek(offset)
                buf = sysfsfile_eeprom.read(num_bytes)
                break
            except IOError as ex:
                #If offset consists of crucial data, retry reading EEPROM
                if offset < SFP_EEPROM_MANDATORY_FIELD_OFFSET_LIMIT and \
                    (offset + num_bytes) <= SFP_EEPROM_MANDATORY_FIELD_OFFSET_LIMIT:
                    time.sleep(retry_interval)  # Sleep 250ms before retrying
                    retry_count += 1
                else:
                    #If non crucial data, do not perform read retry's
                    break

        if sysfsfile_eeprom is not None:
            sysfsfile_eeprom.close()

        if buf is None:
            return None

        # Python3: The returned buf is a int[]
        # Python2: The returned buf is a str[]
        # TODO: Remove this check once we no longer support Python 2
        if sys.version_info >= (3, 0):
            for x in buf:
                eeprom_raw.append(x)
        else:
            for x in buf:
                eeprom_raw.append(ord(x))
        while len(eeprom_raw) < num_bytes:
            eeprom_raw.append(0)
        return eeprom_raw

    # Read out any bytes from any offset
    def read_eeprom(self, offset, num_bytes):
        """
        read eeprom specfic bytes beginning from a random offset with size as num_bytes

        Args:
             offset :
                     Integer, the offset from which the read transaction will start
             num_bytes:
                     Integer, the number of bytes to be read

        Returns:
            bytearray, if raw sequence of bytes are read correctly from the offset of size num_bytes
            None, if the read_eeprom fails
        """
        self.eeprom_lock.acquire()
        bytes = self.__read_eeprom(offset, num_bytes)
        self.eeprom_lock.release()
        return bytes

    def __write_eeprom(self, offset, num_bytes, write_buffer):
        """
        write eeprom specfic bytes beginning from a random offset with size as num_bytes
        and write_buffer as the required bytes

        Args:
             offset :
                     Integer, the offset from which the read transaction will start
             num_bytes:
                     Integer, the number of bytes to be written
             write_buffer:
                     bytearray, raw bytes buffer which is to be written beginning at the offset

        Returns:
            a Boolean, true if the write succeeded and false if it did not succeed.
        """
        sysfs_sfp_i2c_client_eeprom_path = self.eeprom_path
        if not self.get_presence():
            return False

        sysfsfile_eeprom = None
        try:
            sysfsfile_eeprom = open(sysfs_sfp_i2c_client_eeprom_path, "wb", 0)
            sysfsfile_eeprom.seek(offset)
            # TODO: Remove this check once we no longer support Python 2
            if sys.version_info >= (3, 0):
                for i in range(num_bytes):
                    sysfsfile_eeprom.write(write_buffer[i].to_bytes(1, "little"))
            else:
                for i in range(num_bytes):
                    sysfsfile_eeprom.write(chr(write_buffer[i]))
        except Exception as ex:
            syslog.syslog(syslog.LOG_ERR, "port {0}: {1}: offset {2}: write failed: {3} ".format(self.port_index, sysfs_sfp_i2c_client_eeprom_path, hex(offset), ex))
            return False
        finally:
            if sysfsfile_eeprom is not None:
                sysfsfile_eeprom.close()

        return True

    def write_eeprom(self, offset, num_bytes, write_buffer):
        """
        write eeprom specfic bytes beginning from a random offset with size as num_bytes
        and write_buffer as the required bytes

        Args:
             offset :
                     Integer, the offset from which the read transaction will start
             num_bytes:
                     Integer, the number of bytes to be written
             write_buffer:
                     bytearray, raw bytes buffer which is to be written beginning at the offset

        Returns:
            a Boolean, true if the write succeeded and false if it did not succeed.
        """
        self.eeprom_lock.acquire()
        ret = self.__write_eeprom(offset, num_bytes, write_buffer)
        self.eeprom_lock.release()
        return ret

    def modify_eeprom_byte(self, offset, value, mask=0xff):
        buf = self.read_eeprom(offset, 1)
        if buf is None or len(buf) < 1:
            return False
        old = buf[0]
        new = value & mask
        ret = True
        if new != old & mask:
            buf = bytearray([(old & ~mask) | new])
            ret = self.write_eeprom(offset, 1, buf)
        return ret

    def get_module_type(self):
        buf = self.get_eeprom_cache_raw(0,1)
        return buf[0] if len(buf) > 0 else 0

    def get_module_type_raw(self):
        mt = self.get_module_type()
        return "{0:0{1}x}".format(mt, 2)

    def get_eeprom_raw(self, offset = 0, num_bytes = 256):
        buf = self.read_eeprom(offset, num_bytes)

        if buf is None:
            return None
        eeprom_raw = []
        for n in range(len(buf)):
            eeprom_raw.append("{0:0{1}x}".format(buf[n], 2))
        while len(eeprom_raw) < num_bytes:
            eeprom_raw.append("00")
        return eeprom_raw

    def get_eeprom_type(self, eeprom_ifraw = None):
        type = XCVR_EEPROM_TYPE_UNKNOWN

        raw = eeprom_ifraw
        if raw is None:
            return type

        if (self.port_type == self.PORT_TYPE_QSFP) or (self.port_type == self.PORT_TYPE_QSFPDD):

            # Some faulty modules have different type id at byte 0x00 and 0x80,
            # and one of them holds the correct value
            # e.g. "FIT HON TENG#CU4EP54-01000-EF", "Fiberstore#QSFP-4SFP10G-DACA"

            id1 = raw[0]
            id2 = raw[128]
            if id1 in SFF8024_TYPE_QSFP + SFF8024_TYPE_QSFPDD + \
                SFF8024_TYPE_QSFP_CMIS_COMPLIANT:
                id = id1
            elif id2 in SFF8024_TYPE_QSFP + SFF8024_TYPE_QSFPDD + \
                SFF8024_TYPE_QSFP_CMIS_COMPLIANT:
                id = id2
            # A special case of [Amphenol#NDAAFF-0001]
            elif id1 == '05' and id2 == '01':
                id = id1 = '11'
            else:
                id = SFF8024_TYPE_QSFP[0]

            try:
                if id in SFF8024_TYPE_QSFPDD + SFF8024_TYPE_QSFP_CMIS_COMPLIANT:
                    sfpi_obj = inf8628InterfaceId(raw)
                    sfp_data = sfpi_obj.get_data_pretty()
                    vend = sfp_data['data']['Vendor Name']
                    part = sfp_data['data']['Vendor Part Number']
                else:
                    sfpi_obj = sff8436InterfaceId(raw)
                    sfp_data = sfpi_obj.get_data_pretty()
                    vend = sfp_data['data']['Vendor Name']
                    part = sfp_data['data']['Vendor PN']
            except:
                vend = "Unknown"
                part = "Unknown"

            # Most of 'FIT HON TENG' modules are with broken checksum
            # And it may in QSFP28 format with vendor name truncated as 'FIT \0ON TENG'
            if 'FIT \0ON TENG' in part:
                raw[0] = raw[128] = id
                return XCVR_EEPROM_TYPE_QSFP
            elif vend == 'FIT HON TENG' and part == 'CU4EP54-01000-EF':
                raw[0] = raw[128] = id
                return XCVR_EEPROM_TYPE_QSFPDD

            # QSFPDD check code validation
            if id in SFF8024_TYPE_QSFPDD:
                sum = 0
                for i in range(CMIS_CHECKSUM_START, CMIS_CHECKSUM):
                    sum += int(raw[i], 16)
                if ((sum + int(id1, 16)) & 0xff) == int(raw[CMIS_CHECKSUM], 16) or \
                   ((sum + int(id2, 16)) & 0xff) == int(raw[CMIS_CHECKSUM], 16):
                    type = XCVR_EEPROM_TYPE_OSFP

            # QSFP56 validation
            if id in SFF8024_TYPE_QSFP_CMIS_COMPLIANT:
                qsfp56_eeprom_identifiers = [
                    (0x01, 0x0F, 0x0E, 0x44, 0x01),  #200G QSFP56 SR4
                    (0x02, 0x0F, 0x18, 0x44, 0x01)   #200G QSFP56 FR4
                    ]

                byte85 = int(raw[85], 16)
                byte86 = int(raw[86], 16)
                byte87 = int(raw[87], 16)
                byte88 = int(raw[88], 16)
                byte89 = int(raw[89], 16)
                eeprom_data = (byte85, byte86, byte87, byte88, byte89)
                if eeprom_data in qsfp56_eeprom_identifiers:
                    type = XCVR_EEPROM_TYPE_QSFP56

            # QSFP28 check code validation (CC_BASE)
            if type == XCVR_EEPROM_TYPE_UNKNOWN:
                # check if the media type is QSFP. SFP+/SFP28 may be connected
                # in QSFP port using QSA28 Adapter.
                if raw[0] in SFF8024_TYPE_QSFP:
                    sum = 0
                    for i in range(SFF8636_CC_BASE_START, SFF8636_CC_BASE):
                        sum += int(raw[i], 16)
                    if ((sum + int(id1, 16)) & 0xff) == int(raw[SFF8636_CC_BASE], 16) or \
                       ((sum + int(id2, 16)) & 0xff) == int(raw[SFF8636_CC_BASE], 16):
                        type = XCVR_EEPROM_TYPE_QSFP
            if type != XCVR_EEPROM_TYPE_UNKNOWN:
                raw[0] = raw[128] = id
            else:
                sfpi_obj = sff8436InterfaceId(eeprom_ifraw)
                sfp_data = sfpi_obj.get_data_pretty()
                # FIT ON TENG#U4DP34-0B001-EF, its checksum is totally broken
                if 'FIT' in sfp_data['data']['Vendor Name'] and \
                   'U4DP34-0B001-EF' in sfp_data['data']['Vendor PN']:
                    raw[0] = raw[128] = id
                    type = XCVR_EEPROM_TYPE_QSFP
        if type == XCVR_EEPROM_TYPE_UNKNOWN:
            if raw[0] in SFF8024_TYPE_SFPDD:
                type = XCVR_EEPROM_TYPE_SFPDD
            else:
                # SFP check code validation (CC_BASE)
                sum = 0
                for i in range(SFF8472_CC_BASE_START, SFF8472_CC_BASE):
                    sum += int(raw[i], 16)
                if (sum & 0xff) == int(raw[SFF8472_CC_BASE], 16):
                    type = XCVR_EEPROM_TYPE_SFP
        else:
            return type

        return type

    def __is_direct_attach_cable(self):
        code = None
        mtype = self.get_module_type_raw()
        if mtype in SFF8024_TYPE_SFP:
            code = self.get_eeprom_cache(SFF8472_CONNECTOR_ADDR, 1)
        elif mtype in SFF8024_TYPE_QSFP:
            code = self.get_eeprom_cache(SFF8636_CONNECTOR_ADDR, 1)
        elif mtype in SFF8024_TYPE_QSFPDD + SFF8024_TYPE_QSFP_CMIS_COMPLIANT:
            code = self.get_eeprom_cache(CMIS_CONNECTOR_ADDR, 1)

        if code is None or len(code) < 1:
            ctype = None
        else:
            ctype = connector_dict.get(code[0])
        if ctype in ['Copper pigtail', 'No separable connector']:
            return True
        return False

    def get_lpmode(self):
        """
        Retrieves the lpmode (low power mode) status of this SFP
        Returns:
            A Boolean, True if lpmode is enabled, False if disabled
        """
        lpmode = True
        try:
            is_sff8636 = False
            if self.port_type == self.PORT_TYPE_QSFP:
                is_sff8636 = True
            elif self.port_type == self.PORT_TYPE_QSFPDD:
                module_type = self.get_module_type_raw()
                if module_type not in SFF8024_TYPE_QSFPDD + \
                    SFF8024_TYPE_QSFP_CMIS_COMPLIANT:
                    is_sff8636 = True
            if is_sff8636:
                if self.__is_direct_attach_cable():
                    return True
                buf = self.read_eeprom(SFF8636_PWR_CTRL_ADDR, 1)
                if (buf is not None) and (buf[0] & 0x01):
                    lpmode = True if (buf[0] & 0x02) else False
        except:
            pass
        return lpmode

    def set_lpmode(self, lpmode):
        """
        Sets the lpmode (low power mode) of SFP

        Args:
            lpmode: A Boolean, True to enable lpmode, False to disable it
            Note  : lpmode can be overridden by set_power_override

        Returns:
            A boolean, True if lpmode is set successfully, False if not
        """
        ret = False
        try:
            is_sff8636 = False
            if self.port_type == self.PORT_TYPE_QSFP:
                is_sff8636 = True
            elif self.port_type == self.PORT_TYPE_QSFPDD:
                module_type = self.get_module_type_raw()
                if module_type not in SFF8024_TYPE_QSFPDD + \
                    SFF8024_TYPE_QSFP_CMIS_COMPLIANT:
                    is_sff8636 = True

            if is_sff8636:
                if self.__is_direct_attach_cable():
                    #print("\nSKIPPING DAC")
                    return True if lpmode else False
                buf = self.read_eeprom(SFF8636_PWR_CTRL_ADDR, 1)
                if buf is not None:
                    val = buf[0] & 0xf0
                    if lpmode:
                        val |= 0x03 # power class 1 only
                    else:
                        val |= 0x0d # power class 1-8
                    ret = self.write_eeprom(SFF8636_PWR_CTRL_ADDR, 1, [val])
        except:
            ret = False
        return ret

    def populate_eeprom_cache(self):
        """
        Per port EEPROM cache to avoid redudant EEPROM reads
        EEPROM cache contents are in HEX string format
        """
        
        if self.eeprom_cache is None:
            if (self.port_type == self.PORT_TYPE_QSFPDD) or (self.port_type == self.PORT_TYPE_SFPDD):
                eeprom_ifraw = self.get_eeprom_raw(0, 384)
            elif self.port_type == self.PORT_TYPE_QSFP:
                eeprom_ifraw = self.get_eeprom_raw(0, 256)
            else:
                eeprom_ifraw = self.get_eeprom_raw(0, 128)

            self.eeprom_cache = eeprom_ifraw

    def get_eeprom_cache_raw(self, offset=0, length=0):
        """
        This routine returns SFP EEPROM contents in INT format
        Offset = 0 returns whole cache. Otherwise the buffer returned will start from the
        Offset upto the length of bytes that needs to be read
        """

        buf = None
        if self.eeprom_cache is None:
            self.populate_eeprom_cache()

        if self.eeprom_cache is None:
            syslog.syslog(syslog.LOG_NOTICE, "Get EEPROM Cache Raw failed for Port : {} " \
                          "Offset : {} ".format(self.port_index, offset))
            return None

        # Convert EEPROM (HEX string) contents into HEX values. Before converting, copy
        # the original cache so that the EEPROM cache contents are not modified
        eeprom_bytes = self.eeprom_cache[:]
        for i in range(len(eeprom_bytes)):
            eeprom_bytes[i] = int(eeprom_bytes[i],16)

        if length == 0:
            buf = eeprom_bytes[offset:]
        else:
            buf = eeprom_bytes[offset:(offset+length)]
        return buf


    def clear_eeprom_cache(self):
        """
        Clear EEPROM cache
        """
        if self.eeprom_cache is not None:
            del self.eeprom_cache
            self.eeprom_cache = None

    def get_eeprom_cache(self, offset=0, length=0):
        """
        Read EEPROM cache for SFP object
        EEPROM cache contents are in HEX string format
        """
        buf = None
        if self.eeprom_cache is None:
            self.populate_eeprom_cache()

        if self.eeprom_cache is None:
            syslog.syslog(syslog.LOG_NOTICE, "Get EEPROM Cache failed for Port : {} " \
                          "Offset : {}".format(self.port_index, offset))
        else:
            if length == 0:
                buf = self.eeprom_cache[offset:]
            else:
                buf = self.eeprom_cache[offset:(offset+length)]
        return buf

    def get_transceiver_info(self):
        """
        Retrieves transceiver info of this SFP

        Returns:
            A dict which contains following keys/values :
        ================================================================================
        keys                       |Value Format   |Information
        ---------------------------|---------------|----------------------------
        type                       |1*255VCHAR     |type of SFP
        hardware_rev               |1*255VCHAR     |hardware version of SFP
        serial                     |1*255VCHAR     |serial number of the SFP
        manufacturer            |1*255VCHAR     |SFP vendor name
        model                      |1*255VCHAR     |SFP model name
        connector                  |1*255VCHAR     |connector information
        encoding                   |1*255VCHAR     |encoding information
        ext_identifier             |1*255VCHAR     |extend identifier
        ext_rateselect_compliance  |1*255VCHAR     |extended rateSelect compliance
        cable_length               |INT            |cable length in m
        nominal_bit_rate           |INT            |nominal bit rate by 100Mbs
        specification_compliance   |1*255VCHAR     |specification compliance
        vendor_date                |1*255VCHAR     |vendor date
        vendor_oui                 |1*255VCHAR     |vendor OUI
        application_advertisement  |1*255VCHAR     |supported applications advertisement
        ================================================================================
        """
        info_dict_keys = ['type', 'hardware_rev', 'serial', 'manufacturer',
                          'model', 'connector', 'encoding', 'ext_identifier',
                          'ext_rateselect_compliance', 'cable_type', 'cable_length', 'nominal_bit_rate',
                          'specification_compliance', 'type_abbrv_name','vendor_date', 'vendor_oui',
                          'application_advertisement']
        transceiver_info_dict = {}.fromkeys(info_dict_keys, 'N/A')

        #To avoid redudant EEPROM reads, maintaining a per port EEPROM cache
        self.populate_eeprom_cache()

        eeprom_ifraw = self.eeprom_cache

        if eeprom_ifraw is None:
            syslog.syslog(syslog.LOG_ERR, "Get Transceiver Failed while reading EEPROM " \
                          "Cache for Port : {}".format(self.port_index))
            return None

        type = self.get_eeprom_type(eeprom_ifraw)
        if type == XCVR_EEPROM_TYPE_UNKNOWN:
            return None

        sfpi_obj = None
        sfp_data = None
        sfp_keys = {}
        if type in (XCVR_EEPROM_TYPE_QSFPDD, XCVR_EEPROM_TYPE_QSFP56):
            sfpi_obj = inf8628InterfaceId(eeprom_ifraw)
            if sfpi_obj is None:
                return None
            sfp_data = sfpi_obj.get_data_pretty()

            sfp_keys['type']             = 'Identifier'
            sfp_keys['type_abbrv_name']  = 'type_abbrv_name'
            sfp_keys['manufacturer']     = 'Vendor Name'
            sfp_keys['model']            = 'Vendor Part Number'
            sfp_keys['hardware_rev']     = 'Vendor Revision'
            sfp_keys['serial']           = 'Vendor Serial Number'
            sfp_keys['vendor_date']      = 'Vendor Date Code(YYYY-MM-DD Lot)'
            sfp_keys['vendor_oui']       = 'Vendor OUI'
            sfp_keys['module_state']     = 'Module State'
            sfp_keys['media_type']       = 'Media Type'
            sfp_keys['memory_type']      = 'Upper Memory Type'
            sfp_keys['power_class']      = 'Power Class'
            sfp_keys['revision_compliance'] = 'Revision Compliance'

            for key in cmis_cable_length_types:
                if key in sfp_data['data']:
                    if sfp_data['data'][key] <= 0:
                        continue
                    transceiver_info_dict['cable_type'] = key
                    transceiver_info_dict['cable_length'] = str(sfp_data['data'][key])
                    break

            app_adv_dict = sfp_data['data'].get('Application Advertisement')
            if (app_adv_dict is not None) and len(app_adv_dict) > 0:
                transceiver_info_dict['application_advertisement'] = str(app_adv_dict)

            # Set the Max Speed based on the Media Type from EEPROM
            if type == XCVR_EEPROM_TYPE_QSFP56:
                # QSFP56 modules use 4 HW lanes and support 200G
                transceiver_info_dict['xcvr_speed_max'] = '200000'
            else:
                # As of today, all the known QSFPDD modules support 400G
                transceiver_info_dict['xcvr_speed_max'] = '400000'

            # It's expected that PAGE1 could be unavailable
            mem_page_raw = self.get_eeprom_raw(CMIS_IMPL_MEM_PAGES_ADDR, 1)
            if mem_page_raw is None:
                mem_page_raw = ['00']

            mem_page_data = sfpi_obj.parse_implemented_memory_pages(mem_page_raw, 0)
            if mem_page_data is not None:
                transceiver_info_dict['memory_pages'] = mem_page_data['data']['Implemented Memory Pages']['value']

            if 'Diagnostic Pages Implemented' in transceiver_info_dict['memory_pages']:
                diag_raw = self.get_eeprom_raw(0xa00, 32)
                if diag_raw is None:
                    return transceiver_info_dict
                sfpd_obj = inf8628Diag(diag_raw)
                if sfpd_obj is None:
                    return transceiver_info_dict
                diag_data = sfpd_obj.get_data_pretty()
                if diag_data is None:
                    return transceiver_info_dict
                transceiver_info_dict['diag_caps_loopback'] = diag_data['data']['Loopback Capabilities']
                transceiver_info_dict['diag_caps_pattern'] = diag_data['data']['General Pattern Capabilities']
                transceiver_info_dict['diag_caps_pattern_gen_host'] = diag_data['data']['Pattern Generator Capabilities - Host']
                transceiver_info_dict['diag_caps_pattern_gen_media'] = diag_data['data']['Pattern Generator Capabilities - Media']
                transceiver_info_dict['diag_caps_pattern_chk_host'] = diag_data['data']['Pattern Checker Capabilities - Host']
                transceiver_info_dict['diag_caps_pattern_chk_media'] = diag_data['data']['Pattern Checker Capabilities - Media']
                transceiver_info_dict['diag_caps_report'] = diag_data['data']['Reporting Capabilities']

        elif type == XCVR_EEPROM_TYPE_QSFP:
            sfpi_obj = sff8436InterfaceId(eeprom_ifraw)
            if sfpi_obj is None:
                return None
            sfp_data = sfpi_obj.get_data_pretty()
            link_code = sfpi_obj.parse_link_code(eeprom_ifraw, 192)
            if link_code in [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x17, 0x18, \
                            0x1A, 0x1B, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27]:
                wavelength_data = sfpi_obj.parse_wavelength(eeprom_ifraw, 186)
                transceiver_info_dict['wavelength'] = wavelength_data['data']['Wavelength']['value']

            sfp_keys['type']             = 'Identifier'
            sfp_keys['type_abbrv_name']  = 'type_abbrv_name'
            sfp_keys['ext_identifier']   = 'Extended Identifier'
            sfp_keys['encoding']         = 'Encoding'
            sfp_keys['ext_rateselect_compliance'] = 'Extended RateSelect Compliance'
            sfp_keys['connector']        = 'Connector'
            sfp_keys['hardware_rev']     = 'Vendor Rev'
            sfp_keys['manufacturer']     = 'Vendor Name'
            sfp_keys['model']            = 'Vendor PN'
            sfp_keys['memory_type']      = 'Upper Memory Type'
            sfp_keys['nominal_bit_rate'] = 'Nominal Bit Rate(100Mbs)'
            sfp_keys['serial']           = 'Vendor SN'
            sfp_keys['vendor_date']      = 'Vendor Date Code(YYYY-MM-DD Lot)'
            sfp_keys['vendor_oui']       = 'Vendor OUI'

            for key in qsfp_cable_length_types:
                if key in sfp_data['data']:
                    if sfp_data['data'][key] <= 0:
                        continue
                    transceiver_info_dict['cable_type'] = key
                    transceiver_info_dict['cable_length'] = str(sfp_data['data'][key])
                    break

            compliance_code_dict = sfp_data['data'].get('Specification compliance')
            if (compliance_code_dict is not None) and len(compliance_code_dict) > 0:
                transceiver_info_dict['specification_compliance'] = str(compliance_code_dict)

            if '100G' in compliance_code_dict['10/40G Ethernet Compliance Code']:
                transceiver_info_dict['xcvr_speed_max'] = '100000'
            else:
                transceiver_info_dict['xcvr_speed_max'] = '40000'

        elif type == XCVR_EEPROM_TYPE_SFP:
            sfpi_obj = sff8472InterfaceId(eeprom_ifraw)
            if sfpi_obj is None:
                return None
            sfp_data = sfpi_obj.get_data_pretty()

            sfp_keys['type']             = 'TypeOfTransceiver'
            sfp_keys['type_abbrv_name']  = 'type_abbrv_name'
            sfp_keys['manufacturer']     = 'VendorName'
            sfp_keys['model']            = 'VendorPN'
            sfp_keys['hardware_rev']     = 'VendorRev'
            sfp_keys['serial']           = 'VendorSN'
            sfp_keys['connector']        = 'Connector'
            sfp_keys['encoding']         = 'EncodingCodes'
            sfp_keys['ext_identifier']   = 'ExtIdentOfTypeOfTransceiver'
            sfp_keys['nominal_bit_rate'] = 'NominalSignallingRate(UnitsOf100Mbd)'
            sfp_keys['vendor_date']      = 'VendorDataCode(YYYY-MM-DD Lot)'
            sfp_keys['vendor_oui']       = 'VendorOUI'
            sfp_keys['option_values']    = 'OptionValues'

            for key in sfp_cable_length_types:
                if key in sfp_data['data']:
                    if sfp_data['data'][key] <= 0:
                        continue
                    transceiver_info_dict['cable_type'] = key
                    transceiver_info_dict['cable_length'] = str(sfp_data['data'][key])
                    break

            compliance_code_dict = sfp_data['data'].get('TransceiverCodes')
            if (compliance_code_dict is not None) and len(compliance_code_dict) > 0:
                transceiver_info_dict['specification_compliance'] = str(compliance_code_dict)

            nbr_s = sfp_data['data']['NominalSignallingRate(UnitsOf100Mbd)']
            if nbr_s == 'N/A':
                transceiver_info_dict['xcvr_speed_max'] = '25000'
            try:
                nbr = int(nbr_s)
            except:
                nbr = 250
            if nbr >= 250:
                transceiver_info_dict['xcvr_speed_max'] = '25000'
            elif nbr >= 100:
                transceiver_info_dict['xcvr_speed_max'] = '10000'
            else:
                transceiver_info_dict['xcvr_speed_max'] = '1000'

        elif type == XCVR_EEPROM_TYPE_SFPDD:
            sfpi_obj = mis2InterfaceId(eeprom_ifraw)
            if sfpi_obj is None:
                return None
            sfp_data = sfpi_obj.get_data_pretty()

            sfp_keys['type']             = 'Identifier'
            sfp_keys['type_abbrv_name']  = 'type_abbrv_name'
            sfp_keys['manufacturer']     = 'Vendor Name'
            sfp_keys['model']            = 'Vendor Part Number'
            sfp_keys['hardware_rev']     = 'Vendor Revision'
            sfp_keys['serial']           = 'Vendor Serial Number'
            sfp_keys['vendor_date']      = 'Vendor Date Code(YYYY-MM-DD Lot)'
            sfp_keys['vendor_oui']       = 'Vendor OUI'
            sfp_keys['module_state']     = 'Module State'
            sfp_keys['media_type']       = 'Media Type'
            sfp_keys['memory_type']      = 'Upper Memory Type'
            sfp_keys['power_class']      = 'Power Class'
            sfp_keys['revision_compliance'] = 'Revision Compliance'

            for key in mis_cable_length_types:
                if key in sfp_data['data']:
                    if sfp_data['data'][key] <= 0:
                        continue
                    transceiver_info_dict['cable_type'] = key
                    transceiver_info_dict['cable_length'] = str(sfp_data['data'][key])
                    break

            app_adv_dict = sfp_data['data'].get('Application Advertisement')
            if (app_adv_dict is not None) and len(app_adv_dict) > 0:
                transceiver_info_dict['application_advertisement'] = str(app_adv_dict)

            # As of today, all the known SFPDD modules support 100G
            transceiver_info_dict['xcvr_speed_max'] = '100000'

            # It's expected that PAGE1 could be unavailable
            mem_page_raw = self.get_eeprom_raw(MIS2_IMPL_MEM_PAGES_ADDR, 1)
            if mem_page_raw is None:
                mem_page_raw = ['00']

            mem_page_data = sfpi_obj.parse_implemented_memory_pages(mem_page_raw, 0)
            if mem_page_data is not None:
                transceiver_info_dict['memory_pages'] = mem_page_data['data']['Implemented Memory Pages']['value']

            if 'Diagnostic Pages Implemented' in transceiver_info_dict['memory_pages']:
                diag_raw = self.get_eeprom_raw(0xa00, 32)
                if diag_raw is None:
                    return transceiver_info_dict
                sfpd_obj = mis2Diag(diag_raw)
                if sfpd_obj is None:
                    return transceiver_info_dict
                diag_data = sfpd_obj.get_data_pretty()
                if diag_data is None:
                    return transceiver_info_dict
                transceiver_info_dict['diag_caps_loopback'] = diag_data['data']['Loopback Capabilities']
                transceiver_info_dict['diag_caps_pattern'] = diag_data['data']['General Pattern Capabilities']
                transceiver_info_dict['diag_caps_pattern_gen_host'] = diag_data['data']['Pattern Generator Capabilities - Host']
                transceiver_info_dict['diag_caps_pattern_gen_media'] = diag_data['data']['Pattern Generator Capabilities - Media']
                transceiver_info_dict['diag_caps_pattern_chk_host'] = diag_data['data']['Pattern Checker Capabilities - Host']
                transceiver_info_dict['diag_caps_pattern_chk_media'] = diag_data['data']['Pattern Checker Capabilities - Media']
        for k in sfp_keys:
            dict = sfp_data['data']
            name = sfp_keys[k]
            if name in dict:
                transceiver_info_dict[k] = str(dict[name])
            else:
                transceiver_info_dict[k] = 'N/A'

        return transceiver_info_dict

    def get_transceiver_bulk_status(self):
        """
        Retrieves transceiver bulk status of this SFP

        Returns:
            A dict which contains following keys/values :
        ========================================================================
        keys                       |Value Format   |Information
        ---------------------------|---------------|----------------------------
        rx_los                     |BOOLEAN        |RX loss-of-signal status, True if has RX los, False if not.
        tx_fault                   |BOOLEAN        |TX fault status, True if has TX fault, False if not.
        reset_status               |BOOLEAN        |reset status, True if SFP in reset, False if not.
        lp_mode                    |BOOLEAN        |low power mode status, True in lp mode, False if not.
        tx_disable                 |BOOLEAN        |TX disable status, True TX disabled, False if not.
        tx_disabled_channel        |HEX            |disabled TX channels in hex, bits 0 to 3 represent channel 0
                                   |               |to channel 3.
        temperature                |INT            |module temperature in Celsius
        voltage                    |INT            |supply voltage in mV
        tx<n>bias                  |INT            |TX Bias Current in mA, n is the channel number,
                                   |               |for example, tx2bias stands for tx bias of channel 2.
        rx<n>power                 |INT            |received optical power in mW, n is the channel number,
                                   |               |for example, rx2power stands for rx power of channel 2.
        tx<n>power                 |INT            |TX output power in mW, n is the channel number,
                                   |               |for example, tx2power stands for tx power of channel 2.
        ========================================================================
        """
        transceiver_dom_info_dict = {}

        dom_info_dict_keys = ['temperature', 'voltage',  'rx1power',
                              'rx2power',    'rx3power', 'rx4power',
                              'tx1bias',     'tx2bias',  'tx3bias',
                              'tx4bias',     'tx1power', 'tx2power',
                              'tx3power',    'tx4power',
                             ]
        transceiver_dom_info_dict = {}.fromkeys(dom_info_dict_keys, 'N/A')

        eeprom_ifraw = self.get_eeprom_raw()

        if eeprom_ifraw is None:
            return transceiver_dom_info_dict

        type = self.get_eeprom_type(eeprom_ifraw)

        if type == XCVR_EEPROM_TYPE_UNKNOWN:
            return transceiver_dom_info_dict

        elif type in (XCVR_EEPROM_TYPE_QSFPDD, XCVR_EEPROM_TYPE_QSFP56):
            dom_raw = [ '00' for i in range(CMIS_PAGE_ADDR_11h + CMIS_PAGE_SIZE) ]
            dom_pos = 0
            for x in eeprom_ifraw:
                dom_raw[dom_pos] = x
                dom_pos += 1
            dom_pos = CMIS_PAGE_ADDR_11h
            # Refresh the Lane-specific Clear-on-Read registers (e.g. LOS, LOL...)
            tmp = self.get_eeprom_raw(dom_pos + (137 & 0x7f), 16)
            tmp = self.get_eeprom_raw(dom_pos, CMIS_PAGE_SIZE)
            if tmp is not None:
                for x in tmp:
                    dom_raw[dom_pos] = x
                    dom_pos += 1

            sfpd_obj = inf8628Dom(dom_raw)
            if sfpd_obj is None:
                return transceiver_dom_info_dict
            dom_data = sfpd_obj.get_data_pretty()
            if dom_data is None:
                return transceiver_dom_info_dict

            transceiver_dom_info_dict['temperature'] = dom_data['data']['Temperature']
            transceiver_dom_info_dict['voltage'] = dom_data['data']['Vcc']
            transceiver_dom_info_dict['rx1power'] = dom_data['data']['RX1Power']
            transceiver_dom_info_dict['rx2power'] = dom_data['data']['RX2Power']
            transceiver_dom_info_dict['rx3power'] = dom_data['data']['RX3Power']
            transceiver_dom_info_dict['rx4power'] = dom_data['data']['RX4Power']
            transceiver_dom_info_dict['rx5power'] = dom_data['data']['RX5Power']
            transceiver_dom_info_dict['rx6power'] = dom_data['data']['RX6Power']
            transceiver_dom_info_dict['rx7power'] = dom_data['data']['RX7Power']
            transceiver_dom_info_dict['rx8power'] = dom_data['data']['RX8Power']
            transceiver_dom_info_dict['tx1bias'] = dom_data['data']['TX1Bias']
            transceiver_dom_info_dict['tx2bias'] = dom_data['data']['TX2Bias']
            transceiver_dom_info_dict['tx3bias'] = dom_data['data']['TX3Bias']
            transceiver_dom_info_dict['tx4bias'] = dom_data['data']['TX4Bias']
            transceiver_dom_info_dict['tx5bias'] = dom_data['data']['TX5Bias']
            transceiver_dom_info_dict['tx6bias'] = dom_data['data']['TX6Bias']
            transceiver_dom_info_dict['tx7bias'] = dom_data['data']['TX7Bias']
            transceiver_dom_info_dict['tx8bias'] = dom_data['data']['TX8Bias']
            transceiver_dom_info_dict['tx1power'] = dom_data['data']['TX1Power']
            transceiver_dom_info_dict['tx2power'] = dom_data['data']['TX2Power']
            transceiver_dom_info_dict['tx3power'] = dom_data['data']['TX3Power']
            transceiver_dom_info_dict['tx4power'] = dom_data['data']['TX4Power']
            transceiver_dom_info_dict['tx5power'] = dom_data['data']['TX5Power']
            transceiver_dom_info_dict['tx6power'] = dom_data['data']['TX6Power']
            transceiver_dom_info_dict['tx7power'] = dom_data['data']['TX7Power']
            transceiver_dom_info_dict['tx8power'] = dom_data['data']['TX8Power']

        elif type == XCVR_EEPROM_TYPE_QSFP:
            sfpd_obj = sff8436Dom()
            if sfpd_obj is None:
                return transceiver_dom_info_dict

            dom_temperature_data = sfpd_obj.parse_temperature(eeprom_ifraw, SFF8636_DOM_TEMP_ADDR)
            dom_voltage_data = sfpd_obj.parse_voltage(eeprom_ifraw, SFF8636_DOM_VOLT_ADDR)
            dom_channel_monitor_data = sfpd_obj.parse_channel_monitor_params_with_tx_power(eeprom_ifraw, SFF8636_DOM_CHAN_MON_ADDR)
            if (int(eeprom_ifraw[SFF8636_DOM_TYPE_ADDR], 16) & 0x04) > 0:
                transceiver_dom_info_dict['tx1power'] = dom_channel_monitor_data['data']['TX1Power']['value']
                transceiver_dom_info_dict['tx2power'] = dom_channel_monitor_data['data']['TX2Power']['value']
                transceiver_dom_info_dict['tx3power'] = dom_channel_monitor_data['data']['TX3Power']['value']
                transceiver_dom_info_dict['tx4power'] = dom_channel_monitor_data['data']['TX4Power']['value']
            transceiver_dom_info_dict['temperature'] = dom_temperature_data['data']['Temperature']['value']
            transceiver_dom_info_dict['voltage'] = dom_voltage_data['data']['Vcc']['value']
            transceiver_dom_info_dict['rx1power'] = dom_channel_monitor_data['data']['RX1Power']['value']
            transceiver_dom_info_dict['rx2power'] = dom_channel_monitor_data['data']['RX2Power']['value']
            transceiver_dom_info_dict['rx3power'] = dom_channel_monitor_data['data']['RX3Power']['value']
            transceiver_dom_info_dict['rx4power'] = dom_channel_monitor_data['data']['RX4Power']['value']
            transceiver_dom_info_dict['tx1bias'] = dom_channel_monitor_data['data']['TX1Bias']['value']
            transceiver_dom_info_dict['tx2bias'] = dom_channel_monitor_data['data']['TX2Bias']['value']
            transceiver_dom_info_dict['tx3bias'] = dom_channel_monitor_data['data']['TX3Bias']['value']
            transceiver_dom_info_dict['tx4bias'] = dom_channel_monitor_data['data']['TX4Bias']['value']

        elif type == XCVR_EEPROM_TYPE_SFPDD:
            # Refresh the Lane-specific Clear-on-Read registers (e.g. LOS, LOL...)
            tmp = self.get_eeprom_raw(6, 4)

            sfpd_obj = mis2Dom(eeprom_ifraw)
            if sfpd_obj is None:
                return transceiver_dom_info_dict
            dom_data = sfpd_obj.get_data_pretty()
            if dom_data is None:
                return transceiver_dom_info_dict

            transceiver_dom_info_dict['temperature'] = dom_data['data']['Temperature']
            transceiver_dom_info_dict['voltage'] = dom_data['data']['Vcc']
            transceiver_dom_info_dict['rx1power'] = dom_data['data']['RX1Power']
            transceiver_dom_info_dict['rx2power'] = dom_data['data']['RX2Power']
            transceiver_dom_info_dict['tx1bias'] = dom_data['data']['TX1Bias']
            transceiver_dom_info_dict['tx2bias'] = dom_data['data']['TX2Bias']
            transceiver_dom_info_dict['tx1power'] = dom_data['data']['TX1Power']
            transceiver_dom_info_dict['tx2power'] = dom_data['data']['TX2Power']

        else:
            dom_raw = [ '00' for i in range(128) ]

            dom_temp_raw = self.get_eeprom_raw(SFF8472_DOM_TEMP_ADDR, 16)
            if dom_temp_raw is None:
                return transceiver_dom_info_dict
            for i in range(len(dom_temp_raw)):
                dom_raw[(SFF8472_DOM_TEMP_ADDR & 0xff) + i] = dom_temp_raw[i]

            dom_stcr_raw = self.get_eeprom_raw(SFF8472_DOM_STCR_ADDR, 1)
            if dom_stcr_raw is None:
                return transceiver_dom_info_dict
            for i in range(len(dom_stcr_raw)):
                dom_raw[(SFF8472_DOM_STCR_ADDR & 0xff) + i] = dom_stcr_raw[i]

            sfpd_obj = sff8472Dom(eeprom_raw_data=dom_raw, calibration_type=1)
            if sfpd_obj is None:
                return transceiver_dom_info_dict
            dom_data = sfpd_obj.get_data_pretty()
            transceiver_dom_info_dict['temperature'] = dom_data['data']['MonitorData']['Temperature']
            transceiver_dom_info_dict['voltage']     = dom_data['data']['MonitorData']['Vcc']
            transceiver_dom_info_dict['rx1power']    = dom_data['data']['MonitorData']['RXPower']
            transceiver_dom_info_dict['tx1power']    = dom_data['data']['MonitorData']['TXPower']
            transceiver_dom_info_dict['tx1bias']     = dom_data['data']['MonitorData']['TXBias']
            transceiver_dom_info_dict['rx1los']      = dom_data['data']['StatusControl']['RXLOSState']
            transceiver_dom_info_dict['rx1los']      = 'true' if transceiver_dom_info_dict['rx1los'] == 'On' else 'false'
            transceiver_dom_info_dict['tx1disable']  = dom_data['data']['StatusControl']['TXDisableState']
            transceiver_dom_info_dict['tx1disable']  = 'true' if transceiver_dom_info_dict['tx1disable'] == 'On' else 'false'
            transceiver_dom_info_dict['tx1fault']    = dom_data['data']['StatusControl']['TXFaultState']
            transceiver_dom_info_dict['tx1fault']    = 'true' if transceiver_dom_info_dict['tx1fault'] == 'On' else 'false'

        return transceiver_dom_info_dict

    def get_transceiver_diag_status(self):
        transceiver_diag_info_dict = {}

        if (self.port_type != self.PORT_TYPE_QSFPDD) and (self.port_type != self.PORT_TYPE_SFPDD):
            return transceiver_diag_info_dict

        module_type = self.get_module_type_raw()
        if module_type not in SFF8024_TYPE_QSFPDD + \
            SFF8024_TYPE_QSFP_CMIS_COMPLIANT:
            return transceiver_diag_info_dict

        if self.__is_direct_attach_cable():
            return transceiver_diag_info_dict

        # CMIS/MIS Module State (0x03 at lower page)
        if self.port_type == self.PORT_TYPE_QSFPDD:
            sfpi_obj = inf8628InterfaceId()
        elif self.port_type == self.PORT_TYPE_SFPDD:
            sfpi_obj = mis2InterfaceId()
        if sfpi_obj is None:
            return None
        diag_raw = self.get_eeprom_raw(0x03, 1)
        if diag_raw is None:
            return transceiver_diag_info_dict
        diag_data = sfpi_obj.parse_module_state(diag_raw, 0)
        if diag_data is None:
            return transceiver_diag_info_dict
        transceiver_diag_info_dict['module_state'] = diag_data['data']['Module State']['value']

        # CMIS/MIS DIAG (13h, 14h)
        if self.port_type == self.PORT_TYPE_QSFPDD:
            sfpd_obj = inf8628Diag()
        elif self.port_type == self.PORT_TYPE_SFPDD:
            sfpd_obj = mis2Diag()
        if sfpd_obj is None:
            return transceiver_diag_info_dict

        caps = self.read_eeprom(0xa02, 1)
        if caps is None:
            return transceiver_diag_info_dict

        if self.port_type == self.PORT_TYPE_QSFPDD:
            rev = self.read_eeprom(SfpStandard.CMIS_REG_REV, 1)
            revision = 0x30
        elif self.port_type == self.PORT_TYPE_SFPDD:
            rev = self.read_eeprom(SfpStandard.MIS_REG_REV, 1)
            revision = 0x20
        if (rev[0] >= revision):
            buf = self.read_eeprom(MOD_FLAGS_ADDR, 1)
            lwp = self.read_eeprom(MOD_POWER_ADDR, 1)
            sta = (buf[0] >> 1) & MOD_STATE_MASK
            if ((sta != MOD_STATE_READY) or (lwp[0] != 0)):
                return transceiver_diag_info_dict
        # PRBS controls
        prbs_cr = [144 & 0x7f, 152 & 0x7f, 160 & 0x7f, 168 & 0x7f]
        prbs_en = False
        for cr in prbs_cr:
            buf = self.read_eeprom(0xa00 + cr, 1)
            if (buf is not None and len(buf) > 0 and buf[0] > 0):
                prbs_en = True
                break
        if not prbs_en:
            return transceiver_diag_info_dict
        # BER
        if (caps[0] & 0x01) > 0:
            self.write_eeprom(0xa80, 1, [0x01])
            time.sleep(1)
            diag_raw = self.get_eeprom_raw(0xac0, 32)
            if diag_raw is None:
                return transceiver_diag_info_dict
            diag_data = sfpd_obj.parse_ber(diag_raw, 0)
            if diag_data is None:
                return transceiver_diag_info_dict
            if self.port_type == self.PORT_TYPE_QSFPDD:
                transceiver_diag_info_dict['diag_host_ber1'] = diag_data['data']['BER1']['value']
                transceiver_diag_info_dict['diag_host_ber2'] = diag_data['data']['BER2']['value']
                transceiver_diag_info_dict['diag_host_ber3'] = diag_data['data']['BER3']['value']
                transceiver_diag_info_dict['diag_host_ber4'] = diag_data['data']['BER4']['value']
                transceiver_diag_info_dict['diag_host_ber5'] = diag_data['data']['BER5']['value']
                transceiver_diag_info_dict['diag_host_ber6'] = diag_data['data']['BER6']['value']
                transceiver_diag_info_dict['diag_host_ber7'] = diag_data['data']['BER7']['value']
                transceiver_diag_info_dict['diag_host_ber8'] = diag_data['data']['BER8']['value']
            elif self.port_type == self.PORT_TYPE_SFPDD:
                transceiver_diag_info_dict['diag_host_ber1'] = diag_data['data']['BER1']['value']
                transceiver_diag_info_dict['diag_host_ber2'] = diag_data['data']['BER2']['value'] 

            diag_data = sfpd_obj.parse_ber(diag_raw, 16)
            if diag_data is None:
                return transceiver_diag_info_dict
            if self.port_type == self.PORT_TYPE_QSFPDD:
                transceiver_diag_info_dict['diag_media_ber1'] = diag_data['data']['BER1']['value']
                transceiver_diag_info_dict['diag_media_ber2'] = diag_data['data']['BER2']['value']
                transceiver_diag_info_dict['diag_media_ber3'] = diag_data['data']['BER3']['value']
                transceiver_diag_info_dict['diag_media_ber4'] = diag_data['data']['BER4']['value']
                transceiver_diag_info_dict['diag_media_ber5'] = diag_data['data']['BER5']['value']
                transceiver_diag_info_dict['diag_media_ber6'] = diag_data['data']['BER6']['value']
                transceiver_diag_info_dict['diag_media_ber7'] = diag_data['data']['BER7']['value']
                transceiver_diag_info_dict['diag_media_ber8'] = diag_data['data']['BER8']['value']
            elif self.port_type == self.PORT_TYPE_SFPDD:
                transceiver_diag_info_dict['diag_media_ber1'] = diag_data['data']['BER1']['value']
                transceiver_diag_info_dict['diag_media_ber2'] = diag_data['data']['BER2']['value']
        # SNR
        if (caps[0] & 0x30) > 0:
            self.write_eeprom(0xa80, 1, [0x06])
            time.sleep(1)
            diag_raw = self.get_eeprom_raw(0xac0, 64)
            if diag_raw is None:
                return transceiver_diag_info_dict

            diag_data = sfpd_obj.parse_snr(diag_raw, 16)
            if diag_data is None:
                return transceiver_diag_info_dict
            if self.port_type == self.PORT_TYPE_QSFPDD:
                transceiver_diag_info_dict['diag_host_snr1'] = diag_data['data']['SNR1']['value']
                transceiver_diag_info_dict['diag_host_snr2'] = diag_data['data']['SNR2']['value']
                transceiver_diag_info_dict['diag_host_snr3'] = diag_data['data']['SNR3']['value']
                transceiver_diag_info_dict['diag_host_snr4'] = diag_data['data']['SNR4']['value']
                transceiver_diag_info_dict['diag_host_snr5'] = diag_data['data']['SNR5']['value']
                transceiver_diag_info_dict['diag_host_snr6'] = diag_data['data']['SNR6']['value']
                transceiver_diag_info_dict['diag_host_snr7'] = diag_data['data']['SNR7']['value']
                transceiver_diag_info_dict['diag_host_snr8'] = diag_data['data']['SNR8']['value']
            elif self.port_type == self.PORT_TYPE_SFPDD:
                transceiver_diag_info_dict['diag_host_snr1'] = diag_data['data']['SNR1']['value']
                transceiver_diag_info_dict['diag_host_snr2'] = diag_data['data']['SNR2']['value']

            diag_data = sfpd_obj.parse_snr(diag_raw, 48)
            if diag_data is None:
                return transceiver_diag_info_dict
            if self.port_type == self.PORT_TYPE_QSFPDD:
                transceiver_diag_info_dict['diag_media_snr1'] = diag_data['data']['SNR1']['value']
                transceiver_diag_info_dict['diag_media_snr2'] = diag_data['data']['SNR2']['value']
                transceiver_diag_info_dict['diag_media_snr3'] = diag_data['data']['SNR3']['value']
                transceiver_diag_info_dict['diag_media_snr4'] = diag_data['data']['SNR4']['value']
                transceiver_diag_info_dict['diag_media_snr5'] = diag_data['data']['SNR5']['value']
                transceiver_diag_info_dict['diag_media_snr6'] = diag_data['data']['SNR6']['value']
                transceiver_diag_info_dict['diag_media_snr7'] = diag_data['data']['SNR7']['value']
                transceiver_diag_info_dict['diag_media_snr8'] = diag_data['data']['SNR8']['value']
            elif self.port_type == self.PORT_TYPE_SFPDD:
                transceiver_diag_info_dict['diag_media_snr1'] = diag_data['data']['SNR1']['value']
                transceiver_diag_info_dict['diag_media_snr2'] = diag_data['data']['SNR2']['value']

        return transceiver_diag_info_dict

    def get_transceiver_threshold_info(self):
        """
        Retrieves transceiver threshold info of this SFP

        Returns:
            A dict which contains following keys/values :
        ========================================================================
        keys                       |Value Format   |Information
        ---------------------------|---------------|----------------------------
        temphighalarm              |FLOAT          |High Alarm Threshold value of temperature in Celsius.
        templowalarm               |FLOAT          |Low Alarm Threshold value of temperature in Celsius.
        temphighwarning            |FLOAT          |High Warning Threshold value of temperature in Celsius.
        templowwarning             |FLOAT          |Low Warning Threshold value of temperature in Celsius.
        vcchighalarm               |FLOAT          |High Alarm Threshold value of supply voltage in mV.
        vcclowalarm                |FLOAT          |Low Alarm Threshold value of supply voltage in mV.
        vcchighwarning             |FLOAT          |High Warning Threshold value of supply voltage in mV.
        vcclowwarning              |FLOAT          |Low Warning Threshold value of supply voltage in mV.
        rxpowerhighalarm           |FLOAT          |High Alarm Threshold value of received power in dBm.
        rxpowerlowalarm            |FLOAT          |Low Alarm Threshold value of received power in dBm.
        rxpowerhighwarning         |FLOAT          |High Warning Threshold value of received power in dBm.
        rxpowerlowwarning          |FLOAT          |Low Warning Threshold value of received power in dBm.
        txpowerhighalarm           |FLOAT          |High Alarm Threshold value of transmit power in dBm.
        txpowerlowalarm            |FLOAT          |Low Alarm Threshold value of transmit power in dBm.
        txpowerhighwarning         |FLOAT          |High Warning Threshold value of transmit power in dBm.
        txpowerlowwarning          |FLOAT          |Low Warning Threshold value of transmit power in dBm.
        txbiashighalarm            |FLOAT          |High Alarm Threshold value of tx Bias Current in mA.
        txbiaslowalarm             |FLOAT          |Low Alarm Threshold value of tx Bias Current in mA.
        txbiashighwarning          |FLOAT          |High Warning Threshold value of tx Bias Current in mA.
        txbiaslowwarning           |FLOAT          |Low Warning Threshold value of tx Bias Current in mA.
        ========================================================================
        """
        transceiver_dom_threshold_info_dict = {}

        dom_info_dict_keys = ['temphighalarm',    'temphighwarning',
                              'templowalarm',     'templowwarning',
                              'vcchighalarm',     'vcchighwarning',
                              'vcclowalarm',      'vcclowwarning',
                              'rxpowerhighalarm', 'rxpowerhighwarning',
                              'rxpowerlowalarm',  'rxpowerlowwarning',
                              'txpowerhighalarm', 'txpowerhighwarning',
                              'txpowerlowalarm',  'txpowerlowwarning',
                              'txbiashighalarm',  'txbiashighwarning',
                              'txbiaslowalarm',   'txbiaslowwarning'
                             ]
        transceiver_dom_threshold_info_dict = {}.fromkeys(dom_info_dict_keys, 'N/A')

        eeprom_ifraw = self.get_eeprom_raw()
        if eeprom_ifraw is None:
            return transceiver_dom_threshold_info_dict

        type = self.get_eeprom_type(eeprom_ifraw)

        if type == XCVR_EEPROM_TYPE_UNKNOWN:
            return transceiver_dom_threshold_info_dict

        elif type in (XCVR_EEPROM_TYPE_QSFPDD, XCVR_EEPROM_TYPE_QSFP56):
            dom_raw = self.get_eeprom_raw(CMIS_DOM_THRES_ADDR, 128)
            if dom_raw is None:
                return transceiver_dom_threshold_info_dict

            sfpd_obj = inf8628Dom()
            if sfpd_obj is None:
                return transceiver_dom_threshold_info_dict

            dom_module_threshold_data  = sfpd_obj.parse_module_threshold_values(dom_raw, CMIS_DOM_THRES_MODULE_OFFSET)
            dom_channel_threshold_data = sfpd_obj.parse_channel_threshold_values(dom_raw, CMIS_DOM_THRES_CHANNEL_OFFSET)
            transceiver_dom_threshold_info_dict['temphighalarm']   = dom_module_threshold_data['data']['TempHighAlarm']['value']
            transceiver_dom_threshold_info_dict['temphighwarning'] = dom_module_threshold_data['data']['TempHighWarning']['value']
            transceiver_dom_threshold_info_dict['templowalarm']    = dom_module_threshold_data['data']['TempLowAlarm']['value']
            transceiver_dom_threshold_info_dict['templowwarning']  = dom_module_threshold_data['data']['TempLowWarning']['value']
            transceiver_dom_threshold_info_dict['vcchighalarm']    = dom_module_threshold_data['data']['VccHighAlarm']['value']
            transceiver_dom_threshold_info_dict['vcchighwarning']  = dom_module_threshold_data['data']['VccHighWarning']['value']
            transceiver_dom_threshold_info_dict['vcclowalarm']     = dom_module_threshold_data['data']['VccLowAlarm']['value']
            transceiver_dom_threshold_info_dict['vcclowwarning']   = dom_module_threshold_data['data']['VccLowWarning']['value']
            transceiver_dom_threshold_info_dict['rxpowerhighalarm']   = dom_channel_threshold_data['data']['RxPowerHighAlarm']['value']
            transceiver_dom_threshold_info_dict['rxpowerhighwarning'] = dom_channel_threshold_data['data']['RxPowerHighWarning']['value']
            transceiver_dom_threshold_info_dict['rxpowerlowalarm']    = dom_channel_threshold_data['data']['RxPowerLowAlarm']['value']
            transceiver_dom_threshold_info_dict['rxpowerlowwarning']  = dom_channel_threshold_data['data']['RxPowerLowWarning']['value']
            transceiver_dom_threshold_info_dict['txpowerhighalarm']   = dom_channel_threshold_data['data']['TxPowerHighAlarm']['value']
            transceiver_dom_threshold_info_dict['txpowerhighwarning'] = dom_channel_threshold_data['data']['TxPowerHighWarning']['value']
            transceiver_dom_threshold_info_dict['txpowerlowalarm']    = dom_channel_threshold_data['data']['TxPowerLowAlarm']['value']
            transceiver_dom_threshold_info_dict['txpowerlowwarning']  = dom_channel_threshold_data['data']['TxPowerLowWarning']['value']
            transceiver_dom_threshold_info_dict['txbiashighalarm']    = dom_channel_threshold_data['data']['TxBiasHighAlarm']['value']
            transceiver_dom_threshold_info_dict['txbiashighwarning']  = dom_channel_threshold_data['data']['TxBiasHighWarning']['value']
            transceiver_dom_threshold_info_dict['txbiaslowalarm']     = dom_channel_threshold_data['data']['TxBiasLowAlarm']['value']
            transceiver_dom_threshold_info_dict['txbiaslowwarning']   = dom_channel_threshold_data['data']['TxBiasLowWarning']['value']

        elif type == XCVR_EEPROM_TYPE_QSFP:
            dom_raw = self.get_eeprom_raw(SFF8636_DOM_THRES_ADDR, 128)
            if dom_raw is None:
                return transceiver_dom_threshold_info_dict

            sfpd_obj = sff8436Dom()
            if sfpd_obj is None:
                return transceiver_dom_threshold_info_dict

            dom_module_threshold_data = sfpd_obj.parse_module_threshold_values(dom_raw, SFF8636_DOM_THRES_MODULE_OFFSET)
            dom_channel_threshold_data = sfpd_obj.parse_channel_threshold_values(dom_raw, SFF8636_DOM_THRES_CHANNEL_OFFSET)
            transceiver_dom_threshold_info_dict['temphighalarm']   = dom_module_threshold_data['data']['TempHighAlarm']['value']
            transceiver_dom_threshold_info_dict['temphighwarning'] = dom_module_threshold_data['data']['TempHighWarning']['value']
            transceiver_dom_threshold_info_dict['templowalarm']    = dom_module_threshold_data['data']['TempLowAlarm']['value']
            transceiver_dom_threshold_info_dict['templowwarning']  = dom_module_threshold_data['data']['TempLowWarning']['value']
            transceiver_dom_threshold_info_dict['vcchighalarm']    = dom_module_threshold_data['data']['VccHighAlarm']['value']
            transceiver_dom_threshold_info_dict['vcchighwarning']  = dom_module_threshold_data['data']['VccHighWarning']['value']
            transceiver_dom_threshold_info_dict['vcclowalarm']     = dom_module_threshold_data['data']['VccLowAlarm']['value']
            transceiver_dom_threshold_info_dict['vcclowwarning']   = dom_module_threshold_data['data']['VccLowWarning']['value']
            transceiver_dom_threshold_info_dict['rxpowerhighalarm']   = dom_channel_threshold_data['data']['RxPowerHighAlarm']['value']
            transceiver_dom_threshold_info_dict['rxpowerhighwarning'] = dom_channel_threshold_data['data']['RxPowerHighWarning']['value']
            transceiver_dom_threshold_info_dict['rxpowerlowalarm']    = dom_channel_threshold_data['data']['RxPowerLowAlarm']['value']
            transceiver_dom_threshold_info_dict['rxpowerlowwarning']  = dom_channel_threshold_data['data']['RxPowerLowWarning']['value']
            if (int(eeprom_ifraw[SFF8636_DOM_TYPE_ADDR], 16) & 0x04) > 0:
                transceiver_dom_threshold_info_dict['txpowerhighalarm']   = dom_channel_threshold_data['data']['TxPowerHighAlarm']['value']
                transceiver_dom_threshold_info_dict['txpowerhighwarning'] = dom_channel_threshold_data['data']['TxPowerHighWarning']['value']
                transceiver_dom_threshold_info_dict['txpowerlowalarm']    = dom_channel_threshold_data['data']['TxPowerLowAlarm']['value']
                transceiver_dom_threshold_info_dict['txpowerlowwarning']  = dom_channel_threshold_data['data']['TxPowerLowWarning']['value']
            transceiver_dom_threshold_info_dict['txbiashighalarm']    = dom_channel_threshold_data['data']['TxBiasHighAlarm']['value']
            transceiver_dom_threshold_info_dict['txbiashighwarning']  = dom_channel_threshold_data['data']['TxBiasHighWarning']['value']
            transceiver_dom_threshold_info_dict['txbiaslowalarm']     = dom_channel_threshold_data['data']['TxBiasLowAlarm']['value']
            transceiver_dom_threshold_info_dict['txbiaslowwarning']   = dom_channel_threshold_data['data']['TxBiasLowWarning']['value']

        elif type == XCVR_EEPROM_TYPE_SFP:
            dom_raw = self.get_eeprom_raw(SFF8472_DOM_THRES_ADDR, 40)
            if dom_raw is None:
                return transceiver_dom_threshold_info_dict
            sfpd_obj = sff8472Dom(calibration_type=1)
            if sfpd_obj is None:
                return transceiver_dom_threshold_info_dict

            dom_threshold_data = sfpd_obj.parse_alarm_warning_threshold(dom_raw, 0)
            transceiver_dom_threshold_info_dict['temphighalarm']      = dom_threshold_data['data']['TempHighAlarm']['value']
            transceiver_dom_threshold_info_dict['temphighwarning']    = dom_threshold_data['data']['TempHighWarning']['value']
            transceiver_dom_threshold_info_dict['templowalarm']       = dom_threshold_data['data']['TempLowAlarm']['value']
            transceiver_dom_threshold_info_dict['templowwarning']     = dom_threshold_data['data']['TempLowWarning']['value']
            transceiver_dom_threshold_info_dict['vcchighalarm']       = dom_threshold_data['data']['VoltageHighAlarm']['value']
            transceiver_dom_threshold_info_dict['vcchighwarning']     = dom_threshold_data['data']['VoltageHighWarning']['value']
            transceiver_dom_threshold_info_dict['vcclowalarm']        = dom_threshold_data['data']['VoltageLowAlarm']['value']
            transceiver_dom_threshold_info_dict['vcclowwarning']      = dom_threshold_data['data']['VoltageLowWarning']['value']
            transceiver_dom_threshold_info_dict['rxpowerhighalarm']   = dom_threshold_data['data']['RXPowerHighAlarm']['value']
            transceiver_dom_threshold_info_dict['rxpowerhighwarning'] = dom_threshold_data['data']['RXPowerHighWarning']['value']
            transceiver_dom_threshold_info_dict['rxpowerlowalarm']    = dom_threshold_data['data']['RXPowerLowAlarm']['value']
            transceiver_dom_threshold_info_dict['rxpowerlowwarning']  = dom_threshold_data['data']['RXPowerLowWarning']['value']
            transceiver_dom_threshold_info_dict['txbiashighalarm']    = dom_threshold_data['data']['BiasHighAlarm']['value']
            transceiver_dom_threshold_info_dict['txbiashighwarning']  = dom_threshold_data['data']['BiasHighWarning']['value']
            transceiver_dom_threshold_info_dict['txbiaslowalarm']     = dom_threshold_data['data']['BiasLowAlarm']['value']
            transceiver_dom_threshold_info_dict['txbiaslowwarning']   = dom_threshold_data['data']['BiasLowWarning']['value']
            transceiver_dom_threshold_info_dict['txpowerhighalarm']   = dom_threshold_data['data']['TXPowerHighAlarm']['value']
            transceiver_dom_threshold_info_dict['txpowerhighwarning'] = dom_threshold_data['data']['TXPowerHighWarning']['value']
            transceiver_dom_threshold_info_dict['txpowerlowalarm']    = dom_threshold_data['data']['TXPowerLowAlarm']['value']
            transceiver_dom_threshold_info_dict['txpowerlowwarning']  = dom_threshold_data['data']['TXPowerLowWarning']['value']

        elif type == XCVR_EEPROM_TYPE_SFPDD:
            dom_raw = self.get_eeprom_raw(MIS2_DOM_THRES_ADDR, 128)
            if dom_raw is None:
                return transceiver_dom_threshold_info_dict

            sfpd_obj = mis2Dom()
            if sfpd_obj is None:
                return transceiver_dom_threshold_info_dict

            dom_module_threshold_data  = sfpd_obj.parse_module_threshold_values(dom_raw, MIS2_DOM_THRES_MODULE_OFFSET)
            dom_channel_threshold_data = sfpd_obj.parse_channel_threshold_values(dom_raw, MIS2_DOM_THRES_CHANNEL_OFFSET)
            transceiver_dom_threshold_info_dict['temphighalarm']   = dom_module_threshold_data['data']['TempHighAlarm']['value']
            transceiver_dom_threshold_info_dict['temphighwarning'] = dom_module_threshold_data['data']['TempHighWarning']['value']
            transceiver_dom_threshold_info_dict['templowalarm']    = dom_module_threshold_data['data']['TempLowAlarm']['value']
            transceiver_dom_threshold_info_dict['templowwarning']  = dom_module_threshold_data['data']['TempLowWarning']['value']
            transceiver_dom_threshold_info_dict['vcchighalarm']    = dom_module_threshold_data['data']['VccHighAlarm']['value']
            transceiver_dom_threshold_info_dict['vcchighwarning']  = dom_module_threshold_data['data']['VccHighWarning']['value']
            transceiver_dom_threshold_info_dict['vcclowalarm']     = dom_module_threshold_data['data']['VccLowAlarm']['value']
            transceiver_dom_threshold_info_dict['vcclowwarning']   = dom_module_threshold_data['data']['VccLowWarning']['value']
            transceiver_dom_threshold_info_dict['rxpowerhighalarm']   = dom_channel_threshold_data['data']['RxPowerHighAlarm']['value']
            transceiver_dom_threshold_info_dict['rxpowerhighwarning'] = dom_channel_threshold_data['data']['RxPowerHighWarning']['value']
            transceiver_dom_threshold_info_dict['rxpowerlowalarm']    = dom_channel_threshold_data['data']['RxPowerLowAlarm']['value']
            transceiver_dom_threshold_info_dict['rxpowerlowwarning']  = dom_channel_threshold_data['data']['RxPowerLowWarning']['value']
            transceiver_dom_threshold_info_dict['txpowerhighalarm']   = dom_channel_threshold_data['data']['TxPowerHighAlarm']['value']
            transceiver_dom_threshold_info_dict['txpowerhighwarning'] = dom_channel_threshold_data['data']['TxPowerHighWarning']['value']
            transceiver_dom_threshold_info_dict['txpowerlowalarm']    = dom_channel_threshold_data['data']['TxPowerLowAlarm']['value']
            transceiver_dom_threshold_info_dict['txpowerlowwarning']  = dom_channel_threshold_data['data']['TxPowerLowWarning']['value']
            transceiver_dom_threshold_info_dict['txbiashighalarm']    = dom_channel_threshold_data['data']['TxBiasHighAlarm']['value']
            transceiver_dom_threshold_info_dict['txbiashighwarning']  = dom_channel_threshold_data['data']['TxBiasHighWarning']['value']
            transceiver_dom_threshold_info_dict['txbiaslowalarm']     = dom_channel_threshold_data['data']['TxBiasLowAlarm']['value']
            transceiver_dom_threshold_info_dict['txbiaslowwarning']   = dom_channel_threshold_data['data']['TxBiasLowWarning']['value']

        else:
            pass

        return transceiver_dom_threshold_info_dict

    def soft_reset(self):
        """
        Reset SFP and return all user module settings to their default srate.

        Returns:
            A boolean, True if successful, False if not
        """
        if (self.port_type != SfpStandard.PORT_TYPE_QSFPDD):
            return False

        self.eeprom_lock.acquire()

        # Identifier
        id = self.__read_eeprom(SfpStandard.CMIS_REG_ID, 1)
        if (id is None) or (id[0] not in SfpStandard.CMIS_IDS):
            self.eeprom_lock.release()
            return False

        # Revision Compliance ID
        rev = self.__read_eeprom(SfpStandard.CMIS_REG_REV, 1)
        if (rev is None) or (rev[0] < 0x30):
            self.eeprom_lock.release()
            return False

        off = SfpStandard.CMIS_REG_MOD_CTRL
        val = SfpStandard.CMIS_MOD_CTRL_SW_RESET | SfpStandard.CMIS_MOD_CTRL_FORCE_LP
        ret = self.__write_eeprom(off, 1, [val])
        if ret:
            time.sleep(1)

        self.eeprom_lock.release()
        return ret

    def __cable_diagnostics_vct(self):
        """
        Virtual Cable Tester for the 1000BASE-T

        Returns:
            A dict which contains following keys/values :
        ========================================================================
        keys                       |Value Format   |Information
        ---------------------------|---------------|----------------------------
        result                     |STRING         |The result of the conducted test
        length                     |STRING         |The cable length in meters
        ========================================================================
        """
        copper_base = 0x8180
        length_map = ['< 50m',  '50 - 80m', '80 - 110m', '110 - 140m',
                      '> 140m', '> 140m',   '> 140m',    '> 140m']
        status_map = ['OK', 'SHORT', 'OPEN', 'FAILED']
        status = len(status_map) - 1
        res = { 'result': 'FAILED' }
        for retries in range(3):
            # Enable Cable Diagnostic Test
            buf = [0x80]
            if not self.write_eeprom(copper_base + 28 * 2, len(buf), buf):
                return res
            for t in range(20):
                time.sleep(0.5)
                buf = self.read_eeprom(copper_base + 28 * 2, 1)
                if buf is None:
                    return res
                if (buf[0] & 0x80) == 0:
                    break
            status = len(status_map) - 1
            # Timeout
            if buf[0] & 0x80:
                continue
            for chan in range(4):
                buf = [chan]
                if not self.write_eeprom(copper_base + 22 * 2, len(buf), buf):
                    return res
                buf = self.read_eeprom(copper_base + 28 * 2, 1)
                if buf is None:
                    return res
                status = (buf[0] >> 5) & 0x3
                # Abort if not OK
                if status_map[status] != 'OK':
                    break
            # Retry only if it's FAILED
            if status_map[status] != 'FAILED':
                break
        res['result'] = status_map[status]
        # cable length is not accurate until the link is up
        if status_map[status] == 'OK':
            val = None
            for retries in range(6):
                time.sleep(0.5)
                buf = self.read_eeprom(copper_base + 17 * 2, 2)
                if (buf is not None) and (len(buf) == 2):
                    val = (buf[0] << 8) | buf[1]
                    if (val & 0x400):
                        break
            if val is None:
                res['result'] = 'FAILED'
            else:
                res['length'] = length_map[(val >> 7) & 0x07]
        return res

    def __twos_comp(self, num, bits):
        try:
            if ((num & (1 << (bits - 1))) != 0):
                num = num - (1 << bits)
            return num
        except:
            return 0

    def __get_byte(self, off):
        byte = 0
        try:
            buf = self.read_eeprom(off, 1)
            if buf is not None:
                byte = buf[0]
        except:
            byte = 0
        return byte

    def __get_word(self, off):
        word = 0
        try:
            buf = self.read_eeprom(off, 2)
            if buf is not None:
                word = (buf[0] << 8) | buf[1]
        except:
            word = 0
        return word

    def __cable_diagnostics_sff8472(self):
        """
        SFP/SFP+ Diagnostic Tester for SFF8472

        Returns:
            A dict which contains following keys/values :
        ========================================================================
        keys                       |Value Format   |Information
        ---------------------------|---------------|----------------------------
        result                     |STRING         |The result of the conducted test
        length                     |STRING         |The cable length in meters
        ========================================================================
        """
        res = {}

        # Static information for transceiver capability
        cap = self.read_eeprom(SFF8472_ENHANCED_OPTS_ADDR, 1)
        if (cap is None) or ((cap[0] & SFF8472_ENHANCED_OPTS_MASK) == 0):
            return res

        # Data Ready (BIT0), low active
        for t in range(100):
            buf = self.read_eeprom(SFF8472_DOM_STCR_ADDR, 1)
            if buf is None:
                return res
            if (buf[0] & SFF8472_DOM_STCR_NOT_READY) == 0:
                break
            time.sleep(0.1)

        # Decode the DOM information and perform sanity checks
        eopt = cap[0]
        stcr = buf[0]
        if (stcr & SFF8472_DOM_STCR_NOT_READY) > 0:
            res['result'] = 'Timeout'
            return res

        # Temp.
        val = self.__twos_comp(self.__get_word(SFF8472_DOM_TEMP_ADDR), 16)
        top = self.__twos_comp(self.__get_word(SFF8472_DOM_TEMP_WARM_HI_ADDR), 16)
        low = self.__twos_comp(self.__get_word(SFF8472_DOM_TEMP_WARM_LO_ADDR), 16)
        if top > 1:
            if low >= val:
                res['result'] = 'Lo TEMP'
                return res
            if top <= val:
                res['result'] = 'Hi TEMP'
                return res
        else:
            res['result'] = 'Not Supported'
            return res

        # Volt.
        val = self.__get_word(SFF8472_DOM_VOLT_ADDR)
        top = self.__get_word(SFF8472_DOM_VOLT_WARM_HI_ADDR)
        low = self.__get_word(SFF8472_DOM_VOLT_WARM_LO_ADDR)
        if top > 1:
            if low >= val:
                res['result'] = 'Lo VOLT'
                return res
            if top <= val:
                res['result'] = 'Hi VOLT'
                return res
        else:
            res['result'] = 'Not Supported'
            return res

        # Rx Power
        val = self.__get_word(SFF8472_DOM_RXPWR_ADDR)
        top = self.__get_word(SFF8472_DOM_RXPWR_WARM_HI_ADDR)
        low = self.__get_word(SFF8472_DOM_RXPWR_WARM_LO_ADDR)
        if top > 1:
            if low >= val:
                res['result'] = 'Lo RxPwr'
                return res
            if top <= val:
                res['result'] = 'Hi RxPwr'
                return res

        # Tx Power
        val = self.__get_word(SFF8472_DOM_TXPWR_ADDR)
        top = self.__get_word(SFF8472_DOM_TXPWR_WARM_HI_ADDR)
        low = self.__get_word(SFF8472_DOM_TXPWR_WARM_LO_ADDR)
        if top > 1:
            if low >= val:
                res['result'] = 'Lo TxPwr'
                return res
            if top <= val:
                res['result'] = 'Hi TxPwr'
                return res

        # RX_LOS
        if (eopt & SFF8472_ENHANCED_OPTS_RX_LOS) and (stcr & SFF8472_DOM_STCR_RX_LOS):
            res['result'] = 'RX_LOS'
            return res

        # TX_DISABLE
        if (eopt & SFF8472_ENHANCED_OPTS_TX_DISABLE) and (stcr & SFF8472_DOM_STCR_TX_DISABLE):
            res['result'] = 'TX_DISABLED'
            return res

        # TX_FAULT
        if (eopt & SFF8472_ENHANCED_OPTS_TX_FAULT) and (stcr & SFF8472_DOM_STCR_TX_FAULT):
            res['result'] = 'TX_FAULT'
            return res

        res['result'] = 'PASS'
        return res

    def __cable_diagnostics_sff8636(self):
        """
        QSFP Diagnostic Tester for SFF8636

        Note:
        All of these interrupt flags are optional to both copper and optics,
        so they could always reserved as ZERO and results in a false test report.

        Returns:
            A dict which contains following keys/values :
        ========================================================================
        keys                       |Value Format   |Information
        ---------------------------|---------------|----------------------------
        result                     |STRING         |The result of the conducted test
        length                     |STRING         |The cable length in meters
        ========================================================================
        """
        res = {}

        # Data Ready (BIT0), low active
        for t in range(100):
            buf = self.read_eeprom(SFF8636_MOD_STATE_ADDR, 1)
            if buf is None:
                return res
            if (buf[0] & SFF8636_MOD_STATE_NOT_READY) == 0:
                break
            time.sleep(0.1)
        if buf[0] & SFF8636_MOD_STATE_NOT_READY:
            res['result'] = 'Timeout'
            return res

        # Temp.
        val = self.__twos_comp(self.__get_word(SFF8636_DOM_TEMP_ADDR), 16)
        top = self.__twos_comp(self.__get_word(SFF8636_DOM_TEMP_WARM_HI_ADDR), 16)
        low = self.__twos_comp(self.__get_word(SFF8636_DOM_TEMP_WARM_LO_ADDR), 16)
        if top > 1:
            if top <= val:
                res['result'] = 'Hi TEMP'
                return res
            if low >= val:
                res['result'] = 'Lo TEMP'
                return res
        else:
            res['result'] = 'Not Supported'
            return res

        # Volt.
        val = self.__get_word(SFF8636_DOM_VOLT_ADDR)
        top = self.__get_word(SFF8636_DOM_VOLT_WARM_HI_ADDR)
        low = self.__get_word(SFF8636_DOM_VOLT_WARM_LO_ADDR)
        if top > 1:
            if top <= val:
                res['result'] = 'Hi VOLT'
                return res
            if low >= val:
                res['result'] = 'Lo VOLT'
                return res
        else:
            res['result'] = 'Not Supported'
            return res

        # Rx Power
        top = self.__get_word(SFF8636_DOM_RXPWR_WARM_HI_ADDR)
        low = self.__get_word(SFF8636_DOM_RXPWR_WARM_LO_ADDR)
        if top > 1:
            for lane in range(0, 4):
                val = self.__get_word(SFF8636_DOM_RXPWR_ADDR + (2 * lane))
                if top <= val:
                    res['result'] = 'Hi RxPwr(L{0})'.format(lane + 1)
                    return res
                if low >= val:
                    res['result'] = 'Lo RxPwr(L{0})'.format(lane + 1)
                    return res

        # Tx Power
        if self.__get_byte(SFF8636_DOM_TYPE_ADDR) & 0x04:
            top = self.__get_word(SFF8636_DOM_TXPWR_WARM_HI_ADDR)
            low = self.__get_word(SFF8636_DOM_TXPWR_WARM_LO_ADDR)
        else:
            top = 0
            low = 0
        if top > 1:
            for lane in range(0, 4):
                val = self.__get_word(SFF8636_DOM_TXPWR_ADDR + (2 * lane))
                if top <= val:
                    res['result'] = 'Hi TxPwr(L{0})'.format(lane + 1)
                    return res
                if low >= val:
                    res['result'] = 'Lo TxPwr(L{0})'.format(lane + 1)
                    return res

        res['result'] = 'PASS'
        return res

    def cable_diagnostics(self):
        """
        Retrieves cable diagnostics info of this SFP

        Returns:
            A dict which contains following keys/values :
        ========================================================================
        keys                       |Value Format   |Information
        ---------------------------|---------------|----------------------------
        result                     |STRING         |The result of the conducted test
        length                     |STRING         |The cable length in meters
        timestamp                  |STRING         |The timestamp when the test is completed
        ========================================================================
        """
        report_keys = ['type', 'vendor_name', 'part_number', 'result', 'length', 'timestamp']
        report_dict = {}.fromkeys(report_keys, 'N/A')
        report_dict['type'] = 'XCVR'
        report_dict['result'] = 'Not Supported'
        info = self.get_transceiver_info()
        if info is not None:
            report_dict['vendor_name'] = info['manufacturer']
            report_dict['part_number'] = info['model']
            try:
                if info['type_abbrv_name'] in ['SFP']:
                    if '1000BASE-T' in info.get('specification_compliance'):
                        report_dict['type'] = 'TDR'
                        report_dict.update(self.__cable_diagnostics_vct())
                else:
                    pass
            except:
                pass

        report_dict['timestamp'] = datetime.now().strftime("%d-%b-%Y %H:%M:%S")
        return report_dict

    def hard_tx_disable(self, tx_disable):
        """
        Sets SFP module tx_disable pin
        Args:
            tx_disable : A Boolean, True to set tx_disable pin,
                         False to clear tx_disable pin.
        Returns:
            A boolean, True if tx_disable is set/cleared successfully, False if not
        """
        raise NotImplementedError
