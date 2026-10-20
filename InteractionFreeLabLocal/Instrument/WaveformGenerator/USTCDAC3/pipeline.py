from .error import InstructionParaError, InstructionNameError, InstructionParaNumError, RegAmountNotEqualError
from .utils import format_hex_data


from struct import pack
import numpy as np

_INSTRUCTION_TABLE = [
    dict(
        name='NULL',
        head=0x00,
        paras=()
    ),
    dict(
        name='INST_RST',
        head=0x01,
        paras=()
    ),
    dict(
        name='PARAM_CIRCUIT',
        head=0x02,
        paras=('REG_ADDR', 'REG_DATA')
    ),
    dict(
        name='PARAM_WAVE',
        head=0x03,
        paras=('GATE_TYPE', 'WAVE_ID')
    ),
    dict(
        name='GEN_CARRY',
        head=0x04,
        paras=('WAVE_ID', 'LEN', 'FREQ', 'PHASE')
    ),
    dict(
        name='GEN_COS',
        head=0x05,
        paras=('WAVE_ID', 'LEN', 'AMP')
    ),
    dict(
        name='GEN_RECT',
        head=0x06,
        paras=('WAVE_ID', 'LEN', 'AMP')
    ),
    dict(
        name='GEN_GAUS',
        head=0x07,
        paras=('WAVE_ID', 'LEN', 'AMP', 'R_SIGMA',
               'START_TIME', 'STOP_TIME')
    ),
    dict(
        name='GEN_FLAT',
        head=0x08,
        paras=('WAVE_ID', 'LEN', 'AMP', 'EDGE')
    ),
    dict(
        name='GEN_RRING',
        head=0x09,
        paras=('WAVE_ID', 'LEN', 'AMP', 'R_SIGMA',
               'START_TIME', 'STOP_TIME', 'LEN',
               'AMP', 'EDGE')
    ),
    dict(
        name='GEN_ACZ',
        head=0x0A,
        paras=('WAVE_ID', 'LEN', 'LAMDA_2', 'LAMDA_3',
               'THETA_I', 'THETA_F')
    ),
    dict(
        name='GATE_XY',
        head=0x20,
        paras=('TIME', 'PHASE', 'FREQ', 'DRAG')
    ),
    dict(
        name='GATE_XY2',
        head=0x21,
        paras=('TIME', 'PHASE', 'FREQ', 'DRAG')
    ),
    dict(
        name='GATE_X12',
        head=0x22,
        paras=('TIME', 'PHASE', 'FREQ', 'DRAG')
    ),
    dict(
        name='GATE_XARB',
        head=0x23,
        paras=('TIME', 'PHASE', 'FREQ', 'DRAG', 'AMP')
    ),
    dict(
        name='GATE_Z',
        head=0x24,
        paras=('TIME', 'PHASE')
    ),
    dict(
        name='GATE_ZARB',
        head=0x25,
        paras=('TIME', 'PHASE', 'AMP', 'LEN')
    ),
    dict(
        name='GATE_LDRIVE',
        head=0x26,
        paras=('TIME', 'PHASE', 'LEN')
    ),
    dict(
        name='GATE_ARB',
        head=0x27,
        paras=('TIME', 'WAVE_ID', 'PHASE', 'FREQ', 'DRAG')
    ),
    dict(
        name='GATE_M',
        head=0x28,
        paras=('LENGTH', 'TIME', 'DELAY', 'WAVE_ID_LIST', 'FREQ_LIST')
    ),
    dict(
        name='START_CIRCUIT',
        head=0x55,
        paras=('EXP_ID', 'CIRCUIT_NUM', 'LOOP_COUNT')
    ),
    dict(
        name='OP_BIAS',
        head=0x56,
        paras=('AMP', )
    ),
    dict(
        name='INSTR_FEEDBACK',
        head=0x57,
        paras=()
    ),
    dict(
        name='STOP_CIRCUIT',
        head=0xAA,
        paras=()
    ),
    dict(
        name='DIRECT_ENVO',
        head=0xAB,
        paras=('WAVE_ID', 'ENVO_DATA')
    ),
    dict(
        name='DIRECT_WAVE',
        head=0xAC,
        paras=('WAVE_DATA', )
    ),
    dict(
        name='DIRECT_SEQ',
        head=0xAD,
        paras=('SEQ_DATA', )
    ),
    dict(
        name='DIRECT_TAIL',
        head=0xAE,
        paras=('TAIL_DATA', )
    ),
    dict(
        name='CIRCUIT_CORECT',
        head=0xAF,
        paras=()
    )
]

_INSTRUCTION_DATA_FORMAT = [
    dict(
        name='EXP_ID',
        width=4,
        para_a=1,
        para_b=0
    ),
    dict(
        name='CIRCUIT_NUM',
        width=4,
        para_a=1,
        para_b=0
    ),
    dict(
        name='WAVE_ID',
        width=2,
        para_a=1,
        para_b=0
    ),
    dict(
        name='LOOP_COUNT',
        width=4,
        para_a=1,
        para_b=0
    ),
    dict(
        name='TIME',
        width=4,
        para_a=2*1e9,
        para_b=0
    ),
    dict(
        name='REG_AMOUNT',
        width=4,
        para_a=1,
        para_b=0
    ),
    dict(
        name='REG_ADDR',
        width=4,
        para_a=1,
        para_b=0
    ),
    dict(
        name='REG_DATA',
        width=4,
        para_a=1,
        para_b=0
    ),
    dict(
        name='START_TIME',
        width=4,
        para_a=2*1e9,
        para_b=0
    ),
    dict(
        name='STOP_TIME',
        width=4,
        para_a=2*1e9,
        para_b=0
    ),
    dict(
        name='LEN',
        width=4,
        para_a=2*1e9,
        para_b=0
    ),
    dict(
        name='FREQ',
        width=4,
        para_a=1,
        para_b=2**30
    ),
    dict(
        name='PHASE',
        width=2,
        para_a=1e4,
        para_b=0
    ),
    dict(
        name='AMP',
        width=2,
        para_a=1,
        para_b=32768
    ),
    dict(
        name='EDGE',
        width=2,
        para_a=100,
        para_b=0
    ),
    dict(
        name='LAMDA_2',
        width=1,
        para_a=100,
        para_b=50
    ),
    dict(
        name='LAMDA_3',
        width=1,
        para_a=100,
        para_b=0
    ),
    dict(
        name='THETA_I',
        width=1,
        para_a=100,
        para_b=0
    ),
    dict(
        name='THETA_F',
        width=1,
        para_a=100,
        para_b=0
    ),
    dict(
        name='DRAG',
        width=4,
        para_a=1000,
        para_b=10000
    ),
    dict(
        name='LENGTH',
        width=4,
        para_a=1,
        para_b=0
    )
]


class PipelineInstruction:

    def __init__(self):
        """Implementation of Quantum Circuit Pipleline Instruction.
        """
        self.init_instruction_map()
        self.init_format_map()

    def init_instruction_map(self):
        """Init instruction map.
        """
        inst_name_map = {}
        inst_head_map = {}
        for instruction in _INSTRUCTION_TABLE:
            inst_name = instruction['name']
            inst_head = instruction['head']
            inst_paras = instruction['paras']
            name_info = dict(
                head=inst_head,
                paras=inst_paras
            )
            head_info = dict(
                name=inst_name,
                paras=inst_paras
            )
            inst_name_map[f'{inst_name}'] = name_info
            inst_head_map[f'{inst_head}'] = head_info
        self.inst_name_map = inst_name_map
        self.inst_head_map = inst_head_map

    def init_format_map(self):
        """Init instruction parameters format map.
        """
        format_name_map = {}
        for format in _INSTRUCTION_DATA_FORMAT:
            data_name = format['name']
            format_info = dict(
                width=format['width'],
                para_a=format['para_a'],
                para_b=format['para_b']
            )
            format_name_map[f'{data_name}'] = format_info
        self.format_name_map = format_name_map

    def get_instruction_head_by_name(self, name):
        """Get instruction head identification by instruction name.

        Args:
            name (str): Instruction name.

        Raises:
            InstructionNameError: Input the wrong instruction name.

        Returns:
            int: Head identification of instruction.
        """
        if name not in self.inst_name_map.keys():
            raise InstructionNameError(name)
        head = self.inst_name_map[name]['head']
        return head

    def get_instruction_paras_by_name(self, name):
        """Get instruction parameters by instruction name.

        Args:
            name (str): Instruction name.

        Raises:
            InstructionNameError: Input the wrong instruction name.

        Returns:
            turple: Parameters of instruction.
        """
        if name not in self.inst_name_map.keys():
            raise InstructionNameError(name)
        paras = self.inst_name_map[name]['paras']
        return paras

    def get_instruction_name_by_head(self, head):
        """Get instruction name by instruction head.

        Args:
            head (int): Instruction head identification.

        Returns:
            str: Name of instruction.
        """
        name = self.inst_head_map[head]['name']
        return name

    def get_instruction_paras_by_head(self, head):
        """Get instruction parameters by instruction head.

        Args:
            head (int): Instruction head identification.

        Returns:
            turple: Parameters of instruction.
        """
        paras = self.inst_head_map[head]['paras']
        return paras

    def get_para_format_by_name(self, name):
        """Get instruction parameter data format by
        parameter name.

        Args:
            name (str): Name of parameter.

        Returns:
            turple: Format of parameter.
        """
        para_format = self.format_name_map[name]
        return para_format['width'], para_format['para_a'], para_format['para_b']

    def para_scale(self, value, para_a, para_b):
        """Parameter scaling function.

        Note:
            Scaling function: y = ax + b.

        Args:
            value (float): Value of parameter.
            para_a (float): Parameter a of scaling function.
            para_b (flaot): Parameter b of scaling function.

        Returns:
            int: Parameter value after scaling.
        """
        return int(para_a * value + para_b)

    def pack_instructions(self, instructions):
        """Pack instruction on the basis of the definition of
            pipeline instruction format.


        Raises:
            InstructionNameError: Input the wrong instruction name.
            InstructionParaNumError: Input the wrong number of instruction parameters.
            InstructionParaError: Input the wrong parameter of instruction.

        Returns:
            bytes: Bytes of instruction.
        """
        format_map = {
            1: '<B',
            2: '<H',
            4: '<I'
        }
        contents = b''
        for inst in instructions:
            head_bytes = b''
            paras_bytes = b''
            inst_name = inst['inst_name'].upper()
            head = self.get_instruction_head_by_name(inst_name)
            head_bytes = pack('B', head)
            if inst_name not in self.inst_name_map:
                raise InstructionNameError(inst_name)
            parameter = inst['parameter']
            instruction_paras = self.get_instruction_paras_by_name(inst_name)
            if len(parameter) != len(instruction_paras):
                raise InstructionParaNumError(inst_name, len(instruction_paras), len(parameter))
            if inst_name.upper() in ('PARAM_CIRCUIT'):
                addr_list = parameter['reg_addr_list']
                data_list = parameter['reg_data_list']
                if len(addr_list) != len(data_list):
                    raise RegAmountNotEqualError(len(addr_list), len(data_list))
                amount = len(addr_list)
                amount_width, _, _ = self.get_para_format_by_name('REG_AMOUNT')
                addr_width, _, _ = self.get_para_format_by_name('REG_ADDR')
                data_width, _, _ = self.get_para_format_by_name('REG_DATA')
                length = addr_width * amount + data_width * amount + amount_width
                length_bytes = pack('<I', length)
                amount_bytes = pack('<I', amount)
                reg_bytes = b''
                for addr, data in zip(addr_list, data_list):
                    addr_bytes = pack('<I', addr)
                    data_bytes = pack('<I', data)
                    reg_bytes += addr_bytes + data_bytes
                paras_bytes += length_bytes + amount_bytes + reg_bytes
                content = b''.join([head_bytes, paras_bytes])
            else:
                for para in parameter:
                    value = parameter[para]
                    para_upper = para.upper()
                    if para_upper not in instruction_paras:
                        raise InstructionParaError(inst_name, para_upper)
                    if para_upper in ('ENVELOPE_DATA', 'WAVE_DATA', 'SEQ_DATA', 'TAIL_DATA'):
                        data = parameter[para]
                        data_u16 = np.array(data, dtype='<u2')
                        data_bytes = data_u16.tobytes()
                        length = len(data_bytes)
                        length_bytes = pack('<I', length)
                        paras_bytes += length_bytes + data_bytes
                    else:
                        width, para_a, para_b = self.get_para_format_by_name(para_upper)
                        para_value = int(self.para_scale(value, para_a, para_b))
                        pack_type = format_map[width]
                        paras_bytes += pack(pack_type, para_value)
                content = b''.join([head_bytes, paras_bytes])
            contents += content
        # display_data = format_hex_data(contents)
        # print(display_data)
        return contents
