########################################################################
# DellEMC
#
# Module contains the initialization and main interface to consuming apps
#
########################################################################

import inspect
import syslog

from .ext_media_utils import DEFAULT_NO_DATA_VALUE, media_eeprom_address, sfp_read_bytes
from .ext_media_common import get_form_factor_info, \
        qsfp56_dd_prep_to_set_fec_mode, qsfp56_dd_set_media_fec_mode, qsfp56_dd_get_media_fec_mode, \
        qsfp28_enable_media_power, qsfp28_select_rate, is_qsfp28_dd, qsfp28_dd_select_rate, qsfp28_dd_media_lockdown_set
from .ext_media_handler_base import media_static_info
from .ext_media_cmis_init import cmis_init
from .ext_media_cmis_diag import cmis_diag

CMIS_VER_ADDR = media_eeprom_address(offset=1)
CMIS_VER_3= 0x30

"""
Finds the appropriate driver module, executes calls
Returns a dictionary of attributes from media, with default of DEFAULT_NO_DATA_VALUE is not able to get data.
"""
def get_static_info(sfp_obj, platform_obj=None):
    eeprom_path = sfp_obj.get_eeprom_sysfs_path()

    eeprom_bytes = sfp_obj.get_eeprom_cache_raw()
    if eeprom_bytes is None:
        syslog.syslog(syslog.LOG_ERR, "No EEPROM content for Port {}".format(sfp_obj.port_index))
        return None

    # Get an instance of the form factor handler, or return None (or throw) if error
    def get_handler_instance():

        # Get the corresponding form-factor 
        form_factor_name, form_factor_module = get_form_factor_info(eeprom_bytes)
        if None is form_factor_name:
            return None
        if None is form_factor_module:
            raise NotImplementedError("Unable to find implementation for form-factor: " + str(form_factor_name))

        form_factor_module_name = str(form_factor_module.__name__)
        # Based on the form-factor, select the obj

        # Get the classes
        handler_class_list = inspect.getmembers(form_factor_module, lambda cl: inspect.isclass(cl))

        handler_class = None

        # Pick class which matches filename, less ext_media prefix
        for cl_name, cl in handler_class_list:
            if form_factor_module_name.split('ext_media_handler_')[1] ==  cl_name:
                handler_class = cl
                break
        if handler_class is None:
            return None

        handler_instance = handler_class(eeprom_bytes, sfp_obj)
        return handler_instance

    handler_inst = None
    try:
        handler_inst = get_handler_instance()
    except:
        pass

    # List of functions which are expected to be implemented by handler 
    std_meth_list = inspect.getmembers(media_static_info, lambda x: inspect.ismethod(x) or inspect.isfunction(x))

    ret_dict = dict()
    # Now pick and run only methods which intersect 
    for meth, _ in std_meth_list:
        # Key is the suffix of the get_*** method
        key = meth.split('get_')[1]
        # Set default value
        value = DEFAULT_NO_DATA_VALUE
        try:
            value = str(getattr(handler_inst, meth)(eeprom_bytes))
            if value == 'None':
                value = DEFAULT_NO_DATA_VALUE
        except Exception as e:
            #print("Could not perform {} on device {}: {}".format(meth, eeprom_path, e))
            pass
        ret_dict[key] = value

    if ret_dict['cable_class'] == 'FIBER':
        ret_dict['cable_length_detailed'] = '0.0'

    try:
        ret_dict['qsa_adapter'] = str(sfp_obj.qsa_adapter_type)
    except AttributeError:
        ret_dict['qsa_adapter'] = str(get_qsa_status(ret_dict, sfp_obj))

    try:
        ret_dict['is_qualified'] = str(is_qualified(ret_dict, platform_obj, sfp_obj))

        ret_dict['max_port_power'] = str(get_max_port_power(sfp_obj))

        # Vendor remap based on part number
        remap = get_overrides(ret_dict, platform_obj)
        for key in  remap:
            ret_dict[key] = remap[key]
    except:
        pass

    return ret_dict


"""
Checks if the QSA adapter is connected 
Basically if the port is Q*** and the module inserted is s***, then a QSA must have been used
"""
def get_qsa_status(info_dict, sfp_obj):
    try:
        media_ff = info_dict.get('form_factor', DEFAULT_NO_DATA_VALUE)

        port_ff = sfp_obj.get_port_form_factor()
        # Form factor starts with 'Q'
        if port_ff[0] == 'Q' and media_ff in ['SFP', 'SFP+', 'SFP28', 'SFP56-DD']:
            return 'Present'
    except:
        pass

    return DEFAULT_NO_DATA_VALUE

"""
Gets the maximum power the port is allowed to dissipate
"""
def get_max_port_power(sfp_obj):
    try:
        return sfp_obj.get_max_port_power()
    except:
        pass

    # We can try to use port defaults
    try:
        port_ff = sfp_obj.get_port_form_factor()
        if port_ff in ['QSFP', 'QSFP+']:
            return 4.0
        elif port_ff in ['QSFP28']:
            return 4.5
        elif port_ff in ['QSFP28-DD']:
            return 8.0
        elif port_ff in ['QSFP56']:
            return 8.0
        elif port in ['QSFP56-DD']:
            return 10.0
        else:
            return 2.5
    except:
        pass
    return DEFAULT_NO_DATA_VALUE

"""
We check the media part info against the set of supported parts from the given platform
"""
def is_qualified(info_dict, platform_obj, sfp_obj):
    try:
        if info_dict['vendor_part_number'] in platform_obj.get_qualified_media_list():
            return True
    except:
        pass

    return False

"""
Contains maps to override or extend the standard fields with vendor-specific info, based on some attribures
This provides a mechanism for media attributes to be updated by using the part number
"""
def get_overrides(info_dict, platform_obj):
    try:
        return platform_obj.get_override_dict()[info_dict['vendor_part_number']]
    except:
        pass
    return dict()

def default_cmis_3_4_init(sfp_obj, application, lanes_per_port):
    """
    Perform the CMIS 3.0 and 4.0 initialization sequence

    Args:
        sfp_obj:
                A SFP object that inheris SfpBase/SfpSandard class
        application:
                The desired application code
        lanes_per_port:
                Lanes per port if the desired application code

    Returns:
        a Boolean, true if succeeded and false if failed
    """
    try:
        cmis_initializer = cmis_init(sfp_obj, logging=False)
        return cmis_initializer.initialize(application, lanes_per_port, 1)
    except Exception as ex:
        syslog.syslog(syslog.LOG_ERR, "CMIS: ERR: {0}".format(ex))
    return False

initialized_cmis_diag_dict = {}

def get_cmis_dom_info(sfp_obj):
    global initialized_cmis_diag_dict

    try:
        if sfp_obj not in initialized_cmis_diag_dict.keys():
            initialized_cmis_diag_dict[sfp_obj] = cmis_diag(sfp_obj, logging=False)
        return initialized_cmis_diag_dict[sfp_obj].get_dom_info()
    except:
        pass
    return None

def control_cmis_diags(sfp_obj, mode, enable):
    global initialized_cmis_diag_dict

    try:
        return initialized_cmis_diag_dict[sfp_obj].set_cmis_loopback_mode_enable(mode, enable)
    except:
        pass
    return False

def qsfp28_enable_high_power_class(sfp_obj, media_power):
    """
    Enable power class for the power delivered by media
    media_power - The power in watts delivered by media
    """
    eeprom_path = sfp_obj.get_eeprom_sysfs_path()
    qsfp28_enable_media_power(eeprom_path, media_power)

def select_rate(sfp_obj, rate):
    """
    Select rate on supported media
    sfp_obj: Media object
    rate : Rate to be selected
    """
    eeprom_path = sfp_obj.get_eeprom_sysfs_path()
    eeprom = sfp_obj.get_eeprom_cache_raw()
    if is_qsfp28_dd(eeprom):
        return qsfp28_dd_select_rate(sfp_obj, rate)
    else:
        return qsfp28_select_rate(sfp_obj, rate)

def prepare_to_set_fec_mode(sfp_obj):
    """
    Prepare media to set FEC mode
    sfp_obj: Media object
    """
    return qsfp56_dd_prep_to_set_fec_mode(sfp_obj)

def set_media_fec_mode(sfp_obj, mode, on_insertion, breakout_mode):
    """
    Set media fec mode per user configuration
    mode - FEC mode to be configured on  media
    on-insertion - True if media fec to be applied on insertion
               False if requested mode is configuration change
    """
    return qsfp56_dd_set_media_fec_mode(sfp_obj, mode, on_insertion, breakout_mode)


def get_media_fec_mode(sfp_obj):
    """ Get media fec mode on media """
    return qsfp56_dd_get_media_fec_mode(sfp_obj)

def media_lockdown_set(sfp_obj, status):
    """ media lockdown set """
    cmis_ver = sfp_read_bytes(sfp_obj, CMIS_VER_ADDR, 1)[0]
    sfp_id = sfp_read_bytes(sfp_obj, media_eeprom_address(offset=0), 1)[0]
    # if qsfp dd or qsfp +
    if (cmis_ver >= CMIS_VER_3) and (sfp_id == 0x18 or sfp_id == 0x1e):
        return qsfp28_dd_media_lockdown_set(sfp_obj, status)
