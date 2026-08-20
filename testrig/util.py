# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

from .distro.fedora import FedoraDistro
from .distro.ubuntu import UbuntuDistro


def get_distro(no_root=False):
    os_release_path = "/etc/os-release"
    os_id = None
    os_versionid = None
    os_id_like = None

    with open(os_release_path, "r") as os_release_file:
        for line in os_release_file:
            if line.startswith("ID="):
                os_id = line.split("=")[1].strip().strip('"')
            if line.startswith("VERSION_ID="):
                os_versionid = line.split("=")[1].strip().strip('"')
            # ID_LIKE identifies the broader distro family (e.g. "debian" for ubuntu)
            if line.startswith("ID_LIKE="):
                os_id_like = line.split("=")[1].strip().strip('"')

    distro_info = {"id": os_id, "version": os_versionid, "id_like": os_id_like}

    if distro_info["id"] == "ubuntu":
        return UbuntuDistro(distro_info, no_root=no_root)
    elif distro_info["id"] == "fedora":
        return FedoraDistro(distro_info, no_root=no_root)
    else:
        raise Exception("Unsupported distro {}".format(distro_info["id"]))
