#----------------------------------------------------------------------------
# SFF-8024 Rev 4.5
#----------------------------------------------------------------------------

from __future__ import print_function

type_of_transceiver = {
    '00': 'Unknown or unspecified',
    '01': 'GBIC',
    '02': 'Module/connector soldered to motherboard',
    '03': 'SFP/SFP+/SFP28',
    '04': '300 pin XBI',
    '05': 'XENPAK',
    '06': 'XFP',
    '07': 'XFF',
    '08': 'XFP-E',
    '09': 'XPAK',
    '0a': 'X2',
    '0b': 'DWDM-SFP/SFP+',
    '0c': 'QSFP',
    '0d': 'QSFP+ or later',
    '0e': 'CXP or later',
    '0f': 'Shielded Mini Multilane HD 4X',
    '10': 'Shielded Mini Multilane HD 8X',
    '11': 'QSFP28 or later',
    '12': 'CXP2 (aka CXP28) or later',
    '13': 'CDFP (Style 1/Style2)',
    '14': 'Shielded Mini Multilane HD 4X Fanout Cable',
    '15': 'Shielded Mini Multilane HD 8X Fanout Cable',
    '16': 'CDFP (Style 3)',
    '17': 'microQSFP',
    '18': 'QSFP-DD Double Density 8X Pluggable Transceiver',
    '19': 'OSFP 8X Pluggable Transceiver',
    '1a': 'SFP-DD Double Density 2X Pluggable Transceiver',
    '1e': 'QSFP CMIS'
}

type_abbrv_name = {
    '00': 'Unknown',
    '01': 'GBIC',
    '02': 'Soldered',
    '03': 'SFP',
    '04': 'XBI300',
    '05': 'XENPAK',
    '06': 'XFP',
    '07': 'XFF',
    '08': 'XFP-E',
    '09': 'XPAK',
    '0a': 'X2',
    '0b': 'DWDM-SFP',
    '0c': 'QSFP',
    '0d': 'QSFP+',
    '0e': 'CXP',
    '0f': 'HD4X',
    '10': 'HD8X',
    '11': 'QSFP28',
    '12': 'CXP2',
    '13': 'CDFP-1/2',
    '14': 'HD4X-Fanout',
    '15': 'HD8X-Fanout',
    '16': 'CDFP-3',
    '17': 'MicroQSFP',
    '18': 'QSFP-DD',
    '19': 'OSFP-8X',
    '1a': 'SFP-DD',
    '1e': 'QSFP_CMIS'
}

connector_dict = {
    '00': 'Unknown or unspecified',
    '01': 'SC',
    '02': 'FC Style 1 copper connector',
    '03': 'FC Style 2 copper connector',
    '04': 'BNC/TNC',
    '05': 'FC coax headers',
    '06': 'Fiberjack',
    '07': 'LC',
    '08': 'MT-RJ',
    '09': 'MU',
    '0a': 'SG',
    '0b': 'Optical Pigtail',
    '0c': 'MPO 1x12',
    '0d': 'MPO 2x16',
    '20': 'HSSDC II',
    '21': 'Copper pigtail',
    '22': 'RJ45',
    '23': 'No separable connector',
    '24': 'MXC 2x16',
    '25': 'CS optical connector',
    '26': 'SN optical connector',
    '27': 'MPO 2x12',
    '28': 'MPO 1x16',
    }

# SFF8636
ext_type_of_transceiver = {
    '0': 'Power Class 1',
    '1': 'Power Class 2',
    '2': 'Power Class 3',
    '3': 'Power Class 4',
    '4': 'Power Class 5',
    '5': 'Power Class 6',
    '6': 'Power Class 7',
    '7': 'Power Class 8'
    }

# CMIS4
power_class_of_transceiver = {
    '00': 'Power Class 1',
    '01': 'Power Class 2',
    '02': 'Power Class 3',
    '03': 'Power Class 4',
    '04': 'Power Class 5',
    '05': 'Power Class 6',
    '06': 'Power Class 7',
    '07': 'Power Class 8'
    }

type_of_media_interface = {
    '00': 'Undefined',
    '01': 'nm_850_media_interface',
    '02': 'sm_media_interface',
    '03': 'passive_copper_media_interface',
    '04': 'active_cable_media_interface',
    '05': 'base_t_media_interface',
    }

host_electrical_interface = {
    '00': 'Undefined',
    '01': '1000BASE -CX(Clause 39)',
    '02': 'XAUI(Clause 47)',
    '03': 'XFI (SFF INF-8071i)',
    '04': 'SFI (SFF-8431)',
    '05': '25GAUI C2M (Annex 109B)',
    '06': 'XLAUI C2M (Annex 83B)',
    '07': 'XLPPI (Annex 86A)',
    '08': 'LAUI-2 C2M (Annex 135C)',
    '09': '50GAUI-2 C2M (Annex 135E)',
    '0a': '50GAUI-1 C2M (Annex 135G)',
    '0b': 'CAUI-4 C2M (Annex 83E)',
    '41': 'CAUI-4 C2M (Annex 83E) without FEC',
    '42': 'CAUI-4 C2M (Annex 83E) with RS(528,514) FEC',
    '0c': '100GAUI-4 C2M (Annex 135E)',
    '0d': '100GAUI-2 C2M (Annex 135G)',
    '0e': '200GAUI-8 C2M (Annex 120C)',
    '0f': '200GAUI-4 C2M (Annex 120E)',
    '10': '400GAUI-16 C2M (Annex 120C)',
    '11': '400GAUI-8 C2M (Annex 120E)',
    '13': '10GBASE-CX4 (Clause 54)',
    '14': '25GBASE-CR CA-L (Clause 110)',
    '15': '25GBASE-CR CA-S (Clause 110)',
    '16': '25GBASE-CR CA-N (Clause 110)',
    '17': '40GBASE-CR4 (Clause 85)',
    '43': '50GBASE-CR2 with RS (Clause 91) FEC',
    '44': '50GBASE-CR2 with BASE-R (Clause 74 Fire code) FEC',
    '45': '50GBASE-CR2 with no FEC',
    '18': '50GBASE-CR (Clause 126)',
    '19': '100GBASE-CR10 (Clause 85)',
    '1a': '100GBASE-CR4 (Clause 92)',
    '1b': '100GBASE-CR2 (Clause 136)',
    '1c': '200GBASE-CR4 (Clause 136)',
    '1d': '400G CR8',
    '1e': '1000BASE-T (Clause 40)',
    '1f': '2.5GBASE-T (Clause 126)',
    '20': '5GBASE-T (Clause 126)',
    '21': '10GBASE-T (Clause 55)',
    '22': '25GBASE-T (Clause 113)',
    '23': '40GBASE-T (Clause 113)',
    '24': '50GBASE-T (Placeholder)',
    '25': '8GFC (FC-PI-4)',
    '26': '10GFC (10GFC)',
    '27': '16GFC (FC-PI-5)',
    '28': '32GFC (FC-PI-6)',
    '29': '64GFC (FC-PI-7)',
    '2a': '128GFC (FC-PI-6P)',
    '2b': '256GFC (FC-PI-7P)',
    '2c': 'IB SDR (Arch.Spec.Vol.2)',
    '2d': 'IB DDR (Arch.Spec.Vol.2)',
    '2e': 'IB QDR (Arch.Spec.Vol.2)',
    '2f': 'IB FDR (Arch.Spec.Vol.2)',
    '30': 'IB EDR (Arch.Spec.Vol.2)',
    '31': 'IB HDR (Arch.Spec.Vol.2)',
    '32': 'IB NDR',
    '33': 'E.96 (CPRI Specification V7.0)',
    '34': 'E.99 (CPRI Specification V7.0)',
    '35': 'E.119 (CPRI Specification V7.0)',
    '36': 'E.238 (CPRI Specification V7.0)',
    '37': 'OTL3.4 (ITU-T G.709/Y.1331 G.Sup58)',
    '38': 'OTL4.10 (ITU-T G.709/Y.1331 G.Sup58)',
    '39': 'OTL4.4 (ITU-T G.709/Y.1331 G.Sup58)',
    '3a': 'OTLC.4 (ITU-T G.709.1/Y.1331 G.Sup58)',
    '3b': 'FOIC1.4 (ITU-T G.709.1/Y.1331 G.Sup58)',
    '3c': 'FOIC1.2 (ITU-T G.709.1/Y.1331 G.Sup58)',
    '3d': 'FOIC2.8 (ITU-T G.709.1/Y.1331 G.Sup58)',
    '3e': 'FOIC2.4 (ITU-T G.709.1/Y.1331 G.Sup58)',
    '3f': 'FOIC4.16 (ITU-T G.709.1 G.Sup58)',
    '40': 'FOIC4.8 (ITU-T G.709.1 G.Sup58)', 
    }

nm_850_media_interface = {
    '00': 'Undefined',
    '01': '10GBASE-SW (Clause 52)',
    '02': '10GBASE-SR (Clause 52)',
    '03': '25GBASE-SR (Clause 112)',
    '04': '40GBASE-SR4 (Clause 86)',
    '05': '40GE SWDM4 MSA Spec',
    '06': '40GE BiDi',
    '07': '50GBASE-SR (Clause 138)',
    '08': '100GBASE-SR10 (Clause 86)',
    '09': '100GBASE-SR4 (Clause 95)',
    '0a': '100GE SWDM4 MSA Spec',
    '0b': '100GE BiDi',
    '0c': '100GBASE-SR2 (Clause 138)',
    '0d': '100G-SR (Placeholder)',
    '0e': '200GBASE-SR4 (Clause 138)',
    '0f': '400GBASE-SR16 (Clause 123)',
    '10': '400GBASE-SR8 (Clause 138)',
    '11': '400G-SR4 (Placeholder)',
    '12': '800G-SR8 (Placeholder)',
    '1a': '400GBASE-SR4.2 (Clause 150) (400GE BiDi)',
    '13': '8GFC-MM (FC-PI-4)',
    '14': '10GFC-MM (10GFC)',
    '15': '16GFC-MM (FC-PI-5)',
    '16': '32GFC-MM (FC-PI-6)',
    '17': '64GFC-MM (FC-PI 7)',
    '18': '128GFC-MM4 (FC-PI-6P)',
    '19': '256GFC-MM4 (FC-PI-7P)',
    }

sm_media_interface = {
    '00': 'Undefined',
    '01': '10GBASE-LW (Cl 52)',
    '02': '10GBASE-EW (Cl 52)',
    '03': '10G-ZW',
    '04': '10GBASE-LR (Cl 52)',
    '05': '10GBASE-ER (Cl 52)',
    '06': '10G-ZR',
    '07': '25GBASE-LR (Cl 114)',
    '08': '25GBASE-ER (Cl 114)',
    '09': '40GBASE-LR4 (Cl 87)',
    '0a': '40GBASE-FR (Cl 89)',
    '0b': '50GBASE-FR (Cl 139)',
    '0c': '50GBASE-LR (Cl 139)',
    '40': '50GBASE-ER (Cl 139)',
    '0d': '100GBASE-LR4 (Cl 88)',
    '0e': '100GBASE-ER4 (Cl 88)',
    '0f': '100G PSM4 MSA Spec',
    '34': '100G CWDM4-OCP',
    '10': '100G CWDM4 MSA Spec',
    '11': '100G 4WDM-10 MSA Spec',
    '12': '100G 4WDM-20 MSA Spec',
    '13': '100G 4WDM-40 MSA Spec',
    '14': '100GBASE-DR (Cl 140)',
    '15': '100G-FR/100GBASE-FR1 (Cl 140)',
    '16': '100G-LR/100GBASE-LR1 (Cl 140)',
    '17': '200GBASE-DR4 (Cl 121)',
    '18': '200GBASE-FR4 (Cl 122)',
    '19': '200GBASE-LR4 (Cl 122)',
    '41': '200GBASE-ER4 (Cl 122)',
    '1a': '400GBASE-FR8 (Cl 122)',
    '1b': '400GBASE-LR8 (Cl 122)',
    '42': '400GBASE-ER8 (Cl 122)',
    '1c': '400GBASE-DR4 (Cl 124)',
    '1d': '400G-FR4/400GBASE-FR4 (Cl 151)',
    '43': '400GBASE-LR4-6 (Cl 151)',
    '1e': '400G-LR4-10',
    '1f': '8GFC-SM (FC-PI-4)',
    '20': '10GFC-SM (10GFC)',
    '21': '16GFC-SM (FC-PI-5)',
    '22': '32GFC-SM (FC-PI-6)',
    '23': '64GFC-SM (FC-PI-7)',
    '24': '128GFC-PSM4 (FC-PI-6P)',
    '25': '256GFC-PSM4 (FC-PI-7P)',
    '26': '128GFC-CWDM4 (FC-PI-6P)',
    '27': '256GFC-CWDM4 (FC-PI-7P)',
    '2c': '4I1-9D1F (G.959.1)',
    '2d': '4L1-9C1F (G.959.1)',
    '2e': '4L1-9D1F (G.959.1)',
    '2f': 'C4S1-9D1F (G.695)',
    '30': 'C4S1-4D1F (G.695)',
    '31': '4I1-4D1F (G.959.1)',
    '32': '8R1-4D1F (G.959.1)',
    '33': '8I1-4D1F (G.959.1)',
    '38': '10G-SR',
    '39': '10G-LR',
    '3a': '25G-SR',
    '3b': '25G-LR',
    '3c': '10G-LR-BiDi',
    '3d': '25G-LR-BiDi',
    '3e': '400ZR, DWDM, amplified',
    '3f': '400ZR, Single Wavelength, Unamplified',
    }

passive_copper_media_interface = {
    '00': 'Undefined',
    '01': 'Copper cable',
    '02': 'Passive Loopback module',
    }

active_cable_media_interface = {
    '00': 'Undefined',
    '01': 'Active Cable assembly with BER < 10^-12',
    '02': 'Active Cable assembly with BER < 5x10^-5',
    '03': 'Active Cable assembly with BER < 2.6x10^-4',
    '04': 'Active Cable assembly with BER < 10^-6',
    'bf': 'Active Loopback module',
    }

base_t_media_interface = {
    '00': 'Undefined',
    '01': '1000BASE-T (Clause 40)',
    '02': '2.5GBASE-T (Clause 126)',
    '03': '5GBASE-T (Clause 126)',
    '04': '10GBASE-T (Clause 55)',
    }

ext_specification_compliance = {
    '00': 'Unspecified',
    '01': '100G AOC (Active Optical Cable) or 25GAUI C2M AOC',
    '02': '100GBASE-SR4 or 25GBASE-SR',
    '03': '100GBASE-LR4 or 25GBASE-LR',
    '04': '100GBASE-ER4 or 25GBASE-ER',
    '05': '100GBASE-SR10',
    '06': '100G CWDM4',
    '07': '100G PSM4 Parallel SMF',
    '08': '100G ACC (Active Copper Cable) or 25GAUI C2M ACC',
    '09': 'Obsolete (assigned before 100G CWDM4 MSA required FEC)',
    '0b': '100GBASE-CR4, 25GBASE-CR CA-25G-L or 50GBASE-CR2 with RS',
    '0c': '25GBASE-CR CA-25G-S or 50GBASE-CR2 with BASE-R',
    '0d': '25GBASE-CR CA-25G-N or 50GBASE-CR2 with no FEC',
    '10': '40GBASE-ER4',
    '11': '4 x 10GBASE-SR',
    '12': '40G PSM4 Parallel SMF',
    '13': 'G959.1 profile P1I1-2D1 (10709 MBd, 2km, 1310 nm SM)',
    '14': 'G959.1 profile P1S1-2D2 (10709 MBd, 40km, 1550 nm SM)',
    '15': 'G959.1 profile P1L1-2D2 (10709 MBd, 80km, 1550 nm SM)',
    '16': '10GBASE-T with SFI electrical interface',
    '17': '100G CLR4',
    '18': '100G AOC or 25GAUI C2M AOC',
    '19': '100G ACC or 25GAUI C2M ACC',
    '1a': '100GE-DWDM2',
    '1b': '100G 1550nm WDM',
    '1c': '10GBASE-T Short Reach',
    '1d': '5GBASE-T',
    '1e': '2.5GBASE-T',
    '1f': '40G SWDM4',
    '20': '100G SWDM4',
    '21': '100G PAM4 BiDi',
    '22': '4WDM-10 MSA',
    '23': '4WDM-20 MSA',
    '24': '4WDM-40 MSA',
    '25': '100GBASE-DR',
    '26': '100G-FR or 100GBASE-FR1',
    '27': '100G-LR or 100GBASE-LR1',
    '30': 'Active Copper Cable with 50GAUI, 100GAUI-2 or 200GAUI-4 C2M. Providing a worst BER of 10-6 or below',
    '31': 'Active Optical Cable with 50GAUI, 100GAUI-2 or 200GAUI-4 C2M. Providing a worst BER of 10-6 or below',
    '32': 'Active Copper Cable with 50GAUI, 100GAUI-2 or 200GAUI-4 C2M. Providing a worst BER of 2.6x10-4 for ACC, 10-5 for AUI, or below',
    '33': 'Active Optical Cable with 50GAUI, 100GAUI-2 or 200GAUI-4 C2M. Providing a worst BER of 2.6x10-4 for AOC, 10-5 for AUI, or below',
    '40': '50GBASE-CR, 100GBASE-CR2, or 200GBASE-CR4',
    '41': '50GBASE-SR, 100GBASE-SR2, or 200GBASE-SR4',
    '42': '50GBASE-FR or 200GBASE-DR4',
    '43': '200GBASE-FR4',
    '44': '200G 1550 nm PSM4',
    '45': '50GBASE-LR',
    '46': '200GBASE-LR4',
    '50': '64GFC EA',
    '51': '64GFC SW',
    '52': '64GFC LW',
    '53': '128GFC EA',
    '54': '128GFC SW',
    '55': '128GFC LW'
}

ext_specification_compliance_sfp = {
    '00': 'Unspecified',
    '01': '25GAUI C2M AOC',
    '02': '25GBASE-SR',
    '03': '25GBASE-LR',
    '04': '25GBASE-ER',
    '08': '25GAUI C2M ACC',
    '0b': '25GBASE-CR CA-25G-L',
    '0c': '25GBASE-CR CA-25G-S',
    '0d': '25GBASE-CR CA-25G-N',
    '16': '10GBASE-T with SFI electrical interface',
    '18': '25GAUI C2M AOC',
    '19': '25GAUI C2M ACC',
    '1c': '10GBASE-T Short Reach',
    '1d': '5GBASE-T',
    '1e': '2.5GBASE-T',
    '30': '50GAUI ACC. BER of 10-6 or below',
    '31': '50GAUI AOC. BER of 10-6 or below',
    '32': '50GAUI ACC. BER of 2.6x10-4 or below',
    '33': '50GAUI AOC. BER of 2.6x10-4 or below',
    '40': '50GBASE-CR',
    '41': '50GBASE-SR',
    '42': '50GBASE-FR',
    '45': '50GBASE-LR',
}

ext_specification_compliance_qsfp = {
    '00': 'Unspecified',
    '01': '100G AOC (Active Optical Cable)',
    '02': '100GBASE-SR4',
    '03': '100GBASE-LR4',
    '04': '100GBASE-ER4',
    '05': '100GBASE-SR10',
    '06': '100G CWDM4',
    '07': '100G PSM4 Parallel SMF',
    '08': '100G ACC (Active Copper Cable)',
    '09': 'Obsolete (assigned before 100G CWDM4 MSA required FEC)',
    '0b': '100GBASE-CR4',
    '10': '40GBASE-ER4',
    '11': '4 x 10GBASE-SR',
    '12': '40G PSM4 Parallel SMF',
    '17': '100G CLR4',
    '18': '100G AOC',
    '19': '100G ACC',
    '1f': '40G SWDM4',
    '20': '100G SWDM4',
    '21': '100G PAM4 BiDi',
    '25': '100GBASE-DR',
    '26': '100GBASE-FR',
    '30': '200GAUI-4 C2M ACC. BER of 10-6 or below',
    '31': '200GAUI-4 C2M AOC. BER of 10-6 or below',
    '32': '200GAUI-4 C2M ACC. BER of 2.6x10-4 or below',
    '33': '200GAUI-4 C2M AOC. BER of 2.6x10-4 or below',
    '40': '200GBASE-CR4',
    '41': '200GBASE-SR4',
    '46': '200GBASE-LR4',
}
