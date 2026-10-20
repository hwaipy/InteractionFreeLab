# coding: utf-8
from datetime import datetime
from os import stat
from .register import _REGISTER_MAP
from .utils import format_hex_data, int_to_bytes, int_to_ip


class AWGStatus:
    """Class for collecting AWG working status from all modules.
    """

    def __init__(self, awg):
        self.awg = awg
        self.status = None
        self.update_time = None

    def get_status(self, update=False):
        if not update and self.status is not None:
            return self.status
        udp_status = self.get_udp_status()
        feedback_status = self.get_feedback_status()
        trig_status = self.get_trig_status()
        awg_status = self.get_awg_status()
        cpu_status = self.get_cpu_status()
        # TODO: collect status from rest modules

        self.update_time = datetime.now()
        self.status = dict(
            name=self.awg.name, udp=udp_status, feedback=feedback_status,
            trig=trig_status, awg=awg_status, cpu=cpu_status,
            update_time=str(self.update_time))
        return self.status

    def get_module_registers(self, module_name):
        awg = self.awg
        packet = awg.packet()
        module_name = module_name.upper()
        reg_module = _REGISTER_MAP.module_map[module_name]
        reg_names = []
        for reg in reg_module:
            reg_name = reg['name']
            full_name = f'{module_name}.{reg_name}'
            packet(full_name)
            reg_names.append(reg_name)
        result = packet.send()
        register = {}
        for name, item in zip(reg_names, result):
            register[name] = item['data']
        return register

    def get_udp_status(self):
        register = self.get_module_registers('UDP')

        fix_date = register['FIX_DATE']

        reg_mac_h = register['LOCAL_MAC_H']
        reg_mac_l = register['LOCAL_MAC_L']
        mac_h = int_to_bytes(reg_mac_h)[2:]
        mac_l = int_to_bytes(reg_mac_l)
        mac = mac_h + mac_l
        mac_hex = format_hex_data(mac)
        local_mac = mac_hex.replace(' ', '-')

        def reg_to_ip(name):
            return int_to_ip(register[name])

        local_ip = reg_to_ip('LOCAL_IP')
        gateway_ip = reg_to_ip('GATEWAY_IP')
        subnet_mask = reg_to_ip('SUBNET_MASK')
        local_port = register['LOCAL_PORT']
        status = dict(
            fix_date=fix_date, local_mac=local_mac,
            local_ip=local_ip, gateway_ip=gateway_ip,
            subnet_mask=subnet_mask, local_port=local_port)
        return status

    def get_feedback_status(self):
        register = self.get_module_registers('FEEDBACK')

        fix_date = register['FIX_DATE']
        status = dict(
            fix_date=fix_date)
        return status

    def get_trig_status(self):
        register = self.get_module_registers('TRIG')

        fix_date = register['FIX_DATE']
        status = dict(
            fix_date=fix_date)
        return status

    def get_awg_status(self):
        register = self.get_module_registers('AWG')

        fix_date = register['FIX_DATE']
        status = dict(
            fix_date=fix_date)
        return status

    def get_cpu_status(self):
        register = self.get_module_registers('CPU')

        fix_date = register['FIX_DATE']
        status = dict(
            fix_date=fix_date)
        return status
