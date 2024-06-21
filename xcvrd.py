#!/usr/bin/env python2

"""
    xcvrd
    Transceiver information update daemon for SONiC
"""

try:
    import ast
    import json
    import multiprocessing
    import os
    import signal
    import string
    import re
    import collections
    import sys
    import threading
    import time
    import random
    from datetime import datetime
    from enum import Enum
    from sonic_py_common import daemon_base, device_info, logger
    from sonic_py_common import multi_asic
    from swsscommon import swsscommon
    from swsssdk import ConfigDBConnector

    from .xcvrd_copper import CopperManagerTask
    from .xcvrd_utilities import y_cable_helper
    from .xcvrd_utilities.media_autoconf import MediaAutoconf
except ImportError as e:
    raise ImportError(str(e) + " - required module not found")

#
# Constants ====================================================================
#

SYSLOG_IDENTIFIER = "xcvrd"

START_SFP_READ_BEFORE_PORT_INIT = False

PLATFORM_SPECIFIC_MODULE_NAME = "sfputil"
PLATFORM_SPECIFIC_CLASS_NAME = "SfpUtil"

STATE_PORT_XCVR_TABLE = 'PORT_XCVR_STATUS_TABLE'
TRANSCEIVER_INFO_TABLE = 'TRANSCEIVER_INFO'
TRANSCEIVER_DIAG_TABLE = 'TRANSCEIVER_DIAG'
TRANSCEIVER_DOM_SENSOR_TABLE = 'TRANSCEIVER_DOM_SENSOR'
TRANSCEIVER_STATUS_TABLE = 'TRANSCEIVER_STATUS'

SELECT_TIMEOUT_MSECS = 1000

DOM_INFO_UPDATE_PERIOD_SECS = 60
TIME_FOR_SFP_READY_SECS = 1
TIME_FOR_SFP_POLL_SECS = 3
TIME_FOR_XCVR_CONFIG_POLL_SECS = 3
XCVRD_MAIN_THREAD_SLEEP_SECS = 60

# SFP status definition, shall be aligned with the definition in get_change_event() of ChassisBase
SFP_STATUS_REMOVED = '0'
SFP_STATUS_INSERTED = '1'

# SFP error code enum, new elements can be added to the enum if new errors need to be supported.
SFP_STATUS_ERR_ENUM = Enum('SFP_STATUS_ERR_ENUM', ['SFP_STATUS_ERR_I2C_STUCK', 'SFP_STATUS_ERR_BAD_EEPROM',
                                                   'SFP_STATUS_ERR_UNSUPPORTED_CABLE', 'SFP_STATUS_ERR_HIGH_TEMP',
                                                   'SFP_STATUS_ERR_BAD_CABLE'], start=2)

# Convert the error code to string and store them in a set for convenience
errors_block_eeprom_reading = set(str(error_code.value) for error_code in SFP_STATUS_ERR_ENUM)

EVENT_ON_ALL_SFP = '-1'
# events definition
SYSTEM_NOT_READY = 'system_not_ready'
SYSTEM_BECOME_READY = 'system_become_ready'
SYSTEM_FAIL = 'system_fail'
NORMAL_EVENT = 'normal'
# states definition
STATE_INIT = 0
STATE_NORMAL = 1
STATE_EXIT = 2

PHYSICAL_PORT_NOT_EXIST = -1
SFP_EEPROM_NOT_READY = -2

SFPUTIL_LOAD_ERROR = 1
PORT_CONFIG_LOAD_ERROR = 2
NOT_IMPLEMENTED_ERROR = 3
SFP_SYSTEM_ERROR = 4

RETRY_TIMES_FOR_SYSTEM_READY = 30
RETRY_PERIOD_FOR_SYSTEM_READY_MSECS = 5000

RETRY_TIMES_FOR_SYSTEM_FAIL = 30
RETRY_PERIOD_FOR_SYSTEM_FAIL_MSECS = 5000

TEMP_UNIT = 'C'
VOLT_UNIT = 'Volts'
POWER_UNIT = 'dBm'
BIAS_UNIT = 'mA'

media_settings = ''
g_dict = {}
manager = multiprocessing.Manager()
g_xcvr = manager.dict()
g_gearbox_interfaces = {}
# Global platform specific sfputil class instance
platform_sfputil = None
# Global chassis object based on new platform api
platform_chassis = None
# Global first physical port number
first_phy_port = None
# Global ext media module
ext_media_module = None
# DOM info updater process
dom_info_update = None
# XCVR configuration updater process
xcvr_config_updater = None
# CMIS init task worker
cmis_init_worker = None
# CMIS diag task worker
cmis_diag_worker = None
# Manager of the multiprocessing
mpmgr = multiprocessing.Manager()


# Global logger instance for helper functions and classes
# TODO: Refactor so that we only need the logger inherited
# by DaemonXcvrd
helper_logger = logger.Logger(SYSLOG_IDENTIFIER)

media_autoconf = MediaAutoconf(helper_logger)

XCVR_STATE_EMPTY   = 0
XCVR_STATE_ERROR   = 1
XCVR_STATE_INCOMP  = 2
XCVR_STATE_CONFIG  = 3
XCVR_STATE_READY   = 4

XCVR_EVENT_NOOP     = 'noop'     # no-operation
XCVR_EVENT_CONFIG   = 'config'   # transceiver configuration

#
# Helper functions =============================================================
#

# Update names of the subprocesses
def update_proc_name(name):
    try:
        import setproctitle
        setproctitle.setproctitle(name)
    except Exception as err:
        helper_logger.log_error("Set proc name failed for {}: {}".format(name, str(err)))

# Find out the underneath physical port list by logical name
def logical_port_name_to_physical_port_list(port_name, err_on_nofound=True):
    if port_name.startswith("Eth"):
        if platform_sfputil.is_logical_port(port_name):
            return platform_sfputil.get_logical_to_physical(port_name)
        else:
            if err_on_nofound:
                helper_logger.log_error("Invalid port '{}'".format(port_name))
            return None
    else:
        return [int(port_name)]

# Get physical port name


def get_physical_port_name(logical_port, physical_port, ganged):
    if logical_port == physical_port:
        return logical_port
    elif ganged:
        return logical_port + ":{} (ganged)".format(physical_port)
    else:
        return logical_port

# Strip units and beautify


def strip_unit_and_beautify(value, unit):
    # Strip unit from raw data
    if type(value) is str:
        width = len(unit)
        if value[-width:] == unit:
            value = value[:-width]
        return value
    else:
        return str(value)

def _wrapper_port_start():
    if platform_chassis is not None:
        try:
            return first_phy_port
        except NotImplementedError:
            pass
    return platform_sfputil.port_start

def _wrapper_port_end():
    if platform_chassis is not None:
        try:
            # Always _wrapper_port_end()+1 is used in the range function, hence provide a proper num based on 0-based/1-based port numbering
            return (platform_chassis.get_num_sfps()-1+first_phy_port)
        except NotImplementedError:
            pass
    return platform_sfputil.port_end

def _wrapper_is_native_RJ45(physical_port, sfp=None):
    ret = False
    if platform_chassis is not None:
        try:
            if sfp is None:
                sfp = platform_chassis.get_sfp(physical_port)
            ret = (sfp.port_type in [sfp.PORT_TYPE_NONE])
        except Exception as ex:
            pass
    return ret

def _wrapper_get_presence(physical_port):
    ret = False
    legacy_mode = False

    if platform_chassis is None:
        legacy_mode = True
    else:
        try:
            sfp = platform_chassis.get_sfp(physical_port)
            if _wrapper_is_native_RJ45(physical_port, sfp):
                ret = True
            else:
                ret = sfp.get_presence()
        except NotImplementedError:
            legacy_mode = True
        except Exception as ex:
            helper_logger.log_notice("Port {0}: Unable to get SFP presence: {1}".format(physical_port, ex))
            ret = False

    if legacy_mode:
        try:
            ret = platform_sfputil.get_presence(physical_port)
        except Exception as ex:
            helper_logger.log_notice("Port {0}: Unable to get SFP presence: {1}".format(physical_port, ex))
            ret = False

    return ret

def _wrapper_clear_eeprom_cache(logical_port):
    if platform_chassis is not None:
        physical_port_list = logical_port_name_to_physical_port_list(logical_port)
        if physical_port_list is None:
            helper_logger.log_error("No physical ports found for logical " \
                                    "port '{}'".format(logical_port))
            return

        for physical_port in physical_port_list:
            try:
                platform_chassis.get_sfp(physical_port).clear_eeprom_cache()
            except Exception as ex:
                helper_logger.log_error("EEPROM Cache clear for " \
                                        "port '{}' Error {}".format(logical_port, ex))
    return


def _wrapper_get_transceiver_eeprom(physical_port, offset, length):
    if not _wrapper_get_presence(physical_port):
        return None
    buf = None
    if platform_chassis is not None:
        try:
            buf = platform_chassis.get_sfp(physical_port).get_eeprom_raw(offset, length)
        except:
            buf = None
    if buf is None:
        try:
            buf = platform_sfputil._read_eeprom_devid(physical_port, platform_sfputil.IDENTITY_EEPROM_ADDR, offset, length)
        except:
            buf = None
    return buf

def _wrapper_set_transceiver_eeprom(physical_port, offset, value):
    if not _wrapper_get_presence(physical_port):
        return False
    ret = False
    if platform_chassis is not None:
        try:
            buf = [int(value, 16)]
            ret = platform_chassis.get_sfp(physical_port).write_eeprom(offset, 1, buf)
            return ret
        except:
            pass
    filepath = platform_sfputil._get_port_eeprom_path(physical_port, platform_sfputil.IDENTITY_EEPROM_ADDR)
    eeprom = None
    try:
        eeprom = open(filepath, "wb", 0)
        eeprom.seek(offset)
        eeprom.write(chr(int(value, 16)))
        ret = True
    except Exception as ex:
        print("_wrapper_set_transceiver_eeprom: {0}".format(ex))
        ret = False
    finally:
        if eeprom is not None:
            eeprom.close()
    return ret

def _wrapper_is_qsfpdd_cage(physical_port):
    if physical_port is None:
        return False
    if platform_chassis is not None:
        try:
            sfp = platform_chassis.get_sfp(physical_port)
            return True if sfp.port_type == sfp.PORT_TYPE_QSFPDD else False
        except:
            return False
    try:
        if physical_port in platform_sfputil.osfp_ports:
            return True
    except:
        pass
    return False

def _wrapper_is_sfp_cage(physical_port):
    ret = False
    legacy_mode = False

    if platform_chassis is None:
        legacy_mode = True
    else:
        legacy_mode = False
        try:
            platform_chassis.get_all_sfps()[0].get_presence()
        except:
            legacy_mode = True

    if legacy_mode:
        if physical_port in platform_sfputil.qsfp_ports:
            ret = False
        elif physical_port in platform_sfputil.osfp_ports:
            ret = False
        else:
            ret = True
    else:
        try:
            sfp = platform_chassis.get_sfp(physical_port)
            ret = True if sfp.port_type == sfp.PORT_TYPE_SFP else False
        except:
            ret = False

    return ret

def _wrapper_is_copper_sfp(physical_port):
    if not _wrapper_is_sfp_cage(physical_port):
        return False
    buf = _wrapper_get_transceiver_eeprom(physical_port, 0, 8)
    if (buf is None) or (len(buf) < 7):
        return False
    if int(buf[0], 16) != 0x03:
        return False
    if (int(buf[6], 16) & 0x08) == 0:
        return False
    return True


def _wrapper_is_replaceable(physical_port):
    if platform_chassis is not None:
        try:
            return platform_chassis.get_sfp(physical_port).is_replaceable()
        except NotImplementedError:
            pass
    return False

def _transceiver_info_fixup(info):
    if info is None:
        return info

    if info.get('display_name', 'N/A') in ['N/A']:
        xtype = info.get('type_abbrv_name', 'N/A')
        xconn = info.get('connector', 'N/A')
        if (xtype in ['SFP']) and (xconn in ['CopperPigtail', 'Copper pigtail', 'No separable connector']):
            try:
                nbr = int(info.get('nominal_bit_rate', '0'))
            except:
                nbr = 0
            if nbr >= 250:
                info['display_name'] = 'SFP28 25GBASE-CR-DAC'
            elif nbr >= 100:
                info['display_name'] = 'SFP+ 10GBASE-CR-DAC'
            else:
                info['display_name'] = 'SFP 1000BASE-CX-DAC'
        elif xtype in ['QSFP-DD']:
            if info.get('media_type', 'N/A') in ['passive_copper_media_interface']:
                type = info.get('type', 'QSFP56-DD')
                appl = info.get('application_advertisement', 'N/A')
                if appl in ['', 'N/A', 'n/a'] or '400G CR8' in appl:
                    media = '400GBASE-CR8'
                else:
                    media = '200GBASE-CR8'
                info['display_name'] = "{} {}".format(type, media)

    return info

def _wrapper_get_transceiver_info(physical_port):

    # Remap old fields to new fields so dependent apps dont break
    # This fixes some fields which are normally parsed incorrectly
    remap = {   'vendor_date' : 'vendor_date_code',
                'vendorrev' : 'vendor_revision',
                'serial' : 'vendor_serial_number',
                'vendor_oui' : 'vendor_oui',
                'model' : 'vendor_part_number',
                'manufacturer' : 'vendor_name',
                'connector' : 'connector_type',
                'type': 'form_factor',
                'cable_length' : 'cable_length_detailed'}

    default_dict = None
    if platform_chassis is not None:
        try:
            sfp_obj = platform_chassis.get_sfp(physical_port)

            if _wrapper_is_native_RJ45(physical_port, sfp_obj):
                xcvr_info_keys = [
                    'type', 'hardware_rev', 'serial', 'manufacturer',
                    'model', 'connector', 'encoding', 'ext_identifier',
                    'ext_rateselect_compliance', 'cable_type', 'cable_length', 'nominal_bit_rate',
                    'specification_compliance', 'type_abbrv_name','vendor_date', 'vendor_oui',
                    'application_advertisement'
                ]
                default_dict = {}.fromkeys(xcvr_info_keys, 'N/A')
                default_dict['type'] = 'RJ45'
                default_dict['type_abbrv_name'] = 'RJ45'
                default_dict['connector'] = 'RJ45'
                default_dict['display_name'] = 'RJ45'
            else:
                default_dict = sfp_obj.get_transceiver_info()

                # Try ext method if available
                if ext_media_module is not None:
                    try:
                        # Does it conform?
                        if not hasattr(sfp_obj, 'get_eeprom_sysfs_path'):
                            # Does not conform to eeprom_sysfs_path
                            eeprom_path = ''
                            try:
                                if hasattr(sfp_obj, 'eeprom_path'): eeprom_path = sfp_obj.eeprom_path
                                # Trying sfputil method
                                else: eeprom_path = platform_sfputil.port_to_eeprom_mapping[physical_port]
                            except:
                                pass
                            # Lib expects this method
                            def get_eeprom_sysfs_path(): return eeprom_path
                            sfp_obj.get_eeprom_sysfs_path = get_eeprom_sysfs_path
                        ext_dict = ext_media_module.get_static_info(sfp_obj, platform_chassis)

                        # Update the default dict with new values
                        for s in remap:
                            new_val = ext_dict.get(remap[s], 'N/A')
                            if new_val != 'N/A':
                                default_dict[s] = new_val
                        # We might be overwriting the correct 'vendor_oui' present in the default_dict with 'N/A'
                        ext_dict.pop('vendor_oui', None)
                        default_dict.update(ext_dict)
                    except:
                        pass

            return _transceiver_info_fixup(default_dict)

        except NotImplementedError:
            pass
        except Exception as e:
            helper_logger.log_error("Error in get_transceiver_info for port {} - {}".format(physical_port, e))
            return None

    default_dict = platform_sfputil.get_transceiver_info_dict(physical_port)
    return _transceiver_info_fixup(default_dict)

def _wrapper_get_transceiver_dom_info(physical_port):
    if platform_chassis is not None:
        try:
            sfp = platform_chassis.get_sfp(physical_port)
            if _wrapper_is_native_RJ45(physical_port, sfp):
                return None
            else:
                return sfp.get_transceiver_bulk_status()
        except NotImplementedError:
            pass
    return platform_sfputil.get_transceiver_dom_info_dict(physical_port)


def _wrapper_get_transceiver_dom_threshold_info(physical_port):
    if platform_chassis is not None:
        try:
            sfp = platform_chassis.get_sfp(physical_port)
            if _wrapper_is_native_RJ45(physical_port, sfp):
                return None
            else:
                return sfp.get_transceiver_threshold_info()
        except NotImplementedError:
            pass
    return platform_sfputil.get_transceiver_dom_threshold_info_dict(physical_port)

def _wrapper_get_transceiver_media_type_notify(physical_port):
    if platform_chassis is not None:
        return None
    else:
        try:
            return platform_sfputil.is_media_type_set_required(physical_port)
        except NotImplementedError:
            return None

def _wrapper_get_transceiver_change_event():
    if platform_chassis is not None:
        try:
            status, events = platform_chassis.get_change_event(TIME_FOR_SFP_POLL_SECS * 1000)
            sfp_events = events['sfp']
            return status, sfp_events
        except NotImplementedError:
            raise NotImplementedError
    else:
        return platform_sfputil.get_transceiver_change_event()

def _wrapper_check_transceiver_compatible(physical_port, xcvr_info, port_speed):
    if platform_chassis is None: # Platform API 1.0
        return platform_sfputil.get_transceiver_compatibility(physical_port, port_speed)
    else:                        # Platform API 2.0
        return platform_sfputil.get_transceiver_compatibility(xcvr_info, port_speed)

# Load media settings key plugin, if available
try:
    import sonic_platform.media_settings_plugin
    get_media_settings_key_plugin = sonic_platform.media_settings_plugin.get_media_settings_key
except:
    get_media_settings_key_plugin = None

# Wrapper to call plugin, if loaded

def _wrapper_get_media_settings_key(physical_port, transceiver_dict):
    if get_media_settings_key_plugin is not None:
        return get_media_settings_key_plugin(physical_port, transceiver_dict)
    return get_media_settings_key(physical_port, transceiver_dict)
    
def _wrapper_get_sfp_type(physical_port):
    if platform_chassis:
        try:
            return platform_chassis.get_sfp(physical_port).sfp_type
        except (NotImplementedError, AttributeError):
            pass
    return None

# Remove unnecessary unit from the raw data
def beautify_dom_info_dict(dom_info_dict, physical_port=None):
    dom_info_dict['temperature'] = strip_unit_and_beautify(dom_info_dict['temperature'], TEMP_UNIT)
    dom_info_dict['voltage'] = strip_unit_and_beautify(dom_info_dict['voltage'], VOLT_UNIT)
    dom_info_dict['rx1power'] = strip_unit_and_beautify(dom_info_dict['rx1power'], POWER_UNIT)
    dom_info_dict['rx2power'] = strip_unit_and_beautify(dom_info_dict['rx2power'], POWER_UNIT)
    dom_info_dict['rx3power'] = strip_unit_and_beautify(dom_info_dict['rx3power'], POWER_UNIT)
    dom_info_dict['rx4power'] = strip_unit_and_beautify(dom_info_dict['rx4power'], POWER_UNIT)
    dom_info_dict['tx1bias'] = strip_unit_and_beautify(dom_info_dict['tx1bias'], BIAS_UNIT)
    dom_info_dict['tx2bias'] = strip_unit_and_beautify(dom_info_dict['tx2bias'], BIAS_UNIT)
    dom_info_dict['tx3bias'] = strip_unit_and_beautify(dom_info_dict['tx3bias'], BIAS_UNIT)
    dom_info_dict['tx4bias'] = strip_unit_and_beautify(dom_info_dict['tx4bias'], BIAS_UNIT)
    dom_info_dict['tx1power'] = strip_unit_and_beautify(dom_info_dict['tx1power'], POWER_UNIT)
    dom_info_dict['tx2power'] = strip_unit_and_beautify(dom_info_dict['tx2power'], POWER_UNIT)
    dom_info_dict['tx3power'] = strip_unit_and_beautify(dom_info_dict['tx3power'], POWER_UNIT)
    dom_info_dict['tx4power'] = strip_unit_and_beautify(dom_info_dict['tx4power'], POWER_UNIT)
    if physical_port is not None: 
        if 'rx5power' in dom_info_dict:
            dom_info_dict['rx5power'] = strip_unit_and_beautify(dom_info_dict['rx5power'], POWER_UNIT)
            dom_info_dict['rx6power'] = strip_unit_and_beautify(dom_info_dict['rx6power'], POWER_UNIT)
            dom_info_dict['rx7power'] = strip_unit_and_beautify(dom_info_dict['rx7power'], POWER_UNIT)
            dom_info_dict['rx8power'] = strip_unit_and_beautify(dom_info_dict['rx8power'], POWER_UNIT)
            dom_info_dict['tx5bias'] = strip_unit_and_beautify(dom_info_dict['tx5bias'], BIAS_UNIT)
            dom_info_dict['tx6bias'] = strip_unit_and_beautify(dom_info_dict['tx6bias'], BIAS_UNIT)
            dom_info_dict['tx7bias'] = strip_unit_and_beautify(dom_info_dict['tx7bias'], BIAS_UNIT)
            dom_info_dict['tx8bias'] = strip_unit_and_beautify(dom_info_dict['tx8bias'], BIAS_UNIT)
            dom_info_dict['tx5power'] = strip_unit_and_beautify(dom_info_dict['tx5power'], POWER_UNIT)
            dom_info_dict['tx6power'] = strip_unit_and_beautify(dom_info_dict['tx6power'], POWER_UNIT)
            dom_info_dict['tx7power'] = strip_unit_and_beautify(dom_info_dict['tx7power'], POWER_UNIT)
            dom_info_dict['tx8power'] = strip_unit_and_beautify(dom_info_dict['tx8power'], POWER_UNIT)


def beautify_dom_threshold_info_dict(dom_info_dict):
    dom_info_dict['temphighalarm'] = strip_unit_and_beautify(dom_info_dict['temphighalarm'], TEMP_UNIT)
    dom_info_dict['temphighwarning'] = strip_unit_and_beautify(dom_info_dict['temphighwarning'], TEMP_UNIT)
    dom_info_dict['templowalarm'] = strip_unit_and_beautify(dom_info_dict['templowalarm'], TEMP_UNIT)
    dom_info_dict['templowwarning'] = strip_unit_and_beautify(dom_info_dict['templowwarning'], TEMP_UNIT)

    dom_info_dict['vcchighalarm'] = strip_unit_and_beautify(dom_info_dict['vcchighalarm'], VOLT_UNIT)
    dom_info_dict['vcchighwarning'] = strip_unit_and_beautify(dom_info_dict['vcchighwarning'], VOLT_UNIT)
    dom_info_dict['vcclowalarm'] = strip_unit_and_beautify(dom_info_dict['vcclowalarm'], VOLT_UNIT)
    dom_info_dict['vcclowwarning'] = strip_unit_and_beautify(dom_info_dict['vcclowwarning'], VOLT_UNIT)

    dom_info_dict['txpowerhighalarm'] = strip_unit_and_beautify(dom_info_dict['txpowerhighalarm'], POWER_UNIT)
    dom_info_dict['txpowerlowalarm'] = strip_unit_and_beautify(dom_info_dict['txpowerlowalarm'], POWER_UNIT)
    dom_info_dict['txpowerhighwarning'] = strip_unit_and_beautify(dom_info_dict['txpowerhighwarning'], POWER_UNIT)
    dom_info_dict['txpowerlowwarning'] = strip_unit_and_beautify(dom_info_dict['txpowerlowwarning'], POWER_UNIT)

    dom_info_dict['rxpowerhighalarm'] = strip_unit_and_beautify(dom_info_dict['rxpowerhighalarm'], POWER_UNIT)
    dom_info_dict['rxpowerlowalarm'] = strip_unit_and_beautify(dom_info_dict['rxpowerlowalarm'], POWER_UNIT)
    dom_info_dict['rxpowerhighwarning'] = strip_unit_and_beautify(dom_info_dict['rxpowerhighwarning'], POWER_UNIT)
    dom_info_dict['rxpowerlowwarning'] = strip_unit_and_beautify(dom_info_dict['rxpowerlowwarning'], POWER_UNIT)

    dom_info_dict['txbiashighalarm'] = strip_unit_and_beautify(dom_info_dict['txbiashighalarm'], BIAS_UNIT)
    dom_info_dict['txbiaslowalarm'] = strip_unit_and_beautify(dom_info_dict['txbiaslowalarm'], BIAS_UNIT)
    dom_info_dict['txbiashighwarning'] = strip_unit_and_beautify(dom_info_dict['txbiashighwarning'], BIAS_UNIT)
    dom_info_dict['txbiaslowwarning'] = strip_unit_and_beautify(dom_info_dict['txbiaslowwarning'], BIAS_UNIT)

# Update port sfp info in db
def post_port_sfp_info_to_db(logical_port_name, table, transceiver_dict, skip_sfp_read, stop_event=threading.Event()):
    ganged_port = False
    ganged_member_num = 1

    physical_port_list = logical_port_name_to_physical_port_list(logical_port_name)
    if physical_port_list is None:
        helper_logger.log_error("No physical ports found for logical port '{}'".format(logical_port_name))
        return PHYSICAL_PORT_NOT_EXIST

    if len(physical_port_list) > 1:
        ganged_port = True

    for physical_port in physical_port_list:
        if stop_event.is_set():
            break

        if skip_sfp_read == False and not _wrapper_get_presence(physical_port):
            continue
        if skip_sfp_read == True and physical_port not in transceiver_dict:
            continue

        port_name = get_physical_port_name(logical_port_name, ganged_member_num, ganged_port)
        ganged_member_num += 1

        try:
            if skip_sfp_read == True:
                port_info_dict = transceiver_dict[physical_port]
            else:
                port_info_dict = _wrapper_get_transceiver_info(physical_port)

            # global cache for the transceiver info
            g_xcvr[logical_port_name] = port_info_dict
            g_xcvr[physical_port] = port_info_dict

            if port_info_dict is not None:
                is_replaceable = _wrapper_is_replaceable(physical_port)
                if skip_sfp_read == False:
                    transceiver_dict[physical_port] = port_info_dict
                fvs = swsscommon.FieldValuePairs(
                    [('type', port_info_dict['type']),
                     ('hardware_rev', port_info_dict['hardware_rev']),
                     ('serial', port_info_dict['serial']),
                     ('manufacturer', port_info_dict['manufacturer']),
                     ('model', port_info_dict['model']),
                     ('vendor_oui', port_info_dict['vendor_oui']),
                     ('vendor_date', port_info_dict['vendor_date']),
                     ('connector', port_info_dict['connector']),
                     ('encoding', port_info_dict['encoding']),
                     ('ext_identifier', port_info_dict['ext_identifier']),
                     ('ext_rateselect_compliance', port_info_dict['ext_rateselect_compliance']),
                     ('cable_type', port_info_dict['cable_type']),
                     ('cable_length', port_info_dict['cable_length']),
                     ('specification_compliance', port_info_dict['specification_compliance']),
                     ('nominal_bit_rate', port_info_dict['nominal_bit_rate']),
                     ('application_advertisement', port_info_dict['application_advertisement']
                      if 'application_advertisement' in port_info_dict else 'N/A'),
                     ('is_replaceable', str(is_replaceable)),
                     ])
                table.set(port_name, fvs)
                # extra entries due to ext_media library
                fvs = swsscommon.FieldValuePairs(list(port_info_dict.items()))
                table.set(port_name, fvs)
            else:
                return SFP_EEPROM_NOT_READY

        except NotImplementedError:
            helper_logger.log_error("This functionality is currently not implemented for this platform")
            sys.exit(NOT_IMPLEMENTED_ERROR)

# Update port dom threshold info in db


def post_port_dom_threshold_info_to_db(logical_port_name, table,
                                       stop=threading.Event(), cache=None):
    #Initialize the DOM Threshold dict with default (N/A) Values for passive
    #copper media since they do not have DOM contents
    default_xcvr_thres_dom_values = {}

    dom_info_dict_keys = ['temphighalarm', 'temphighwarning',
                          'templowalarm', 'templowwarning',
                          'vcchighalarm', 'vcchighwarning',
                          'vcclowalarm', 'vcclowwarning',
                          'rxpowerhighalarm', 'rxpowerhighwarning',
                          'rxpowerlowalarm', 'rxpowerlowwarning',
                          'txpowerhighalarm', 'txpowerhighwarning',
                          'txpowerlowalarm', 'txpowerlowwarning',
                          'txbiashighalarm', 'txbiashighwarning',
                          'txbiaslowalarm', 'txbiaslowwarning'
                         ]
    default_xcvr_thres_dom_values = {}.fromkeys(dom_info_dict_keys, 'N/A')

    ganged_port = False
    ganged_member_num = 1

    physical_port_list = logical_port_name_to_physical_port_list(logical_port_name)
    if physical_port_list is None:
        helper_logger.log_error("No physical ports found for logical port '{}'".format(logical_port_name))
        return PHYSICAL_PORT_NOT_EXIST

    if len(physical_port_list) > 1:
        ganged_port = True

    for physical_port in physical_port_list:
        if stop.is_set():
            break

        time.sleep(0.001)
        if not _wrapper_get_presence(physical_port) or \
            _wrapper_is_native_RJ45(physical_port):
            continue

        port_name = get_physical_port_name(logical_port_name,
                                           ganged_member_num, ganged_port)
        ganged_member_num += 1

        try:
            dom_info_dict = None
            if cache is not None:
                dom_info_dict = cache.get(physical_port)
            #Skip reading EEPROM for media with no DOM support and populate default
            #values (N/A) for this media which gets used by northbound interfaces
            if not dom_is_supported(logical_port_name):
                dom_info_dict = default_xcvr_thres_dom_values
            if dom_info_dict is None:
                dom_info_dict = _wrapper_get_transceiver_dom_threshold_info(physical_port)
            if cache is not None:
                cache[physical_port] = dom_info_dict
            if dom_info_dict is not None:
                beautify_dom_threshold_info_dict(dom_info_dict)
                fvs = swsscommon.FieldValuePairs(
                    [('temphighalarm', dom_info_dict['temphighalarm']),
                     ('temphighwarning', dom_info_dict['temphighwarning']),
                     ('templowalarm', dom_info_dict['templowalarm']),
                     ('templowwarning', dom_info_dict['templowwarning']),
                     ('vcchighalarm', dom_info_dict['vcchighalarm']),
                     ('vcchighwarning', dom_info_dict['vcchighwarning']),
                     ('vcclowalarm', dom_info_dict['vcclowalarm']),
                     ('vcclowwarning', dom_info_dict['vcclowwarning']),
                     ('txpowerhighalarm', dom_info_dict['txpowerhighalarm']),
                     ('txpowerlowalarm', dom_info_dict['txpowerlowalarm']),
                     ('txpowerhighwarning', dom_info_dict['txpowerhighwarning']),
                     ('txpowerlowwarning', dom_info_dict['txpowerlowwarning']),
                     ('rxpowerhighalarm', dom_info_dict['rxpowerhighalarm']),
                     ('rxpowerlowalarm', dom_info_dict['rxpowerlowalarm']),
                     ('rxpowerhighwarning', dom_info_dict['rxpowerhighwarning']),
                     ('rxpowerlowwarning', dom_info_dict['rxpowerlowwarning']),
                     ('txbiashighalarm', dom_info_dict['txbiashighalarm']),
                     ('txbiaslowalarm', dom_info_dict['txbiaslowalarm']),
                     ('txbiashighwarning', dom_info_dict['txbiashighwarning']),
                     ('txbiaslowwarning', dom_info_dict['txbiaslowwarning'])
                     ])
                table.set(port_name, fvs)
            else:
                return SFP_EEPROM_NOT_READY

        except NotImplementedError:
            helper_logger.log_error("This functionality is currently not implemented for this platform")
            sys.exit(NOT_IMPLEMENTED_ERROR)

# Update port dom sensor info in db
def post_port_dom_info_to_db(logical_port_name, table, stop_event=threading.Event(), cache=None):

    ganged_port = False
    ganged_member_num = 1

    physical_port_list = logical_port_name_to_physical_port_list(logical_port_name)
    if physical_port_list is None:
        helper_logger.log_error("No physical ports found for logical port '{}'".format(logical_port_name))
        return PHYSICAL_PORT_NOT_EXIST

    #Skip reading EEPROM for media with no DOM support. During Bootup/SFP Insertion
    #default values (N/A) are already set in the TRANSCEIVER_INFO Table.
    if not dom_is_supported(logical_port_name):
        return

    if len(physical_port_list) > 1:
        ganged_port = True

    for physical_port in physical_port_list:
        if stop_event.is_set():
            break

        time.sleep(0.001)
        if not _wrapper_get_presence(physical_port):
            continue

        port_name = get_physical_port_name(logical_port_name, ganged_member_num, ganged_port)
        ganged_member_num += 1

        try:
            dom_info_dict = None
            if cache is not None:
                dom_info_dict = cache.get(physical_port)
            if dom_info_dict is None:
                dom_info_dict = _wrapper_get_transceiver_dom_info(physical_port)
            if cache is not None:
                cache[physical_port] = dom_info_dict
            if dom_info_dict is not None:
                beautify_dom_info_dict(dom_info_dict, physical_port)
                if 'rx5power' in dom_info_dict:
                    fvs = swsscommon.FieldValuePairs(
                        [('temperature', dom_info_dict['temperature']),
                         ('voltage', dom_info_dict['voltage']),
                         ('rx1power', dom_info_dict['rx1power']),
                         ('rx2power', dom_info_dict['rx2power']),
                         ('rx3power', dom_info_dict['rx3power']),
                         ('rx4power', dom_info_dict['rx4power']),
                         ('rx5power', dom_info_dict['rx5power']),
                         ('rx6power', dom_info_dict['rx6power']),
                         ('rx7power', dom_info_dict['rx7power']),
                         ('rx8power', dom_info_dict['rx8power']),
                         ('tx1bias', dom_info_dict['tx1bias']),
                         ('tx2bias', dom_info_dict['tx2bias']),
                         ('tx3bias', dom_info_dict['tx3bias']),
                         ('tx4bias', dom_info_dict['tx4bias']),
                         ('tx5bias', dom_info_dict['tx5bias']),
                         ('tx6bias', dom_info_dict['tx6bias']),
                         ('tx7bias', dom_info_dict['tx7bias']),
                         ('tx8bias', dom_info_dict['tx8bias']),
                         ('tx1power', dom_info_dict['tx1power']),
                         ('tx2power', dom_info_dict['tx2power']),
                         ('tx3power', dom_info_dict['tx3power']),
                         ('tx4power', dom_info_dict['tx4power']),
                         ('tx5power', dom_info_dict['tx5power']),
                         ('tx6power', dom_info_dict['tx6power']),
                         ('tx7power', dom_info_dict['tx7power']),
                         ('tx8power', dom_info_dict['tx8power'])
                         ])
                else:
                    fvs = swsscommon.FieldValuePairs(
                        [('temperature', dom_info_dict['temperature']),
                         ('voltage', dom_info_dict['voltage']),
                         ('rx1power', dom_info_dict['rx1power']),
                         ('rx2power', dom_info_dict['rx2power']),
                         ('rx3power', dom_info_dict['rx3power']),
                         ('rx4power', dom_info_dict['rx4power']),
                         ('tx1bias', dom_info_dict['tx1bias']),
                         ('tx2bias', dom_info_dict['tx2bias']),
                         ('tx3bias', dom_info_dict['tx3bias']),
                         ('tx4bias', dom_info_dict['tx4bias']),
                         ('tx1power', dom_info_dict['tx1power']),
                         ('tx2power', dom_info_dict['tx2power']),
                         ('tx3power', dom_info_dict['tx3power']),
                         ('tx4power', dom_info_dict['tx4power'])
                         ])

                table.set(port_name, fvs)

            else:
                return SFP_EEPROM_NOT_READY

        except NotImplementedError:
            helper_logger.log_error("This functionality is currently not implemented for this platform")
            sys.exit(NOT_IMPLEMENTED_ERROR)

# Update port diag info in db
def post_port_diag_info_to_db(logical_port_name, table, stop_event=threading.Event(), cache=None):
    ganged_port = False
    ganged_member_num = 1

    physical_port_list = logical_port_name_to_physical_port_list(logical_port_name)
    if physical_port_list is None:
        helper_logger.log_error("No physical ports found for logical port '%s'" % logical_port_name)
        return PHYSICAL_PORT_NOT_EXIST

    if len(physical_port_list) > 1:
        ganged_port = True

    for physical_port in physical_port_list:
        if stop_event.is_set():
            break

        port_name = get_physical_port_name(logical_port_name, ganged_member_num, ganged_port)
        ganged_member_num += 1

        if not _wrapper_get_presence(physical_port):
            try:
                table._del(port_name)
            except:
                pass
            continue

        try:
            buf = None
            if cache is not None:
                buf = cache.get(physical_port)
            if buf is None:
                buf = platform_chassis.get_sfp(physical_port).get_transceiver_diag_status()
            if cache is not None:
                cache[physical_port] = buf
            if buf is None or len(buf) == 0:
                try:
                    table._del(port_name)
                except:
                    pass
                continue

            fvs_raw = []
            for key in buf.keys():
                fvp_raw = (key, buf[key])
                fvs_raw.append(fvp_raw)
            fvs = swsscommon.FieldValuePairs(fvs_raw)
            table.set(port_name, fvs)
        except Exception as ex:
            # Failure is expected when its SFP plugin does not inherit from SfpStandard.
            pass

xcvr_state_tbl = {
    XCVR_STATE_EMPTY:   { "xcvr_state": "N/A",          "xcvr_app_status": "down" },
    XCVR_STATE_ERROR:   { "xcvr_state": "Error",        "xcvr_app_status": "down" },
    XCVR_STATE_INCOMP:  { "xcvr_state": "Incompatible", "xcvr_app_status": "up" },
    XCVR_STATE_CONFIG:  { "xcvr_state": "Config",       "xcvr_app_status": "down" },
    XCVR_STATE_READY:   { "xcvr_state": "Ready",        "xcvr_app_status": "up" }
}

def notify_port_xcvr_status(port_name, app_status_port_tbl, state_port_xcvr_tbl, flag):
    xcvr_sync_file_path = "/usr/share/sonic/platform/xcvr_sync"

    # TODO change to reversed logic to enable xcvr_sync
    if os.path.isfile(xcvr_sync_file_path):
        return True

    # xcvr state not in list, consider error
    if flag not in xcvr_state_tbl:
        helper_logger.log_error("Port {} xcvr_app_status {} not support".format(port_name, flag))
        flag = XCVR_STATE_ERROR

    fvs = swsscommon.FieldValuePairs([("xcvr_status", xcvr_state_tbl[flag]["xcvr_app_status"])])
    tm = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    state_fvs = swsscommon.FieldValuePairs([("xcvr_status", xcvr_state_tbl[flag]["xcvr_state"]), ("xcvr_time", tm)])

    state_port_xcvr_tbl.set(port_name, state_fvs)

    app_status_port_tbl.set(port_name, fvs)

    helper_logger.log_notice("Port {} xcvr_app_status change to {}".format(port_name, xcvr_state_tbl[flag]["xcvr_app_status"]))

    xcvr_config_updater.notify_port_status(port_name, g_xcvr.get(port_name), flag)

    return True

###
### Collect SFP info before PortInitDone
### to reduce time of post_port_sfp_dom_info_to_db
###
def port_sfp_info_collect(transceiver_dict):
    logical_port_list = platform_sfputil.logical

    helper_logger.log_info("Start: load port SFP info.")
    for logical_port_name in logical_port_list:
        physical_port_list = logical_port_name_to_physical_port_list(logical_port_name)
        if physical_port_list is None:
            continue

        for physical_port in physical_port_list:
            time.sleep(0.001)
            if not _wrapper_get_presence(physical_port):
                continue

            port_info_dict = _wrapper_get_transceiver_info(physical_port)
            if port_info_dict is not None:
                transceiver_dict[physical_port]=port_info_dict
            else:
                helper_logger.log_error("load port {} SFP info failed.".format(physical_port))

    helper_logger.log_notice("End: load port SFP info.")

def default_passive_media_dom_entry_set(logical_port_name, dom_table):
    """
    Initialize the DOM dict with default (N/A) Values for media which 
    does not have DOM support
    """
    default_dom_dict = {}

    dom_info_dict_keys = ['temperature', 'voltage', 'rx1power',
                          'rx2power', 'rx3power', 'rx4power',
                          'tx1bias', 'tx2bias', 'tx3bias',
                          'tx4bias', 'tx1power', 'tx2power',
                          'tx3power', 'tx4power',
                         ]
    default_dom_dict = {}.fromkeys(dom_info_dict_keys, 'N/A')

    ganged_port = False
    ganged_member_num = 1

    physical_port_list = logical_port_name_to_physical_port_list(logical_port_name)
    if physical_port_list is None:
        helper_logger.log_error("No physical ports found for " \
                                "logical port {}".format(logical_port_name))
        return

    if len(physical_port_list) > 1:
        ganged_port = True

    for physical_port in physical_port_list:
        if not _wrapper_get_presence(physical_port) or \
            _wrapper_is_native_RJ45(physical_port):
            continue

        port_name = get_physical_port_name(logical_port_name,
                                           ganged_member_num, ganged_port)
        ganged_member_num += 1
        fvs = swsscommon.FieldValuePairs(
            [('temperature', default_dom_dict['temperature']),
             ('voltage', default_dom_dict['voltage']),
             ('rx1power', default_dom_dict['rx1power']),
             ('rx2power', default_dom_dict['rx2power']),
             ('rx3power', default_dom_dict['rx3power']),
             ('rx4power', default_dom_dict['rx4power']),
             ('tx1bias', default_dom_dict['tx1bias']),
             ('tx2bias', default_dom_dict['tx2bias']),
             ('tx3bias', default_dom_dict['tx3bias']),
             ('tx4bias', default_dom_dict['tx4bias']),
             ('tx1power', default_dom_dict['tx1power']),
             ('tx2power', default_dom_dict['tx2power']),
             ('tx3power', default_dom_dict['tx3power']),
             ('tx4power', default_dom_dict['tx4power'])
             ])

        dom_table.set(port_name, fvs)

# Update port dom/sfp info in db
def post_port_sfp_dom_info_to_db(is_warm_start, mod_tbl, transceiver_dict, stop_event=threading.Event()):
    # Connect to STATE_DB and create transceiver dom/sfp info tables
    #transceiver_dict, state_db, appl_db, int_tbl, dom_tbl, app_port_tbl = {}, {}, {}, {}, {}, {}
    state_db, appl_db, int_tbl, dom_tbl, app_port_tbl, state_port_xcvr_tbl, app_status_port_tbl = {}, {}, {}, {}, {}, {}, {}

    # Get the namespaces in the platform
    namespaces = multi_asic.get_front_end_namespaces()
    for namespace in namespaces:
        asic_id = multi_asic.get_asic_index_from_namespace(namespace)
        state_db[asic_id] = daemon_base.db_connect("STATE_DB", namespace)
        appl_db[asic_id] = daemon_base.db_connect("APPL_DB", namespace)
        int_tbl[asic_id] = swsscommon.Table(state_db[asic_id], TRANSCEIVER_INFO_TABLE)
        dom_tbl[asic_id] = swsscommon.Table(state_db[asic_id], TRANSCEIVER_DOM_SENSOR_TABLE)
        app_port_tbl[asic_id] = swsscommon.ProducerStateTable(appl_db[asic_id], swsscommon.APP_PORT_TABLE_NAME)
        state_port_xcvr_tbl[asic_id] = swsscommon.Table(state_db[asic_id], STATE_PORT_XCVR_TABLE)
        app_status_port_tbl[asic_id] = swsscommon.ProducerStateTable(appl_db[asic_id], swsscommon.APP_PORT_APP_STATUS_TABLE_NAME)

    # Post all the current interface dom/sfp info to STATE_DB
    helper_logger.log_info("Begin: Post all port SFP info to DB")
    logical_port_list = platform_sfputil.logical
    for logical_port_name in logical_port_list:
        if stop_event.is_set():
            break
        asic_index = platform_sfputil.get_asic_id_for_logical_port(logical_port_name)
        if asic_index is None:
            helper_logger.log_debug("Got invalid asic index for {}, ignored".format(logical_port_name))
            #continue ----- #FIXME
            asic_index = 0

        physical_port_list = logical_port_name_to_physical_port_list(logical_port_name)
        if physical_port_list is None:
            continue
        for physical_port in physical_port_list:
            time.sleep(0.001)
            if not _wrapper_get_presence(physical_port):
                continue

            # Start config xcvr if not warm-boot
            if is_warm_start == False:
                notify_port_xcvr_status(logical_port_name, app_status_port_tbl[asic_index], state_port_xcvr_tbl[asic_index], XCVR_STATE_CONFIG)

            rc = post_port_sfp_info_to_db(logical_port_name, int_tbl[asic_index], transceiver_dict, START_SFP_READ_BEFORE_PORT_INIT, stop_event)
            if rc is None:
                if transceiver_dict.get(physical_port) is not None:
                    mod_tbl[physical_port] = SFP_STATE_READY
                ## Do not notify media settings during warm reboot to avoid dataplane traffic impact
                if is_warm_start == False:
                    xcvr_config_updater.prepare_for_config(logical_port_name)
                    # skipping interface_type notification here.
                    xcvr_state = notify_media_setting(logical_port_name, transceiver_dict, app_port_tbl[asic_index], False)
                    app_port_tbl[asic_index].flush()
                    notify_port_xcvr_status(logical_port_name, app_status_port_tbl[asic_index], state_port_xcvr_tbl[asic_index], xcvr_state)
                    power_up_media(logical_port_name, transceiver_dict, int_tbl[asic_index])
                else:
                    rec, fvp = state_port_xcvr_tbl[asic_index].get(logical_port_name)
                    if rec:
                        try:
                            xcvr_status_dict = dict(fvp)
                            xcvr_status = XCVR_STATE_READY if xcvr_status_dict['xcvr_status'] == "Ready" else XCVR_STATE_EMPTY
                            xcvr_config_updater.notify_port_status(logical_port_name, g_xcvr.get(logical_port_name), xcvr_status) 
                        except KeyError:
                            pass

                adapter = ""
                if transceiver_dict.get(physical_port) is not None:
                    d = transceiver_dict[physical_port]
                    adapter = "(" + d.get('qsa_adapter', 'N/A') +")" if d.get('qsa_adapter', 'N/A') not in ('N/A', 'Present') else ""
                if START_SFP_READ_BEFORE_PORT_INIT == False:
                    transceiver_dict.clear()

                helper_logger.log_notice(logical_port_name + ": SFP inserted" + str(adapter))
    helper_logger.log_notice("End: Post all port SFP info to DB")
    fvs = swsscommon.FieldValuePairs([("status", "yes")])
    # TODO correct the below code. int_tbl[asic_id] or int_tbl[asic_index]
    int_tbl[asic_id].set("XcvrInitDone", fvs)
    for logical_port_name in logical_port_list:
        if stop_event.is_set():
            break
        asic_index = platform_sfputil.get_asic_id_for_logical_port(logical_port_name)
        if asic_index is None:
            helper_logger.log_debug("Got invalid asic index for {}, ignored".format(logical_port_name))
            #continue ----- #FIXME
            asic_index = 0
        physical_port_list = logical_port_name_to_physical_port_list(logical_port_name)
        if physical_port_list is None:
            continue
        for physical_port in physical_port_list:
            time.sleep(0.001)
            if not _wrapper_get_presence(physical_port):
                continue
            post_port_dom_threshold_info_to_db(logical_port_name, dom_tbl[asic_index], stop_event)
        if not dom_is_supported(logical_port_name):
            default_passive_media_dom_entry_set(logical_port_name, dom_tbl[asic_index])
    helper_logger.log_info("SFP DOM/Threshold info updated")

    # Only clear SFP tx_disable pins after XcvrInitDone, otherwise some
    # 1G copper SFP may have carrier signal after reboot before port up.
    if is_warm_start == False and platform_chassis is not None:
        try:
            for sfp in platform_chassis.get_all_sfps():
                if sfp.hard_tx_disable(False) :
                    helper_logger.log_notice("Clear SFP module tx_disable")
        except NotImplementedError:
            helper_logger.log_info("SFP hard_tx_disable method not implemented")
        except Exception as ex:
            helper_logger.log_error("SFP hard_tx_disable method failed: {}".format(ex))

# Delete port dom/sfp info from db
def del_port_sfp_dom_info_from_db(logical_port_name, int_tbl, dom_tbl):

    ganged_port = False
    ganged_member_num = 1

    physical_port_list = logical_port_name_to_physical_port_list(logical_port_name)
    if physical_port_list is None:
        helper_logger.log_error("No physical ports found for logical " \
                                "port '{}'".format(logical_port_name))
        return PHYSICAL_PORT_NOT_EXIST

    if len(physical_port_list) > 1:
        ganged_port = True

    g_xcvr[logical_port_name] = None
    for physical_port in physical_port_list:
        g_xcvr[physical_port] = None
        port_name = get_physical_port_name(logical_port_name, ganged_member_num, ganged_port)
        ganged_member_num += 1

        try:
            if int_tbl != None:
                int_tbl._del(port_name)
            if dom_tbl != None:
                dom_tbl._del(port_name)

        except NotImplementedError:
            helper_logger.log_error("This functionality is currently not " \
                                    "implemented for this platform")
            sys.exit(NOT_IMPLEMENTED_ERROR)

#
# parse interface range/list string like 0-4,5,7,9-12
# return list of interfaces
#
def parse_interface_in_range(intf_filter):
    intf_fs = []

    if intf_filter is None:
        return intf_fs

    fs = intf_filter.split(',')
    for x in fs:
        if '-' in x:
            # handle range
            start = x.split('-')[0].strip()
            end = x.split('-')[1].strip()

            if not start.isdigit() or not end.isdigit():
                continue
            for i in range(int(start), int(end)+1):
                intf_fs.append(str(i))
        else:
            intf_fs.append(x)

    return intf_fs

# recover missing sfp table entries if any


def recover_missing_sfp_table_entries(sfp_util, int_tbl, status_tbl, stop_event):
    transceiver_dict = {}

    logical_port_list = sfp_util.logical
    for logical_port_name in logical_port_list:
        if stop_event.is_set():
            break

        # Get the asic to which this port belongs
        asic_index = sfp_util.get_asic_id_for_logical_port(logical_port_name)
        if asic_index is None:
            helper_logger.log_debug("Got invalid asic index for {}, ignored".format(logical_port_name))
            #continue ----- #FIXME
            asic_index = 0

        keys = int_tbl[asic_index].getKeys()
        if logical_port_name not in keys and not detect_port_in_error_status(logical_port_name, status_tbl[asic_index]):
            post_port_sfp_info_to_db(logical_port_name, int_tbl[asic_index], transceiver_dict, False, stop_event)

def media_init(logical_port, xcvr_dict=None):

    # Skip if PAI20 is not available
    if platform_chassis is None:
        return True

    physical_port_list = logical_port_name_to_physical_port_list(logical_port)
    if physical_port_list is None:
        return False

    xcvr_dict = None if g_xcvr is None else g_xcvr.get(logical_port)
    if xcvr_dict is None:
        return False

    if xcvr_dict.get('revision_compliance') not in ['3.0', '4.0', '5.0']:
        return False
    if xcvr_dict.get('media_type') == 'passive_copper_media_interface':
        return False

    if cmis_init_worker is not None:
        cmis_init_worker.task_notify(logical_port, physical_port_list, XCVR_EVENT_CONFIG, xcvr_dict)
    else:
        helper_logger.log_error("media_init: cmis init is not initiatzed")

    return True

# Set of initialized ports, to prevent double-init
initialized_port_set = set()
# Will initialize the media module as needed
def power_up_media(logical_port, transceiver_dict, int_tbl):
    global initialized_port_set

    physical_port_list = logical_port_name_to_physical_port_list(logical_port)

    if platform_chassis is None:
        return

    for physical_port in physical_port_list:
        ret = physical_port_high_power_media_check(int_tbl, physical_port, logical_port)
        if ret is not None and 'media_lock_down_state' in ret and ret['media_lock_down_state'] == True:
            continue
        if physical_port in initialized_port_set:
            # Not allowed to init port twice
            continue

        try:
            xcvr_dict = transceiver_dict.get(physical_port)
        except:
            xcvr_dict = None
        if xcvr_dict is None:
            continue

        try:
            media_init(logical_port, xcvr_dict)
        except Exception as ex:
            helper_logger.log_info("media_init: {}".format(ex))

        if ext_media_module is not None:
            # Try ext mod init sequence if available
            try:
                if xcvr_dict['form_factor'] == 'QSFP28':
                    media_power = xcvr_dict['power_rating_max']
                    sfp_obj = platform_chassis.get_sfp(physical_port)
                    if float(media_power) >= 4.0:
                        if sfp_obj.get_max_port_power() >= float(media_power):
                            helper_logger.log_info(logical_port + "Enabling High Power Class")
                            ext_media_module.qsfp28_enable_high_power_class(sfp_obj, float(media_power))
                        else:
                            helper_logger.log_warning(logical_port + ": High Power Media Not Supported. Media Power : %s Port Capacity : %s"%(media_power, str(sfp_obj.get_max_port_power())))
            except (KeyError, RuntimeError) :
                pass
        try:
            # Use default init by bringing out of low power mode
            if xcvr_dict.get('revision_compliance') not in ['3.0', '4.0', '5.0'] \
               or xcvr_dict.get('media_type') == 'passive_copper_media_interface':
                platform_chassis.get_sfp(physical_port).set_lpmode(False)
            initialized_port_set.add(physical_port)
            continue
        except:
            pass
        continue

# De-initialize media after removal
def power_down_media(logical_port):
    global initialized_port_set
    physical_port_list = logical_port_name_to_physical_port_list(logical_port)

    for physical_port in physical_port_list:
        try:
            # Ensure port is in low power mode
            platform_chassis.get_sfp(physical_port).set_lpmode(True)
        except:
            pass
        if physical_port in initialized_port_set:
            initialized_port_set.remove(physical_port)

g_ifdn_tbl = {}
def update_xcvr_if_reason(logical_port, op, event, reason='PHY_LINK_DOWN'):
    global g_ifdn_tbl

    helper_logger.log_debug("if-down-reason: {0},{1},{2}".format(logical_port, op, event))

    asic_id = platform_sfputil.get_asic_id_for_logical_port(logical_port)
    if asic_id is None:
        helper_logger.log_warning("if-down-reason: {0}: Unable to get asic index, fallback to 0".format(logical_port))
        asic_id = 0

    ifdn_tbl = g_ifdn_tbl.get(asic_id)
    if ifdn_tbl is None:
        appl_db = None
        for namespace in multi_asic.get_front_end_namespaces():
            if asic_id != multi_asic.get_asic_index_from_namespace(namespace):
                continue
            appl_db = daemon_base.db_connect("APPL_DB", namespace)
            break
        if appl_db is not None:
            ifdn_tbl = swsscommon.Table(appl_db, "IF_REASON_EVENT")
            g_ifdn_tbl[asic_id] = ifdn_tbl

    if ifdn_tbl is None:
        helper_logger.log_error("if-down-reason: {0}: Unable to create IF_REASON_EVENT table".format(logical_port))
        return

    if op == 'set':
        try:
            fvs = swsscommon.FieldValuePairs([\
                        ("reason", reason), \
                        ('timestamp', datetime.utcnow().strftime("%Y-%m-%d.%H:%M:%S.%f"))])
            ifdn_tbl.set("{0}:{1}".format(logical_port, event), fvs)
        except Exception as ex:
            helper_logger.log_error("if-down-reason: SET {0}:{1} {2}".format(logical_port, event, ex))
    elif op == 'del':
        try:
            ifdn_tbl._del("{0}:{1}".format(logical_port, event))
        except Exception as ex:
            helper_logger.log_error("if-down-reason: DEL {0}:{1} {2}".format(logical_port, event, ex))

    return

def do_sfp_insertion(logical_port, int_tbl, dom_tbl, app_port_tbl, app_status_port_tbl, state_port_xcvr_tbl):
    transceiver_dict = {}
    update_xcvr_if_reason(logical_port, 'del', 'transceiver_not_present')
    rc = post_port_sfp_info_to_db(logical_port, int_tbl, transceiver_dict, False)
    if rc == SFP_EEPROM_NOT_READY:
        helper_logger.log_warning(logical_port + ": SFP EEPROM is not ready (do_sfp_insertion)")
    elif rc is None:
        if not dom_is_supported(logical_port):
            default_passive_media_dom_entry_set(logical_port, dom_tbl)
        post_port_dom_threshold_info_to_db(logical_port, dom_tbl)
        xcvr_config_updater.prepare_for_config(logical_port)
        # Notify media setting and interface_type
        xcvr_state = notify_media_setting(logical_port, transceiver_dict, app_port_tbl, True)
        # Power up module for data transmission
        power_up_media(logical_port, transceiver_dict, int_tbl)

        notify_port_xcvr_status(logical_port, app_status_port_tbl, state_port_xcvr_tbl, xcvr_state)
        adapter = ""
        if g_xcvr.get(logical_port) is not None:
            d = g_xcvr[logical_port]
            adapter = "(" + d.get('qsa_adapter', 'N/A') +")" if d.get('qsa_adapter', 'N/A') not in ('N/A', 'Present') else ""

        transceiver_dict.clear()
        helper_logger.log_notice(logical_port + ": SFP inserted" + str(adapter))
    return 0 if rc is None else rc

def do_sfp_removal(logical_port, app_port_tbl, app_status_port_tbl, state_port_xcvr_tbl, int_tbl, dom_tbl):
    update_xcvr_if_reason(logical_port, 'set', 'transceiver_not_present')
    notify_port_xcvr_status(logical_port, app_status_port_tbl, state_port_xcvr_tbl, XCVR_STATE_EMPTY)
    adapter = ""
    if g_xcvr.get(logical_port) is not None:
        d = g_xcvr[logical_port]
        adapter = "(" + d.get('qsa_adapter', 'N/A') +")" if d.get('qsa_adapter', 'N/A') not in ('N/A', 'Present') else ""

    del_port_sfp_dom_info_from_db(logical_port, int_tbl, dom_tbl)
    # cleanup after media removal
    _wrapper_clear_eeprom_cache(logical_port)
    power_down_media(logical_port)
    helper_logger.log_notice(logical_port + ": SFP removed" + str(adapter))

def check_port_in_range(range_str, physical_port):
    range_separator = '-'
    range_list = range_str.split(range_separator)
    start_num = int(range_list[0].strip())
    end_num = int(range_list[1].strip())
    if start_num <= physical_port <= end_num:
        return True
    return False
#
# Get port per lane speed
#
def get_port_lane_speed(port):
    port_speed = platform_sfputil.get_logical_speed(port)
    port_lanes = platform_sfputil.get_logical_lanes(port)

    port_lanes_count = port_hw_lanes_count(port_speed, port_lanes)

    return str(int(int(port_speed)/port_lanes_count))


def get_media_compliance_code(d):
    media_compliance_code = ''

    sup_compliance_dict = ['10GEthernetComplianceCode', '10/40G Ethernet Compliance Code', '25/100G Ethernet Compliance Code']
    media_compliance_dict_str = d['specification_compliance'] if 'specification_compliance' in d else 'N/A'

    if media_compliance_dict_str != 'N/A':
        media_compliance_dict = ast.literal_eval(media_compliance_dict_str)

        for i in range(len(sup_compliance_dict)):
            if sup_compliance_dict[i] in media_compliance_dict:
               media_compliance_code = media_compliance_dict[sup_compliance_dict[i]]
    return media_compliance_code


#
# Get platform-dependent media setting value for physical_port and key
# physical_port: integer value of port index
# key:           value like ['FIBERSTORE-QSFP28-100G-DAC', 'QSFP28']
#
# 1. Search in SPEED_MEDIA_SETTINGS by port lane_speed first
#   a) if SPEED_MEDIA_SETTINGS exists, use tuning values base on port lane_speed
#   b) if no SPEED_MEDIA_SETTINGS in media_settings.json, then fall back to tune by transceivers
#
# 2. if input key is empty, means called from port speed change handler
#   a) if SPEED_MEDIA_SETTINGS exists, use tuning values base on port lane_speed
#   b) if no SPEED_MEDIA_SETTINGS in media_settings.json, then skip transceiver tuning
#      serdes tuning should be called from do_sfp_insertion()
#
def get_media_settings_value(physical_port, logical_port_name, key):
    range_separator = '-'
    comma_separator = ','
    media_dict = {}
    default_dict = {}

    if "SPEED_MEDIA_SETTINGS" in g_dict:
        # Get lane speed (string)
        port_lane_speed = get_port_lane_speed(logical_port_name)
        # Get port specific parameters
        for intf in g_dict["SPEED_MEDIA_SETTINGS"]:
            intf_fs = parse_interface_in_range(intf)
            if str(physical_port) in intf_fs:
                media_dict = g_dict["SPEED_MEDIA_SETTINGS"][intf]
                break
        # Find the port specific parameters from <lane_speed>,<key>
        for txr_key in media_dict:
            for k in key:
                p = "{0},{1}".format(port_lane_speed, k)
                if txr_key.find(',') < 0:
                    continue
                if re.match(txr_key, p) is not None:
                    return [txr_key, media_dict[txr_key], "S_{0}".format(p)]
        # Find the port specific parameters from <lane_speed>
        for txr_key in media_dict:
            if txr_key.find(',') >= 0:
                continue
            if float(port_lane_speed) == float(txr_key):
                return [txr_key, media_dict[txr_key], "S_{0}".format(port_lane_speed)]

    if len(key) == 0:
        return ["", default_dict, "Not Need"]

    # Keys under global media settings can be a list or range or list of ranges
    # of physical port numbers. Below are some examples
    # 1-32
    # 1,2,3,4,5
    # 1-4,9-12

    if "GLOBAL_MEDIA_SETTINGS" in g_dict:
        for keys in g_dict["GLOBAL_MEDIA_SETTINGS"]:
            keys_fs = parse_interface_in_range(keys)
            if str(physical_port) in keys_fs:
                media_dict = g_dict["GLOBAL_MEDIA_SETTINGS"][keys]
                break

        # If there is a match in the global profile for a media type,
        # fetch those values
        #
        for txr_key in media_dict:
            i = 0
            for k in key:
                if (k in txr_key.split(',') or
                    re.match(txr_key, k) is not None
                    ):
                    return [txr_key, media_dict[txr_key], "G_{}".format(i)]
                i += 1

        if "Default" in media_dict:
            default_dict = media_dict['Default']

    media_dict = {}

    if "PORT_MEDIA_SETTINGS" in g_dict:
        for keys in g_dict["PORT_MEDIA_SETTINGS"]:
            keys_fs = parse_interface_in_range(keys)
            if str(physical_port) in keys_fs:
                media_dict = g_dict["PORT_MEDIA_SETTINGS"][keys]
                break

        if len(media_dict) == 0:
            if default_dict != 0:
                return ["default_dict", default_dict, "G_D"]
            else:
                helper_logger.log_error("Error: No values for physical port '%d'" % physical_port)
            return ["", {}, "N_F"]

        for txr_key in media_dict:
            i = 0
            for k in key:
                if (k in txr_key.split(',') or
                    re.match(txr_key, k) is not None
                    ):
                    return txr_key, media_dict[txr_key], "P_{}".format(i)
                i += 1

        if "Default" in media_dict:
            return ["default_dict", media_dict['Default'], "P_D"]
        elif len(default_dict) != 0:
            return ["default_dict", default_dict, "G_D"]
        else:
            return ["", {}, "N_F"]

    else:
       if default_dict != 0:
            return ["default_dict", default_dict, "N_F"]

# MEDIA TYPE: 'COPPER' or 'OPTICAL'
def get_media_type(transceiver_dict):
    type = 'COPPER'

    if ('application_advertisement' in transceiver_dict) and \
       (transceiver_dict['application_advertisement'] != 'N/A'):
        media_compliance_dict_str = transceiver_dict['application_advertisement']
    else:
        media_compliance_dict_str = transceiver_dict['specification_compliance']
    if ('BASE-CR' in media_compliance_dict_str) or ('BASE-T' in media_compliance_dict_str) or \
       ('BASE-CX' in media_compliance_dict_str) or ('ACC' in media_compliance_dict_str) or \
       ('Passive Cable' in media_compliance_dict_str) or (transceiver_dict.get('media_interface') == 'CR'):
        type = 'COPPER'
    else:
        type = 'OPTICAL'

    return type

def dom_is_supported(port_name):
    """
    Checks if the media inserted has DOM support. If DOM support
    is not present, skip reading the DOM EEPROM contents
    """

    xcvr_info = g_xcvr.get(port_name)
    if xcvr_info is None or 'cable_class' not in xcvr_info:
        return False

    physical_port_list = logical_port_name_to_physical_port_list(port_name, False)
    if physical_port_list is None or platform_chassis is None:
        return False

    physical_port = physical_port_list[0]
    media = platform_chassis.get_sfp(physical_port)
    if xcvr_info.get('cable_class') == "DAC" and not media.copper_dom_supported():
        return False

    return True

def get_media_settings_key(physical_port, transceiver_dict):
    d = transceiver_dict[physical_port]
    sup_len_str = 'Length Cable Assembly(m)'
    vendor_name_str = d['manufacturer'] if 'manufacturer' in d else ''
    vendor_pn_str = d['model'] if 'model' in d else ''
    vendor_key = vendor_name_str.upper() + '-' + vendor_pn_str if (vendor_name_str or vendor_pn_str) else ''
    media_len = ''
    if 'cable_type' in d and d['cable_type'] == sup_len_str:
        media_len = d['cable_length']

    media_compliance_code = get_media_compliance_code(d)

    # For some 'SFP+' media, 'type_abbrv_name' is 'SFP' and it is misleading.
    # Using 'type_abbrv_name' only when 'form_factor' is not available
    if 'form_factor' in d and d['form_factor'] != '':
        media_type = d['form_factor']
    else:
        media_type = d['type_abbrv_name'] if 'type_abbrv_name' in d else ''

    media_key = ''
    if len(media_type) != 0:
        media_key += media_type
        if media_type == "SFP":
            if ('nominal_bit_rate' in d) and (d['nominal_bit_rate'] == '255'):
                media_key += '28'

    if len(media_compliance_code) != 0:
        media_key += '-' + media_compliance_code

        # do not use media_len if not program 
        if len(media_len) != 0 and media_len != '0' and media_len != '0.0':
            media_key += '-' + media_len + 'M'

    form_factor_media_if_key = ''
    # Entries may not be present
    try:
        media_interface = d['media_interface']
        form_factor_media_if_key = '{}-{}'.format(d['form_factor'], media_interface)
        if media_interface == 'CR':
            form_factor_media_if_key = '{}-{}'.format(form_factor_media_if_key, d['cable_length_detailed'])
    except:
        pass

    # media_type|cable_length
    media_type_ext = []
    media_type_ext.append(get_media_type(d))
    if len(media_len) != 0 and media_len != '0' and media_len != '0.0':
        media_type_ext.append(media_len + 'M')

    media_keys = [vendor_key, media_key, form_factor_media_if_key]
    if len(media_type_ext) > 1:
        media_keys.append("-".join(media_type_ext))
    media_keys.append(media_type_ext[0])
    return media_keys


def get_media_val_str_from_dict(media_dict):
    media_str = ''
    lane_str = 'lane'
    lane_separator = ','
    tmp_dict = {}

    for keys in media_dict:
        lane_num = int(keys.strip()[len(lane_str):])
        tmp_dict[lane_num] = media_dict[keys]

    for key in range(0, len(tmp_dict)):
        media_str += tmp_dict[key]
        if key != list(tmp_dict.keys())[-1]:
            media_str += lane_separator
    return media_str


def get_media_val_str(lane_dict, logical_idx, num_lanes_per_logical_port):
    lane_str = "lane"
    logical_media_dict = {}
    media_val_str = ''

    #For each logical port, start lane gives the index of first lane assigned
    start_lane = logical_idx * num_lanes_per_logical_port
    for lane_idx in range(start_lane, start_lane + num_lanes_per_logical_port):
        lane_idx_str = lane_str + str(lane_idx)
        logical_lane_idx_str = lane_str + str(lane_idx - start_lane)
        if lane_dict.get(lane_idx_str) is not None:
            logical_media_dict[logical_lane_idx_str] = lane_dict[lane_idx_str]
        else:
            helper_logger.log_debug("Lane {} is not in lane_dict".format(lane_idx_str))
            continue
        helper_logger.log_debug("Lane {} is assigned with pre-emphasis value '{}'".format(lane_idx,logical_media_dict[logical_lane_idx_str]))
    media_val_str = get_media_val_str_from_dict(logical_media_dict)
    return media_val_str

platform_def_dict = None
hw_lane_adjust = False

def platform_def_load():
    (platform_path, hwsku_path) = device_info.get_paths_to_platform_and_hwsku_dirs()
    platform_json = os.path.join(hwsku_path, 'platform-def.json')
    if not os.path.isfile(platform_json):
        #
        # then search under $platform
        #
        platform_json = os.path.join(platform_path, 'platform-def.json')
        if not os.path.isfile(platform_json):
            return None

    pfile = open(platform_json, "r")
    data = pfile.read()
    platform_def_dict = json.loads(data)

    return platform_def_dict

def port_hw_lanes_count(port_speed, port_lanes):
    global platform_def_dict
    global hw_lane_adjust

    if platform_def_dict is None:
        platform_def_dict = platform_def_load()

        if platform_def_dict and 'port_pmap_phy_lanes' in platform_def_dict:
            if platform_def_dict['port_pmap_phy_lanes'] == 1:
                hw_lane_adjust = True

    lane_count = len(port_lanes.split(','))
    if hw_lane_adjust and int(port_speed) > 25000 and not (int(port_speed) == 40000 and lane_count == 4):
        lane_count = lane_count*2

    return lane_count


g_app_port_tbl = {}
def notify_media_setting(logical_port_name, transceiver_dict,
                         app_port_tbl, intf_type_update):
    ganged_port = False
    ganged_member_num = 1
    global g_app_port_tbl

    physical_port_list = logical_port_name_to_physical_port_list(logical_port_name)
    if physical_port_list is None:
        helper_logger.log_error("Error: No physical ports found for logical port '{}'".format(logical_port_name))
        return PHYSICAL_PORT_NOT_EXIST

    asic_id = platform_sfputil.get_asic_id_for_logical_port(logical_port_name)
    if asic_id is None:
        helper_logger.log_warning("notify_media_setting: {0}: Unable to get asic index, fallback to 0".format(logical_port_name))
        asic_id = 0

    port_tbl = g_app_port_tbl.get(asic_id)
    if port_tbl is None:
        appl_db = None
        for namespace in multi_asic.get_front_end_namespaces():
            if asic_id != multi_asic.get_asic_index_from_namespace(namespace):
                continue
            appl_db = daemon_base.db_connect("APPL_DB", namespace)
            break
        if appl_db is not None:
            port_tbl = swsscommon.Table(appl_db, swsscommon.APP_PORT_TABLE_NAME)
            if port_tbl is None:
                helper_logger.log_error("notify-media-setting: {0}: Unable to create APP_PORT_TABLE".format(logical_port_name))
                return
            g_app_port_tbl[asic_id] = port_tbl


    (status, fvs) = port_tbl.get(logical_port_name)
    if len(fvs) == 0:
        return XCVR_STATE_ERROR

    port_info = dict(fvs)
    port_lanes = port_info.get('lanes', '')
    port_speed = port_info.get('speed', '')
    media_fec_mode = port_info.get('media-fec-mode', '')
    port_lanes_count = port_hw_lanes_count(port_speed, port_lanes)

    if len(physical_port_list) > 1:
        ganged_port = True

    for physical_port in physical_port_list:
        time.sleep(0.001)
        if not _wrapper_get_presence(physical_port):
            helper_logger.log_info("port %s/%d presence not detected during notify"
                             % (logical_port_name, physical_port))
            update_xcvr_if_reason(logical_port_name, 'set', 'transceiver_not_present')
            continue
        update_xcvr_if_reason(logical_port_name, 'del', 'transceiver_not_present')
        #
        # transceiver_dict is empty when called from app_db_update_task
        #
        if transceiver_dict and physical_port not in transceiver_dict:
            helper_logger.log_error("Media %d eeprom not populated in "
                             "transceiver dict" % physical_port)
            update_xcvr_if_reason(logical_port_name, 'set', 'transceiver_bad_eeprom')
            continue
        update_xcvr_if_reason(logical_port_name, 'del', 'transceiver_bad_eeprom')

        xcvr_status = transceiver_validate_compatibility(physical_port, logical_port_name,
                                           transceiver_dict)

        # Update if-down-reason for transceiver_incompatible, and then continue with
        # the preemphasis configurations
        if not xcvr_status:
            update_xcvr_if_reason(logical_port_name, 'set', 'transceiver_incompatible')
        else:
            update_xcvr_if_reason(logical_port_name, 'del', 'transceiver_incompatible')

        logical_port_list = platform_sfputil.get_physical_to_logical(physical_port)
        num_logical_ports = len(logical_port_list)
        logical_idx = logical_port_list.index(logical_port_name)
        port_name = get_physical_port_name(logical_port_name,
                                           ganged_member_num, ganged_port)
        ganged_member_num += 1
        if intf_type_update == True:
            notify_interface_type(physical_port, port_name, transceiver_dict, app_port_tbl)

        if len(media_settings) != 0:

            if transceiver_dict:
                key = _wrapper_get_media_settings_key(physical_port, transceiver_dict)
            else:
                key = ["", ""]

            [matched_pattern, media_dict, keyword] = get_media_settings_value(physical_port, logical_port_name, key)

            #
            # Not need tunning
            # When port speed change, and there is no tuning values for speeds in json
            #
            if keyword == "Not Need":
                return XCVR_STATE_READY

            if(len(media_dict) == 0):
                msg = "'%s' in obtaining media setting for"  % (str(logical_port_name))
                for c in key:
                    msg += " [" + str(c) + "]"
                helper_logger.log_warning(msg)

        else:
            matched_pattern = ""
            media_dict = {}
            keyword = ''
            key = ["", ""]

        fvs_dict = {}
        for media_key in media_dict:
            media_key_valid = False

            if type(media_dict[media_key]) is collections.OrderedDict:
                media_val_str = get_media_val_str(media_dict[media_key],
                                                  logical_idx, port_lanes_count)
            else:
                media_val_str = media_dict[media_key]
            if media_key in ('preemphasis', 'idriver', 'ipredriver', 'main', 'pre1', 'pre2', 'pre3', 'post1', 'post2', 'post3') :
                media_len = len(media_val_str.split(','))

                # use port_lanes_count from DB instead of from sfputil
                if media_len > port_lanes_count :
                    media_val_str = ','.join(media_val_str.split(',')[:port_lanes_count])
                    media_len = len(media_val_str.split(','))
                if port_lanes_count != media_len:
                    helper_logger.log_warning("SFP %s(%d/%d) Patt:%s %s|%s does not match lanes:%s, ignore..." % \
                        (logical_port_name, num_logical_ports, logical_idx, matched_pattern, str(media_key), str(media_val_str), port_lanes))
                    # do not add media_key/media_val_str into fvs
                else:
                    fvs_dict[str(media_key)] = str(media_val_str)
                    media_key_valid = True
            else:
                fvs_dict[str(media_key)] = str(media_val_str)
                media_key_valid = True
            if media_key_valid is True:
                helper_logger.log_notice("SFP {0}({1}/{2}) Patt:{3} media setting({4}:{5}|{6})".format(logical_port_name,
                    num_logical_ports, logical_idx, matched_pattern, keyword, media_key, media_val_str))

        if media_fec_mode != '':
            fvs_dict['media-fec-mode'] = media_fec_mode

        # Media Auto-Config
        if transceiver_dict is not None:
            sfp_index = port_info.get('index', '-1')
            xcvr_info = transceiver_dict.get(int(sfp_index))
            autoconf = media_autoconf.get_config(port_info, xcvr_info, port_hw_lanes_count)
            if autoconf is not None and len(autoconf) > 0:
                helper_logger.log_notice("SFP {0}({1}/{2}) AC=({3})".format(logical_port_name,
                    num_logical_ports, logical_idx, ",".join(["{}={}".format(k, v) for k, v in autoconf.items()])))
                # DO NOT override the configs from media_settings.json
                for k, v in autoconf.items():
                    if k in fvs_dict:
                        continue
                    if k in ['intf_type', 'medium'] and ('intf_type' in fvs_dict or 'medium' in fvs_dict):
                        continue
                    fvs_dict[k] = v

        fvp = [(k, v) for k, v in fvs_dict.items()]
        if len(fvp) > 0:
            fvs = swsscommon.FieldValuePairs(fvp)
            app_port_tbl.set(port_name, fvs)

        return XCVR_STATE_READY

    # return error here
    return XCVR_STATE_ERROR

def notify_interface_type(physical_port, port_name, transceiver_dict, app_port_tbl):
    if _wrapper_get_transceiver_media_type_notify(physical_port) == True:
        # Updating connector type only for SFP/SFP+
        if transceiver_dict[physical_port]['type_abbrv_name'] == "SFP" and \
           transceiver_dict[physical_port]['nominal_bit_rate'] != '255':
            connector_type = ''
            connector_type = transceiver_dict[physical_port]['connector']
            intf_type = None
            if connector_type == 'CopperPigtail':
                intf_type = "CR"
            elif connector_type != 'Unknown':
                intf_type = "KR"
            if intf_type is not None:
                fvs = swsscommon.FieldValuePairs([("intf_type", intf_type)])
                helper_logger.log_info("Notifying interface type for SFP {}".format(port_name))
                app_port_tbl.set(port_name, fvs)
    return

def transceiver_validate_compatibility(physical_port, logical_port_name, transceiver_dict):
    supported = True
    port_speed = None
    app_db = daemon_base.db_connect("APPL_DB")
    port_tbl = swsscommon.Table(app_db, swsscommon.APP_PORT_TABLE_NAME)

    if transceiver_dict is None:
        helper_logger.log_debug("{} Optic compatibility check fail (eeprom not ready)".format(logical_port_name))
        return False

    (status, fvs) = port_tbl.get(logical_port_name)
    for val in fvs:
        if val[0] == "speed":
            port_speed = val[1]
            break
    if port_speed is None:
        helper_logger.log_debug("{} Optic compatibility check fail (invalid port speed)".format(logical_port_name))
        return False

    status1, supported = _wrapper_check_transceiver_compatible(physical_port,
                                                               transceiver_dict.get(physical_port),
                                                               port_speed)
    if status1 == None and supported == None:
        return True

    if supported == None:
        helper_logger.log_debug("{} Optic compatibility check fail".format(logical_port_name))
        return False
    elif supported == False:
        helper_logger.log_debug("{} Incompatible transceiver type detected. intf_speed {} status {}".format(logical_port_name, port_speed, status1))
        return False
    else:
        #helper_logger.log_notice("{} Transceiver compatible".format(logical_port_name))
        #helper_logger.log_notice("{} {}".format(status1, supported))
        return True

def waiting_time_compensation_with_sleep(time_start, time_to_wait):
    time_now = time.time()
    time_diff = time_now - time_start
    if time_diff < time_to_wait:
        time.sleep(time_to_wait - time_diff)

# Update port SFP status table on receiving SFP change event


def update_port_transceiver_status_table(logical_port_name, status_tbl, status):
    fvs = swsscommon.FieldValuePairs([('status', status)])
    status_tbl.set(logical_port_name, fvs)

# Delete port from SFP status table


def delete_port_from_status_table(logical_port_name, status_tbl):
    status_tbl._del(logical_port_name)

# Check whether port in error status


def detect_port_in_error_status(logical_port_name, status_tbl):
    rec, fvp = status_tbl.get(logical_port_name)
    if rec:
        status_dict = dict(fvp)
        if status_dict['status'] in errors_block_eeprom_reading:
            return True
        else:
            return False
    else:
        return False

# Init TRANSCEIVER_STATUS table


def init_port_sfp_status_tbl(stop_event=threading.Event()):
    # Connect to STATE_DB and create transceiver status table
    state_db, status_tbl = {}, {}

    # Get the namespaces in the platform
    namespaces = multi_asic.get_front_end_namespaces()
    for namespace in namespaces:
        asic_id = multi_asic.get_asic_index_from_namespace(namespace)
        state_db[asic_id] = daemon_base.db_connect("STATE_DB", namespace)
        status_tbl[asic_id] = swsscommon.Table(state_db[asic_id], TRANSCEIVER_STATUS_TABLE)

    # Init TRANSCEIVER_STATUS table
    logical_port_list = platform_sfputil.logical
    for logical_port_name in logical_port_list:
        if stop_event.is_set():
            break

        # Get the asic to which this port belongs
        asic_index = platform_sfputil.get_asic_id_for_logical_port(logical_port_name)
        if asic_index is None:
            helper_logger.log_debug("Got invalid asic index for {}, ignored".format(logical_port_name))
            #continue ----- #FIXME
            asic_index = 0

        physical_port_list = logical_port_name_to_physical_port_list(logical_port_name)
        if physical_port_list is None:
            helper_logger.log_error("No physical ports found for logical port '{}'".format(logical_port_name))
            update_port_transceiver_status_table(logical_port_name, status_tbl[asic_index], SFP_STATUS_REMOVED)

        for physical_port in physical_port_list:
            if stop_event.is_set():
                break

            if not _wrapper_get_presence(physical_port):
                update_port_transceiver_status_table(logical_port_name, status_tbl[asic_index], SFP_STATUS_REMOVED)
            else:
                update_port_transceiver_status_table(logical_port_name, status_tbl[asic_index], SFP_STATUS_INSERTED)

def physical_port_high_power_media_check(int_tbl, physical_port, logical_port_name, enable=None):
    high_wattage_optics_enable = True
    db_media_lockdown_state = False
    db_val = None
    ganged_port = False
    ganged_member_num = 1
    ret = {"error":None}
    # check if high power media enable support available
    if not hasattr(platform_chassis, 'port_power_threshold'):
        return None
    if not _wrapper_get_presence(physical_port):
        helper_logger.log_info("No media present in port {} physical port {}".format(logical_port_name, physical_port))
        return None
    xcvr_dict = g_xcvr.get(physical_port)
    if xcvr_dict is None or \
       'form_factor' not in xcvr_dict or xcvr_dict['form_factor'] is None or \
       'power_rating_max' not in xcvr_dict or xcvr_dict['power_rating_max'] is None:
        helper_logger.log_info("tranceiver info not present port {} physical port {}".format(logical_port_name, physical_port))
        return None
    port_name = get_physical_port_name(logical_port_name, ganged_member_num, ganged_port)
    sfp = platform_chassis.get_sfp(physical_port)
    (status, fvs) = int_tbl.get(port_name)
    hwoe_db_val = None
    db_val = None
    for val in fvs:
        if val[0] == "media-lockdown-state":
            db_val = val[1]
        if val[0] == "high-wattage-optics-enable":
            hwoe_db_val = val[1]
    if db_val is not None and db_val == "true":
        db_media_lockdown_state = True
    if hwoe_db_val is not None and hwoe_db_val == "false":
        high_wattage_optics_enable = False
    # if high wattage config not present in tranceiver table get it from appdb
    if hwoe_db_val is None:
        app_db = daemon_base.db_connect("APPL_DB")
        port_tbl = swsscommon.Table(app_db, swsscommon.APP_PORT_TABLE_NAME)
        (status, fvs) = port_tbl.get(port_name)
        db_val = None
        for val in fvs:
            if val[0] == "high-wattage-optics-enable":
                db_val = val[1]
                break
        if db_val is not None and db_val == "false":
            high_wattage_optics_enable = False

    if enable != None:
        if high_wattage_optics_enable == enable:
            helper_logger.log_info("high wattage optics enable same as previous value port {} physical port {} status {}".format(logical_port_name, physical_port, enable))
            if db_media_lockdown_state == True:
                ret['media_lock_down_state'] = True
            return ret
        high_wattage_optics_enable = enable
    db_enable_val = "true" if high_wattage_optics_enable else "false"
    fvs = swsscommon.FieldValuePairs([('high-wattage-optics-enable', db_enable_val)])
    int_tbl.set(port_name, fvs)

    if high_wattage_optics_enable:
        threshold = sfp.get_port_alarm_thresh_power()
    else:
        threshold = sfp.get_port_warn_thresh_power()
    fvs_thresh = swsscommon.FieldValuePairs([('max_port_power', str(threshold))])
    int_tbl.set(port_name, fvs_thresh)

    media_power = None
    lockdown_state = "true" if db_media_lockdown_state else "false"
    high_power_media = "false"
    if xcvr_dict['form_factor'] in ['QSFP+', 'QSFP56', 'QSFP-DD', 'QSFP28-DD', 'QSFP56-DD']:
        media_power = float(xcvr_dict['power_rating_max'])
        if media_power > platform_chassis.get_high_power_media_thresh():
           high_power_media = "true"
        if media_power > threshold:
            if not(db_media_lockdown_state):
                if ext_media_module is not None:
                    ext_media_module.media_lockdown_set(sfp, True)
                    lockdown_state = "true"
        else:
            if db_media_lockdown_state:
                if ext_media_module is not None:
                    ext_media_module.media_lockdown_set(sfp, False)
                    lockdown_state = "false"
    fvs = swsscommon.FieldValuePairs(
        [('media-lockdown-state', lockdown_state),
         ('is-high-power-media', high_power_media)])
    int_tbl.set(port_name, fvs)
    sfp = platform_chassis.get_sfp(physical_port)
    high_power_media_enable = False if lockdown_state == "true" else True 
    try:
        sfp.set_media_power_enable(high_power_media_enable)
    except (NotImplementedError, AttributeError):
        pass
    if high_power_media == "true":  
        if lockdown_state == "true":
            helper_logger.log_notice("Media in port {} serial number {} is high-wattage-optic and is disabled".format(logical_port_name, xcvr_dict['serial']))
        else:
            helper_logger.log_notice("Media in port {} serial number {} is high-wattage-optic".format(logical_port_name, xcvr_dict['serial']))
    logical_port_list = platform_sfputil.get_physical_to_logical(physical_port)
    # update other breakout ports db entry if port is in breakout mode
    for logical_port in  logical_port_list:
        port_name = get_physical_port_name(logical_port, ganged_member_num, ganged_port)
        int_tbl.set(port_name, fvs)
        int_tbl.set(port_name, fvs_thresh)
    ret['is_high_power_media'] = True if high_power_media == "true" else False
    ret['media_lock_down_state'] = True if lockdown_state == "true" else False
    return ret

#
# Helper classes ===============================================================
#
class app_db_update_task:
    def __init__(self):
        self.task_thread = None
        self.task_stopping_event = multiprocessing.Event()
        self.stop = threading.Event()


    def task_worker(self, stopping_event):
        helper_logger.log_notice("Start app db monitoring loop (pid {0})".format(os.getpid()))
        update_proc_name('xcvrd_appdb')

        # Connect to APP_DB and create transceiver dom info table
        appl_db = daemon_base.db_connect("APPL_DB")
        sel = swsscommon.Select()
        cst = swsscommon.SubscriberStateTable(appl_db, swsscommon.APP_PORT_TABLE_NAME)
        sel.addSelectable(cst)
        app_port_tbl = swsscommon.ProducerStateTable(appl_db, swsscommon.APP_PORT_TABLE_NAME)

        # Make sure this daemon started after all port configured
        while not stopping_event.is_set():
            (state, c) = sel.select(SELECT_TIMEOUT_MSECS)
            if state == swsscommon.Select.TIMEOUT:
                continue
            if state != swsscommon.Select.OBJECT:
                helper_logger.log_warning("sel.select() did not return swsscommon.Select.OBJECT")
                continue

            (key, op, fvs) = cst.pop()
            if key == 'PortInitDone':
                continue

            if '.' in key:
                # subinterface names in APP_DB PORT_TABLE has '.' in their names. We should
                # ignore them here
                continue

            if op == "DEL":
                # what's the case that one logical port could have multiple physical ports?
                # alway use the first index
                port_index = platform_sfputil.get_logical_to_physical(key)[0]
                port_lanes = platform_sfputil.get_logical_lanes(key)
                port_speed = platform_sfputil.get_logical_speed(key)
                platform_sfputil.del_logical_port(key)

                helper_logger.log_notice("DPB-0 {} port {} {}/{}/{}.".format('del', key, port_index, port_lanes, port_speed))
                msg = {'opt': 'del', 'index': port_index, 'port': key, 'speed': port_speed, 'lanes' : port_lanes}

                # Send msg to sfp_state_update process
                sfp_state_update.task_notify(msg)
                dom_info_update.task_notify(msg)
                xcvr_config_updater.dpb_msg_post(msg)
                time.sleep(0.1)

                continue

            if op == "SET":
                # add port
                if not platform_sfputil.is_logical_port(key):
                    port_speed = None
                    port_lanes = None
                    port_index = None
                    for fv in fvs:
                        if fv[0] == "speed":
                            port_speed = fv[1]
                        if fv[0] == "lanes":
                            port_lanes = fv[1]
                        if fv[0] == "index":
                            if ',' in fv[1]:
                                port_index = int(fv[1].split(',')[0])
                            else:
                                port_index = int(fv[1])

                    if port_speed != None and port_lanes != None and port_index != None:
                        platform_sfputil.add_logical_port(key, port_index, port_lanes, port_speed)

                        helper_logger.log_notice("DPB-0 {} port {} {}/{}/{}.".format('add', key, port_index, port_lanes, port_speed))

                        msg = {'opt': 'add', 'index': port_index, 'port': key, 'speed': port_speed, 'lanes': port_lanes}
                        sfp_state_update.task_notify(msg)
                        dom_info_update.task_notify(msg)
                        try:
                            xcvr_config_updater.dpb_msg_post(msg)
                        except Exception as ex:
                            helper_logger.log_info("Xcvr Config exception {}".format(ex))
                        time.sleep(0.1)
                        continue

                for fv in fvs:
                    if fv[0] == "speed":
                        port_speed = platform_sfputil.get_logical_speed(key)
                        if  port_speed != fv[1]:
                            helper_logger.log_info("port " + key + " speed change " + port_speed + " to " + fv[1])

                            platform_sfputil.set_logical_speed(key, fv[1])
                            notify_media_setting(key, {} if g_xcvr is None else g_xcvr, app_port_tbl, False)

        helper_logger.log_info("Stop APP_DB monitoring loop")

    def task_run(self):
        if self.task_stopping_event.is_set():
            return

        self.task_thread = multiprocessing.Process(target=self.task_worker, args=(self.task_stopping_event,))
        self.task_thread.start()

    def task_stop(self):
        self.task_stopping_event.set()
        os.kill(self.task_thread.pid, signal.SIGKILL)

# Thread wrapper class to update CMIS diagnostics periodically
class cmis_diag_update_task:

    diag_loopback_keys = [
        'lb_host_input_enabled',  'lb_media_input_enabled',
        'lb_host_output_enabled', 'lb_media_output_enabled'
    ]
    diag_pattern_keys = [
        'prbs_gen_host_enabled',  'prbs_chk_host_enabled',
        'prbs_gen_media_enabled', 'prbs_chk_media_enabled'
    ]
    diag_pattern_type_keys = [
        'prbs_gen_host_type',  'prbs_chk_host_type',
        'prbs_gen_media_type', 'prbs_chk_media_type'
    ]

    def __init__(self):
        self.task_process = None
        self.task_stopping_event = multiprocessing.Event()
        self.task_queue = mpmgr.Queue()
        self.diag_state = {}

    def loopback_ctrl(self, logical_port, physical_port, mode, enable):
        ret = False
        helper_logger.log_debug("CMIS diag: {0}: loopback_ctrl: {1},{2}".format(logical_port, mode, enable))
        sfp = platform_chassis.get_sfp(physical_port)
        caps = sfp.read_eeprom(0xa00, 1)
        if caps is None or len(caps) < 1:
            caps = [0]
        byte = 0xff if enable.lower() == 'true' else 0x00
        if   mode == 'lb_media_output_enabled' and (caps[0] & 0x01) > 0:
            ret = sfp.modify_eeprom_byte(0xa00 + (180 & 0x7f), byte)
        elif mode == 'lb_media_input_enabled'  and (caps[0] & 0x02) > 0:
            ret = sfp.modify_eeprom_byte(0xa00 + (181 & 0x7f), byte)
        elif mode == 'lb_host_output_enabled'  and (caps[0] & 0x04) > 0:
            ret = sfp.modify_eeprom_byte(0xa00 + (182 & 0x7f), byte)
        elif mode == 'lb_host_input_enabled'   and (caps[0] & 0x08) > 0:
            ret = sfp.modify_eeprom_byte(0xa00 + (183 & 0x7f), byte)

        if ret:
            fvs = swsscommon.FieldValuePairs([(mode, enable.lower())])
            self.diag_tbl.set(logical_port, fvs)

        return ret

    def pattern_ctrl(self, logical_port, physical_port, mode, enable):
        ret = False
        helper_logger.log_debug("CMIS diag: {0}: pattern_ctrl: {1},{2}".format(logical_port, mode, enable))
        sfp = platform_chassis.get_sfp(physical_port)
        byte = 0xff if enable.lower() == 'true' else 0x00
        if   mode == 'prbs_gen_host_enabled':
            ret = sfp.modify_eeprom_byte(0xa00 + (144 & 0x7f), byte)
        elif mode == 'prbs_gen_media_enabled':
            ret = sfp.modify_eeprom_byte(0xa00 + (152 & 0x7f), byte)
        elif mode == 'prbs_chk_host_enabled':
            ret = sfp.modify_eeprom_byte(0xa00 + (160 & 0x7f), byte)
        elif mode == 'prbs_chk_media_enabled':
            ret = sfp.modify_eeprom_byte(0xa00 + (168 & 0x7f), byte)

        if ret:
            fvs = swsscommon.FieldValuePairs([(mode, enable.lower())])
            self.diag_tbl.set(logical_port, fvs)

        return ret

    def pattern_select(self, logical_port, physical_port, mode, type):
        ret = False
        helper_logger.log_debug("CMIS diag: {0}: pattern_select: {1},{2}".format(logical_port, mode, type))
        sfp = platform_chassis.get_sfp(physical_port)
        buf = sfp.read_eeprom(0xa00, 16)
        if buf is None or len(buf) == 0:
            return ret
        code = int(type, 10) & 0xf
        byte = (code << 4) | code
        if   mode == 'prbs_gen_host_type':
            cap = (buf[5] << 8) | buf[4]
            if cap & (1 << code) > 0:
                ret = sfp.write_eeprom(0xa00 + (148 & 0x7f), 4, [byte, byte, byte, byte])
        elif mode == 'prbs_gen_media_type':
            cap = (buf[7] << 8) | buf[6]
            if cap & (1 << code) > 0:
                ret = sfp.write_eeprom(0xa00 + (156 & 0x7f), 4, [byte, byte, byte, byte])
        elif mode == 'prbs_chk_host_type':
            cap = (buf[9] << 8) | buf[8]
            if cap & (1 << code) > 0:
                ret = sfp.write_eeprom(0xa00 + (164 & 0x7f), 4, [byte, byte, byte, byte])
        elif mode == 'prbs_chk_media_type':
            cap = (buf[11] << 8) | buf[10]
            if cap & (1 << code) > 0:
                ret = sfp.write_eeprom(0xa00 + (172 & 0x7f), 4, [byte, byte, byte, byte])

        if ret:
            fvs = swsscommon.FieldValuePairs([(mode, type)])
            self.diag_tbl.set(logical_port, fvs)

        return ret

    def task_notify(self, logical_port, event=XCVR_STATE_CONFIG, data=None):
        if self.task_stopping_event.is_set():
            return
        helper_logger.log_debug("CMIS diag: {0}: reapplying the config".format(logical_port))
        self.task_queue.put([logical_port, event, data])
        time.sleep(0.001)

    def task_poll(self):
        while not self.task_queue.empty():
            if self.task_stopping_event.is_set():
                return
            try:
                msg = self.task_queue.get(block=False)
            except:
                msg = None
            if msg is None:
                break

            logical_port = msg[0]
            event = msg[1]
            data = msg[2]

            if event != XCVR_EVENT_CONFIG:
                continue

            physical_port_list = logical_port_name_to_physical_port_list(logical_port, False)
            if physical_port_list is None:
                continue

            attr_list = []
            for attr in self.diag_loopback_keys:
                attr_list.append(attr)
            for attr in self.diag_pattern_keys:
                attr_list.append(attr)
            for attr in attr_list:
                st_key = "{0}:{1}".format(logical_port, attr)
                self.diag_state[st_key] = 'false'

            # reload the configuration from CONFIG_DB
            try:
                (status, fvs) = self.conf_diag_tbl.get(logical_port)
                if fvs is None:
                    continue
                for v in fvs:
                    if v[0] not in attr_list:
                        continue
                    st_key = "{0}:{1}".format(logical_port, v[0])
                    self.diag_state[st_key] = v[1]
            except Exception as ex:
                helper_logger.log_notice("CMIS diag: {0}: Unable to get config: {1}".format(logical_port, ex))
                continue

            for key in self.diag_state.keys():
                if key is None:
                    continue
                tok = str(key).split(':')
                if len(tok) < 2:
                    continue
                intf = tok[0]
                attr = tok[1]
                data = self.diag_state.get(key)
                if (intf != logical_port) or (data is None):
                    continue

                # loopback control
                if attr in self.diag_loopback_keys:
                    for physical_port in physical_port_list:
                        self.loopback_ctrl(logical_port, physical_port, attr, data)
                # pattern select
                if attr in self.diag_pattern_type_keys:
                    for physical_port in physical_port_list:
                        self.pattern_select(logical_port, physical_port, attr, data)
                # loopback control
                if attr in self.diag_pattern_keys:
                    for physical_port in physical_port_list:
                        self.pattern_ctrl(logical_port, physical_port, attr, data)
        return

    def task_worker(self):
        helper_logger.log_notice("Start CMIS diagnostic control loop (pid {0})".format(os.getpid()))
        update_proc_name('xcvrd_cmisdiag')

        if platform_chassis is None:
            helper_logger.log_notice("Stopping CMIS diagnostic control loop due to missing PAI20 support")
            return

        self.state_db = daemon_base.db_connect("STATE_DB")
        self.diag_tbl = swsscommon.Table(self.state_db, TRANSCEIVER_DIAG_TABLE)

        self.conf_db = daemon_base.db_connect("CONFIG_DB")
        self.conf_diag_tbl = swsscommon.Table(self.conf_db, TRANSCEIVER_DIAG_TABLE)

        while not self.task_stopping_event.is_set():
            self.task_poll()

            try:
                port_list = self.conf_diag_tbl.getKeys()
            except:
                port_list = []

            for port in port_list:
                try:
                    (status, fvs) = self.conf_diag_tbl.get(port)
                except:
                    status = False
                if not status:
                    continue

                physical_port_list = logical_port_name_to_physical_port_list(port, False)
                if physical_port_list is None or len(physical_port_list) < 1:
                    continue

                physical_port = physical_port_list[0]
                if not _wrapper_get_presence(physical_port):
                    continue

                # loopback control
                for fv in fvs:
                    st_key = "{0}:{1}".format(port, fv[0])
                    if (fv[0] in self.diag_loopback_keys) and (self.diag_state.get(st_key) != fv[1]):
                        self.loopback_ctrl(port, physical_port, fv[0], fv[1])
                        self.diag_state[st_key] = fv[1]
                # pattern select
                for fv in fvs:
                    st_key = "{0}:{1}".format(port, fv[0])
                    if (fv[0] in self.diag_pattern_type_keys) and (self.diag_state.get(st_key) != fv[1]):
                        self.pattern_select(port, physical_port, fv[0], fv[1])
                        self.diag_state[st_key] = fv[1]
                # pattern control
                for fv in fvs:
                    st_key = "{0}:{1}".format(port, fv[0])
                    if (fv[0] in self.diag_pattern_keys) and (self.diag_state.get(st_key) != fv[1]):
                        self.pattern_ctrl(port, physical_port, fv[0], fv[1])
                        self.diag_state[st_key] = fv[1]

            time.sleep(TIME_FOR_SFP_POLL_SECS)

        helper_logger.log_notice("Stop CMIS diagnostic control loop")

    def task_run(self):
        if self.task_stopping_event.is_set():
            return

        sfp_num = 0
        for physical_port in range(_wrapper_port_start(), _wrapper_port_end() + 1):
            if _wrapper_is_qsfpdd_cage(physical_port):
                sfp_num += 1
        if sfp_num <= 0:
            return

        self.task_process = multiprocessing.Process(target=self.task_worker)
        self.task_process.start()

    def task_stop(self):
        self.task_stopping_event.set()
        if self.task_process is not None:
            self.task_process.join()

# Thread wrapper class to update CMIS diagnostics status periodically
class cmis_init_update_task:
    def __init__(self):
        self.appl_db = None
        self.appl_port_tbl = None
        self.port_locks = {}
        self.task_workers = []
        self.task_stopping_event = multiprocessing.Event()
        self.task_queue = mpmgr.Queue()
        self.state_db = None
        self.state_xcvr_tbl = None

    def get_application_mode(self, logical_port, xcvr_dict):
        code = 1
        speed = 0
        host_intf = []

        app_adv = None if (xcvr_dict is None) else xcvr_dict.get('application_advertisement')
        if app_adv is None:
            return (code, 0)

        lanes_str = "0"
        speed_str = "0"
        try:
            (status, fvs) = self.appl_port_tbl.get(logical_port)
            if fvs is None:
                return (code, 0)
            for v in fvs:
                if v[0] == 'lanes':
                    lanes_str = v[1]
                elif v[0] == 'speed':
                    speed_str = v[1]
                    speed = int(speed_str)
        except Exception as ex:
            helper_logger.log_notice("CMIS init (pid {0}): {1}: Unable to get app code: {2}".format(os.getpid(), logical_port, ex))
            pass

        lanes_per_port = port_hw_lanes_count(speed_str, lanes_str)
        if lanes_per_port < 1:
            lanes_per_port = 1
        speed = speed / lanes_per_port

        if lanes_per_port == 0 or speed == 0:
            return (code, lanes_per_port)
        elif lanes_per_port == 8 and speed == 50000:
            host_intf = ['400GAUI-8 C2M (Annex 120E)', '400G CR8']
        elif lanes_per_port == 8 and speed == 25000:
            host_intf = ['200GAUI-8 C2M (Annex 120C)']
        elif lanes_per_port == 4 and speed == 50000:
            host_intf = ['200GAUI-4 C2M (Annex 120E)', '200GBASE-CR4 (Clause 136)']
        elif lanes_per_port == 4 and speed == 25000:
            host_intf = ['100GAUI-4 C2M (Annex 135E)', '100GBASE-CR4 (Clause 92)']
        elif lanes_per_port == 2 and speed == 50000:
            host_intf = ['100GAUI-2 C2M (Annex 135G)', '100GBASE-CR2 (Clause 136)']
        elif lanes_per_port == 1 and speed == 50000:
            host_intf = ['50GAUI-1 C2M (Annex 135G)', '50GBASE-CR (Clause 126)']
        elif lanes_per_port == 1 and speed == 25000:
            host_intf = ['25GAUI C2M (Annex 109B)', '25GBASE-CR CA-L (Clause 110)', '25GBASE-CR CA-S (Clause 110)', '25GBASE-CR CA-N (Clause 110)']

        helper_logger.log_notice("CMIS init (pid {0}): {1}, intf={2}".format(os.getpid(), logical_port, host_intf))

        if host_intf is None:
            return (code, lanes_per_port)

        adv = eval(app_adv)
        for key in adv:
            if adv[key]['host_if'] in host_intf:
                code = key
                break
        helper_logger.log_notice("CMIS init (pid {0}): {1}, appl={2}".format(os.getpid(), logical_port, code))
        return (code, lanes_per_port)

    def task_notify(self, logical_port, physical_port_list, event, data):
        if self.task_stopping_event.is_set():
            return
        self.task_queue.put([logical_port, physical_port_list, event, data])
        time.sleep(0.001)

    def task_worker(self):
        helper_logger.log_notice("Start CMIS init task (pid {0})".format(os.getpid()))
        update_proc_name('xcvrd_cmisinit')

        self.appl_db = daemon_base.db_connect("APPL_DB")
        self.appl_port_tbl = swsscommon.Table(self.appl_db,
                                              swsscommon.APP_PORT_TABLE_NAME)
        self.state_db = daemon_base.db_connect("STATE_DB")
        self.state_xcvr_tbl = swsscommon.Table(self.state_db, swsscommon.STATE_PORT_XCVR_STATUS_TABLE_NAME)
        while not self.task_stopping_event.is_set():
            m = None
            try:
                m = self.task_queue.get(block=True)
            except:
                m = None
            if m is None:
                time.sleep(0.5)
                continue

            logical_port = m[0]
            physical_port_list = m[1]
            event = m[2]
            xcvr_dict = m[3]

            if event != XCVR_EVENT_CONFIG:
                continue

            physical_port = physical_port_list[0]

            try:
                sfp = platform_chassis.get_sfp(physical_port)
                if sfp.get_media_power_enable() == False:
                    continue
            except (NotImplementedError, AttributeError):
                pass
            except Exception as ex:
                helper_logger.log_notice("CMIS init (pid {0}): {1}".format(os.getpid(), ex))
                continue

            try:
                if xcvr_dict is None:
                    xcvr_dict = sfp.get_transceiver_info()
            except Exception as ex:
                helper_logger.log_notice("CMIS init (pid {0}): {1}".format(os.getpid(), ex))
                continue

            # xcvr_dict could be None without exception
            if xcvr_dict is None:
                continue

            helper_logger.log_notice("CMIS init (pid {0}): {1}: {2},{3}".format(os.getpid(), \
                              logical_port, xcvr_dict.get('type_abbrv_name'), \
                              xcvr_dict.get('media_type')))

            if xcvr_dict.get('revision_compliance') not in ['3.0', '4.0', '5.0']:
                continue
            if xcvr_dict.get('media_type') == 'passive_copper_media_interface':
                continue

            self.port_locks[physical_port].acquire()

            fvs = swsscommon.FieldValuePairs([('xcvr_init_status', 'inprogress')])
            self.state_xcvr_tbl.set(logical_port, fvs)
            try:
                (app, lpp) = self.get_application_mode(logical_port, xcvr_dict)
                ret = ext_media_module.default_cmis_3_4_init(sfp, app, lpp)
                helper_logger.log_notice("CMIS init (pid {0}): {1}: {2}".format(os.getpid(), logical_port, ("succeed" if ret else "fail")))
            except Exception as ex:
                helper_logger.log_error("CMIS init (pid {0}): {1}: {2}".format(os.getpid(), logical_port, ex))

            fvs = swsscommon.FieldValuePairs([('xcvr_init_status', 'completed')])
            self.state_xcvr_tbl.set(logical_port, fvs)

            self.port_locks[physical_port].release()

            # Ensure the DIAG control will be re-applied after CMIS init sequence
            cmis_diag_worker.task_notify(logical_port, event, xcvr_dict)

        helper_logger.log_notice("Stop CMIS init task (pid {0})".format(os.getpid()))

    def task_run(self):
        if platform_chassis is None:
            helper_logger.log_notice("Stopping CMIS init task due to missing PAI20 support")
            return

        sfp_num = 0
        for physical_port in range(_wrapper_port_start(), _wrapper_port_end() + 1):
            if _wrapper_is_qsfpdd_cage(physical_port):
                sfp_num += 1
        if sfp_num <= 0:
            return

        for n in range(_wrapper_port_start(), _wrapper_port_end() + 1):
            self.port_locks[n] = multiprocessing.Lock()

        for n in range(8):
            p = multiprocessing.Process(target=self.task_worker)
            self.task_workers.append(p)
            p.start()

    def task_stop(self):
        self.task_stopping_event.set()
        for p in self.task_workers:
            p.join()

class XcvrConfigTask(object):
    """ Thread wrapper class to monitor and perform xcvr configuration change """
    def __init__(self):
        self.lock = multiprocessing.Lock()
        self.media_fec_config = {}
        self.port_brk_mode = {}
        self.port_index_lock = {}
        self.port_status = {}
        self.media_fec_status = {}
        self.media_type = {}
        self.media_rate = {}
        self.task_process = None
        self.StateDbHdl = None
        self.ApplDbHdl = None
        self.task_stopping_event = multiprocessing.Event()
        self.mqueue = mpmgr.Queue()
        # TODO Revisit this code for multi asic
        self.state_db = daemon_base.db_connect("STATE_DB")
        self.state_sel = swsscommon.Select()
        self.state_xcvr_tbl = swsscommon.Table(self.state_db, swsscommon.STATE_PORT_XCVR_STATUS_TABLE_NAME)
        self.port_tbl = swsscommon.Table(self.state_db, swsscommon.STATE_PORT_TABLE_NAME)
        self.appl_db = daemon_base.db_connect("APPL_DB")
        self.appl_port_pst = swsscommon.ProducerStateTable(self.appl_db, swsscommon.APP_PORT_TABLE_NAME)
        self.int_tbl = swsscommon.Table(self.state_db, TRANSCEIVER_INFO_TABLE)
        self.tasks = []

    def prepare_for_config(self, logical_port):
        """
        Prepare the media for media-fec configurtion
        logical_port : to be initialized for media-fec configuration
        """
        physical_port_list = logical_port_name_to_physical_port_list(logical_port, False)
        if physical_port_list is None:
            return

        if platform_chassis is None:
            return

        for physical_port in physical_port_list:
            try:
                logical_port_list = platform_sfputil.get_physical_to_logical(physical_port)
                if logical_port != logical_port_list[0]:
                    return

                if physical_port not in self.port_index_lock:
                    self.port_index_lock[physical_port] = multiprocessing.Lock()

                sfp = platform_chassis.get_sfp(physical_port)
                if ext_media_module is not None:
                    with self.port_index_lock[physical_port]:
                        if ext_media_module.prepare_to_set_fec_mode(sfp):
                            fvs = swsscommon.FieldValuePairs([('xcvr_port_status', 'down'),('xcvr_init_status', 'inprogress')])
                            self.state_xcvr_tbl.set(logical_port, fvs)
            except NotImplementedError:
                pass

    def configure_media_fec(self, logical_port, mode, on_insertion, breakout_mode):
        """
        Configure the logical port to request media-fec mode
        logical_port : to be configurd for media-fec mode
        mode : media-fec mode to which the media to be configured
        on_insertion :  the request is due ot OIR or due to user initiated config change
        breakout_mode: Current breakout mode of the port
        """
        # If physical ports are not assigned to a logical port in the DB we can not configure fec
        physical_port_list = logical_port_name_to_physical_port_list(logical_port, False)
        if physical_port_list is None:
            helper_logger.log_notice("{0}: physical_port_list is None".format(logical_port))
            return

        for physical_port in physical_port_list:
            ret = physical_port_high_power_media_check(self.int_tbl, physical_port, logical_port)
            if ret is not None and 'media_lock_down_state' in ret and ret['media_lock_down_state'] == True:
                continue

            if physical_port not in self.port_index_lock:
                self.port_index_lock[physical_port] = multiprocessing.Lock()

            sfp = platform_chassis.get_sfp(physical_port)
            if ext_media_module is not None:
                with self.port_index_lock[physical_port]:
                    ct_mode = ext_media_module.set_media_fec_mode(sfp, mode, on_insertion, breakout_mode)

                # Update APPL DB to be refered by show int status
                if ct_mode is not None:
                    logical_port_list = platform_sfputil.get_physical_to_logical(physical_port)
                    fvs = swsscommon.FieldValuePairs([('media-fec-mode', ct_mode)])
                    for port in logical_port_list:
                        (status, pt) = self.port_tbl.get(port)
                        if status == True:
                            self.port_tbl.set(port, fvs)
                else:
                    logical_port_list = platform_sfputil.get_physical_to_logical(physical_port)
                    for port in logical_port_list:
                        self.port_tbl.hdel(port, 'media-fec-mode')

    def dpb_msg_post(self, msg):
        """ Post dynamic breakout message to xcvr_config task """
        if self.task_stopping_event.is_set():
            return
        self.mqueue.put(['dpb_info', msg])
        time.sleep(0.001)

    def notify_port_status(self, logical_port, transceiver_info, flag):
        if self.task_stopping_event.is_set():
            return
        self.mqueue.put(['xcvr_info', [logical_port, transceiver_info, flag]])
        time.sleep(0.001)

    def process_dpb_msg(self, msg):
        """ Process incoming DPB messages """
        opt = msg['opt']
        index = msg['index']
        lanes = msg['lanes']
        port = msg['port']
        speed = int(msg['speed'])
        if opt == 'del':
            platform_sfputil.del_logical_port(port)
        if opt == 'add':
            platform_sfputil.add_logical_port(port, index, lanes, speed)
            first_port = self.first_logical_port_in_bo(port)
            if first_port in self.media_type:
                physical_port = index
                sfp = platform_chassis.get_sfp(physical_port)
                if ext_media_module is not None:
                    if self.media_type[first_port] == 'SR4.2':
                        ct_mode = ext_media_module.get_media_fec_mode(sfp)
                        if ct_mode is not None:
                            fvs = swsscommon.FieldValuePairs([('media-fec-mode', ct_mode)])
                            helper_logger.log_notice("{0} : media fec status is updated to {1}".\
                                format(port, ct_mode))
                            self.port_tbl.set(port, fvs)
                        else:
                            self.port_tbl.hdel(port, 'media-fec-mode')

    def dual_rate_media_init(self, msg):
        logical_port = msg[0]
        xcvr_info = msg[1]
        flag = msg[2]
        media_type = ''

        if flag != XCVR_STATE_READY:
            return

        if (xcvr_info is not None and 'display_name' in xcvr_info):
            if 'SR4.2' in xcvr_info.get('display_name'):
                media_type = 'SR4.2'
            elif 'DUALRATE' in xcvr_info.get('display_name'):
                media_type = 'DUALRATE'
                speed = int(platform_sfputil.get_logical_speed(logical_port))
                self.media_rate[logical_port] = 0
                self.process_speed_change(logical_port, speed)

        if media_type == '':
            if logical_port in self.media_type:
                del self.media_type[logical_port]
        else:
            self.media_type[logical_port] = media_type

    def process_xcvr_msg(self, msg):
        self.dual_rate_media_init(msg)
        self.process_config_init(msg)

    def msg_poll(self):
        """ Poll incoming message (dpb message, xcvr info message) """
        while not self.mqueue.empty():
            if self.task_stopping_event.is_set():
                return
            msg = self.mqueue.get(block=False)
            if msg[0] == 'dpb_info':
                self.process_dpb_msg(msg[1])
            elif msg[0] == 'xcvr_info':
                self.process_xcvr_msg(msg[1])

    @staticmethod
    def first_logical_port_in_bo(logical_port):
        """ Whether the logical port in the first port on breakout group """
        first_logical_port = None

        if logical_port.startswith('Eth'):
            physical_port_list = logical_port_name_to_physical_port_list(logical_port, False)
            if physical_port_list is not None:
                for physical_port in physical_port_list:
                    logical_port_list = platform_sfputil.get_physical_to_logical(physical_port)
                    first_logical_port = logical_port_list[0]
                    break
        return first_logical_port

    def process_speed_change(self, logical_port, speed):
        """ Process Speed change """
        if logical_port not in self.media_rate or speed != self.media_rate[logical_port]:
            self.media_rate[logical_port] = speed
            physical_port_list = logical_port_name_to_physical_port_list(logical_port, False)
            if physical_port_list is None:
                helper_logger.log_notice("{0}: physical_port_list is None".format(logical_port))
                return
            for physical_port in physical_port_list:
                sfp = platform_chassis.get_sfp(physical_port)
                if ext_media_module is not None:
                    #Updating transceiver info for DUALRATE media on speed/rate change 
                    specification_compliance,form_factor = ext_media_module.select_rate(sfp, speed)
                if specification_compliance is not None and form_factor is not None:
                    try:
                        port_info_dict = g_xcvr.get(physical_port)
                        transceiver_dict = {}
                        if port_info_dict is not None:
                            transceiver_dict[physical_port] = port_info_dict
                            d = transceiver_dict[physical_port]
                            d['specification_compliance'] = specification_compliance
                            d['form_factor'] = form_factor
                            helper_logger.log_debug("Specification_compliance and form_factor updated for port {} speed {}".format(logical_port,speed))
                        notify_media_setting(logical_port, transceiver_dict, self.appl_port_pst, True)
                    except:
                        helper_logger.log_notice("Processing speed {} update for port {} failed".format(speed,logical_port))

    def process_media_fec_change(self, logical_port, port_status, media_fec_mode, xcvr_init_status=False):
        """ Process media FEC change """
        media_inserted = False

        if port_status == 'down':
            self.media_fec_config[logical_port] = ''
            self.port_brk_mode[logical_port] = ''
            self.port_status[logical_port] = port_status
            return

        if xcvr_init_status == False:
            return

        breakout_mode = None
        if logical_port.startswith('Eth'):
            physical_port_list = logical_port_name_to_physical_port_list(logical_port, False)
            if physical_port_list is not None:
                for physical_port in physical_port_list:
                    logical_port_list = platform_sfputil.get_physical_to_logical(physical_port)
                    port_speed = platform_sfputil.get_logical_speed(logical_port)
                    port_lane_speed = int(int(port_speed)/1000)
                    numports_in_bo = len(logical_port_list)
                    if port_lane_speed and numports_in_bo:
                        breakout_mode = "{}x{}".format(numports_in_bo, port_lane_speed);
                        helper_logger.log_debug("configure media fec Logical {} to {}: {}"\
                                .format(logical_port, port_lane_speed, breakout_mode))
                        break
                    else:
                        helper_logger.log_notice("configure media fec Logical {} to {}".format(logical_port, 0))


        if logical_port not in self.media_fec_config or logical_port not in self.port_status or \
            logical_port not in self.port_brk_mode:
            return
        if media_fec_mode == self.media_fec_config[logical_port] and \
            breakout_mode == self.port_brk_mode[logical_port]:
            return

        if self.port_status[logical_port] == 'down':
            media_inserted = True
            self.port_status[logical_port] = 'up'

        self.media_fec_config[logical_port] = media_fec_mode
        self.port_brk_mode[logical_port] = breakout_mode
        task = multiprocessing.Process(target=self.configure_media_fec, \
                     args=(logical_port, media_fec_mode, media_inserted, breakout_mode, ))
        task.start()
        self.tasks.append(task)

    def process_high_wattage_optics_enable(self, logical_port_name, enable_status, int_tbl):
        """ Process high wattage optics enable status """
        if not hasattr(platform_chassis, 'port_power_threshold'):
            return None
        enable = False
        ganged_port = False
        ganged_member_num = 1
        if enable_status == "true":
            enable = True
        remove_reinsert = False
        physical_port_list = logical_port_name_to_physical_port_list(logical_port_name, False)
        if physical_port_list is None or len(physical_port_list) < 1:
            return
        for physical_port in physical_port_list:
            port_name = get_physical_port_name(logical_port_name, ganged_member_num, ganged_port)
            ganged_member_num += 1
            physical_port = physical_port_list[0]
            if not _wrapper_get_presence(physical_port):
                continue
            sfp = platform_chassis.get_sfp(physical_port)
            (status, fvs) = int_tbl.get(port_name)
            prev_lock_state = None
            for val in fvs:
                if val[0] == "media-lockdown-state":
                    prev_lock_state = val[1] 
            ret = physical_port_high_power_media_check(int_tbl, physical_port, logical_port_name, enable)
            if ret is None:
                continue
            (status, fvs) = int_tbl.get(port_name)
            cur_lock_state = None
            for val in fvs:
                if val[0] == "media-lockdown-state":
                    cur_lock_state = val[1]
            if prev_lock_state is not None and cur_lock_state is not None:
                # media is getting enabled from disabled state
                if prev_lock_state == "true" and cur_lock_state == "false":
                    remove_reinsert = True
        if remove_reinsert == True:
            state_db = daemon_base.db_connect("STATE_DB")
            dom_tbl = swsscommon.Table(state_db, TRANSCEIVER_DOM_SENSOR_TABLE)
            state_port_xcvr_tbl = swsscommon.Table(state_db, STATE_PORT_XCVR_TABLE)
            int_tbl = swsscommon.Table(state_db, TRANSCEIVER_INFO_TABLE)
            
            appl_db = daemon_base.db_connect("APPL_DB")
            app_port_tbl = swsscommon.ProducerStateTable(appl_db, swsscommon.APP_PORT_TABLE_NAME)
            app_status_port_tbl = swsscommon.ProducerStateTable(appl_db, swsscommon.APP_PORT_APP_STATUS_TABLE_NAME)

            do_sfp_removal(logical_port_name, app_port_tbl, app_status_port_tbl, state_port_xcvr_tbl, int_tbl, dom_tbl)
            do_sfp_insertion(logical_port_name, int_tbl, dom_tbl, app_port_tbl, app_status_port_tbl, state_port_xcvr_tbl)

    def join_media_fec_process(self):
        if len(self.tasks) > 0:
            self.tasks[0].join(0.01)
            if not self.tasks[0].is_alive():
                del self.tasks[0]
                pass

    def process_appldb_change(self, logical_port, field, value):
        physical_port_list = logical_port_name_to_physical_port_list(logical_port, False)
        if physical_port_list is None:
            helper_logger.log_notice("{0}: physical_port_list is None".format(logical_port))
            return
        for physical_port in physical_port_list:
            try:
                media = platform_chassis.get_sfp(physical_port)
                if not media.appldb_update_notify(field, value, logical_port):
                    helper_logger.log_error("Xcvr Config task %s change failed %s=%s" \
                                                % (logical_port, field, value))
            except:
                helper_logger.log_error("Xcvr Config task %s change exception" \
                                        % (logical_port))

    def process_config_init(self, msg):
        logical_port = msg[0]
        flag = msg[2]

        physical_port_list = logical_port_name_to_physical_port_list(logical_port, False)
        if physical_port_list is None:
            helper_logger.log_notice("{0}: physical_port_list is None".format(logical_port))
            return
        for physical_port in physical_port_list:
            try:
                # Initialize the media to the last updated configs
                media = platform_chassis.get_sfp(physical_port)
                default = True if flag != XCVR_STATE_READY else False
                media.media_phy_init(default, logical_port)
                if flag == XCVR_STATE_EMPTY:
                    media.media_phy_remove(logical_port)
            except:
                helper_logger.log_error("Xcvr Config task %s change init exception" \
                                        % (logical_port))


    def app_porttbl_handler(self, key, data):
        op ="DEL"
        keys = self.ApplDbHdl.get_keys(swsscommon.APP_PORT_TABLE_NAME)
        if key in keys:
            op = "SET"

        if key not in ['PortInitDone', 'PortConfigDone'] and \
                key == self.first_logical_port_in_bo(key) and \
                op == "SET":
                    for attr in data:
                        if attr == "":
                            continue
                        if attr == 'high-wattage-optics-enable':
                            self.process_high_wattage_optics_enable(key, data[attr], self.int_tbl)
                        if attr == "media-fec-mode" and key in self.media_fec_config:
                            try:
                                xcvr_status_entry = self.StateDbHdl.get_entry(swsscommon.STATE_PORT_XCVR_STATUS_TABLE_NAME, key)
                            except:
                                xcvr_status_entry = {}
                            if xcvr_status_entry is None:
                                xcvr_status_entry = {}
                            xcvr_init_status = False
                            if ('xcvr_init_status' in xcvr_status_entry):
                                xcvr_init_status = False if xcvr_status_entry['xcvr_init_status'] == 'inprogress' else True
                                self.process_media_fec_change(key, self.port_status[key], data[attr], xcvr_init_status)
                                continue
                        self.process_appldb_change(key, attr, data[attr])

    def state_xcvr_statustbl_handler(self, key, data):
        op ="DEL"
        keys = self.StateDbHdl.get_keys(swsscommon.STATE_PORT_XCVR_STATUS_TABLE_NAME)
        if key in keys:
            op = "SET"
        if key not in ['PortInitDone', 'PortConfigDone'] and \
                key == self.first_logical_port_in_bo(key) and \
                op == "SET":
                    media_fec_mode = 'ieee'
                    port_status = None
                    speed = None
                    xcvr_init_status = False
                    if ('xcvr_port_status' in data):
                        port_status = data['xcvr_port_status']
                    if ('xcvr_speed' in data):
                        speed = int(data['xcvr_speed'])
                    if ('xcvr_init_status' in data):
                        xcvr_init_status = False if data['xcvr_init_status'] == 'inprogress' else True

                    if port_status is not None:
                        port = self.ApplDbHdl.get_entry(swsscommon.APP_PORT_TABLE_NAME, key)
                        if "media-fec-mode" in port:
                            media_fec_mode = port["media-fec-mode"]
                        self.process_media_fec_change(key, port_status, media_fec_mode, xcvr_init_status)

                    if speed is not None and key in self.media_type and self.media_type[key] == 'DUALRATE':
                        self.process_speed_change(key, speed)

    def XcvrConfigApplDbListnerTask(self):
        self.ApplDbHdl = ConfigDBConnector()
        self.ApplDbHdl.db_connect('APPL_DB', wait_for_init=False, retry_on=True)
        self.ApplDbHdl.subscribe(swsscommon.APP_PORT_TABLE_NAME, lambda table, key, data: self.app_porttbl_handler(key, data))
        self.ApplDbHdl.listen_subscribed()

    def XcvrConfigStateDbListnerTask(self):
        self.StateDbHdl = ConfigDBConnector()
        self.StateDbHdl.db_connect("STATE_DB", wait_for_init=False, retry_on=True)
        self.StateDbHdl.subscribe(swsscommon.STATE_PORT_XCVR_STATUS_TABLE_NAME, lambda table, key, data: self.state_xcvr_statustbl_handler(key, data))
        self.StateDbHdl.listen_subscribed()

    def task_worker(self):
        """ The main worker function of xcvrd_config task """

        helper_logger.log_notice("Start Xcvr Config task (pid {0})".format(os.getpid()))
        update_proc_name('xcvrd_config')
        self.applDBListner = threading.Thread(target=self.XcvrConfigApplDbListnerTask)
        self.applDBListner.start()
        self.stateDBListner = threading.Thread(target=self.XcvrConfigStateDbListnerTask)
        self.stateDBListner.start()

        while not self.task_stopping_event.is_set():
            self.join_media_fec_process()
            self.msg_poll()
            time.sleep(0.1)

    def task_run(self):
        """ Run the task from main thread """
        if self.task_stopping_event.is_set():
            return

        if platform_chassis is None:
            helper_logger.log_notice("Platform_chassis is None. Skipping XcvrdConfigTask..")
            return

        # Check if the SFP plugin is truly implemented
        try:
            platform_chassis.get_all_sfps()[0].get_presence()
        except:
            helper_logger.log_notice("Platform_chassis.get_sfp(0) is failing. Skipping XcvrdConfigTask..")
            return

        self.task_process = multiprocessing.Process(target=self.task_worker)
        self.task_process.start()

    def task_stop(self):
        """ Stop the xcvr_config thread """
        self.task_stopping_event.set()
        try:
            self.task_process.join()
        except:
            pass

# Thread wrapper class to update dom info periodically


class DomInfoUpdateTask(object):
    def __init__(self):
        self.task_queue = mpmgr.Queue()
        self.task_process = None
        self.task_stopping_event = multiprocessing.Event()

    def task_worker(self):
        helper_logger.log_notice("Start DOM/DIAG monitoring loop (pid {0})".format(os.getpid()))
        update_proc_name('xcvrd_dominfo')

        # Connect to STATE_DB and create transceiver dom info table
        state_db, dom_tbl, status_tbl, diag_tbl = {}, {}, {}, {}

        # Get the namespaces in the platform
        namespaces = multi_asic.get_front_end_namespaces()
        for namespace in namespaces:
            asic_id = multi_asic.get_asic_index_from_namespace(namespace)
            state_db[asic_id] = daemon_base.db_connect("STATE_DB", namespace)
            diag_tbl[asic_id] = swsscommon.Table(state_db[asic_id], TRANSCEIVER_DIAG_TABLE)
            dom_tbl[asic_id] = swsscommon.Table(state_db[asic_id], TRANSCEIVER_DOM_SENSOR_TABLE)
            status_tbl[asic_id] = swsscommon.Table(state_db[asic_id], TRANSCEIVER_STATUS_TABLE)

        # Start loop to update dom info in DB periodically
        while not self.task_stopping_event.is_set():
            exit_loop = False
            while not self.task_queue.empty() and not exit_loop:
                try:
                    msg = self.task_queue.get(block=True, timeout=1)
                except:
                    msg = None
                if msg is None:
                    break
                opt   = msg.get('opt')
                index = msg.get('index')
                lanes = msg.get('lanes')
                port  = msg.get('port')
                speed = msg.get('speed')
                helper_logger.log_notice("DPB-DOM {} port {} {}/{}/{}.".format(opt, port, index, lanes, speed))
                if opt == 'del':
                    platform_sfputil.del_logical_port(port)
                elif opt == 'add':
                    platform_sfputil.add_logical_port(port, index, lanes, speed)

            dom_cache = {}
            thre_cache = {}
            diag_cache = {}
            logical_port_list = platform_sfputil.logical
            if len(logical_port_list) > 1:
                poll_delay = DOM_INFO_UPDATE_PERIOD_SECS / len(logical_port_list)
            else:
                poll_delay = DOM_INFO_UPDATE_PERIOD_SECS
            for logical_port_name in logical_port_list:
                # Get the asic to which this port belongs
                asic_index = platform_sfputil.get_asic_id_for_logical_port(logical_port_name)
                if asic_index is None:
                    helper_logger.log_debug("Got invalid asic index for {}, ignored".format(logical_port_name))
                    #continue ----- #FIXME
                    asic_index = 0

                if not detect_port_in_error_status(logical_port_name, status_tbl[asic_index]):
                    post_port_dom_info_to_db(logical_port_name, dom_tbl[asic_index], self.task_stopping_event, dom_cache)
                    post_port_diag_info_to_db(logical_port_name, diag_tbl[asic_index], self.task_stopping_event, diag_cache)

                time.sleep(poll_delay)
                if self.task_stopping_event.is_set():
                    exit_loop = True
                    break

        helper_logger.log_info("Stop DOM/DIAG monitoring loop")

    def task_run(self):
        if self.task_stopping_event.is_set():
            return
        self.task_process = multiprocessing.Process(target=self.task_worker)
        self.task_process.start()

    def task_notify(self, msg):
        if self.task_stopping_event.is_set():
            return
        self.task_queue.put(msg)
        time.sleep(0.001)

    def task_stop(self):
        self.task_stopping_event.set()
        self.task_process.join()

SFP_STATE_EMPTY  = 0
SFP_STATE_INSERT = 1
SFP_STATE_READY  = 2

# Process wrapper class to update sfp state info periodically
class SfpStateUpdateTask(object):
    def __init__(self, mod_tbl):
        self.task_queue = mpmgr.Queue()
        self.task_process = None
        self.stop_event = threading.Event()
        self.task_stopping_event = multiprocessing.Event()

        # Initialize SFP module presence table
        self.mod_tbl = mod_tbl

        # NOTE: Moved below code to DaemonXCVRD init() func.
        #for key in range(_wrapper_port_start(), _wrapper_port_end() + 1):
            #self.mod_tbl[key] = SFP_STATE_EMPTY

        #warmstart = swsscommon.WarmStart()
        #warmstart.initialize("xcvrd", "pmon")
        #warmstart.checkWarmStart("xcvrd", "pmon", False)
        #is_warm_start = warmstart.isWarmStart()

        #transceiver_dict = {}
        #if START_SFP_READ_BEFORE_PORT_INIT == True:
            #port_sfp_info_collect(transceiver_dict)

        ## Make sure this daemon started after all port configured
        #helper_logger.log_info("Wait for port config is done")
        #self.wait_for_port_config_done()

        ## Post all the current interface dom/sfp info to STATE_DB
        #post_port_sfp_dom_info_to_db(is_warm_start, self.mod_tbl, transceiver_dict, self.stop_event)

    def _port_in_breakout(self, port_brk_tbl, brk_tbl, port):
        (status, fvs) = port_brk_tbl.get(port)
        if status != True:
            return False

        master_port = None
        for val in fvs:
            if val[0] == "master":
                master_port = val[1]
                break

        (status, fvs) = brk_tbl.get(master_port)
        if status != True:
            return False

        brk_status = None
        for val in fvs:
            if val[0] == "status":
                brk_status = val[1]
                break

        if brk_status == "InProgress":
            return True

        return False

    def _event_poll(self, int_tbl, dom_tbl, app_port_tbl, app_status_port_tbl, state_port_xcvr_tbl, port_brk_tbl, brk_tbl):
        for key in range(_wrapper_port_start(), _wrapper_port_end() + 1):
            logical_port_list = platform_sfputil.get_physical_to_logical(int(key))
            if logical_port_list is None:
                continue

            if _wrapper_get_presence(key):
                if self.mod_tbl[key] == SFP_STATE_EMPTY:
                    self.mod_tbl[key] = SFP_STATE_INSERT
                    continue

                if self.mod_tbl[key] != SFP_STATE_READY:
                    rc = SFP_EEPROM_NOT_READY
                    for logical_port in logical_port_list:
                        # Get the asic to which this port belongs
                        asic_index = platform_sfputil.get_asic_id_for_logical_port(logical_port)
                        if asic_index is None:
                            helper_logger.log_debug("Got invalid asic index for {}, ignored".format(logical_port))
                            #continue ----- #FIXME
                            asic_index = 0

                        if self._port_in_breakout(port_brk_tbl[asic_index], brk_tbl[asic_index], logical_port):
                            helper_logger.log_notice("Port " + logical_port + " breakout InProgress..")
                            continue

                        rc = do_sfp_insertion(logical_port, int_tbl[asic_index], dom_tbl[asic_index], app_port_tbl[asic_index], app_status_port_tbl[asic_index], state_port_xcvr_tbl[asic_index])
                        if rc != 0:
                            break
                    if rc == 0:
                        self.mod_tbl[key] = SFP_STATE_READY
            else:
                if self.mod_tbl[key] != SFP_STATE_EMPTY:
                    for logical_port in logical_port_list:
                        # Get the asic to which this port belongs
                        asic_index = platform_sfputil.get_asic_id_for_logical_port(logical_port)
                        if asic_index is None:
                            helper_logger.log_debug("Got invalid asic index for {}, ignored".format(logical_port))
                            #continue ----- #FIXME
                            asic_index = 0
                        do_sfp_removal(logical_port, app_port_tbl[asic_index], app_status_port_tbl[asic_index], state_port_xcvr_tbl[asic_index], int_tbl[asic_index], dom_tbl[asic_index])
                    self.mod_tbl[key] = SFP_STATE_EMPTY

    # Wait for port init is done
    def wait_for_port_init_done(self):
        # Connect to APPL_DB and subscribe to PORT table notifications
        appl_db = daemon_base.db_connect("APPL_DB")

        sel = swsscommon.Select()
        sst = swsscommon.SubscriberStateTable(appl_db, swsscommon.APP_PORT_TABLE_NAME)
        sel.addSelectable(sst)

        # Make sure this daemon started after all port configured
        while not self.stop_event.is_set():
            (state, c) = sel.select(SELECT_TIMEOUT_MSECS)
            if state == swsscommon.Select.TIMEOUT:
                continue
            if state != swsscommon.Select.OBJECT:
                helper_logger.log_warning("sel.select() did not return swsscommon.Select.OBJECT")
                continue

            (key, op, fvp) = sst.pop()

            # Wait until PortInitDone
            if key in ["PortConfigDone", "PortInitDone"]:
                break

    def _mapping_event_from_change_event(self, status, port_dict):
        """
        mapping from what get_transceiver_change_event returns to event defined in the state machine
        the logic is pretty straightforword
        """
        if status:
            if bool(port_dict):
                event = NORMAL_EVENT
            else:
                event = SYSTEM_BECOME_READY
                # here, a simple timeout event whose port_dict is empty is mapped
                # into a SYSTEM_BECOME_READY event so that it can be handled
                port_dict[EVENT_ON_ALL_SFP] = SYSTEM_BECOME_READY
        else:
            if EVENT_ON_ALL_SFP in port_dict.keys():
                event = port_dict[EVENT_ON_ALL_SFP]
            else:
                # this should not happen. just for protection
                event = SYSTEM_FAIL
                port_dict[EVENT_ON_ALL_SFP] = SYSTEM_FAIL

        helper_logger.log_debug("mapping from {} {} to {}".format(status, port_dict, event))
        return event


    def del_port_sfp_info_from_db(self, port, int_tbl, dom_tbl):
        try:
            int_tbl._del(port)
            dom_tbl._del(port)

        except NotImplementedError:
            helper_logger.log_error("This functionality is currently not implemented for this platform")
            sys.exit(NOT_IMPLEMENTED_ERROR)


    def process_dpb_msg(self, msg, int_tbl, dom_tbl, app_port_tbl, app_status_port_tbl, state_port_xcvr_tbl):
        global platform_sfputil

        if msg == None:
            return

        # helper_logger.log_notice("Got msg: {}".format(str(msg)))

        opt    = msg['opt']
        index  = msg['index']
        lanes  = msg['lanes']
        port   = msg['port']
        speed  = msg['speed']

        # helper_logger.log_info("DPB-2 cmd {}".format(cmd))
        # Get the asic to which this port belongs
        asic_index = platform_sfputil.get_asic_id_for_logical_port(port)
        if asic_index is None:
            helper_logger.log_debug("Got invalid asic index for {}, ignored".format(port))
            #continue ----- #FIXME
            asic_index = 0

        if opt == 'del':
            do_sfp_removal(port, app_port_tbl[asic_index], app_status_port_tbl[asic_index], state_port_xcvr_tbl[asic_index],int_tbl[asic_index], dom_tbl[asic_index])
            helper_logger.log_notice("DPB-1 port {} state:{} SFP removed from cage {}".format(port, self.mod_tbl[index], index))
            platform_sfputil.del_logical_port(port)

        if opt == 'add':
            platform_sfputil.add_logical_port(port, index, lanes, speed)
            helper_logger.log_notice("DPB-1 port {} state:{} {}/{} SFP added in cage {}".format(port, self.mod_tbl[index], lanes, speed, index))
            do_sfp_insertion(port, int_tbl[asic_index], dom_tbl[asic_index], app_port_tbl[asic_index], app_status_port_tbl[asic_index], state_port_xcvr_tbl[asic_index])


    def task_worker(self, stopping_event, sfp_error_event, y_cable_presence):
        global platform_sfputil

        helper_logger.log_notice("Start SFP monitoring loop (pid {0})".format(os.getpid()))
        update_proc_name('xcvrd_sfpstate')

        transceiver_dict = {}
        # Connect to STATE_DB and create transceiver dom/sfp info tables
        state_db, appl_db, int_tbl, dom_tbl, status_tbl, app_port_tbl = {}, {}, {}, {}, {}, {}
        config_db, port_brk_tbl, brk_tbl, state_port_xcvr_tbl, app_status_port_tbl = {}, {}, {}, {}, {}

        # Get the namespaces in the platform
        namespaces = multi_asic.get_front_end_namespaces()
        for namespace in namespaces:
            asic_id = multi_asic.get_asic_index_from_namespace(namespace)
            state_db[asic_id] = daemon_base.db_connect("STATE_DB", namespace)
            config_db[asic_id] = daemon_base.db_connect("CONFIG_DB", namespace)
            port_brk_tbl[asic_id] = swsscommon.Table(config_db[asic_id], "BREAKOUT_PORTS")

            int_tbl[asic_id] = swsscommon.Table(state_db[asic_id], TRANSCEIVER_INFO_TABLE)
            dom_tbl[asic_id] = swsscommon.Table(state_db[asic_id], TRANSCEIVER_DOM_SENSOR_TABLE)
            brk_tbl[asic_id] = swsscommon.Table(state_db[asic_id], "PORT_BREAKOUT")
            status_tbl[asic_id] = swsscommon.Table(state_db[asic_id], TRANSCEIVER_STATUS_TABLE)
            state_port_xcvr_tbl[asic_id] = swsscommon.Table(state_db[asic_id], STATE_PORT_XCVR_TABLE)

            # Connect to APPL_DB to notify Media notifications
            appl_db[asic_id] = daemon_base.db_connect("APPL_DB", namespace)
            app_port_tbl[asic_id] = swsscommon.ProducerStateTable(appl_db[asic_id], swsscommon.APP_PORT_TABLE_NAME)

            app_status_port_tbl[asic_id] = swsscommon.ProducerStateTable(appl_db[asic_id],
                                                     swsscommon.APP_PORT_APP_STATUS_TABLE_NAME)

        # Start main loop to listen to the SFP change event.
        # The state migrating sequence:
        # 1. When the system starts, it is in "INIT" state, calling get_transceiver_change_event
        #    with RETRY_PERIOD_FOR_SYSTEM_READY_MSECS as timeout for before reach RETRY_TIMES_FOR_SYSTEM_READY
        #    times, otherwise it will transition to "EXIT" state
        # 2. Once 'system_become_ready' returned, the system enters "SYSTEM_READY" state and starts to monitor
        #    the insertion/removal event of all the SFP modules.
        #    In this state, receiving any system level event will be treated as an error and cause transition to
        #    "INIT" state
        # 3. When system back to "INIT" state, it will continue to handle system fail event, and retry until reach
        #    RETRY_TIMES_FOR_SYSTEM_READY times, otherwise it will transition to "EXIT" state

        # states definition
        # - Initial state: INIT, before received system ready or a normal event
        # - Final state: EXIT
        # - other state: NORMAL, after has received system-ready or a normal event

        # events definition
        # - SYSTEM_NOT_READY
        # - SYSTEM_BECOME_READY
        #   -
        # - NORMAL_EVENT
        #   - sfp insertion/removal
        #   - timeout returned by sfputil.get_change_event with status = true
        # - SYSTEM_FAIL

        # State transition:
        # 1. SYSTEM_NOT_READY
        #     - INIT
        #       - retry < RETRY_TIMES_FOR_SYSTEM_READY
        #             retry ++
        #       - else
        #             max retry reached, treat as fatal, transition to EXIT
        #     - NORMAL
        #         Treat as an error, transition to INIT
        # 2. SYSTEM_BECOME_READY
        #     - INIT
        #         transition to NORMAL
        #     - NORMAL
        #         log the event
        #         nop
        # 3. NORMAL_EVENT
        #     - INIT (for the vendors who don't implement SYSTEM_BECOME_READY)
        #         transition to NORMAL
        #         handle the event normally
        #     - NORMAL
        #         handle the event normally
        # 4. SYSTEM_FAIL
        #     - INIT
        #       - retry < RETRY_TIMES_FOR_SYSTEM_READY
        #             retry ++
        #       - else
        #             max retry reached, treat as fatal, transition to EXIT
        #     - NORMAL
        #         Treat as an error, transition to INIT

        # State           event               next state
        # INIT            SYSTEM NOT READY    INIT / EXIT
        # INIT            SYSTEM FAIL         INIT / EXIT
        # INIT            SYSTEM BECOME READY NORMAL
        # NORMAL          SYSTEM BECOME READY NORMAL
        # NORMAL          SYSTEM FAIL         INIT
        # INIT/NORMAL     NORMAL EVENT        NORMAL
        # NORMAL          SYSTEM NOT READY    INIT
        # EXIT            -

        retry = 0
        timeout = RETRY_PERIOD_FOR_SYSTEM_READY_MSECS
        state = STATE_INIT

        # if-down-reason initialization
        for key in range(_wrapper_port_start(), _wrapper_port_end() + 1):
            logical_port_list = platform_sfputil.get_physical_to_logical(int(key))
            if logical_port_list is None:
                continue
            op = 'del' if _wrapper_get_presence(key) else 'set'
            for logical_port in logical_port_list:
                update_xcvr_if_reason(logical_port, op, 'transceiver_not_present')

        # SFP monitoring
        while not stopping_event.is_set():

            next_state = state
            time_start = time.time()

            # Look for  DPB Messages
            while not self.task_queue.empty():
                msg = self.task_queue.get(block=True, timeout=0.1)
                if msg == None:
                    continue

                self.process_dpb_msg(msg, int_tbl, dom_tbl, app_port_tbl, app_status_port_tbl, state_port_xcvr_tbl)

            try:
                status, port_dict = _wrapper_get_transceiver_change_event()
            except:
                self._event_poll(int_tbl, dom_tbl, app_port_tbl, app_status_port_tbl, state_port_xcvr_tbl, port_brk_tbl, brk_tbl)
                time.sleep(TIME_FOR_SFP_POLL_SECS)
                continue

            helper_logger.log_debug("Got event {} {} in state {}".format(status, port_dict, state))
            event = self._mapping_event_from_change_event(status, port_dict)
            if event == SYSTEM_NOT_READY:
                if state == STATE_INIT:
                    # system not ready, wait and retry
                    if retry >= RETRY_TIMES_FOR_SYSTEM_READY:
                        helper_logger.log_error("System failed to get ready in {} secs or received system error. Exiting...".format(
                            (RETRY_PERIOD_FOR_SYSTEM_READY_MSECS/1000)*RETRY_TIMES_FOR_SYSTEM_READY))
                        next_state = STATE_EXIT
                        sfp_error_event.set()
                    else:
                        retry = retry + 1

                        # get_transceiver_change_event may return immediately,
                        # we want the retry expired in expected time period,
                        # So need to calc the time diff,
                        # if time diff less that the pre-defined waiting time,
                        # use sleep() to complete the time.
                        time_now = time.time()
                        time_diff = time_now - time_start
                        if time_diff < RETRY_PERIOD_FOR_SYSTEM_READY_MSECS/1000:
                            time.sleep(RETRY_PERIOD_FOR_SYSTEM_READY_MSECS/1000 - time_diff)
                elif state == STATE_NORMAL:
                    helper_logger.log_error("Got system_not_ready in normal state, treat as fatal. Exiting...")
                    next_state = STATE_EXIT
                else:
                    next_state = STATE_EXIT
            elif event == SYSTEM_BECOME_READY:
                if state == STATE_INIT:
                    next_state = STATE_NORMAL
                    helper_logger.log_notice("Got system_become_ready in init state, transition to normal state")
                elif state == STATE_NORMAL:
                    helper_logger.log_debug("Got system_become_ready in normal state, ignored")
                else:
                    next_state = STATE_EXIT
            elif event == NORMAL_EVENT:
                if state == STATE_NORMAL or state == STATE_INIT:
                    if state == STATE_INIT:
                        next_state = STATE_NORMAL
                    # this is the originally logic that handled the transceiver change event
                    # this can be reached in two cases:
                    #   1. the state has been normal before got the event
                    #   2. the state was init and transition to normal after got the event.
                    #      this is for the vendors who don't implement "system_not_ready/system_becom_ready" logic
                    for key, value in port_dict.items():
                        logical_port_list = platform_sfputil.get_physical_to_logical(int(key))
                        if logical_port_list is None:
                            helper_logger.log_warning("Got unknown FP port index {}, ignored".format(key))
                            continue
                        for logical_port in logical_port_list:

                            # Get the asic to which this port belongs
                            asic_index = platform_sfputil.get_asic_id_for_logical_port(logical_port)
                            if asic_index is None:
                                helper_logger.log_debug("Got invalid asic index for {}, ignored".format(logical_port))
                                #continue ----- #FIXME
                                asic_index = 0

                            if value == SFP_STATUS_INSERTED:
                                helper_logger.log_notice(logical_port + ": Got SFP inserted event")
                                update_xcvr_if_reason(logical_port, 'del', 'transceiver_not_present')
                                # A plugin event will clear the error state.
                                update_port_transceiver_status_table(
                                    logical_port, status_tbl[asic_index], SFP_STATUS_INSERTED)
                                helper_logger.log_notice("receive plug in and update port sfp status table.")
                                rc = post_port_sfp_info_to_db(logical_port, int_tbl[asic_index], transceiver_dict, False)
                                # If we didn't get the sfp info, assuming the eeprom is not ready, give a try again.
                                if rc == SFP_EEPROM_NOT_READY:
                                    helper_logger.log_warning("SFP EEPROM is not ready. One more try...")
                                    time.sleep(TIME_FOR_SFP_READY_SECS + random.random())
                                    post_port_sfp_info_to_db(logical_port, int_tbl[asic_index], transceiver_dict, False)
                                if not dom_is_supported(logical_port):
                                    default_passive_media_dom_entry_set(logical_port, dom_tbl[asic_index])
                                post_port_dom_threshold_info_to_db(logical_port, dom_tbl[asic_index])
                                xcvr_config_updater.prepare_for_config(logical_port)
                                # Notify media setting and interface_type
                                xcvr_state = notify_media_setting(logical_port, transceiver_dict, app_port_tbl[asic_index], True)
                                power_up_media(logical_port, transceiver_dict, int_tbl[asic_index])
                                notify_port_xcvr_status(logical_port, app_status_port_tbl[asic_index], state_port_xcvr_tbl[asic_index], xcvr_state)
                                adapter = ""
                                physical_port = int(key)
                                if transceiver_dict.get(physical_port) is not None:
                                    d = transceiver_dict[physical_port]
                                    adapter = "(" + d.get('qsa_adapter', 'N/A') +")" if d.get('qsa_adapter', 'N/A') not in ('N/A', 'Present') else ""
                                helper_logger.log_notice(logical_port + ": SFP inserted" + str(adapter))
                                transceiver_dict.clear()
                            elif value == SFP_STATUS_REMOVED:
                                helper_logger.log_notice(logical_port + ": Got SFP removed event")
                                adapter = ""
                                physical_port = int(key)
                                if transceiver_dict.get(physical_port) is not None:
                                    d = transceiver_dict[physical_port]
                                    adapter = d.get('qsa_adapter', 'N/A') if d.get('qsa_adapter', 'N/A') not in ('N/A', 'Present') else ""
                                update_xcvr_if_reason(logical_port, 'set', 'transceiver_not_present')
                                update_port_transceiver_status_table(
                                    logical_port, status_tbl[asic_index], SFP_STATUS_REMOVED)
                                helper_logger.log_notice("receive plug out and update port sfp status table.")
                                del_port_sfp_dom_info_from_db(logical_port, int_tbl[asic_index], dom_tbl[asic_index])
                                notify_port_xcvr_status(logical_port, app_status_port_tbl[asic_index], state_port_xcvr_tbl[asic_index], XCVR_STATE_EMPTY)
                                _wrapper_clear_eeprom_cache(logical_port)
                                power_down_media(logical_port)
                                helper_logger.log_notice(logical_port + ": SFP removed" + str(adapter))
                            elif value in errors_block_eeprom_reading:
                                helper_logger.log_notice("Got SFP Error event")
                                # Add port to error table to stop accessing eeprom of it
                                # If the port already in the error table, the stored error code will
                                # be updated to the new one.
                                update_port_transceiver_status_table(logical_port, status_tbl[asic_index], value)
                                helper_logger.log_notice("receive error update port sfp status table.")
                                # In this case EEPROM is not accessible, so remove the DOM info
                                # since it will be outdated if long time no update.
                                # but will keep the interface info in the DB since it static.
                                del_port_sfp_dom_info_from_db(logical_port, None, dom_tbl[asic_index])
                                _wrapper_clear_eeprom_cache(logical_port)

                            else:
                                # SFP return unkown event, just ignore for now.
                                helper_logger.log_warning("Got unknown event {}, ignored".format(value))
                                continue

                    # Since ports could be connected to a mux cable, if there is a change event process the change for being on a Y cable Port
                    y_cable_helper.change_ports_status_for_y_cable_change_event(
                        port_dict, y_cable_presence, stopping_event)
                else:
                    next_state = STATE_EXIT
            elif event == SYSTEM_FAIL:
                if state == STATE_INIT:
                    # To overcome a case that system is only temporarily not available,
                    # when get system fail event will wait and retry for a certain period,
                    # if system recovered in this period xcvrd will transit to INIT state
                    # and continue run, if can not recover then exit.
                    if retry >= RETRY_TIMES_FOR_SYSTEM_FAIL:
                        helper_logger.log_error("System failed to recover in {} secs. Exiting...".format(
                            (RETRY_PERIOD_FOR_SYSTEM_FAIL_MSECS/1000)*RETRY_TIMES_FOR_SYSTEM_FAIL))
                        next_state = STATE_EXIT
                        sfp_error_event.set()
                    else:
                        retry = retry + 1
                        waiting_time_compensation_with_sleep(time_start, RETRY_PERIOD_FOR_SYSTEM_FAIL_MSECS/1000)
                elif state == STATE_NORMAL:
                    helper_logger.log_error("Got system_fail in normal state, treat as error, transition to INIT...")
                    next_state = STATE_INIT
                    timeout = RETRY_PERIOD_FOR_SYSTEM_FAIL_MSECS
                    retry = 0
                else:
                    next_state = STATE_EXIT
            else:
                helper_logger.log_warning("Got unknown event {} on state {}.".format(event, state))

            if next_state != state:
                helper_logger.log_debug("State transition from {} to {}".format(state, next_state))
                state = next_state

            if next_state == STATE_EXIT:
                os.kill(os.getppid(), signal.SIGTERM)
                break

        helper_logger.log_info("Stop SFP monitoring loop")

    def task_run(self, sfp_error_event, y_cable_presence):
        if self.task_stopping_event.is_set():
            return

        self.task_process = multiprocessing.Process(target=self.task_worker, args=(
            self.task_stopping_event, sfp_error_event, y_cable_presence))
        self.task_process.start()

    def task_notify(self, msg):
        if self.task_stopping_event.is_set():
            return
        self.task_queue.put(msg)
        time.sleep(0.001)
        # def process_dpb_msg(self, msg, int_tbl, dom_tbl, app_port_tbl, app_status_port_tbl, state_port_xcvr_tbl):

    def task_stop(self):
        self.task_stopping_event.set()
        if os.environ.get('COVERAGE_RUN') is not None:
            os.kill(self.task_process.pid, signal.SIGTERM)
        else:
            os.kill(self.task_process.pid, signal.SIGKILL)

#
# Daemon =======================================================================
#


class DaemonXcvrd(daemon_base.DaemonBase):
    def __init__(self, log_identifier):
        super(DaemonXcvrd, self).__init__(log_identifier)

        self.set_min_log_priority_debug()
        self.timeout = XCVRD_MAIN_THREAD_SLEEP_SECS
        self.num_asics = multi_asic.get_num_asics()
        self.stop_event = threading.Event()
        self.sfp_error_event = multiprocessing.Event()
        self.y_cable_presence = [False]

    # Signal handler
    def signal_handler(self, sig, frame):
        if sig == signal.SIGHUP:
            self.log_notice("Caught SIGHUP - ignoring...")
        elif sig == signal.SIGINT:
            self.log_notice("Caught SIGINT - exiting...")
            self.stop_event.set()
        elif sig == signal.SIGTERM:
            self.log_notice("Caught SIGTERM - exiting...")
            self.stop_event.set()
        else:
            self.log_warning("Caught unhandled signal '" + sig + "'")

    # Wait for port config is done
    def wait_for_port_config_done(self, namespace):
        # Connect to APPL_DB and subscribe to PORT table notifications
        appl_db = daemon_base.db_connect("APPL_DB", namespace=namespace)

        sel = swsscommon.Select()
        sst = swsscommon.SubscriberStateTable(appl_db, swsscommon.APP_PORT_TABLE_NAME)
        sel.addSelectable(sst)

        # Make sure this daemon started after all port configured
        while not self.stop_event.is_set():
            (state, c) = sel.select(SELECT_TIMEOUT_MSECS)
            if state == swsscommon.Select.TIMEOUT:
                continue
            if state != swsscommon.Select.OBJECT:
                self.log_warning("sel.select() did not return swsscommon.Select.OBJECT")
                continue

            (key, op, fvp) = sst.pop()
            if key in ["PortConfigDone", "PortInitDone"]:
                break

    def load_media_settings(self):
        global media_settings
        global g_dict
        (platform_path, hwsku_path) = device_info.get_paths_to_platform_and_hwsku_dirs()

        media_settings_file_path = os.path.join(platform_path, "media_settings.json")
        if not os.path.isfile(media_settings_file_path):
            self.log_notice("xcvrd: No media file exists %s" % (media_settings_file_path))
            return {}

        media_file = open(media_settings_file_path, "r")
        media_settings = media_file.read()
        g_dict = json.loads(media_settings, object_pairs_hook=collections.OrderedDict)

    def get_gearbox_interfaces(self):
        global g_gearbox_interfaces
        (platform_path, hwsku_path) = device_info.get_paths_to_platform_and_hwsku_dirs()

        gearbox_config_file_path = os.path.join(hwsku_path, "gearbox_config.json")
        if not os.path.isfile(gearbox_config_file_path):
            self.log_notice("xcvrd: No gearbox config file exists %s" % (gearbox_config_file_path))
            return {}

        gearbox_file = open(gearbox_config_file_path, "r")
        gearbox_config = json.load(gearbox_file)

        for intf in gearbox_config['interfaces']:
            name = intf.get('name')
            index = intf.get('index')
            g_gearbox_interfaces[name] = index

    # Initialize daemon
    def init(self):
        global platform_sfputil
        global platform_chassis
        global first_phy_port
        global ext_media_module
        global cmis_init_worker
        global cmis_diag_worker
        global xcvr_config_updater

        self.log_info("Start daemon init...")

        # Load new platform api class
        try:
            import sonic_platform.platform
            import sonic_platform_base.sonic_sfp.sfputilhelper
            platform_chassis = sonic_platform.platform.Platform().get_chassis()
            self.log_info("chassis loaded {}".format(platform_chassis))
            # we have to make use of sfputil for some features
            # even though when new platform api is used for all vendors.
            # in this sense, we treat it as a part of new platform api.
            # we have already moved sfputil to sonic_platform_base
            # which is the root of new platform api.
            platform_sfputil = sonic_platform_base.sonic_sfp.sfputilhelper.SfpUtilHelper()

            # Get the ext media mod
            import sonic_platform_base.sonic_sfp.ext_media_api as ext_media_module
        except Exception as e:
            self.log_notice("Failed to load chassis due to {}".format(repr(e)))
            self.log_notice("Fallback to legacy platform routines")

        # Load platform specific sfputil class
        if platform_chassis is None or platform_sfputil is None:
            try:
                platform_chassis = None
                platform_sfputil = self.load_platform_util(PLATFORM_SPECIFIC_MODULE_NAME, PLATFORM_SPECIFIC_CLASS_NAME)
            except Exception as e:
                self.log_error("Failed to load sfputil from legacy platform routines due to {} ... Exiting".format(repr(e)))
                sys.exit(SFPUTIL_LOAD_ERROR)

        if multi_asic.is_multi_asic():
            # Load the namespace details first from the database_global.json file.
            swsscommon.SonicDBConfig.initializeGlobalConfig()

        # Load port info
        try:
            if multi_asic.is_multi_asic():
                # For multi ASIC platforms we pass DIR of port_config_file_path and the number of asics
                (platform_path, hwsku_path) = device_info.get_paths_to_platform_and_hwsku_dirs()
                platform_sfputil.read_all_porttab_mappings(hwsku_path, self.num_asics)
            else:
                # For single ASIC platforms we pass port_config_file_path and the asic_inst as 0
                # ** Community DPB uses device_info
                # port_config_file_path = device_info.get_path_to_port_config_file()
                port_config_file_path = self.get_path_to_port_config_file()
                platform_sfputil.read_porttab_mappings(port_config_file_path, 0)
        except Exception as e:
            self.log_error("Failed to read port info: {}".format(str(e)), True)
            sys.exit(PORT_CONFIG_LOAD_ERROR)

        # Find out the physical port is 0-based or 1-based
        if platform_sfputil.logical_to_physical[platform_sfputil.logical[0]][0] == 0:
            first_phy_port = 0
        elif platform_sfputil.logical_to_physical[platform_sfputil.logical[0]][0] == 1:
            first_phy_port = 1
        else:
            # default is 1-based
            first_phy_port = 1

        # Connect to STATE_DB and create transceiver dom/sfp info tables
        state_db, self.int_tbl, self.dom_tbl, self.status_tbl = {}, {}, {}, {}

        # Get the namespaces in the platform
        namespaces = multi_asic.get_front_end_namespaces()
        for namespace in namespaces:
            asic_id = multi_asic.get_asic_index_from_namespace(namespace)
            state_db[asic_id] = daemon_base.db_connect("STATE_DB", namespace)
            self.int_tbl[asic_id] = swsscommon.Table(state_db[asic_id], TRANSCEIVER_INFO_TABLE)
            self.dom_tbl[asic_id] = swsscommon.Table(state_db[asic_id], TRANSCEIVER_DOM_SENSOR_TABLE)
            self.status_tbl[asic_id] = swsscommon.Table(state_db[asic_id], TRANSCEIVER_STATUS_TABLE)

        self.load_media_settings()

        self.get_gearbox_interfaces()

        # Initialize SFP module presence table
        self.mod_tbl = {}
        for key in range(_wrapper_port_start(), _wrapper_port_end() + 1):
            self.mod_tbl[key] = SFP_STATE_EMPTY

        warmstart = swsscommon.WarmStart()
        warmstart.initialize("xcvrd", "pmon")
        warmstart.checkWarmStart("xcvrd", "pmon", False)
        is_warm_start = warmstart.isWarmStart()

        transceiver_dict = {}
        if START_SFP_READ_BEFORE_PORT_INIT == True:
            port_sfp_info_collect(transceiver_dict)

        self.log_info("Wait for port config is done")
        for namespace in namespaces:
            self.wait_for_port_config_done(namespace)

        # Init the xcvr configuration process
        xcvr_config_updater = XcvrConfigTask()
        # Start the xcvr config update process
        xcvr_config_updater.task_run()

        # Init CMIS task at deactivated state
        cmis_diag_worker = cmis_diag_update_task()
        cmis_init_worker = cmis_init_update_task()

        # Post all the current interface dom/sfp info to STATE_DB
        self.log_info("Post all port DOM/SFP info to DB")
        post_port_sfp_dom_info_to_db(is_warm_start, self.mod_tbl, transceiver_dict, self.stop_event)

        # Init port sfp status table
        self.log_info("Init port sfp status table")
        init_port_sfp_status_tbl(self.stop_event)

        # Init port y_cable status table
        y_cable_helper.init_ports_status_for_y_cable(
            platform_sfputil, platform_chassis, self.y_cable_presence, self.stop_event)

    # Deinitialize daemon
    def deinit(self):
        self.log_info("Start daemon deinit...")

        # Delete all the information from DB and then exit
        logical_port_list = platform_sfputil.logical
        for logical_port_name in logical_port_list:
            # Get the asic to which this port belongs
            asic_index = platform_sfputil.get_asic_id_for_logical_port(logical_port_name)
            if asic_index is None:
                helper_logger.log_debug("Got invalid asic index for {}, ignored".format(logical_port_name))
                #continue ----- #FIXME
                asic_index = 0

            del_port_sfp_dom_info_from_db(logical_port_name, self.int_tbl[asic_index], self.dom_tbl[asic_index])
            _wrapper_clear_eeprom_cache(logical_port_name)
            delete_port_from_status_table(logical_port_name, self.status_tbl[asic_index])

        if self.y_cable_presence[0] is True:
            y_cable_helper.delete_ports_status_for_y_cable()

    # Run daemon

    def run(self):
        self.log_notice("Starting up... (pid {0})".format(os.getpid()))

        # Initialize proc names
        update_proc_name('xcvrd')

        # Start daemon initialization sequence
        self.init()

        # Start the copper manager thread
        copper_manager = CopperManagerTask(platform_chassis, helper_logger)
        copper_manager.task_run()

        # Start the dom sensor info update thread
        global dom_info_update
        dom_info_update = DomInfoUpdateTask()
        dom_info_update.task_run()

        # Start the CMIS diag worker process
        cmis_diag_worker.task_run()

        # Start the CMIS worker process
        cmis_init_worker.task_run()

        # Start the sfp state info update process
        global sfp_state_update
        sfp_state_update = SfpStateUpdateTask(self.mod_tbl)
        sfp_state_update.task_run(self.sfp_error_event, self.y_cable_presence)

        # Start the Y-cable state info update process if Y cable presence established
        y_cable_state_update = None
        if self.y_cable_presence[0] is True:
            y_cable_state_update = y_cable_helper.YCableTableUpdateTask()
            y_cable_state_update.task_run()

        # Start the db update thread
        app_db_update = app_db_update_task()
        app_db_update.task_run()

        # Start main loop
        self.log_info("Start daemon main loop")

        while not self.stop_event.wait(self.timeout):
            # Check the integrity of the sfp info table and recover the missing entries if any
            recover_missing_sfp_table_entries(platform_sfputil, self.int_tbl, self.status_tbl, self.stop_event)

        self.log_info("Stop daemon main loop")

        # Stop the dom sensor info update thread
        self.log_info("Stopping dom sensor info update task")
        dom_info_update.task_stop()

        # Stop the app db update process
        self.log_info("Stopping app db update task")
        app_db_update.task_stop()

        # Stop the sfp state info update process
        self.log_info("Stopping sfp state info update task")
        sfp_state_update.task_stop()

        # Stop the copper manager thread
        self.log_info("Stopping copper ports manager task")
        copper_manager.task_stop()

        # Stop the CMIS diag worker process
        self.log_info("Stopping CMIS diag worker task")
        cmis_diag_worker.task_stop()

        # Stop the CMIS init worker process
        self.log_info("Stopping CMIS init worker process")
        cmis_init_worker.task_stop()

        # Stop the Y-cable state info update process
        if self.y_cable_presence[0] is True:
            self.log_info("Stopping Y-cable state info update task")
            y_cable_state_update.task_stop()

        # Stop the configuration work process
        self.log_info("Stopping  configuration updater task")
        xcvr_config_updater.task_stop()

        # Start daemon deinitialization sequence
        self.deinit()

        self.log_info("Shutting down...")

        if self.sfp_error_event.is_set():
            sys.exit(SFP_SYSTEM_ERROR)

#
# Main =========================================================================
#

# This is our main entry point for xcvrd script


def main():
    xcvrd = DaemonXcvrd(SYSLOG_IDENTIFIER)
    xcvrd.run()


if __name__ == '__main__':
    main()
