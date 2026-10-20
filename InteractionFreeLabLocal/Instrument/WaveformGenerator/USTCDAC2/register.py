# coding: utf-8
from .error import RegisterMapKeyError


_REGISTER_TABLE = [
    dict(
        name='UDP',
        base_addr=0x100000,
        registers=[
            (0x0000, 'IDNTITY', 'r'),
            (0x0004, 'FIX_DATE', 'r'),
            (0x0008, 'RESERVE', 'r'),
            (0x000C, 'TESTREG', 'rw'),
            (0x0010, 'ETH_ENABLE', 'r'),
            (0x0080, 'LOCAL_MAC_H', 'r'),
            (0x0084, 'LOCAL_MAC_L', 'r'),
            (0x0088, 'LOCAL_IP', 'r'),
            (0x008C, 'GATEWAY_IP', 'r'),
            (0x0090, 'SUBNET_MASK', 'r'),
            (0x0094, 'LOCAL_PORT', 'r'),
            (0x0200, 'STATUS', 'r')
        ]
    ),
    dict(
        name='DAC1',
        base_addr=0x11000,
        registers=[
            (0x0040, 'CH1_GAIN_HIGH', 'rw'),
            (0x0041, 'CH1_GAIN_LOW', 'rw'),
            (0x0044, 'CH2_GAIN_HIGH', 'rw'),
            (0x0045, 'CH2_GAIN_LOW', 'rw')
        ]
    ),
    dict(
        name='DAC2',
        base_addr=0x12000,
        registers=[
            (0x0040, 'CH3_GAIN_HIGH', 'rw'),
            (0x0041, 'CH3_GAIN_LOW', 'rw'),
            (0x0044, 'CH4_GAIN_HIGH', 'rw'),
            (0x0045, 'CH4_GAIN_LOW', 'rw')
        ]
    ),
    dict(
        name='FEEDBACK',
        base_addr=0x120000,
        registers=[
            (0x0000, 'IDNTITY', 'r'),
            (0x0004, 'FIX_DATE', 'r'),
            (0x0008, 'RESERVE', 'r'),
            (0x000C, 'TESTREG', 'rw'),
            (0x0080, 'DELAY_LOAD', 'rw'),
            (0x0084, 'DELAY_VALUE', 'rw'),
            (0x0088, 'QUBIT_INFO_MAP', 'rw'),
            (0x008C, 'SERDES_SYNC_ENABLE', 'rw'),
            (0x0090, 'SIGNAL_ERROR_CNT', 'r'),
            (0x0094, 'SIGNAL_CORRECT_CNT', 'r'),
            (0x0098, 'TOTAL_ERROR_CNT', 'r'),
            (0x009C, 'TOTAL_CORRECT_CNT', 'r'),
            (0x00A0, 'RECV_ERR_CNT', 'r'),
            (0x00A4, 'DECODE', 'r'),
        ]
    ),
    dict(
        name='TRIG',
        base_addr=0x130000,
        registers=[
            (0x0000, 'IDNTITY', 'r'),
            (0x0004, 'FIX_DATE', 'r'),
            (0x0008, 'RESERVE', 'r'),
            (0x000C, 'TESTREG', 'rw'),
            (0x0080, 'C_START_DAC', 'rw'),
            (0x0084, 'C_STOP_START_DAC', 'rw'),
            (0x0088, 'C_START_EXTERNAL', 'rw'),
            (0x008C, 'C_STOP_START_EXTERNAL', 'rw'),
            (0x0090, 'C_TRIG_INTERVAL_L1', 'rw'),
            (0x0094, 'C_TRIG_COUNT_L1', 'rw'),
            (0x0098, 'C_TRIG_INTERVAL_L2', 'rw'),
            (0x009C, 'C_TRIG_COUNT_L2', 'rw'),
            (0x00A0, 'C_STATUS_REG', 'r'),
            (0x00A4, 'C_TRIG_CNT', 'r'),
            (0x00A8, 'C_SOFT_TRIG_CNT', 'r'),
            (0x00AC, 'C_TRIG_AD_SOURCE_SEL', 'rw'),
            (0x00B0, 'C_TRIG_SEL', 'rw'),
            (0x00B4, 'C_ADP_COMPLETE_INT', 'rw'),
            (0x00B8, 'C_MULTI_BOARD_MODE', 'rw'),
            (0x00BC, 'C_TRIG_EN', 'rw'),
            (0x00C0, 'C_TRIG_COUNT_CLEAR', 'rw'),
            (0x00C4, 'C_CMD_ADPT', 'rw'),
        ]
    ),
    dict(
        name='AWG',
        base_addr=0x140000,
        registers=[
            (0x0000, 'IDNTITY', 'r'),
            (0x0004, 'FIX_DATE', 'r'),
            (0x0008, 'RESERVE', 'r'),
            (0x000C, 'TESTREG', 'rw'),
            (0x0020, 'CTRL_REG', 'rw'),
            (0x0030, 'CNFG_REG1', 'rw'),
            (0x0034, 'LOOP_CNT1', 'rw'),
            (0x0038, 'DEFAULT_CODE1', 'rw'),
            (0x0040, 'CNFG_REG2', 'rw'),
            (0x0044, 'LOOP_CNT2', 'rw'),
            (0x0048, 'DEFAULT_CODE2', 'rw'),
            (0x0050, 'CNFG_REG3', 'rw'),
            (0x0054, 'LOOP_CNT3', 'rw'),
            (0x0058, 'DEFAULT_CODE3', 'rw'),
            (0x0060, 'CNFG_REG4', 'rw'),
            (0x0064, 'LOOP_CNT4', 'rw'),
            (0x0068, 'DEFAULT_CODE4', 'rw'),
            (0x0070, 'TF_REG','rw'),
            (0x0080, 'STATUS1', 'r'),
            (0x0084, 'STATUS2', 'r'),
            (0x0088, 'STATUS3', 'r'),
            (0x008C, 'STATUS4', 'r'),

        ]
    ),
    dict(
        name='CPU',
        base_addr=0x9000,
        registers=[
            (0x0000, 'IDNTITY', 'r'),
            (0x0004, 'FIX_DATE', 'r'),
            (0x0008, 'RESERVE', 'r'),
            (0x000C, 'TESTREG', 'rw'),
            (0x0014, 'DDR_ADDR', 'rw'),
            (0x0018, 'DDR_LEN', 'rw'),
            (0x001C, 'OP_STATUS', 'r'),
            (0x0020, 'PERMISSION', 'rw'),
            (0x0028, 'FLASH_FUN', 'rw'),
            (0x002C, 'FLASH_ADDR', 'rw'),
            (0x0030, 'FLASH_LEN', 'rw'),
            (0x0038, 'FLASH_TYPE', 'r'),
            (0x003C, 'IP_ADDRESS', 'rw'),
            (0x0040, 'PORT', 'rw'),
            (0x0044, 'STATUS_EN', 'rw'),
            (0x0050, 'TDEST', 'rw'),
            (0x0054, 'REBOOT', 'rw'),
            (0x005C, 'INIT_HW_COUNTER', 'r'),
            (0x0060, 'GET_STATE_COUNTER', 'r')
        ]
    ),
    dict(
        name='PIPELINE',
        base_addr=0x9000,
        registers=[
            (0x0078, 'RESET', 'rw'),
            (0x007C, 'AVAIL_CKT_NUM', 'r'),
            (0x0080, 'AVAIL_START_NUN', 'r'),
            (0x0084, 'DL_CKT_NUM', 'rw'),
            (0x008C, 'SRCH_CKT_NUM_CH1', 'rw'),
            (0x0090, 'SRCH_CKT_NUM_CH2', 'rw'),
            (0x0094, 'SRCH_CKT_NUM_CH3', 'rw'),
            (0x0098, 'SRCH_CKT_NUM_CH4', 'rw'),
            (0x009C, 'CKT_ANALYSIS_RESULT_CH1_2', 'r'),
            (0x00A0, 'CKT_ANALYSIS_RESULT_CH3_4', 'r'),
            (0x00A4, 'EXEC_CKT_NUM_CH1', 'rw'),
            (0x00A8, 'EXEC_CKT_NUM_CH2', 'rw'),
            (0x00AC, 'EXEC_CKT_NUM_CH3', 'rw'),
            (0x00B0, 'EXEC_CKT_NUM_CH4', 'rw'),
            (0x00B4, 'ABANDON_ST', 'r'),
            (0x00B8, 'ABANDON_EXP_CH1', 'rw'),
            (0x00BC, 'ABANDON_EXP_CH2', 'rw'),
            (0x00C0, 'ABANDON_EXP_CH3', 'rw'),
            (0x00C4, 'ABANDON_EXP_CH4', 'rw')
        ]
    )
]


class RegisterMap:
    def __init__(self):
        self.init_map()

    def init_map(self):
        name_map = {}
        addr_map = {}
        module_map = {}
        permission_map = {}
        for module in _REGISTER_TABLE:
            module_name = module['name']
            base_addr = module['base_addr']
            registers = module['registers']
            items = []
            for addr, name, permission in registers:
                reg_item = dict(
                    base_addr=base_addr,
                    addr=addr,
                    name=name,
                    permission=permission)
                items.append(reg_item)
                name_map[f'{module_name}.{name}'] = reg_item
                if base_addr is not None:
                    addr_map[base_addr, addr] = reg_item
                    permission_map[base_addr, addr] = permission
                else:
                    addr_map[addr] = reg_item
                    permission_map[addr] = permission
            module_map[module_name] = items
        self.name_map = name_map
        self.addr_map = addr_map
        self.module_map = module_map
        self.permission_map = permission_map

    def get_addr_by_name(self, name):
        reg = self.name_map[name]
        return reg['base_addr'], reg['addr']

    def get_name_by_addr(self, *reg):
        idx = list(self.addr_map.keys()).index(reg)
        name = list(self.name_map.keys())[idx]
        return name

    def writable(self, *reg):
        if reg in self.permission_map:
            return 'w' in self.permission_map[reg]
        else:
            raise RegisterMapKeyError(reg)

    def readable(self, *reg):
        if reg in self.permission_map:
            return 'r' in self.permission_map[reg]
        else:
            raise RegisterMapKeyError(reg)


_REGISTER_MAP = RegisterMap()
