"""Windows hardware access for the profiler.

Everything in here talks to Windows directly, because the metrics the Linux
build reads out of sysfs have no sysfs equivalent here:

    Linux                                   Windows
    ------------------------------------    ------------------------------------
    /sys/class/powercap/.../energy_uj       PDH `\\Energy Meter(*)\\Power`
    /sys/class/thermal, coretemp            PDH `\\Thermal Zone Information(*)`
    psutil.cpu_freq(percpu=True)            returns ONE entry, not one per core
    psutil.sensors_temperatures()           does not exist on Windows at all
    /sys/devices/system/cpu/ topology       GetLogicalProcessorInformationEx

All four live metrics come from PDH performance counters read through ctypes,
so the profiler needs no third-party monitoring program, no kernel driver of
its own, and no elevation.

Power is the interesting one. The RAPL MSRs themselves are unreachable from
user mode -- that part of the Windows story is true and unchanged. But the
platform power-engine driver (`intelpep` on Intel, an inbox Windows driver)
already reads them in the kernel and republishes the same RAPL domains as PDH
`Energy Meter` instances: `RAPL_Package0_PKG`, `_PP0` (cores), `_PP1`
(graphics), `_DRAM`. Reading those is the Windows equivalent of opening
`energy_uj`, and it costs nothing -- unlike the Linux build, there is no 100 ms
sleep for an energy delta, because the driver has already differentiated for us
and reports power directly, in milliwatts.

Temperature is the metric Windows serves worst. The only user-mode source is
the set of ACPI thermal zones the firmware chooses to declare, which is a
platform-reported number, not the CPU's own on-die sensor: coarse, laggy, and
on some machines a constant. Read `ThermalZone`'s notes before trusting it.
"""
import ctypes
import time
from ctypes import wintypes

import psutil

# Two texts, because the two metrics are not equally obtainable and must not be
# described as if they were. Missing power stops a run; missing temperature only
# empties a column. Each is shared by the place that hits the problem during a
# run and by `analyzer.py diagnose`, so the wording never drifts between them.
POWER_HELP = """\
CPU power is a required metric, and this machine cannot supply it.

It is read from the Windows performance counter

    \\Energy Meter(RAPL_Package0_PKG)\\Power

which the platform power-engine driver -- `intelpep` on Intel -- publishes from
the RAPL registers. Nothing to install, nothing to run as Administrator. Check
that the driver is running:

    Get-CimInstance Win32_SystemDriver -Filter "Name='intelpep'"

It ships with Windows on Intel platforms. A virtual machine, an AMD platform
with no energy-metering driver, or a machine with its chipset drivers stripped
out may have no energy meter at all -- and there is no user-mode substitute,
because the underlying RAPL registers are MSRs that only a signed kernel driver
can read.

The counters can also be disabled or corrupted in the registry. Rebuild them
from an elevated prompt with:

    lodctr /R

Verify with:  profiler diagnose"""

TEMPERATURE_HELP = """\
CPU temperature is best-effort, and this machine cannot supply it. The run
still goes ahead; the `cpu_temperature` column will be empty, and its chart
will say why.

It is read from

    \\Thermal Zone Information(*)\\High Precision Temperature

which reports the ACPI thermal zones the firmware declares. Firmware that
declares none -- common on desktops, servers and virtual machines -- reports no
temperature to any user-mode program, and there is nothing to install that
would change that. The CPU's own on-die sensor sits behind the same MSRs as
RAPL, and unlike RAPL nothing in Windows republishes it, so reading it needs a
signed kernel driver."""

# ---------------------------------------------------------------- PDH constants
PDH_FMT_DOUBLE = 0x00000200
PDH_MORE_DATA = 0x800007D2
PDH_CSTATUS_VALID_DATA = 0x00000000
PDH_CSTATUS_NEW_DATA = 0x00000001

_FREQUENCY_COUNTER = r"\Processor Information(*)\% Processor Performance"
_ENERGY_COUNTER = r"\Energy Meter(*)\Power"

# Both thermal counters carry the same ACPI reading; the high-precision one is
# in tenths of a kelvin, the plain one in whole kelvin. Try the finer one first
# and keep the divisor that turns each into kelvin.
_THERMAL_COUNTERS = [
    (r"\Thermal Zone Information(*)\High Precision Temperature", 10.0),
    (r"\Thermal Zone Information(*)\Temperature", 1.0),
]


class _PdhCounterValue(ctypes.Structure):
    # DWORD CStatus + union{...}; the union is 8-byte aligned, so the struct is
    # 16 bytes with 4 bytes of padding after CStatus. ctypes reproduces that.
    _fields_ = [("CStatus", wintypes.DWORD), ("doubleValue", ctypes.c_double)]


class _PdhCounterItem(ctypes.Structure):
    _fields_ = [("szName", wintypes.LPWSTR), ("FmtValue", _PdhCounterValue)]


_pdh_library = None


def _load_pdh():
    """The pdh.dll binding, with argtypes/restypes applied once."""
    global _pdh_library
    if _pdh_library is not None:
        return _pdh_library

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

    _pdh_library = pdh
    return pdh


class _PdhCounter:
    """One wildcard PDH counter, sampled as {instance name: value}.

    Shared by all three live metrics, which differ only in the counter path and
    in what they make of the instance names.
    """

    def __init__(self, path):
        self.path = path
        self.error = None
        self._pdh = None
        self._query = None
        self._counter = None
        self._open()

    def _open(self):
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
        if self._pdh.PdhAddEnglishCounterW(query, self.path, 0,
                                           ctypes.byref(counter)) != 0:
            self._pdh.PdhCloseQuery(query)
            self.error = f"counter not found: {self.path}"
            return

        self._query, self._counter = query, counter
        # Rate counters need one priming collection; the first real read then
        # has an interval to compute against.
        self._pdh.PdhCollectQueryData(self._query)

    @property
    def opened(self):
        return self._counter is not None

    def read(self):
        """Sample every instance. Returns {} when the counter has no data."""
        if not self.opened:
            return {}
        if self._pdh.PdhCollectQueryData(self._query) != 0:
            return {}

        size = wintypes.DWORD(0)
        count = wintypes.DWORD(0)
        rc = self._pdh.PdhGetFormattedCounterArrayW(
            self._counter, PDH_FMT_DOUBLE, ctypes.byref(size),
            ctypes.byref(count), None)
        if rc != PDH_MORE_DATA or size.value == 0:
            return {}

        buf = (ctypes.c_byte * size.value)()
        rc = self._pdh.PdhGetFormattedCounterArrayW(
            self._counter, PDH_FMT_DOUBLE, ctypes.byref(size),
            ctypes.byref(count), buf)
        if rc != 0:
            return {}

        items = ctypes.cast(buf, ctypes.POINTER(_PdhCounterItem))
        values = {}
        for i in range(count.value):
            item = items[i]
            if not item.szName:
                continue
            if item.FmtValue.CStatus not in (PDH_CSTATUS_VALID_DATA,
                                             PDH_CSTATUS_NEW_DATA):
                continue
            values[item.szName] = item.FmtValue.doubleValue
        return values

    def probe(self, accept, timeout=2.0, interval=0.25):
        """Sample until `accept` likes the result, then return it (else {}).

        Adding a counter succeeds as soon as the *object* is registered, even
        when it has no instances at all -- `\\Power Meter(*)` does exactly that
        on machines with no power meter -- so "did it open" is not the same
        question as "is there anything to read". Answering the second one has
        to be done by sampling, because a rate counter reports nothing until
        two collections are separated by an interval.
        """
        deadline = time.monotonic() + timeout
        while True:
            values = self.read()
            if accept(values):
                return values
            if time.monotonic() >= deadline:
                return {}
            time.sleep(interval)

    def close(self):
        if self._query is not None and self._pdh is not None:
            self._pdh.PdhCloseQuery(self._query)
        self._query = self._counter = None


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
        self.base_mhz = _base_clock_mhz()
        self.source = None
        self.error = None
        self._counter = None
        self._open()

    def _open(self):
        if self.base_mhz is None:
            self.error = "could not determine the CPU base clock"
            return
        counter = _PdhCounter(_FREQUENCY_COUNTER)
        if not counter.opened:
            self.error = counter.error
            return
        self._counter = counter
        self.source = self.SOURCE

    @property
    def available(self):
        return self._counter is not None

    def read(self):
        """Return {logical cpu index: MHz}, or {} when unavailable."""
        if not self.available:
            return {}

        # Instance names are "group,cpu" plus "_Total" / "0,_Total" rollups.
        mhz = {}
        for name, percent in self._counter.read().items():
            if "_Total" in name:
                continue
            try:
                group, cpu = name.split(",")
                index = int(group) * 64 + int(cpu)
            except ValueError:
                continue
            mhz[index] = percent / 100.0 * self.base_mhz
        return mhz

    def close(self):
        if self._counter is not None:
            self._counter.close()
        self._counter = None


# ---------------------------------------------------------------------- power
class EnergyMeter:
    """CPU package power in watts, from the Windows Energy Meter counters.

    The instances are the RAPL domains, republished by the kernel-side power
    engine driver under names like `RAPL_Package0_PKG`. `Power` is already a
    rate, in milliwatts, so a sample is a single counter read -- there is no
    equivalent of the Linux build's 100 ms sleep to difference an energy
    counter, and therefore no floor under `--metrics_interval_ms`.
    """

    SOURCE = "PDH Energy Meter (RAPL)"

    def __init__(self):
        self.instances = []
        self.source = None
        self.error = None
        self.lost = False       # answered at start, then stopped reporting
        self._counter = _PdhCounter(_ENERGY_COUNTER)
        self._open()

    @staticmethod
    def _select(names):
        """Which instances add up to CPU power, without double counting.

        The RAPL domains nest: PP0 (cores) and PP1 (graphics) are *inside* PKG,
        so summing every instance would bill the same watts twice. Take the
        package total -- one per socket, which is what the Linux build's
        `intel-rapl:0` reports -- and only fall back to the sub-domains when no
        package instance exists. DRAM is deliberately never included: it is
        memory power, not CPU power.

        `_Total` is skipped as a source in its own right because the rollup
        reads a flat 0.0 on the machines checked, and because it would sum the
        nested domains for exactly the reason above.
        """
        usable = [n for n in names if n != "_Total"]
        package = [n for n in usable if n.upper().endswith("_PKG")]
        if package:
            return sorted(package)
        subdomains = [n for n in usable if n.upper().endswith(("_PP0", "_PP1"))]
        if subdomains:
            return sorted(subdomains)
        # An unfamiliar meter with exactly one domain is unambiguous; anything
        # else is guesswork, and guessing here would silently mislabel some
        # other rail as CPU power.
        non_dram = [n for n in usable if not n.upper().endswith("_DRAM")]
        return non_dram if len(non_dram) == 1 else []

    def _acceptable(self, values):
        selected = self._select(values)
        return bool(selected) and any(values[n] > 0 for n in selected)

    def _open(self):
        if not self._counter.opened:
            self.error = ("no Energy Meter performance counter on this machine "
                          "-- the platform has no energy-metering driver")
            return

        values = self._counter.probe(self._acceptable)
        if not values:
            found = ", ".join(sorted(self._counter.read())) or "none"
            self.error = ("the Energy Meter counter reports no usable CPU power "
                          f"domain (instances found: {found})")
            self._counter.close()
            return

        self.instances = self._select(values)
        self.source = f"{self.SOURCE}: {' + '.join(self.instances)}"

    @property
    def available(self):
        return bool(self.instances)

    def cpu_power_watts(self):
        if not self.available:
            return None
        values = self._counter.read()
        milliwatts = [values[name] for name in self.instances if name in values]
        if not milliwatts:
            # Keep sampling -- one dropped read is not worth ending a run over --
            # but remember it, so the sidecar and the closing warning can say so.
            self.lost = True
            return None
        return sum(milliwatts) / 1000.0

    def close(self):
        self._counter.close()


# ---------------------------------------------------------------- temperature
class ThermalZone:
    """CPU temperature in °C, from the ACPI thermal zones.

    This is the weakest metric on Windows and it is worth being blunt about
    why. The Linux build reads the CPU's own on-die sensor (`coretemp`). There
    is no user-mode equivalent here: the die sensor is behind the same MSRs as
    RAPL, and unlike RAPL nothing in Windows republishes it. What is left is
    whatever thermal zones the firmware declares in ACPI, which are a platform
    number -- often a chassis or skin zone, updated slowly, quantised to whole
    kelvin, and on some machines (the Tiger Lake all-in-one this was developed
    on, for one) frozen at a constant that never moves under load.

    So treat a reading as a floor, not as the core temperature, and check the
    run's closing warning: `metrics.py` compares the temperature's spread
    against the CPU load's and says so when the zone never moved.
    """

    SOURCE = "ACPI thermal zone"

    def __init__(self):
        self.zones = []
        self.source = None
        self.error = None
        self.lost = False
        self.scale = None
        self._counter = None
        self._open()

    @staticmethod
    def _celsius(values, scale):
        """Zone readings converted to °C, keeping only the plausible ones."""
        out = {}
        for name, raw in values.items():
            celsius = raw / scale - 273.15
            if 0.0 < celsius < 150.0:
                out[name] = celsius
        return out

    def _open(self):
        for path, scale in _THERMAL_COUNTERS:
            counter = _PdhCounter(path)
            if not counter.opened:
                continue
            values = counter.probe(lambda v: bool(self._celsius(v, scale)))
            zones = self._celsius(values, scale)
            if zones:
                self._counter, self.scale = counter, scale
                self.zones = sorted(zones)
                self.source = f"{self.SOURCE}: {', '.join(self.zones)}"
                return
            counter.close()

        self.error = ("no ACPI thermal zone reports a plausible temperature "
                      "-- this machine's firmware declares none")

    @property
    def available(self):
        return self._counter is not None

    def cpu_temperature_c(self):
        """Hottest zone of the moment.

        Taken per sample rather than pinning one zone at startup: firmware that
        declares several does not label which tracks the CPU, and the warmest
        is the best available guess -- the same rule the Linux build's `topaz`
        backend uses across `sensors` outputs.
        """
        if not self.available:
            return None
        zones = self._celsius(self._counter.read(), self.scale)
        if not zones:
            self.lost = True
            return None
        return max(zones.values())

    def close(self):
        if self._counter is not None:
            self._counter.close()
        self._counter = None


# ----------------------------------------------------------------- description
def describe(frequency, energy, thermal, topology):
    """Human-readable capability summary, printed once when logging starts."""
    lines = []
    if frequency.available:
        lines.append(f"  per-core frequency : PDH performance counters "
                     f"(base clock {frequency.base_mhz:.0f} MHz)")
    else:
        lines.append(f"  per-core frequency : UNAVAILABLE - {frequency.error}")

    if energy.available:
        lines.append(f"  CPU power          : {energy.source}")
    else:
        lines.append(f"  CPU power          : UNAVAILABLE (required) - {energy.error}")

    if thermal.available:
        lines.append(f"  CPU temperature    : {thermal.source}")
        lines.append("                       (firmware-reported zone, not the "
                     "on-die sensor)")
    else:
        lines.append(f"  CPU temperature    : UNAVAILABLE (optional) - {thermal.error}")
        lines.append("                       the run continues; the column "
                     "will be empty")

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
