import time
import syslog
from datetime import datetime
from .ext_media_utils import media_eeprom_address

SEC_TO_MS = 1000
MIN_TO_MS = 60*SEC_TO_MS

# Encoding for the datapath timeouts
timeout_map_ms = {0:1, 1:5, 2:10, 3:50, 4:100, 5:500, 6:1*SEC_TO_MS, 7:5*SEC_TO_MS, 8: 10*SEC_TO_MS, 9: 1*MIN_TO_MS, 10: 5*MIN_TO_MS, 11: 10*MIN_TO_MS, 12: 50*MIN_TO_MS}

# Addr, len of bytes to read

# For factor version
FORM_FACTOR_VER_ADDR            = (media_eeprom_address(offset=0), 1)
# Version of the CMIS-compliant module
CMIS_VER_ADDR                   = (media_eeprom_address(offset=1), 1)
# Power limit of the module
MOD_PWR_LIMIT_ADDR              = (media_eeprom_address(offset=201), 1)
# Module flags
MOD_FLAGS_ADDR                  = (media_eeprom_address(offset=3), 9)
# Datapth init
DATAPATH_DE_INIT_ADDR           = (media_eeprom_address(page=0x10, offset=128), 1)
# SW controlled power
LOW_PWR_ADDR                    = (media_eeprom_address(offset=26), 1)
# Module faults
MOD_FAULT_ADDR                  = (media_eeprom_address(offset=8), 1)
# Laser/TX control (active low)
TX_DISABLE_ADDR                 = (media_eeprom_address(page=0x10, offset=130), 1)
# Staged Control Set 0 - Apply
STAGED_CS0_APPLY_ADDR           = (media_eeprom_address(page=0x10, offset=143), 1)
# Staged Control Set 0 - Select
STAGED_CS0_SELECT_ADDR          = (media_eeprom_address(page=0x10, offset=145), 8)
# Maximum time for datapath to init
DATAPATH_INIT_TIMEOUT           = (media_eeprom_address(page=0x01, offset=144), 1)
# Status of datapath activation
DATAPATH_ACTIVATED_STATE_ADDR   = (media_eeprom_address(page=0x11, offset=128), 4)
# General set of faults
GENERAL_FAULTS_ADDR             = (media_eeprom_address(page=0x11, offset=134), 9)
# Configuration Error Codes
CONFIG_ERRORS_ADDR              = (media_eeprom_address(page=0x11, offset=202), 4)
# Max power the module can draw
CMIS_MAX_POWER_CLASS_ADDR       = (media_eeprom_address(offset=200), 1)
# Media type encoding
CMIS_MEDIA_TYPE_ENCODING_ADDR   = (media_eeprom_address(offset=85), 1)

# Module State (CMIS v4.0, 8.2.1)
MOD_STATE_MASK = 0x7
MOD_STATE_LOW_PWR = 1
MOD_STATE_PWR_UP = 2
MOD_STATE_READY = 3
MOD_STATE_PWR_DN = 4
MOD_STATE_FAULT = 5

DATAPATH_STATE_ACTIVATE = 0x44444444
DATAPATH_STATE_INITIALIZED = 0x77777777
CONFIG_STATE_ACCEPTED = 0x11111111

# Init types:
# COMPLETE: longest (>15s), but more precise. Skips no steps.
# MEDIUM: shorter (~15s), slightly less precise. Skips datapath control
# QUICK: shortest (~5s), uses hardware init. May or may not cause link issues. Suitable for simpler optics.
# AUTO: Determine approx init type based on module complexity.

INIT_TYPE_QUICK = 2
INIT_TYPE_MEDIUM = 1
INIT_TYPE_COMPLETE = 0
INIT_TYPE_AUTO = -1


DEFAULT_APPLICATION = 1
class cmis_init:
    def logger(self, s):
        if self.logging:
            log = "{0}: {1}: {2}".format(datetime.now(), self.sfp_obj.eeprom_path, s)
            syslog.syslog(syslog.LOG_NOTICE, log)

    def reset(self):
        ret = False
        try:
            ret = self.sfp_obj.reset()
            # Firmware init needs 2 seconds delay on reset
            time.sleep(2)
        except:
            ret = False
        return ret

    # Dummy functions those will be override when available
    def get_lpmode(self):
        return True
    def set_lpmode(self, state):
        return
    # Active low; False implies interrupt triggered
    def get_intl_state(self):
        return True


    # Get the CMIS version. 3.0 and 4.0 have slightly different methods
    def get_cmis_ver(self):
        self.logger("Reading CMIS version")
        ret = self.read_bytes(*CMIS_VER_ADDR)[0]
        self.logger("Got CMIS version value of {}".format(hex(ret)))
        return ret

    # Get the general faults
    def get_general_faults(self):
        self.logger("Reading general faults")
        ret = self.read_bytes(*GENERAL_FAULTS_ADDR)
        self.logger("Got general faults at addr: {}, vals: {}".format(vars(GENERAL_FAULTS_ADDR[0]), ret))
        return ret


    # Module flags
    def get_module_flags(self):
        self.logger("Reading module flags")
        ret = self.read_bytes(*MOD_FLAGS_ADDR)
        self.logger("Got module flags at addr: {}, vals: {}".format(vars(MOD_FLAGS_ADDR[0]), ret))
        return ret

    # Get resolution of datapath activate operation
    def get_datapath_activated_states(self):
        self.logger("Reading datapath activation states")
        ret = self.read_bytes(*DATAPATH_ACTIVATED_STATE_ADDR)
        self.logger("Got datapath activation states at addr: {}, vals: {}".format(vars(DATAPATH_ACTIVATED_STATE_ADDR[0]), ret))
        return ret

    # Get resolution of datapath activate operation
    def get_config_errors(self):
        ret = self.read_bytes(*CONFIG_ERRORS_ADDR)
        return ret

    # Set datapath_init
    def set_datapath_init(self, state):
        self.logger("Setting datapath init to "+str(state))
        if self.cmis_ver < 0x40:
            val = (0xFF if state else 0x00)
        else:
            val = (0x00 if state else 0xFF)
        self.write_bytes(DATAPATH_DE_INIT_ADDR[0], [val])

    # Set software based high power
    def set_high_power(self):
        val = 0x00
        self.logger("Setting media to software-based high power mode")
        self.write_bytes(LOW_PWR_ADDR[0], [val])

    # Get module fault
    def get_mod_fault(self):
        self.logger("Reading module faults")

        val = self.read_bytes(*MOD_FAULT_ADDR)[0]
        self.logger("Got module fault val "+str(val))
        return val

    def set_tx_disable(self, state):
        self.logger("Setting tx disable to "+str(state))
        val = (0xFF if state else 0x00)
        self.write_bytes(TX_DISABLE_ADDR[0], [val])

    def get_datapath_timeout(self):
        self.logger("Getting timeout for datapath config")
        val = self.read_bytes(*DATAPATH_INIT_TIMEOUT)[0]

        val &= 0x0F
        ret = timeout_map_ms.get(val, 10*SEC_TO_MS)
        self.logger("Got datapath timeout val of {}ms ".format(str(ret)))
        return ret


    # The driver (optoe) uses a flat addressing space, while the actual device is paged
    def _page_to_flat_offset(self, addr):
        if addr.page > 0 and addr.offset > 127:
            # Convert page and offset to flat address
            return ((addr.page+1)*128) + (addr.offset & 0x7f)
        return addr.offset

    def read_bytes(self, addr, length):
        offset = self._page_to_flat_offset(addr)
        ret = self.sfp_obj.read_eeprom(offset, length)
        if ret is None:
            self.logger("Read failed for addr {}".format(vars(addr)))
        return ret

        self.logger("Will read {} byte(s) from addr {}".format(length, vars(addr)))

        with open(self.sfp_obj.eeprom_path, 'rb+') as fp:
            fp.seek(offset)
            b = fp.read(length)
            # TODO remove these python2/3 checks once completely moved to python3
            if type(b) == bytes:
                # python3
                ret = [int(a) for a in b]
            else:
                # python2
                ret = [int(ord(a)) for a in b]
            self.logger("Read back "+str(ret))
            return ret
        self.logger("Read failed for addr {}".format(vars(addr)))
        return []

    def write_bytes(self, addr, bytes):
        offset = self._page_to_flat_offset(addr)
        self.sfp_obj.write_eeprom(offset, len(bytes), bytes)

    def check_power_compat(self):
        power_max_code = (self.read_bytes(*CMIS_MAX_POWER_CLASS_ADDR)[0] >> 5) & 0x07
        power_old_method = 0.0
        if power_max_code < 0x07:
            # Hard-coded power values
            power_old_method = [1.5, 2.0, 2.5, 3.5, 4.0, 4.5, 5.0][power_max_code]
        # Alternatively, power is encoded as unsigned int in units of 0.25W
        pwr = max(power_old_method, float(self.read_bytes(*CMIS_MAX_POWER_CLASS_ADDR)[0]) * 0.25)

        self.logger("Read media max power is "+str(pwr)+ " Watts")
        if pwr > self.max_port_power():
            self.logger("Media max power of {}W exceeds port max power of {}W".format(pwr, self.max_port_power))
            return False
        return True

    def determine_init_type(self):
        # Determine best init type based on the general complexity of the module
        m_type = self.read_bytes(*CMIS_MEDIA_TYPE_ENCODING_ADDR)[0]

        if m_type in [0x03, 0x05]:
            # Cables. Simple init
            return INIT_TYPE_QUICK
        # No quick SW init for 3.0
        if self.cmis_ver == 0x30:
            return INIT_TYPE_COMPLETE
        if m_type in [0x04]:
            # Active cables
            return INIT_TYPE_MEDIUM
        if m_type in [0x01, 0x02]:
            # SMF, MMF
            return INIT_TYPE_COMPLETE

        self.logger("Could not determined init type automatically. Will use quick init")
        return INIT_TYPE_QUICK


    def __init__(self, sfp_obj, logging=False):
        self.lanes_per_port = 1
        self.logging = logging
        if sfp_obj == None:
            raise ValueError("Need proper arg")
        self.sfp_obj = sfp_obj

        self.logger("Init new cmis obj with object "+str(sfp_obj))

        # Need to know the maximum port power
        try:
            self.max_port_power = sfp_obj.get_max_port_power()
            self.logger("Init got max port power of "+str(self.max_port_power))
        except:
            self.max_port_power = 20.0
            self.logger("Unable to get max port power. Will assume no restrictions and use high value of {}Watts".format(str(self.max_port_power)))

        # lpmode controls are useful but not needed
        try:
            glpm = sfp_obj.get_lpmode
            slpm = sfp_obj.set_lpmode
            if any([glpm, slpm]) is None:
                raise ValueError("Invalid method definitions for lpmode control")
            def g():
                self.logger("Getting lpmode")
                ret = glpm()
                self.logger("Got lpmod value of "+str(ret))
                return ret

            self.get_lpmode = g
            def s(state):
                self.logger("Setting lpmode to "+str(state))
                slpm(state)

            self.set_lpmode = s

        except:
            self.logger("LPMod control missing. Init may not work as needed.")

        # IntL is useful but not needed
        try:
            intl = sfp_obj.get_intl_state
            if intl is None:
                raise ValueError("")
            def i():
                self.logger("Getting intL state")
                ret = intl()
                self.logger("Got intL value of "+str(ret))
                return ret

            self.get_intl_state = i
        except:
            self.logger("IntL state getter not found. Init may not work as needed.")

        # QSFP56 follows CMIS 5.0/CMIS 4.0 specs similar to QSFP56-DD module
        if self.read_bytes(*FORM_FACTOR_VER_ADDR)[0] not in (0x18, 0x19, 0x1e):
            self.logger("Invalid module for CMIS initialization. Exiting")
            self.cmis_ver = -1
            return

        self.cmis_ver = self.get_cmis_ver()

    def initialize_cmis4(self, application=DEFAULT_APPLICATION, lanes_per_port=8, retries=1):
        ready = False
        # Read 2 byte or 4 byte from control register based on number of lanes
        # All QSFP56-DD modules use 32 bit mask and QSFP56 module use 16 bit mask
        bitmask = {
            2: 0xffffffff,
            4: 0xffff0000,
            8: 0xffffffff
        }

        buf = self.read_bytes(STAGED_CS0_SELECT_ADDR[0], 1)
        cur = buf[0] >> 4
        self.logger("CMIS4: Changing application from {0} to {1}...".format(cur, application))

        buf = self.read_bytes(MOD_FLAGS_ADDR[0], 1)
        sta = (buf[0] >> 1) & MOD_STATE_MASK
        if (cur == application) and (sta == MOD_STATE_READY):
            self.logger("CMIS4: No application code update, skipping...")
            return True

        retries = retries * 2
        while not ready and retries >= 0:
            # Do software reset
            self.reset()
            val = 0x10
            self.logger("CMIS4: Setting media to force lowpower mode")
            self.write_bytes(LOW_PWR_ADDR[0], [val])
            self.logger("CMIS4: Enforce Tx disable")
            self.set_tx_disable(True)
            # Deinitialize datapath
            self.set_datapath_init(False)
            time.sleep(1)

            err_d = [0, 0]
            for t in range(20):
                time.sleep(1)
                buf = self.get_datapath_activated_states()
                err_d[0] = (buf[0] << 24) | (buf[1] << 16) | (buf[2] << 8) | buf[3]
                self.logger("CMIS4: checking datapath deactive states...{0},{1}".format(t, hex(err_d[0])))
                if err_d[0] == 0x11111111:
                    break

            # Do application selection
            bytes = []
            for n in range(8):
                bytes.append(application << 4)

            # Setting up the first lane of each port/datapath
            if lanes_per_port == 8:
                pass
            elif lanes_per_port == 4:
                bytes[4] |= 0x08
                bytes[5] |= 0x08
                bytes[6] |= 0x08
                bytes[7] |= 0x08
            elif lanes_per_port == 2:
                bytes[2] |= 0x04
                bytes[3] |= 0x04
                bytes[4] |= 0x08
                bytes[5] |= 0x08
                bytes[6] |= 0x0c
                bytes[7] |= 0x0c
            elif lanes_per_port == 1:
                bytes[1] |= 0x02
                bytes[2] |= 0x04
                bytes[3] |= 0x06
                bytes[4] |= 0x08
                bytes[5] |= 0x0a
                bytes[6] |= 0x0c
                bytes[7] |= 0x0e

            # Toggle the BIT0(i.e. application-defined) and try again
            if retries & 0x01:
                bytes[0] |= 0x01
                bytes[1] |= 0x01
                bytes[2] |= 0x01
                bytes[3] |= 0x01
                bytes[4] |= 0x01
                bytes[5] |= 0x01
                bytes[6] |= 0x01
                bytes[7] |= 0x01

            self.write_bytes(STAGED_CS0_SELECT_ADDR[0], bytes)
            self.write_bytes(STAGED_CS0_APPLY_ADDR[0], [0xff])
            conf_ready = False

            # Activate Hi-Power mode
            self.set_high_power()

            for t in range(5):
                time.sleep(1)
                try:
                    buf = self.get_config_errors()
                    err = (buf[0] << 24) | (buf[1] << 16) | (buf[2] << 8) | buf[3]
                    self.logger("CMIS4: checking config errors...{0},{1}".format(t, hex(err)))
                    if (err & bitmask[lanes_per_port]) != \
                        (CONFIG_STATE_ACCEPTED & bitmask[lanes_per_port]):
                        continue
                    conf_ready = True
                    break
                except:
                    continue
                conf_ready = True
                break
            if not conf_ready:
                self.logger("CMIS4: AppSelect config set failed: {0}".format(hex(err)))
                retries -= 1
                continue

            # Initialize datapath
            self.set_datapath_init(True)

            # Allow 20 seconds for status verification
            # Note:
            #     AVAGO#AFCT-93DRPHZ-AZ2: 4x100->1x400G:  4 seconds
            #     AVAGO#AFCT-93DRPHZ-AZ2: 1x400->4x100G:  2 seconds
            #     DELL EMC#6MGDY:         4x100->1x400G:  8 seconds
            #     DELL EMC#6MGDY:         1x400->4x100G: 14 seconds
            for t in range(30):
                time.sleep(1)
                buf = self.get_datapath_activated_states()
                if buf is None:
                    continue
                err = (buf[0] << 24) | (buf[1] << 16) | (buf[2] << 8) | buf[3]
                self.logger("CMIS4: checking datapath states...{0},{1}".format(t, hex(err)))
                if (err & bitmask[lanes_per_port] != \
                    DATAPATH_STATE_ACTIVATE & bitmask[lanes_per_port]) and \
                    (err & bitmask[lanes_per_port] != \
                    DATAPATH_STATE_INITIALIZED & bitmask[lanes_per_port]):
                    continue
                ready = True
                break
            # Report config failure and try again
            if not ready:
                self.logger("CMIS4: Init failed: DataPath state - {0}".format(hex(err)))
            retries -= 1
        if ready:
            self.logger("CMIS4: Init completed")
        self.logger("CMIS4: Enforcing Tx enable")
        self.set_tx_disable(False)
        return ready

    def initialize_cmis3(self, application=DEFAULT_APPLICATION, lanes_per_port=8, retries=3, init_type=INIT_TYPE_AUTO, force=True):
        if retries < 0:
            self.logger("No more retries. Terminating")
            return False

        buf = self.read_bytes(STAGED_CS0_SELECT_ADDR[0], 1)
        cur = buf[0] >> 4
        self.logger("CMIS3: Changing application from {0} to {1}...".format(cur, application))

        buf = self.read_bytes(MOD_FLAGS_ADDR[0], 1)
        sta = (buf[0] >> 1) & MOD_STATE_MASK
        if (cur == application) and (sta == MOD_STATE_READY):
            self.logger("CMIS3: No application code update, skipping...")
            return True

        if force:
            self.logger("Applying module reset")
            self.reset()

            self.logger("Forcing Low Power Mode")
            self.set_lpmode(True)

            time.sleep(2)
        elif self.check_power_compat():
            # Media power requirements are not compatible with port
            self.logger("Power limits incompatible for media-port combo")
            if not force:
                self.logger("Exiting due to power constraints...")
                return False
            self.logger("Proceed at your own risk")

        if init_type == INIT_TYPE_AUTO:
            self.logger("Will infer init type based on module complexity")
            init_type = self.determine_init_type()
            self.logger("Will use init type "+str(init_type))

        if init_type == INIT_TYPE_QUICK:
            # Use hardware init
            self.logger("Using Hardware-based Quick Init")

            self.set_lpmode(False)
            time.sleep(3)
            ret = (self.get_lpmode() == False)
            self.logger("Quick Init terminated with "+str(ret))
            return ret

        intl_timeout = 5
        self.logger("Wait for INTL to be 0")
        while self.get_intl_state() == True and intl_timeout > 0:
            self.logger("Waiting for INTL to be 0, timeout(s): " +str(intl_timeout))
            time.sleep(1)
            intl_timeout -= 1
        if (intl_timeout <= 0):
            self.logger("WARNING: INTL did not go to 0. Will continue ")


        self.logger("Read module flags/faults to force-clear interrupts and flags")
        self.get_module_flags()
        self.get_general_faults()
        self.logger("Enforce tx disable")
        self.set_tx_disable(True)

        if init_type == INIT_TYPE_COMPLETE:
            self.logger("CMIS3: Setting datapath in deinit state")
            self.set_datapath_init(False)

        err_d = [0, 0]
        for t in range(20):
            time.sleep(1)
            buf = self.get_datapath_activated_states()
            err_d[0] = (buf[0] << 24) | (buf[1] << 16) | (buf[2] << 8) | buf[3]
            self.logger("CMIS3: checking datapath deactive states...{0},{1}".format(t, hex(err_d[0])))
            if err_d[0] == 0x11111111:
                break

        intl_timeout = 10
        self.logger("Wait for INTL to be 0")
        while self.get_intl_state() == True and intl_timeout > 0:
            self.logger("Waiting for INTL to be 0, timeout(s): " +str(intl_timeout))
            time.sleep(1)
            intl_timeout -= 1
        if (intl_timeout <= 0):
            self.logger("WARNING: INTL did not go to 0. Will continue ")

        self.logger("Getting module faults")
        if self.get_mod_fault() != 0:
            self.logger("Module faults seen. Init may not complete correctly")

        dp_init_timeout = 0
        if init_type == INIT_TYPE_COMPLETE:
            # Do application selection
            bytes = []
            for n in range(8):
                bytes.append(application << 4)

            # Setting up the first lane of each port/datapath
            if lanes_per_port == 8:
                pass
            elif lanes_per_port == 4:
                bytes[4] |= 0x08
                bytes[5] |= 0x08
                bytes[6] |= 0x08
                bytes[7] |= 0x08
            elif lanes_per_port == 2:
                bytes[2] |= 0x04
                bytes[3] |= 0x04
                bytes[4] |= 0x08
                bytes[5] |= 0x08
                bytes[6] |= 0x0c
                bytes[7] |= 0x0c
            elif lanes_per_port == 1:
                bytes[1] |= 0x02
                bytes[2] |= 0x04
                bytes[3] |= 0x06
                bytes[4] |= 0x08
                bytes[5] |= 0x0a
                bytes[6] |= 0x0c
                bytes[7] |= 0x0e

            # Toggle the BIT0(i.e. application-defined) and try again
            if retries == 0:
                bytes[0] |= 0x01
                bytes[1] |= 0x01
                bytes[2] |= 0x01
                bytes[3] |= 0x01
                bytes[4] |= 0x01
                bytes[5] |= 0x01
                bytes[6] |= 0x01
                bytes[7] |= 0x01

            self.write_bytes(STAGED_CS0_SELECT_ADDR[0], bytes)
            self.write_bytes(STAGED_CS0_APPLY_ADDR[0], [0xff])
            # As per the spec after application select config is pushed 1 sec
            # sleep is required
            time.sleep(1)

            self.logger("Setting SW-based high power")
            self.set_high_power()
            self.logger("Setting datapath in init state")
            self.set_datapath_init(True)

            self.logger("Determining maximum datapath init time")
            # Certain Media takes extra time for DP to move to active state
            # Extending the timeout value to allow DP Init process to complete
            dp_init_timeout = self.get_datapath_timeout() * 2

            self.logger("CMIS3: Will wait for dp init for up to timeout of {}ms".format(dp_init_timeout))

            def test_dp_actv(da):
                # All need to equal 0x44 or 0x77
                orig = da[0]

                for d in da:
                    if d != orig:
                        return False
                if orig not in [0x44, 0x77]:
                    return False
                return True

            dp_actv = self.get_datapath_activated_states()
            dp_init_timeout /= 1000.0

            while not test_dp_actv(dp_actv) and  dp_init_timeout > 0:
                dp_actv = self.get_datapath_activated_states()
                time.sleep(1)
                dp_init_timeout -= 1.0

        if init_type != INIT_TYPE_COMPLETE:
            self.logger("Setting SW-based high power")
            self.set_high_power()

        self.logger("CMIS3: Enforcing TX enable")
        self.set_tx_disable(False)

        if init_type == INIT_TYPE_COMPLETE:
            time.sleep(1)
            self.logger("Checking datapath activated states. Expect 0x44 per lane")

            # Check each datapath lane for errors
            dp_actv = self.get_datapath_activated_states()

            if any(d != 0x44 for d in dp_actv):
                self.logger("Error seen during dp activation.")
                self.logger("Will retry init")
                #self.reset()
                return self.initialize_cmis3(application, self.lanes_per_port, retries-1, init_type, force)

        # Check for general flags and errors in 2 passes
        passes = 0
        err_seen = False
        while passes < 3:
            self.logger("Reading module flags. Pass "+str(passes))
            mod_flags = self.get_module_flags()
            err_seen = False

            # Byte 3 bits 1-3 contains Module State Encoding [Refer CMIS3 Spec]
            # 011b code refers to Module Ready state
            if  mod_flags[0] & (3<<1) != (3<<1):
                self.logger("Module state is invalid. Byte 3 is invalid: "+ str(mod_flags[0]))
                err_seen = True

            # Byte 8 bits 1,2 refers to Module and Data Path Firmware Faults
            if mod_flags[5] & 0x06 != 0:
                self.logger("Error with flags. Failed")
                err_seen = True
            if not err_seen:
                break
            passes += 1

        if err_seen:
            self.logger("Failed. Flags are still set after init completion")
            self.logger("Will retry init using COMPLETE INIT")
            #self.reset()
            return self.initialize_cmis3(application, self.lanes_per_port, retries-3, INIT_TYPE_COMPLETE, force)

        self.logger("CMIS3: Init completed")
        return True

    def initialize(self, application=DEFAULT_APPLICATION, lanes_per_port=8, retries=3):
        ret = False

        try:
            self.lanes_per_port = lanes_per_port
            if self.cmis_ver >= 0x40:
                ret = self.initialize_cmis4(application, lanes_per_port, retries)
            elif self.cmis_ver >= 0x30:
                ret = self.initialize_cmis3(application, lanes_per_port, retries)
        except Exception as ex:
            self.logger("CMIS init failed: {0}".format(ex))

        return ret
