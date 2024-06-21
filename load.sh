#!/bin/bash
cp ~admin/qsfp_cmis/sonic_sfp/* /host/image-4.2.0-Enterprise_Standard/docker/overlay2/00bcc3e1edaef67fdcf61d88cab292a7b21da27b109b600bfd3784fbe10c73f1/diff/usr/local/lib/python3.7/dist-packages/sonic_sfp/
cp ~admin/qsfp_cmis/sonic_sfp/* /host/image-4.2.0-Enterprise_Standard/docker/overlay2/00bcc3e1edaef67fdcf61d88cab292a7b21da27b109b600bfd3784fbe10c73f1/diff/usr/local/lib/python3.7/dist-packages/sonic_platform_base/sonic_sfp/
cp ~admin/qsfp_cmis/sonic_sfp/* /host/image-4.2.0-Enterprise_Standard/docker/overlay2/f963dfe50b3b3f8a03991b7ee9b6e0c37234ba8eb1422b4c63144ee4a3e07728/diff/usr/local/lib/python2.7/dist-packages/sonic_sfp/
cp ~admin/qsfp_cmis/sonic_sfp/* /host/image-4.2.0-Enterprise_Standard/docker/overlay2/f963dfe50b3b3f8a03991b7ee9b6e0c37234ba8eb1422b4c63144ee4a3e07728/diff/usr/local/lib/python2.7/dist-packages/sonic_platform_base/sonic_sfp/
cp ~admin/qsfp_cmis/sonic_sfp/* /host/image-4.2.0-Enterprise_Standard/docker/overlay2/f963dfe50b3b3f8a03991b7ee9b6e0c37234ba8eb1422b4c63144ee4a3e07728/diff/usr/local/lib/python3.7/dist-packages/sonic_sfp/
cp ~admin/qsfp_cmis/sonic_sfp/* /host/image-4.2.0-Enterprise_Standard/docker/overlay2/f963dfe50b3b3f8a03991b7ee9b6e0c37234ba8eb1422b4c63144ee4a3e07728/diff/usr/local/lib/python3.7/dist-packages/sonic_platform_base/sonic_sfp/
cp ~admin/qsfp_cmis/sonic_sfp/* /host/image-4.2.0-Enterprise_Standard/rw/usr/local/lib/python2.7/dist-packages/sonic_sfp/
cp ~admin/qsfp_cmis/sonic_sfp/* /host/image-4.2.0-Enterprise_Standard/rw/usr/local/lib/python2.7/dist-packages/sonic_platform_base/sonic_sfp/
cp ~admin/qsfp_cmis/sonic_sfp/* /host/image-4.2.0-Enterprise_Standard/rw/usr/local/lib/python3.7/dist-packages/sonic_sfp/
cp ~admin/qsfp_cmis/sonic_sfp/* /host/image-4.2.0-Enterprise_Standard/rw/usr/local/lib/python3.7/dist-packages/sonic_platform_base/sonic_sfp/
cp ~admin/qsfp_cmis/sonic_sfp/* /usr/local/lib/python2.7/dist-packages/sonic_platform_base/sonic_sfp/
cp ~admin/qsfp_cmis/sonic_sfp/* /usr/local/lib/python2.7/dist-packages/sonic_sfp/
cp ~admin/qsfp_cmis/sonic_sfp/* /usr/local/lib/python3.7/dist-packages/sonic_platform_base/sonic_sfp/
cp ~admin/qsfp_cmis/sonic_sfp/* /usr/local/lib/python3.7/dist-packages/sonic_sfp/

cp ~admin/qsfp_cmis/sonic_platform_base/* /host/image-4.2.0-Enterprise_Standard/docker/overlay2/00bcc3e1edaef67fdcf61d88cab292a7b21da27b109b600bfd3784fbe10c73f1/diff/usr/local/lib/python3.7/dist-packages/sonic_platform_base/
cp ~admin/qsfp_cmis/sonic_platform_base/* /host/image-4.2.0-Enterprise_Standard/docker/overlay2/f963dfe50b3b3f8a03991b7ee9b6e0c37234ba8eb1422b4c63144ee4a3e07728/diff/usr/local/lib/python2.7/dist-packages/sonic_platform_base/
cp ~admin/qsfp_cmis/sonic_platform_base/* /host/image-4.2.0-Enterprise_Standard/docker/overlay2/f963dfe50b3b3f8a03991b7ee9b6e0c37234ba8eb1422b4c63144ee4a3e07728/diff/usr/local/lib/python3.7/dist-packages/sonic_platform_base/
cp ~admin/qsfp_cmis/sonic_platform_base/* /host/image-4.2.0-Enterprise_Standard/rw/usr/local/lib/python2.7/dist-packages/sonic_platform_base/
cp ~admin/qsfp_cmis/sonic_platform_base/* /host/image-4.2.0-Enterprise_Standard/rw/usr/local/lib/python3.7/dist-packages/sonic_platform_base/

cp ~admin/qsfp_cmis/xcvrd.py /host/image-4.2.0-Enterprise_Standard/docker/overlay2/f963dfe50b3b3f8a03991b7ee9b6e0c37234ba8eb1422b4c63144ee4a3e07728/diff/usr/local/lib/python2.7/dist-packages/xcvrd/
cp ~admin/qsfp_cmis/xcvrd.py /host/image-4.2.0-Enterprise_Standard/docker/overlay2/f963dfe50b3b3f8a03991b7ee9b6e0c37234ba8eb1422b4c63144ee4a3e07728/diff/usr/local/lib/python3.7/dist-packages/xcvrd/
rm -f /host/image-4.2.0-Enterprise_Standard/docker/overlay2/f963dfe50b3b3f8a03991b7ee9b6e0c37234ba8eb1422b4c63144ee4a3e07728/diff/usr/local/lib/python2.7/dist-packages/xcvrd/*.pyc
rm -f /host/image-4.2.0-Enterprise_Standard/docker/overlay2/f963dfe50b3b3f8a03991b7ee9b6e0c37234ba8eb1422b4c63144ee4a3e07728/diff/usr/local/lib/python3.7/dist-packages/xcvrd/__pycache__/*

killall -9 xcvrd
