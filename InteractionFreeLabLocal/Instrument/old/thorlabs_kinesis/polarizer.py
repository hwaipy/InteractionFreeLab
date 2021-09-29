"Bindings for Thorlabs Polarizer DLL"
# flake8: noqa
from ctypes import (
    Structure,
    cdll,
    c_bool,
    c_short,
    c_int,
    c_uint,
    c_uint16,
    c_int16,
    c_int32,
    c_char,
    c_byte,
    c_long,
    c_float,
    c_double,
    c_ushort,
    POINTER,
    CFUNCTYPE,
)

from Instrument.lab.thorlabs_kinesis._utils import (
    c_word,
    c_dword,
    bind
)

lib = cdll.LoadLibrary("C:\Program Files\Thorlabs\Kinesis\Thorlabs.MotionControl.Polarizer.dll")


# enum FT_Status
FT_OK = c_short(0x00)
FT_InvalidHandle = c_short(0x01)
FT_DeviceNotFound = c_short(0x02)
FT_DeviceNotOpened = c_short(0x03)
FT_IOError = c_short(0x04)
FT_InsufficientResources = c_short(0x05)
FT_InvalidParameter = c_short(0x06)
FT_DeviceNotPresent = c_short(0x07)
FT_IncorrectDevice = c_short(0x08)
FT_Status = c_short

# enum MOT_MotorTypes
MOT_NotMotor = c_int(0)
MOT_DCMotor = c_int(1)
MOT_StepperMotor = c_int(2)
MOT_BrushlessMotor = c_int(3)
MOT_CustomMotor = c_int(100)
MOT_MotorTypes = c_int

# enum POL_Paddles
paddle1 = c_uint16(1)
paddle2 = c_uint16(2)
paddle3 = c_uint16(3)
POL_Paddles = c_uint16

# enum POL_PaddleBits
none = c_ushort(0x0)
PaddleBit1 = c_ushort(0x01)
PaddleBit2 = c_ushort(0x02)
PaddleBit4 = c_ushort(0x04)
AllPaddles = c_ushort(0x07)
POL_PaddleBits = c_ushort


class PolarizerParameters(Structure):
    _fields_ = [("Velocity",c_ushort),
                ("HomePosition", c_double),
                ("JogSize1", c_double),
                ("JogSize2", c_double),
                ("JogSize3", c_double)]

# enum MOT_TravelDirection
MOT_TravelDirectionDisabled = c_short(0x00)
MOT_Forwards                = c_short(0x01)
MOT_Reverse                 = c_short(0x02)
MOT_TravelDirection         = c_short

class TLI_DeviceInfo(Structure):
    _fields_ = [("typeID", c_dword),
                ("description", (65 * c_char)),
                ("serialNo", (9 * c_char)),
                ("PID", c_dword),
                ("isKnownType", c_bool),
                ("motorType", MOT_MotorTypes),
                ("isPiezoDevice", c_bool),
                ("isLaser", c_bool),
                ("isCustomType", c_bool),
                ("isRack", c_bool),
                ("maxPaddles", c_short)]

class TLI_HardwareInformation(Structure):
    _fields_ = [("serialNumber", c_dword),
                ("modelNumber", (8 * c_char)),
                ("type", c_word),
                ("firmwareVersion", c_dword),
                ("notes", (48 * c_char)),
                ("deviceDependantData", (12 * c_byte)),
                ("hardwareVersion", c_word),
                ("modificationState", c_word),
                ("numChannels", c_short)]

#enum MPC_IOModes
MPC_ToggleOnPositiveEdge = c_word(0x01)
MPC_SetPositionOnPositiveEdge = c_word(0x02)
MPC_OutputHighAtSetPosition = c_word(0x04)
MPC_OutputHighWhemMoving = c_word(0x08)
MPC_IOModes              = c_word

#enum MPC_SignalModes
MPC_InputButton = c_word(0x01)
MPC_InputLogic = c_word(0x02)
MPC_InputSwap = c_word(0x04)
MPC_OutputLevel = c_word(0x10)
MPC_OutputPulse = c_word(0x20)
MPC_OutputSwap  = c_word(0x40)
MPC_SignalModes = c_word


class MPC_IOSettings(Structure):
    _fields_ = [("transitTime", c_uint),
                ("ADCspeedValue", c_uint),
                ("digIO1OperMode", MPC_IOModes),
                ("digIO1SignalMode", MPC_SignalModes),
                ("digIO1PulseWidth", c_uint),
                ("digIO2OperMode", MPC_IOModes),
                ("digIO2SignalMode", MPC_SignalModes),
                ("digIO2PulseWidth", c_uint),
                ("reserved1", c_int),
                ("reserved2", c_uint)]

TLI_BuildDeviceList =  bind(lib, "TLI_BuildDeviceList", None, c_short)
TLI_GetDeviceListSize =  bind(lib, "TLI_GetDeviceListSize", None, c_short)
# TLI_GetDeviceList  <- TODO: Implement SAFEARRAY first. BENCHTOPSTEPPERMOTOR_API short __cdecl TLI_GetDeviceList(SAFEARRAY** stringsReceiver);
# TLI_GetDeviceListByType  <- TODO: Implement SAFEARRAY first. BENCHTOPSTEPPERMOTOR_API short __cdecl TLI_GetDeviceListByType(SAFEARRAY** stringsReceiver, int typeID);
# TLI_GetDeviceListByTypes  <- TODO: Implement SAFEARRAY first. BENCHTOPSTEPPERMOTOR_API short __cdecl TLI_GetDeviceListByTypes(SAFEARRAY** stringsReceiver, int * typeIDs, int length);
# 	POLARIZERDLL_API short __cdecl TLI_GetDeviceListExt(char *receiveBuffer, DWORD sizeOfBuffer);
#	POLARIZERDLL_API short __cdecl TLI_GetDeviceListByTypeExt(char *receiveBuffer, DWORD sizeOfBuffer, int typeID);
# 	POLARIZERDLL_API short __cdecl TLI_GetDeviceListByTypesExt(char *receiveBuffer, DWORD sizeOfBuffer, int * typeIDs, int length);
TLI_GetDeviceInfo = bind(lib, "TLI_GetDeviceInfo", [POINTER(c_char), POINTER(TLI_DeviceInfo)], c_short)

MPC_Open = bind(lib, "MPC_Open", [POINTER(c_char)], c_short)
MPC_Close = bind(lib, "MPC_Close", [POINTER(c_char)], c_short)
MPC_CheckConnection = bind(lib, "MPC_CheckConnection", [POINTER(c_char)], c_bool)
MPC_IsChannelValid = bind(lib, "MPC_IsChannelValid", [POINTER(c_char), c_short], c_bool)
MPC_MaxChannelCount = bind(lib, "MPC_MaxChannelCount", [POINTER(c_char), c_int])
MPC_Identify = bind(lib, "MPC_Identify", [POINTER(c_char), c_short])
MPC_GetHardwareInfo = bind(lib, "MPC_GetHardwareInfo", [POINTER(c_char), c_short, POINTER(c_char), c_dword, POINTER(c_word), POINTER(c_word), POINTER(c_char), c_dword, POINTER(c_dword), POINTER(c_word), POINTER(c_word)], c_short)
MPC_GetHardwareInfoBlock = bind(lib, "MPC_GetHardwareInfoBlock", [POINTER(c_char), c_short, POINTER(TLI_HardwareInformation)], c_short)
MPC_GetNumChannels = bind(lib, "MPC_GetNumChannels", [POINTER(c_char)], c_short)
MPC_GetFirmwareVersion = bind(lib, "MPC_GetFirmwareVersion", [POINTER(c_char), c_short], c_dword)
MPC_GetSoftwareVersion = bind(lib, "MPC_GetSoftwareVersion", [POINTER(c_char)])
MPC_LoadSettings = bind(lib, "MPC_LoadSettings", [POINTER(c_char), c_short], c_bool)
MPC_PersistSettings = bind(lib, "MPC_PersistSettings", [POINTER(c_char), c_short], c_bool)


MPC_GetPosition = bind(lib, "MPC_GetPosition", [POINTER(c_char), POL_Paddles], c_double)
MPC_Home = bind(lib, "MPC_Home", [POINTER(c_char), POL_Paddles], c_short)
MPC_MoveToPosition = bind(lib, "MPC_MoveToPosition",  [POINTER(c_char), POL_Paddles, c_double], c_short)
MPC_StartPolling = bind(lib, "MPC_StartPolling",  [POINTER(c_char), c_int], c_bool)
MPC_ClearMessageQueue = bind(lib, "MPC_ClearMessageQueue",  [POINTER(c_char)], c_short)
MPC_StopPolling = bind(lib, "MPC_StopPolling",  [POINTER(c_char)], c_short)



