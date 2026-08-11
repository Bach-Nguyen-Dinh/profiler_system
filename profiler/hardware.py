"""Windows hardware access for the profiler.

Everything in here talks to Windows directly, because the metrics the Linux
build reads out of sysfs have no sysfs equivalent here:

    Linux                                   Windows
    ------------------------------------    ------------------------------------
    /sys/class/powercap/.../energy_uj       no user-mode RAPL; needs a driver
    psutil.cpu_freq(percpu=True)            returns ONE entry, not one per core
    psutil.sensors_temperatures()           does not exist on Windows at all
    /sys/devices/system/cpu/ topology       GetLogicalProcessorInformationEx

Per-core frequency is recovered from the PDH performance counter
`\\Processor Information(*)\\% Processor Performance`, which is what Task
Manager itself displays. That needs no third-party package and no elevation.

Power and temperature have no dependency-free source on Windows. Both are read
from LibreHardwareMonitor (or the older OpenHardwareMonitor) over WMI when that
tool is running; otherwise they are reported as unavailable rather than faked.
"""
import ctypes
from ctypes import wintypes

import psutil

# ---------------------------------------------------------------- PDH constants
PDH_FMT_DOUBLE = 0x00000200
PDH_MORE_DATA = 0x800007D2
PDH_CSTATUS_VALID_DATA = 0x00000000
PDH_CSTATUS_NEW_DATA = 0x00000001

_COUNTER_PATH = r"\Processor Information(*)\% Processor Performance"


class _PdhCounterValue(ctypes.Structure):
    # DWORD CStatus + union{...}; the union is 8-byte aligned, so the struct is
    # 16 bytes with 4 bytes of padding after CStatus. ctypes reproduces that.
    _fields_ = [("CStatus", wintypes.DWORD), ("doubleValue", ctypes.c_double)]


class _PdhCounterItem(ctypes.Structure):
    _fields_ = [("szName", wintypes.LPWSTR), ("FmtValue", _PdhCounterValue)]


def _load_pdh():
    pdh = ctypes.WinDLL("pdh.dll")
    pdh.PdhOpenQueryW.argtypes = [wintypes.LPCWSTR, ctypes.c_size_t,
                                  ctypes.POINTER(wintypes.HANDLE)]
    pdh.PdhAddEnglishCounterW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR,
                                          ctypes.c_size_t,
                                          ctypes.POINTER(wintypes.HANDLE)]
    pdh.PdhCollectQueryData.argtypes = [wintypes.HANDLE]
    pdh.PdhGetFormattedCounterArrayW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    pdh.PdhCloseQuery.argtypes = [wintypes.HANDLE]

    # PDH_STATUS is unsigned. Without this, ctypes decodes the default c_int and
    # PDH_MORE_DATA (0x800007D2) arrives as a negative number that never matches
    # the constant -- which silently turns every counter read into "no data".
    for name in ("PdhOpenQueryW", "PdhAddEnglishCounterW", "PdhCollectQueryData",
                 "PdhGetFormattedCounterArrayW", "PdhCloseQuery"):
        getattr(pdh, name).restype = wintypes.DWORD
    return pdh


# ------------------------------------------------------------ processor topology
RELATION_PROCESSOR_CORE = 0


class _GroupAffinity(ctypes.Structure):
    _fields_ = [("Mask", ctypes.c_ulonglong), ("Group", wintypes.WORD),
                ("Reserved", wintypes.WORD * 3)]


class _ProcessorRelationship(ctypes.Structure):
    _fields_ = [("Flags", ctypes.c_ubyte), ("EfficiencyClass", ctypes.c_ubyte),
                ("Reserved", ctypes.c_ubyte * 20), ("GroupCount", wintypes.WORD),
                ("GroupMask", _GroupAffinity * 1)]


class _LogicalProcessorInfoEx(ctypes.Structure):
    _fields_ = [("Relationship", wintypes.DWORD), ("Size", wintypes.DWORD),
                ("Processor", _ProcessorRelationship)]


def read_topology():
    """Map logical CPUs to physical cores and efficiency classes.

    Returns a dict with `hybrid`, `core_class` ({logical cpu -> 'P'/'E'/None})
    and `physical_cores`. Windows exposes EfficiencyClass per physical core;
    more than one distinct class means a hybrid (Intel 12th gen or newer) CPU.
    On everything older every core reports class 0 and there is no P/E split to
    label -- the cores are just cores.
    """
    empty = {"hybrid": False, "core_class": {}, "physical_cores": None,
             "efficiency_classes": []}
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except OSError:
        return empty

    size = wintypes.DWORD(0)
    k32.GetLogicalProcessorInformationEx(RELATION_PROCESSOR_CORE, None,
                                         ctypes.byref(size))
    if size.value == 0:
        return empty

    buf = (ctypes.c_byte * size.value)()
    if not k32.GetLogicalProcessorInformationEx(RELATION_PROCESSOR_CORE, buf,
                                                ctypes.byref(size)):
        return empty

    cores, offset = [], 0
    while offset < size.value:
        rec = ctypes.cast(ctypes.byref(buf, offset),
                          ctypes.POINTER(_LogicalProcessorInfoEx)).contents
        if rec.Size == 0:
            break
        if rec.Relationship == RELATION_PROCESSOR_CORE:
            grp = rec.Processor.GroupMask[0]
            logical = [grp.Group * 64 + bit for bit in range(64)
                       if grp.Mask >> bit & 1]
            cores.append((rec.Processor.EfficiencyClass, logical))
        offset += rec.Size

    if not cores:
        return empty

    classes = sorted({ec for ec, _ in cores})
    hybrid = len(classes) > 1
    core_class = {}
    if hybrid:
        # Highest efficiency class is the performance core on Intel hybrid parts.
        fastest = max(classes)
        for ec, logical in cores:
            for cpu in logical:
                core_class[cpu] = "P" if ec == fastest else "E"

    return {"hybrid": hybrid, "core_class": core_class,
            "physical_cores": len(cores), "efficiency_classes": classes}


def _base_clock_mhz():
    """Nominal (base) clock, the 100% reference for % Processor Performance."""
    try:
        freq = psutil.cpu_freq()
        if freq and freq.max:
            return float(freq.max)
    except Exception:
        pass
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        with key:
            return float(winreg.QueryValueEx(key, "~MHz")[0])
    except Exception:
        return None


class PerCoreFrequency:
    """Live per-logical-CPU frequency from PDH performance counters.

    `% Processor Performance` is the ratio of delivered to nominal frequency, so
    it exceeds 100 under turbo -- that is expected, not a bug. Multiplying by
    the base clock gives MHz comparable to what the Linux build reports.
    """

    # Recorded once at open time and never cleared, so run metadata written
    # after close() still reports what the run actually used.
    SOURCE = "PDH % Processor Performance"

    def __init__(self):
        self._pdh = None
        self._query = None
        self._counter = None
        self.base_mhz = _base_clock_mhz()
        self.source = None
        self.error = None
        self._open()

    def _open(self):
        if self.base_mhz is None:
            self.error = "could not determine the CPU base clock"
            return
        try:
            self._pdh = _load_pdh()
        except OSError as exc:
            self.error = f"pdh.dll unavailable ({exc})"
            return

        query = wintypes.HANDLE()
        if self._pdh.PdhOpenQueryW(None, 0, ctypes.byref(query)) != 0:
            self.error = "PdhOpenQuery failed"
            return
        counter = wintypes.HANDLE()
        # AddEnglishCounter, not AddCounter: counter names are localised, the
        # English form is stable on every system language.
        if self._pdh.PdhAddEnglishCounterW(query, _COUNTER_PATH, 0,
                                           ctypes.byref(counter)) != 0:
            self._pdh.PdhCloseQuery(query)
            self.error = "processor performance counter not found"
            return

        self._query, self._counter = query, counter
        self.source = self.SOURCE
        # Rate counters need one priming collection; the first real read then
        # has an interval to compute against.
        self._pdh.PdhCollectQueryData(self._query)

    @property
    def available(self):
        return self._counter is not None

    def _raw_items(self):
        size = wintypes.DWORD(0)
        count = wintypes.DWORD(0)
        rc = self._pdh.PdhGetFormattedCounterArrayW(
            self._counter, PDH_FMT_DOUBLE, ctypes.byref(size),
            ctypes.byref(count), None)
        if rc != PDH_MORE_DATA or size.value == 0:
            return None
        buf = (ctypes.c_byte * size.value)()
        rc = self._pdh.PdhGetFormattedCounterArrayW(
            self._counter, PDH_FMT_DOUBLE, ctypes.byref(size),
            ctypes.byref(count), buf)
        if rc != 0:
            return None
        items = ctypes.cast(buf, ctypes.POINTER(_PdhCounterItem))
        return [(items[i].szName, items[i].FmtValue) for i in range(count.value)]

    def read(self):
        """Return {logical cpu index: MHz}, or {} when unavailable."""
        if not self.available:
            return {}
        if self._pdh.PdhCollectQueryData(self._query) != 0:
            return {}
        items = self._raw_items()
        if not items:
            return {}

        # Instance names are "group,cpu" plus "_Total" / "0,_Total" rollups.
        parsed = []
        for name, value in items:
            if not name or "_Total" in name:
                continue
            if value.CStatus not in (PDH_CSTATUS_VALID_DATA, PDH_CSTATUS_NEW_DATA):
                continue
            try:
                group, cpu = name.split(",")
                index = int(group) * 64 + int(cpu)
            except ValueError:
                continue
            parsed.append((index, value.doubleValue))

        return {index: pct / 100.0 * self.base_mhz for index, pct in parsed}

    def close(self):
        if self._query is not None and self._pdh is not None:
            self._pdh.PdhCloseQuery(self._query)
        self._query = self._counter = None


# --------------------------------------------- power & temperature (LHM / OHM)
_MONITOR_NAMESPACES = [
    ("LibreHardwareMonitor", "root\\LibreHardwareMonitor"),
    ("OpenHardwareMonitor", "root\\OpenHardwareMonitor"),
]

# Preference order when several sensors match; "CPU Package" is the whole-socket
# figure closest to what Linux RAPL package energy reports.
_POWER_PREFERENCE = ["cpu package", "package", "cpu cores"]
_TEMP_PREFERENCE = ["cpu package", "core average", "core max", "cpu"]


class HardwareMonitor:
    """Optional power/temperature source backed by LibreHardwareMonitor's WMI.

    Requires the `wmi` package (`pip install wmi`) and LibreHardwareMonitor
    running elevated. When either is missing the profiler still records every
    other metric and leaves these two columns empty.
    """

    def __init__(self):
        self.provider = None
        self.error = None
        self._wmi = None
        self._connect()

    def _connect(self):
        # This runs on the sampling thread. Anything raising here would kill
        # that thread and silently end the whole run, so nothing is allowed to
        # escape -- a missing sensor source must only cost two CSV columns.
        try:
            import wmi
        except ImportError:
            self.error = "the `wmi` package is not installed (pip install wmi)"
            return
        except Exception as exc:
            self.error = f"could not import the `wmi` package ({exc})"
            return

        try:
            import pythoncom  # ships with pywin32, a dependency of `wmi`

            # The sampling thread is not the thread that initialised COM, so it
            # needs its own apartment before any WMI call.
            pythoncom.CoInitialize()
        except Exception:
            pass

        for label, namespace in _MONITOR_NAMESPACES:
            try:
                conn = wmi.WMI(namespace=namespace)
                conn.Sensor()          # probe: raises if the namespace is absent
            except Exception:
                continue
            self._wmi = conn
            self.provider = label
            return

        self.error = ("no LibreHardwareMonitor/OpenHardwareMonitor WMI provider "
                      "found (start it as Administrator)")

    @property
    def available(self):
        return self._wmi is not None

    def _pick(self, sensor_type, preference):
        """Best CPU sensor of `sensor_type`, by name preference then by value."""
        try:
            sensors = self._wmi.Sensor(SensorType=sensor_type)
            # Keep only CPU sensors that are actually reporting a number.
            cpu = [s for s in sensors
                   if s.Identifier and "cpu" in s.Identifier.lower()
                   and s.Value is not None]
        except Exception as exc:
            # Disable the provider rather than raising once per sample.
            self.error = f"WMI query failed: {exc}"
            self._wmi = None
            return None

        if not cpu:
            return None
        for match in (lambda name, wanted: name == wanted,
                      lambda name, wanted: wanted in name):
            for wanted in preference:
                for s in cpu:
                    if s.Name and match(s.Name.lower(), wanted):
                        return float(s.Value)
        return max(float(s.Value) for s in cpu)

    def cpu_power_watts(self):
        if not self.available:
            return None
        return self._pick("Power", _POWER_PREFERENCE)

    def cpu_temperature_c(self):
        if not self.available:
            return None
        return self._pick("Temperature", _TEMP_PREFERENCE)


# ----------------------------------------------------------------- description
def describe(frequency, monitor, topology):
    """Human-readable capability summary, printed once when logging starts."""
    lines = []
    if frequency.available:
        lines.append(f"  per-core frequency : PDH performance counters "
                     f"(base clock {frequency.base_mhz:.0f} MHz)")
    else:
        lines.append(f"  per-core frequency : UNAVAILABLE - {frequency.error}")

    if monitor.available:
        lines.append(f"  power, temperature : {monitor.provider} via WMI")
    else:
        lines.append(f"  power, temperature : UNAVAILABLE - {monitor.error}")

    if topology["hybrid"]:
        p = sum(1 for v in topology["core_class"].values() if v == "P")
        e = sum(1 for v in topology["core_class"].values() if v == "E")
        lines.append(f"  topology           : hybrid CPU, {p} P-core / {e} E-core "
                     f"logical processors")
    else:
        cores = topology["physical_cores"]
        detail = f"{cores} physical cores, " if cores else ""
        lines.append(f"  topology           : non-hybrid CPU ({detail}"
                     f"{psutil.cpu_count()} logical processors)")
    return lines
